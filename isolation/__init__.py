"""
Isolation backends package.
Provides pluggable execution environments for Ada.
"""

from isolation.backend import IsolationBackend
from isolation.sandbox import SandboxBackend
from isolation.docker_backend import DockerBackend

__all__ = ['IsolationBackend', 'SandboxBackend', 'DockerBackend']
