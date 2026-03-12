"""
Tests for intelligence/repo_graph_builder.py
"""

import json
import os

import pytest

from intelligence.repo_graph_builder import RepoGraphBuilder, RepoGraph
from intelligence.symbol_extractor import GraphNode
from intelligence.dependency_analyzer import GraphEdge


@pytest.fixture
def python_repo(tmp_path):
    """Create a minimal Python project for graph building."""
    # Main module
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "models.py").write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "\n"
        "class Product:\n"
        "    def __init__(self, title):\n"
        "        self.title = title\n"
    )
    (tmp_path / "app" / "service.py").write_text(
        "from app.models import User, Product\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        return User('test')\n"
        "\n"
        "def process_order(product_id):\n"
        "    return Product('item')\n"
    )

    # Tests
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_service.py").write_text(
        "from app.service import UserService\n"
        "\n"
        "def test_get_user():\n"
        "    svc = UserService()\n"
        "    assert svc.get_user(1) is not None\n"
    )

    return tmp_path


@pytest.fixture
def builder():
    return RepoGraphBuilder()


class TestBuildGraph:
    def test_builds_graph(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        assert isinstance(graph, RepoGraph)
        assert graph.node_count > 0
        assert graph.edge_count > 0

    def test_finds_all_files(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        file_nodes = graph.files()
        file_paths = {n.file for n in file_nodes}
        assert "app/models.py" in file_paths
        assert "app/service.py" in file_paths
        assert "tests/test_service.py" in file_paths

    def test_finds_classes(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        class_nodes = graph.classes()
        class_names = {n.name for n in class_nodes}
        assert "User" in class_names
        assert "Product" in class_names
        assert "UserService" in class_names

    def test_finds_functions(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        funcs = graph.functions()
        func_names = {n.name for n in funcs}
        assert "process_order" in func_names
        assert "test_get_user" in func_names

    def test_has_import_edges(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        import_edges = [e for e in graph.edges if e.kind == "imports"]
        assert len(import_edges) > 0
        # service.py imports models.py
        assert any(
            "service" in e.source and "models" in e.target
            for e in import_edges
        )

    def test_has_containment_edges(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        contain_edges = [e for e in graph.edges if e.kind == "contains"]
        assert len(contain_edges) > 0

    def test_has_file_hashes(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        assert len(graph.file_hashes) > 0
        assert "app/models.py" in graph.file_hashes

    def test_built_at_set(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        assert graph.built_at > 0


class TestGraphSerialization:
    def test_save_load(self, builder, python_repo, tmp_path):
        graph = builder.build(str(python_repo))
        output_path = str(tmp_path / "graph.json")
        builder.save(graph, output_path)

        assert os.path.exists(output_path)

        loaded = builder.load(output_path)
        assert loaded is not None
        assert loaded.node_count == graph.node_count
        assert loaded.edge_count == graph.edge_count

    def test_load_nonexistent(self, builder):
        result = builder.load("/nonexistent/graph.json")
        assert result is None

    def test_load_invalid_json(self, builder, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        result = builder.load(str(bad_file))
        assert result is None

    def test_graph_to_dict_round_trip(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        d = graph.to_dict()
        restored = RepoGraph.from_dict(d)
        assert restored.node_count == graph.node_count
        assert restored.edge_count == graph.edge_count
        assert restored.repo_path == graph.repo_path


class TestIncrementalUpdate:
    def test_no_changes_returns_same(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        updated = builder.incremental_update(str(python_repo), graph)
        assert updated.node_count == graph.node_count

    def test_detects_added_file(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        original_count = graph.node_count

        # Add a new file
        (python_repo / "app" / "new_module.py").write_text(
            "class NewThing:\n    pass\n"
        )

        updated = builder.incremental_update(str(python_repo), graph)
        assert updated.node_count > original_count

    def test_detects_modified_file(self, builder, python_repo):
        graph = builder.build(str(python_repo))

        # Modify models.py — add a new class
        (python_repo / "app" / "models.py").write_text(
            "class User:\n    pass\n\nclass Product:\n    pass\n\nclass Order:\n    pass\n"
        )

        updated = builder.incremental_update(str(python_repo), graph)
        class_names = {n.name for n in updated.classes()}
        assert "Order" in class_names

    def test_detects_removed_file(self, builder, python_repo):
        graph = builder.build(str(python_repo))

        # Remove a file
        (python_repo / "app" / "service.py").unlink()

        updated = builder.incremental_update(str(python_repo), graph)
        file_paths = {n.file for n in updated.files()}
        assert "app/service.py" not in file_paths


class TestRepoGraphHelpers:
    def test_neighbors(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        # File node should have neighbors via containment
        file_node_id = "file:app/models.py"
        neighbors = graph.neighbors(file_node_id, edge_kinds={"contains"})
        assert len(neighbors) > 0

    def test_reverse_neighbors(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        # A class should have a reverse neighbor (the file that contains it)
        class_node_id = "class:app/models.py:User"
        rev = graph.reverse_neighbors(class_node_id, edge_kinds={"contains"})
        assert any(n.kind == "file" for n in rev)

    def test_summary(self, builder, python_repo):
        graph = builder.build(str(python_repo))
        summary = graph.summary()
        assert "Repository Graph" in summary
        assert "Nodes:" in summary
        assert "Edges:" in summary
