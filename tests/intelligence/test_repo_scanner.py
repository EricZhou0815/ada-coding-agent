"""
Tests for intelligence/repo_scanner.py
"""

import os
import tempfile
import shutil

import pytest

from intelligence.repo_scanner import (
    RepoScanner,
    ScanResult,
    ScannedFile,
    LANGUAGE_MAP,
    IGNORE_DIRS,
    SUPPORTED_LANGUAGES,
)


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository with various file types."""
    # Python files
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "helper.py").write_text("def helper(): pass")
    (tmp_path / "utils" / "__init__.py").write_text("")

    # JavaScript files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("console.log('hi')")
    (tmp_path / "src" / "index.ts").write_text("const x = 1;")

    # Non-source files
    (tmp_path / "README.md").write_text("# README")
    (tmp_path / "data.csv").write_text("a,b,c")

    # Ignored directories
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports = {}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00")

    # Ignored files
    (tmp_path / "package-lock.json").write_text("{}")

    return tmp_path


class TestRepoScanner:
    def test_scan_finds_source_files(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        assert "main.py" in paths
        assert "utils/helper.py" in paths
        assert "utils/__init__.py" in paths
        assert "src/app.js" in paths
        assert "src/index.ts" in paths

    def test_scan_ignores_non_source(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        assert "README.md" not in paths
        assert "data.csv" not in paths

    def test_scan_ignores_dirs(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        # Files in ignored dirs should not appear
        for path in paths:
            assert "node_modules" not in path
            assert "__pycache__" not in path

    def test_scan_ignores_lock_files(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        assert "package-lock.json" not in paths

    def test_language_detection(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        lang_map = {f.path: f.language for f in result.files}
        assert lang_map["main.py"] == "python"
        assert lang_map["src/app.js"] == "javascript"
        assert lang_map["src/index.ts"] == "typescript"

    def test_file_count(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        assert result.file_count == 5  # main.py, helper.py, __init__.py, app.js, index.ts

    def test_files_by_language(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        by_lang = result.files_by_language()
        assert "python" in by_lang
        assert "javascript" in by_lang
        assert "typescript" in by_lang
        assert len(by_lang["python"]) == 3

    def test_parseable_files(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        parseable = result.parseable_files()
        # All files are in supported languages
        assert len(parseable) == result.file_count

    def test_extra_ignore_dirs(self, temp_repo):
        (temp_repo / "custom_ignore").mkdir()
        (temp_repo / "custom_ignore" / "module.py").write_text("x = 1")

        scanner = RepoScanner(extra_ignore_dirs={"custom_ignore"})
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        assert "custom_ignore/module.py" not in paths

    def test_max_file_size(self, temp_repo):
        # Create a large file
        (temp_repo / "large.py").write_text("x = 1\n" * 200000)

        scanner = RepoScanner(max_file_size=100)
        result = scanner.scan(str(temp_repo))

        paths = {f.path for f in result.files}
        assert "large.py" not in paths

    def test_scan_nonexistent_dir(self):
        scanner = RepoScanner()
        result = scanner.scan("/nonexistent/path/xyz")

        assert result.file_count == 0

    def test_scan_result_total_files_seen(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        # total_files_seen includes all files (source + non-source)
        assert result.total_files_seen >= result.file_count

    def test_scanned_file_has_abs_path(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        for f in result.files:
            assert os.path.isabs(f.abs_path)
            assert os.path.exists(f.abs_path)

    def test_uses_forward_slashes(self, temp_repo):
        scanner = RepoScanner()
        result = scanner.scan(str(temp_repo))

        for f in result.files:
            assert "\\" not in f.path, f"Path should use forward slashes: {f.path}"


class TestLanguageMap:
    def test_python_extensions(self):
        assert LANGUAGE_MAP[".py"] == "python"

    def test_javascript_extensions(self):
        assert LANGUAGE_MAP[".js"] == "javascript"
        assert LANGUAGE_MAP[".jsx"] == "javascript"

    def test_typescript_extensions(self):
        assert LANGUAGE_MAP[".ts"] == "typescript"
        assert LANGUAGE_MAP[".tsx"] == "typescript"

    def test_go_extension(self):
        assert LANGUAGE_MAP[".go"] == "go"

    def test_java_extension(self):
        assert LANGUAGE_MAP[".java"] == "java"


class TestSupportedLanguages:
    def test_mvp_languages(self):
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES
        assert "typescript" in SUPPORTED_LANGUAGES
        assert "go" in SUPPORTED_LANGUAGES
        assert "java" in SUPPORTED_LANGUAGES
