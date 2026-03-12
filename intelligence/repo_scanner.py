"""
intelligence/repo_scanner.py

Walks the repository filesystem and collects relevant source files.
Detects programming languages and filters out noise (build artifacts, deps, etc.).
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from utils.logger import logger

# Directories to always skip
IGNORE_DIRS: Set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", "out",
    ".eggs", "*.egg-info", "vendor", "target",
    ".idea", ".vscode", ".vs",
    "coverage", ".nyc_output", "htmlcov",
}

# File patterns to always skip
IGNORE_FILES: Set[str] = {
    ".DS_Store", "Thumbs.db", ".gitignore", ".gitattributes",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "go.sum",
}

# Extension → language mapping
LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
}

# Languages supported for AST parsing in MVP
SUPPORTED_LANGUAGES: Set[str] = {"python", "javascript", "typescript", "go", "java"}


@dataclass
class ScannedFile:
    """Represents a discovered source file."""
    path: str            # Relative path from repo root
    abs_path: str        # Absolute path
    language: str        # Detected language
    size_bytes: int = 0  # File size


@dataclass
class ScanResult:
    """Result of scanning a repository."""
    repo_path: str
    files: List[ScannedFile] = field(default_factory=list)
    skipped_dirs: List[str] = field(default_factory=list)
    total_files_seen: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)

    def files_by_language(self) -> Dict[str, List[ScannedFile]]:
        """Group scanned files by language."""
        by_lang: Dict[str, List[ScannedFile]] = {}
        for f in self.files:
            by_lang.setdefault(f.language, []).append(f)
        return by_lang

    def parseable_files(self) -> List[ScannedFile]:
        """Return only files whose language is supported for AST parsing."""
        return [f for f in self.files if f.language in SUPPORTED_LANGUAGES]


class RepoScanner:
    """
    Walks a repository and collects source files with language detection.
    
    Filters out build artifacts, dependencies, and non-source files.
    """

    def __init__(
        self,
        extra_ignore_dirs: Optional[Set[str]] = None,
        max_file_size: int = 1_000_000,  # 1 MB
    ):
        """
        Args:
            extra_ignore_dirs: Additional directories to skip.
            max_file_size: Skip files larger than this (bytes).
        """
        self.ignore_dirs = IGNORE_DIRS | (extra_ignore_dirs or set())
        self.max_file_size = max_file_size

    def scan(self, repo_path: str) -> ScanResult:
        """
        Scan a repository and collect all source files.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            ScanResult with all discovered files and metadata.
        """
        repo_path = os.path.abspath(repo_path)
        result = ScanResult(repo_path=repo_path)

        if not os.path.isdir(repo_path):
            logger.warning("RepoScanner", f"Not a directory: {repo_path}")
            return result

        for dirpath, dirnames, filenames in os.walk(repo_path, topdown=True):
            # Filter out ignored directories in-place (prevents os.walk from descending)
            original_count = len(dirnames)
            dirnames[:] = [
                d for d in dirnames
                if d not in self.ignore_dirs and not d.endswith(".egg-info")
            ]
            if original_count != len(dirnames):
                result.skipped_dirs.append(dirpath)

            for filename in filenames:
                result.total_files_seen += 1

                if filename in IGNORE_FILES:
                    continue

                ext = os.path.splitext(filename)[1].lower()
                language = LANGUAGE_MAP.get(ext)
                if not language:
                    continue

                abs_file = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_file, repo_path).replace("\\", "/")

                try:
                    size = os.path.getsize(abs_file)
                except OSError:
                    continue

                if size > self.max_file_size:
                    continue

                result.files.append(ScannedFile(
                    path=rel_path,
                    abs_path=abs_file,
                    language=language,
                    size_bytes=size,
                ))

        logger.info(
            "RepoScanner",
            f"Scanned {result.total_files_seen} files, "
            f"collected {result.file_count} source files "
            f"({len(result.files_by_language())} languages)"
        )
        return result
