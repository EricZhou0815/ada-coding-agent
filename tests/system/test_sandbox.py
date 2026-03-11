import os
import pytest
from unittest.mock import patch, mock_open
from isolation.sandbox import SandboxedTools, SecurityError

@pytest.fixture
def sandbox_path(tmp_path):
    path = tmp_path / "sandbox"
    path.mkdir()
    return str(path)

@pytest.fixture
def safe_tools(sandbox_path):
    return SandboxedTools(sandbox_path)

def test_validate_path_safe(safe_tools, sandbox_path):
    safe_file = os.path.join(sandbox_path, "file.txt")
    assert safe_tools._validate_path(safe_file) == safe_file

def test_validate_path_unsafe(safe_tools, sandbox_path):
    unsafe_file = os.path.join(sandbox_path, "../../etc/passwd")
    with pytest.raises(SecurityError, match="Access denied"):
        safe_tools._validate_path(unsafe_file)

def test_read_file_safe(safe_tools, sandbox_path):
    safe_file = os.path.join(sandbox_path, "test.txt")
    with patch("builtins.open", mock_open(read_data="sandbox data")) as mock_file:
        content = safe_tools.read_file(safe_file)
        assert content == "sandbox data"
        mock_file.assert_called_once_with(safe_file, "r")

def test_read_file_unsafe(safe_tools):
    with pytest.raises(SecurityError):
        safe_tools.read_file("/etc/passwd")

def test_write_file_safe(safe_tools, sandbox_path):
    safe_file = os.path.join(sandbox_path, "test.txt")
    with patch("os.makedirs"):
        with patch("builtins.open", mock_open()) as mock_file:
            safe_tools.write_file(safe_file, "data")
            mock_file.assert_called_once_with(safe_file, "w")
            mock_file().write.assert_called_once_with("data")

@patch("subprocess.run")
def test_search_codebase_safe(mock_run, safe_tools, sandbox_path):
    mock_run.return_value.stdout = "result"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    result = safe_tools.search_codebase("keyword", sandbox_path)
    # verify subprocess args included safe_dir
    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == sandbox_path
    assert result["stdout"] == "result"

@patch("subprocess.run")
def test_search_codebase_unsafe_directory_defaults_to_allowed(mock_run, safe_tools, sandbox_path):
    mock_run.return_value.stdout = "result"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    # an unsafe directory will be caught and defaulted to root self.allowed_path
    result = safe_tools.search_codebase("keyword", "/etc")
    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == safe_tools.allowed_path

def test_run_command_dangerous(safe_tools):
    result = safe_tools.run_command("rm -rf /")
    assert result["exit_code"] == 1
    assert "blocked" in result["stderr"]

@patch("subprocess.run")
def test_run_command_safe(mock_run, safe_tools, sandbox_path):
    mock_run.return_value.stdout = "files listed"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    result = safe_tools.run_command("ls -la")
    mock_run.assert_called_once_with(
        "ls -la", shell=True, capture_output=True, text=True, cwd=sandbox_path, timeout=30
    )
    assert result["stdout"] == "files listed"
