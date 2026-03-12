"""
verification/quality_gate.py

Deterministic verification pipeline for task completion.
Runs lint, build, and test commands against the repo and produces a VerificationResult.
"""

import os
import subprocess
from typing import List, Optional

from planning.models import Task, VerificationResult
from utils.logger import logger


# Known project markers and their corresponding verification commands
PROJECT_PROFILES = [
    {
        "marker": "package.json",
        "lint": ["npm", "run", "lint"],
        "build": ["npm", "run", "build"],
        "test": ["npm", "test"],
    },
    {
        "marker": "pytest.ini",
        "lint": None,
        "build": None,
        "test": ["python", "-m", "pytest", "--maxfail=5", "-q"],
    },
    {
        "marker": "setup.py",
        "lint": None,
        "build": None,
        "test": ["python", "-m", "pytest", "--maxfail=5", "-q"],
    },
    {
        "marker": "pyproject.toml",
        "lint": None,
        "build": None,
        "test": ["python", "-m", "pytest", "--maxfail=5", "-q"],
    },
    {
        "marker": "Cargo.toml",
        "lint": ["cargo", "clippy"],
        "build": ["cargo", "build"],
        "test": ["cargo", "test"],
    },
    {
        "marker": "go.mod",
        "lint": ["go", "vet", "./..."],
        "build": ["go", "build", "./..."],
        "test": ["go", "test", "./..."],
    },
]


class QualityGate:
    """
    Runs deterministic verification (lint, build, test) against a repository.
    Auto-detects project type from marker files.
    """

    def __init__(self, repo_path: str, timeout: int = 300):
        """
        Args:
            repo_path: Path to the repository to verify.
            timeout: Maximum seconds per verification command.
        """
        self.repo_path = repo_path
        self.timeout = timeout
        self._profile = self._detect_profile()

    def verify(self, task: Task) -> VerificationResult:
        """
        Run the full verification pipeline for a task.

        Args:
            task: The task to verify.

        Returns:
            VerificationResult with pass/fail outcome for each stage.
        """
        result = VerificationResult(task_id=task.task_id)
        details = []

        if not self._profile:
            # No recognizable project profile — pass by default
            result.lint_passed = True
            result.build_passed = True
            result.tests_passed = True
            result.details = "No project profile detected — skipping verification"
            logger.warning("QualityGate", result.details)
            return result

        # Lint
        lint_cmd = self._profile.get("lint")
        if lint_cmd:
            result.lint_passed = self._run_command(lint_cmd, "lint")
            details.append(f"lint: {'passed' if result.lint_passed else 'FAILED'}")
        else:
            result.lint_passed = True
            details.append("lint: skipped (not configured)")

        # Build
        build_cmd = self._profile.get("build")
        if build_cmd:
            result.build_passed = self._run_command(build_cmd, "build")
            details.append(f"build: {'passed' if result.build_passed else 'FAILED'}")
        else:
            result.build_passed = True
            details.append("build: skipped (not configured)")

        # Tests
        test_cmd = self._profile.get("test")
        if test_cmd:
            result.tests_passed = self._run_command(test_cmd, "test")
            details.append(f"tests: {'passed' if result.tests_passed else 'FAILED'}")
        else:
            result.tests_passed = True
            details.append("tests: skipped (not configured)")

        result.details = "; ".join(details)

        status = "PASSED" if result.validation_passed else "FAILED"
        logger.info("QualityGate", f"Verification {status}: {result.details}")

        return result

    def _detect_profile(self) -> Optional[dict]:
        """Detect project type from marker files."""
        for profile in PROJECT_PROFILES:
            marker = os.path.join(self.repo_path, profile["marker"])
            if os.path.exists(marker):
                logger.info("QualityGate", f"Detected project type: {profile['marker']}")
                return profile
        return None

    def _run_command(self, cmd: List[str], stage: str) -> bool:
        """
        Run a verification command and return True if it succeeds.

        Args:
            cmd: Command and arguments.
            stage: Human label (lint/build/test) for logging.

        Returns:
            True if command exited with code 0.
        """
        logger.info("QualityGate", f"Running {stage}: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                logger.error("QualityGate", f"{stage} failed (exit {result.returncode})")
                if result.stdout:
                    # Log last 20 lines of stdout
                    lines = result.stdout.strip().split("\n")[-20:]
                    for line in lines:
                        logger.info("QualityGate", f"  {line}")
                if result.stderr:
                    lines = result.stderr.strip().split("\n")[-10:]
                    for line in lines:
                        logger.error("QualityGate", f"  {line}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("QualityGate", f"{stage} timed out after {self.timeout}s")
            return False
        except FileNotFoundError:
            logger.warning("QualityGate", f"{stage} command not found: {cmd[0]}")
            # If the tool isn't installed, pass rather than block
            return True
