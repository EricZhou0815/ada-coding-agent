"""
Tests for intelligence/symbol_extractor.py
"""

import pytest

from intelligence.ast_parser import ParsedFile, ParsedSymbol, ParsedImport
from intelligence.repo_scanner import ScannedFile
from intelligence.symbol_extractor import SymbolExtractor, GraphNode


@pytest.fixture
def extractor():
    return SymbolExtractor()


@pytest.fixture
def sample_scanned_file():
    return ScannedFile(
        path="src/user_service.py",
        abs_path="/repo/src/user_service.py",
        language="python",
        size_bytes=1024,
    )


@pytest.fixture
def sample_parsed_file():
    return ParsedFile(
        path="src/user_service.py",
        language="python",
        classes=[
            ParsedSymbol(name="UserService", kind="class", line=5, end_line=30),
        ],
        functions=[
            ParsedSymbol(name="get_user", kind="method", line=10, end_line=15, parent="UserService"),
            ParsedSymbol(name="reset_password", kind="method", line=17, end_line=25, parent="UserService"),
            ParsedSymbol(name="helper_func", kind="function", line=35, end_line=40),
        ],
        imports=[
            ParsedImport(module="os", line=1),
        ],
    )


class TestFileNode:
    def test_creates_file_node(self, extractor, sample_scanned_file):
        node = extractor.extract_file_node(sample_scanned_file)
        assert node.node_id == "file:src/user_service.py"
        assert node.kind == "file"
        assert node.name == "user_service.py"
        assert node.language == "python"

    def test_file_node_has_path(self, extractor, sample_scanned_file):
        node = extractor.extract_file_node(sample_scanned_file)
        assert node.file == "src/user_service.py"


class TestDirectoryNode:
    def test_creates_directory_node(self, extractor):
        node = extractor.extract_directory_node("src/utils")
        assert node.node_id == "dir:src/utils"
        assert node.kind == "directory"
        assert node.name == "utils"

    def test_top_level_directory(self, extractor):
        node = extractor.extract_directory_node("src")
        assert node.name == "src"


class TestSymbolExtraction:
    def test_extracts_class_node(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        class_nodes = [n for n in nodes if n.kind == "class"]
        assert len(class_nodes) == 1
        assert class_nodes[0].name == "UserService"
        assert class_nodes[0].node_id == "class:src/user_service.py:UserService"

    def test_extracts_method_nodes(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        method_nodes = [n for n in nodes if n.kind == "method"]
        assert len(method_nodes) == 2
        names = {m.name for m in method_nodes}
        assert names == {"get_user", "reset_password"}

    def test_method_has_parent(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        method = [n for n in nodes if n.name == "get_user"][0]
        assert method.parent == "class:src/user_service.py:UserService"

    def test_method_node_id_format(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        method = [n for n in nodes if n.name == "get_user"][0]
        assert method.node_id == "method:src/user_service.py:UserService.get_user"

    def test_extracts_function_nodes(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        func_nodes = [n for n in nodes if n.kind == "function"]
        assert len(func_nodes) == 1
        assert func_nodes[0].name == "helper_func"
        assert func_nodes[0].node_id == "function:src/user_service.py:helper_func"
        assert func_nodes[0].parent is None

    def test_nodes_have_line_numbers(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        for node in nodes:
            assert node.line is not None
            assert node.line > 0

    def test_nodes_have_language(self, extractor, sample_parsed_file):
        nodes = extractor.extract_symbols(sample_parsed_file)
        for node in nodes:
            assert node.language == "python"


class TestExtractAll:
    def test_includes_file_node(self, extractor, sample_scanned_file, sample_parsed_file):
        nodes = extractor.extract_all(sample_scanned_file, sample_parsed_file)
        file_nodes = [n for n in nodes if n.kind == "file"]
        assert len(file_nodes) == 1

    def test_includes_symbols(self, extractor, sample_scanned_file, sample_parsed_file):
        nodes = extractor.extract_all(sample_scanned_file, sample_parsed_file)
        # 1 file + 1 class + 2 methods + 1 function = 5
        assert len(nodes) == 5


class TestGraphNodeSerialization:
    def test_to_dict(self, extractor, sample_scanned_file):
        node = extractor.extract_file_node(sample_scanned_file)
        d = node.to_dict()
        assert d["node_id"] == "file:src/user_service.py"
        assert d["kind"] == "file"
        assert d["name"] == "user_service.py"

    def test_round_trip(self, extractor, sample_scanned_file):
        node = extractor.extract_file_node(sample_scanned_file)
        d = node.to_dict()
        restored = GraphNode.from_dict(d)
        assert restored.node_id == node.node_id
        assert restored.kind == node.kind
        assert restored.name == node.name
        assert restored.file == node.file
        assert restored.language == node.language

    def test_to_dict_omits_none_fields(self):
        node = GraphNode(node_id="test:1", name="test", kind="file")
        d = node.to_dict()
        assert "line" not in d
        assert "parent" not in d
