"""
Tests for intelligence/ast_parser.py

Tests regex fallback parsing. Tree-sitter tests only run if tree-sitter-languages is installed.
"""

import pytest

from intelligence.ast_parser import ASTParser, ParsedFile, ParsedSymbol, ParsedImport


@pytest.fixture
def parser():
    return ASTParser()


# ── Python parsing ───────────────────────────────────────────────────────

PYTHON_SOURCE = '''
import os
from utils.logger import logger
from typing import Dict, List

class UserService:
    """Manages user operations."""

    def __init__(self, repo):
        self.repo = repo

    def get_user(self, user_id):
        return self.repo.find(user_id)

    def reset_password(self, user_id, new_pass):
        user = self.get_user(user_id)
        user.password = new_pass

class AdminService(UserService):
    def ban_user(self, user_id):
        pass

def standalone_function():
    return 42

def another_function(x, y):
    return x + y
'''


class TestPythonParsing:
    def test_extracts_classes(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        class_names = [c.name for c in result.classes]
        assert "UserService" in class_names
        assert "AdminService" in class_names

    def test_extracts_methods(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        methods = [f for f in result.functions if f.kind == "method"]
        method_names = [m.name for m in methods]
        assert "get_user" in method_names
        assert "reset_password" in method_names
        assert "ban_user" in method_names

    def test_methods_have_parent(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        methods = [f for f in result.functions if f.kind == "method"]
        for m in methods:
            assert m.parent is not None

    def test_extracts_functions(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        funcs = [f for f in result.functions if f.kind == "function"]
        func_names = [f.name for f in funcs]
        assert "standalone_function" in func_names
        assert "another_function" in func_names

    def test_extracts_imports(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        modules = [i.module for i in result.imports]
        assert "os" in modules
        assert "utils.logger" in modules
        assert "typing" in modules

    def test_import_names(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        logger_import = [i for i in result.imports if i.module == "utils.logger"][0]
        assert "logger" in logger_import.names

    def test_symbols_have_line_numbers(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        for sym in result.all_symbols:
            assert sym.line > 0

    def test_parsed_file_path(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        assert result.path == "user_service.py"
        assert result.language == "python"


# ── JavaScript/TypeScript parsing ────────────────────────────────────────

JS_SOURCE = '''
import { Router } from 'express';
import UserService from './user_service';

class AuthController {
    constructor(service) {
        this.service = service;
    }

    login(req, res) {
        return this.service.authenticate(req.body);
    }
}

function handleError(err) {
    console.error(err);
}

const processRequest = async (req) => {
    return req.body;
};

export default AuthController;
'''


class TestJavaScriptParsing:
    def test_extracts_classes(self, parser):
        result = parser.parse_file("auth.js", "javascript", JS_SOURCE)
        class_names = [c.name for c in result.classes]
        assert "AuthController" in class_names

    def test_extracts_functions(self, parser):
        result = parser.parse_file("auth.js", "javascript", JS_SOURCE)
        func_names = [f.name for f in result.functions]
        assert "handleError" in func_names

    def test_extracts_arrow_functions(self, parser):
        result = parser.parse_file("auth.js", "javascript", JS_SOURCE)
        func_names = [f.name for f in result.functions]
        assert "processRequest" in func_names

    def test_extracts_imports(self, parser):
        result = parser.parse_file("auth.js", "javascript", JS_SOURCE)
        modules = [i.module for i in result.imports]
        assert "express" in modules
        assert "./user_service" in modules


# ── Go parsing ───────────────────────────────────────────────────────────

GO_SOURCE = '''package main

import (
    "fmt"
    "github.com/gin-gonic/gin"
)

type UserHandler struct {
    service *UserService
}

func (h *UserHandler) GetUser(c *gin.Context) {
    fmt.Println("get user")
}

func NewUserHandler(svc *UserService) *UserHandler {
    return &UserHandler{service: svc}
}
'''


class TestGoParsing:
    def test_extracts_structs(self, parser):
        result = parser.parse_file("handler.go", "go", GO_SOURCE)
        class_names = [c.name for c in result.classes]
        assert "UserHandler" in class_names

    def test_extracts_methods(self, parser):
        result = parser.parse_file("handler.go", "go", GO_SOURCE)
        methods = [f for f in result.functions if f.kind == "method"]
        assert any(m.name == "GetUser" for m in methods)

    def test_extracts_functions(self, parser):
        result = parser.parse_file("handler.go", "go", GO_SOURCE)
        funcs = [f for f in result.functions if f.kind == "function"]
        assert any(f.name == "NewUserHandler" for f in funcs)


# ── Java parsing ─────────────────────────────────────────────────────────

JAVA_SOURCE = '''
import java.util.List;
import com.example.UserRepository;

public class UserService {
    private UserRepository repo;

    public User getUser(int id) {
        return repo.findById(id);
    }

    public void deleteUser(int id) {
        repo.deleteById(id);
    }
}
'''


class TestJavaParsing:
    def test_extracts_classes(self, parser):
        result = parser.parse_file("UserService.java", "java", JAVA_SOURCE)
        class_names = [c.name for c in result.classes]
        assert "UserService" in class_names

    def test_extracts_methods(self, parser):
        result = parser.parse_file("UserService.java", "java", JAVA_SOURCE)
        methods = [f for f in result.functions if f.kind == "method"]
        method_names = [m.name for m in methods]
        assert "getUser" in method_names
        assert "deleteUser" in method_names

    def test_extracts_imports(self, parser):
        result = parser.parse_file("UserService.java", "java", JAVA_SOURCE)
        modules = [i.module for i in result.imports]
        assert "java.util.List" in modules
        assert "com.example.UserRepository" in modules


# ── Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_source(self, parser):
        result = parser.parse_file("empty.py", "python", "")
        assert result.classes == []
        assert result.functions == []
        assert result.imports == []

    def test_syntax_error_source(self, parser):
        bad_source = "class Foo(\n  def bar(: pass\n"
        result = parser.parse_file("bad.py", "python", bad_source)
        # Should not crash — may extract partial results
        assert isinstance(result, ParsedFile)

    def test_unsupported_language_returns_empty(self, parser):
        result = parser.parse_file("style.css", "css", "body { color: red; }")
        assert result.classes == []
        assert result.functions == []

    def test_all_symbols_property(self, parser):
        result = parser.parse_file("user_service.py", "python", PYTHON_SOURCE)
        all_sym = result.all_symbols
        assert len(all_sym) == len(result.classes) + len(result.functions)

    def test_file_not_found(self, parser):
        result = parser.parse_file("/nonexistent/file.py", "python")
        assert isinstance(result, ParsedFile)
        assert result.classes == []

    def test_tree_sitter_available_property(self, parser):
        # Should be a boolean
        assert isinstance(parser.tree_sitter_available, bool)
