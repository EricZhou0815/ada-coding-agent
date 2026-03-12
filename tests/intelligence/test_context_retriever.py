"""
Tests for intelligence/context_retriever.py
"""

import pytest

from intelligence.context_retriever import ContextRetriever, RetrievedContext
from intelligence.repo_graph_builder import RepoGraph
from intelligence.symbol_extractor import GraphNode
from intelligence.dependency_analyzer import GraphEdge


def _build_test_graph():
    """Create a test graph for context retrieval tests."""
    nodes = {
        "file:src/auth_controller.py": GraphNode(
            node_id="file:src/auth_controller.py", name="auth_controller.py",
            kind="file", file="src/auth_controller.py", language="python",
        ),
        "class:src/auth_controller.py:AuthController": GraphNode(
            node_id="class:src/auth_controller.py:AuthController", name="AuthController",
            kind="class", file="src/auth_controller.py", line=5,
        ),
        "method:src/auth_controller.py:AuthController.login": GraphNode(
            node_id="method:src/auth_controller.py:AuthController.login", name="login",
            kind="method", file="src/auth_controller.py", line=10,
            parent="class:src/auth_controller.py:AuthController",
        ),
        "file:src/user_service.py": GraphNode(
            node_id="file:src/user_service.py", name="user_service.py",
            kind="file", file="src/user_service.py", language="python",
        ),
        "class:src/user_service.py:UserService": GraphNode(
            node_id="class:src/user_service.py:UserService", name="UserService",
            kind="class", file="src/user_service.py", line=3,
        ),
        "method:src/user_service.py:UserService.reset_password": GraphNode(
            node_id="method:src/user_service.py:UserService.reset_password", name="reset_password",
            kind="method", file="src/user_service.py", line=15,
            parent="class:src/user_service.py:UserService",
        ),
        "file:src/user_repo.py": GraphNode(
            node_id="file:src/user_repo.py", name="user_repo.py",
            kind="file", file="src/user_repo.py", language="python",
        ),
        "class:src/user_repo.py:UserRepository": GraphNode(
            node_id="class:src/user_repo.py:UserRepository", name="UserRepository",
            kind="class", file="src/user_repo.py", line=3,
        ),
        "file:src/config.py": GraphNode(
            node_id="file:src/config.py", name="config.py",
            kind="file", file="src/config.py", language="python",
        ),
        "file:tests/test_auth.py": GraphNode(
            node_id="file:tests/test_auth.py", name="test_auth.py",
            kind="file", file="tests/test_auth.py", language="python",
        ),
    }

    edges = [
        # Containment
        GraphEdge(source="file:src/auth_controller.py", target="class:src/auth_controller.py:AuthController", kind="contains"),
        GraphEdge(source="class:src/auth_controller.py:AuthController", target="method:src/auth_controller.py:AuthController.login", kind="contains"),
        GraphEdge(source="file:src/user_service.py", target="class:src/user_service.py:UserService", kind="contains"),
        GraphEdge(source="class:src/user_service.py:UserService", target="method:src/user_service.py:UserService.reset_password", kind="contains"),
        GraphEdge(source="file:src/user_repo.py", target="class:src/user_repo.py:UserRepository", kind="contains"),
        # Imports
        GraphEdge(source="file:src/auth_controller.py", target="file:src/user_service.py", kind="imports"),
        GraphEdge(source="file:src/user_service.py", target="file:src/user_repo.py", kind="imports"),
        # Tests
        GraphEdge(source="file:tests/test_auth.py", target="file:src/auth_controller.py", kind="tests"),
    ]

    return RepoGraph(
        repo_path="/test/repo",
        nodes=nodes,
        edges=edges,
        file_hashes={},
        built_at=0.0,
    )


@pytest.fixture
def graph():
    return _build_test_graph()


@pytest.fixture
def retriever():
    return ContextRetriever(top_k=10, max_hops=2)


class TestKeywordExtraction:
    def test_extracts_keywords(self, retriever):
        keywords = retriever._extract_keywords("Add password reset endpoint for users")
        assert "password" in keywords
        assert "reset" in keywords
        assert "endpoint" in keywords
        assert "users" in keywords

    def test_removes_stopwords(self, retriever):
        keywords = retriever._extract_keywords("Add a new endpoint for the user service")
        assert "the" not in keywords
        assert "for" not in keywords

    def test_splits_camel_case(self, retriever):
        keywords = retriever._extract_keywords("Fix UserService authentication bug")
        assert "userservice" in keywords
        assert "user" in keywords
        assert "service" in keywords

    def test_splits_snake_case(self, retriever):
        keywords = retriever._extract_keywords("Update reset_password function")
        assert "reset_password" in keywords
        assert "reset" in keywords
        assert "password" in keywords

    def test_short_words_filtered(self, retriever):
        keywords = retriever._extract_keywords("Go to the UI page")
        # Words < 3 chars should be filtered
        assert "go" not in keywords
        assert "to" not in keywords
        assert "ui" not in keywords

    def test_deduplication(self, retriever):
        keywords = retriever._extract_keywords("user user user service")
        assert keywords.count("user") == 1


class TestContextRetrieval:
    def test_finds_relevant_files(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login endpoint", graph)
        file_paths = [f["path"] for f in ctx.relevant_files]
        assert "src/auth_controller.py" in file_paths

    def test_follows_dependencies(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login endpoint", graph)
        file_paths = [f["path"] for f in ctx.relevant_files]
        # Should follow import edge to user_service.py
        assert "src/user_service.py" in file_paths

    def test_finds_password_reset(self, retriever, graph):
        ctx = retriever.get_context("Add password reset endpoint", graph)
        file_paths = [f["path"] for f in ctx.relevant_files]
        assert "src/user_service.py" in file_paths

    def test_returns_symbols(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login", graph)
        symbol_names = [s["name"] for s in ctx.related_symbols]
        assert "AuthController" in symbol_names

    def test_returns_dependencies(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login", graph)
        assert len(ctx.dependencies) > 0

    def test_respects_top_k(self, graph):
        retriever = ContextRetriever(top_k=2, max_hops=2)
        ctx = retriever.get_context("Fix everything in the auth and user service", graph)
        assert len(ctx.relevant_files) <= 2

    def test_scores_are_positive(self, retriever, graph):
        ctx = retriever.get_context("AuthController login", graph)
        for f in ctx.relevant_files:
            assert f["score"] > 0

    def test_files_sorted_by_score(self, retriever, graph):
        ctx = retriever.get_context("AuthController login", graph)
        scores = [f["score"] for f in ctx.relevant_files]
        assert scores == sorted(scores, reverse=True)

    def test_keywords_included(self, retriever, graph):
        ctx = retriever.get_context("Add password reset endpoint", graph)
        assert len(ctx.keywords) > 0
        assert "password" in ctx.keywords


class TestRetrievedContext:
    def test_to_prompt_context(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login", graph)
        prompt = ctx.to_prompt_context()
        assert isinstance(prompt, str)
        assert "Relevant files" in prompt

    def test_to_dict(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController login", graph)
        d = ctx.to_dict()
        assert "relevant_files" in d
        assert "related_symbols" in d
        assert "dependencies" in d
        assert "keywords" in d

    def test_empty_context(self):
        ctx = RetrievedContext(task_description="no match xyz123")
        prompt = ctx.to_prompt_context()
        assert prompt == ""  # No files, symbols, or deps

    def test_prompt_shows_symbols(self, retriever, graph):
        ctx = retriever.get_context("Fix the AuthController", graph)
        prompt = ctx.to_prompt_context()
        if ctx.related_symbols:
            assert "Key symbols" in prompt


class TestEdgeCases:
    def test_empty_graph(self, retriever):
        graph = RepoGraph(repo_path="/empty", nodes={}, edges=[])
        ctx = retriever.get_context("anything", graph)
        assert ctx.relevant_files == []
        assert ctx.related_symbols == []

    def test_no_matching_keywords(self, retriever, graph):
        ctx = retriever.get_context("xyzzy frobnicator quantum", graph)
        # Should return empty or minimal results
        assert isinstance(ctx.relevant_files, list)

    def test_single_word_query(self, retriever, graph):
        ctx = retriever.get_context("login", graph)
        assert isinstance(ctx, RetrievedContext)
