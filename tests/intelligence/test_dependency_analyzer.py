"""
Tests for intelligence/dependency_analyzer.py
"""

import pytest

from intelligence.ast_parser import ParsedFile, ParsedSymbol, ParsedImport
from intelligence.dependency_analyzer import DependencyAnalyzer, GraphEdge
from intelligence.symbol_extractor import GraphNode


@pytest.fixture
def analyzer():
    return DependencyAnalyzer()


def _make_nodes_and_parsed():
    """Create a small test graph with two files and their symbols."""
    # user_service.py imports from user_repo.py
    user_service_parsed = ParsedFile(
        path="src/user_service.py",
        language="python",
        classes=[ParsedSymbol(name="UserService", kind="class", line=5)],
        functions=[
            ParsedSymbol(name="get_user", kind="method", line=10, parent="UserService"),
        ],
        imports=[
            ParsedImport(module="src.user_repo", names=["UserRepo"], line=1),
        ],
    )

    user_repo_parsed = ParsedFile(
        path="src/user_repo.py",
        language="python",
        classes=[ParsedSymbol(name="UserRepo", kind="class", line=3)],
        functions=[
            ParsedSymbol(name="find_user", kind="method", line=8, parent="UserRepo"),
        ],
        imports=[],
    )

    test_parsed = ParsedFile(
        path="tests/test_user_service.py",
        language="python",
        classes=[],
        functions=[
            ParsedSymbol(name="test_get_user", kind="function", line=5),
        ],
        imports=[
            ParsedImport(module="src.user_service", names=["UserService"], line=1),
        ],
    )

    nodes = {
        "file:src/user_service.py": GraphNode(
            node_id="file:src/user_service.py", name="user_service.py", kind="file",
            file="src/user_service.py", language="python",
        ),
        "file:src/user_repo.py": GraphNode(
            node_id="file:src/user_repo.py", name="user_repo.py", kind="file",
            file="src/user_repo.py", language="python",
        ),
        "file:tests/test_user_service.py": GraphNode(
            node_id="file:tests/test_user_service.py", name="test_user_service.py", kind="file",
            file="tests/test_user_service.py", language="python",
        ),
        "class:src/user_service.py:UserService": GraphNode(
            node_id="class:src/user_service.py:UserService", name="UserService", kind="class",
            file="src/user_service.py", line=5,
        ),
        "method:src/user_service.py:UserService.get_user": GraphNode(
            node_id="method:src/user_service.py:UserService.get_user", name="get_user", kind="method",
            file="src/user_service.py", line=10, parent="class:src/user_service.py:UserService",
        ),
        "class:src/user_repo.py:UserRepo": GraphNode(
            node_id="class:src/user_repo.py:UserRepo", name="UserRepo", kind="class",
            file="src/user_repo.py", line=3,
        ),
        "method:src/user_repo.py:UserRepo.find_user": GraphNode(
            node_id="method:src/user_repo.py:UserRepo.find_user", name="find_user", kind="method",
            file="src/user_repo.py", line=8, parent="class:src/user_repo.py:UserRepo",
        ),
        "function:tests/test_user_service.py:test_get_user": GraphNode(
            node_id="function:tests/test_user_service.py:test_get_user", name="test_get_user", kind="function",
            file="tests/test_user_service.py", line=5,
        ),
    }

    parsed_files = {
        "src/user_service.py": user_service_parsed,
        "src/user_repo.py": user_repo_parsed,
        "tests/test_user_service.py": test_parsed,
    }

    return nodes, parsed_files


class TestContainmentEdges:
    def test_file_contains_class(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        containment = [e for e in edges if e.kind == "contains"]
        # file:src/user_service.py should contain class:UserService
        assert any(
            e.source == "file:src/user_service.py"
            and e.target == "class:src/user_service.py:UserService"
            for e in containment
        )

    def test_class_contains_method(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        containment = [e for e in edges if e.kind == "contains"]
        assert any(
            e.source == "class:src/user_service.py:UserService"
            and e.target == "method:src/user_service.py:UserService.get_user"
            for e in containment
        )


class TestImportEdges:
    def test_file_imports_file(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        imports = [e for e in edges if e.kind == "imports"]
        # user_service.py imports user_repo.py
        assert any(
            e.source == "file:src/user_service.py"
            and e.target == "file:src/user_repo.py"
            for e in imports
        )

    def test_import_links_to_symbol(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        imports = [e for e in edges if e.kind == "imports"]
        # user_service.py imports UserRepo symbol
        assert any(
            e.source == "file:src/user_service.py"
            and e.target == "class:src/user_repo.py:UserRepo"
            for e in imports
        )


class TestTestEdges:
    def test_detects_test_file(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        test_edges = [e for e in edges if e.kind == "tests"]
        # test_user_service.py should test user_service.py
        assert any(
            e.source == "file:tests/test_user_service.py"
            for e in test_edges
        )

    def test_test_links_to_imported_module(self, analyzer):
        nodes, parsed_files = _make_nodes_and_parsed()
        edges = analyzer.analyze(parsed_files, nodes)

        test_edges = [e for e in edges if e.kind == "tests"]
        # test file imports user_service → tests edge
        assert any(
            e.source == "file:tests/test_user_service.py"
            and e.target == "file:src/user_service.py"
            for e in test_edges
        )


class TestEdgeSerialization:
    def test_to_dict(self):
        edge = GraphEdge(source="a", target="b", kind="imports")
        d = edge.to_dict()
        assert d == {"source": "a", "target": "b", "kind": "imports"}

    def test_from_dict(self):
        d = {"source": "a", "target": "b", "kind": "contains"}
        edge = GraphEdge.from_dict(d)
        assert edge.source == "a"
        assert edge.target == "b"
        assert edge.kind == "contains"

    def test_round_trip(self):
        edge = GraphEdge(source="x", target="y", kind="tests")
        restored = GraphEdge.from_dict(edge.to_dict())
        assert restored.source == edge.source
        assert restored.target == edge.target
        assert restored.kind == edge.kind


class TestEmptyInput:
    def test_no_parsed_files(self, analyzer):
        edges = analyzer.analyze({}, {})
        assert edges == []

    def test_files_without_imports(self, analyzer):
        parsed = ParsedFile(
            path="standalone.py", language="python",
            classes=[], functions=[], imports=[],
        )
        nodes = {
            "file:standalone.py": GraphNode(
                node_id="file:standalone.py", name="standalone.py", kind="file",
                file="standalone.py",
            ),
        }
        edges = analyzer.analyze({"standalone.py": parsed}, nodes)
        # No edges — no classes, no imports
        assert len(edges) == 0
