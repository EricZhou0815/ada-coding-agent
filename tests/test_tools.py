import os
import pytest
import subprocess
from unittest.mock import patch, mock_open
from tools.tools import Tools

@pytest.fixture
def tools():
    return Tools()

def test_read_file(tools):
    with patch("builtins.open", mock_open(read_data="hello world")) as mock_file:
        content = tools.read_file("test.txt")
        mock_file.assert_called_once_with("test.txt", "r")
        assert content == "hello world"

def test_write_file(tools):
    with patch("builtins.open", mock_open()) as mock_file:
        tools.write_file("test.txt", "new content")
        mock_file.assert_called_once_with("test.txt", "w")
        mock_file().write.assert_called_once_with("new content")

@patch("os.remove")
def test_delete_file(mock_remove, tools):
    tools.delete_file("test.txt")
    mock_remove.assert_called_once_with("test.txt")

@patch("os.walk")
def test_list_files(mock_walk, tools):
    mock_walk.return_value = [
        ("root", ["dir1", ".git"], ["file1.txt", ".hidden"]),
        ("root/dir1", [], ["file2.txt"])
    ]
    files = tools.list_files("root")
    # should ignore .git and .hidden
    assert "file1.txt" in files
    assert "dir1/file2.txt" in files
    assert ".hidden" not in files

def test_edit_file_success(tools):
    mock_content = "def test():\n    pass\n"
    with patch("builtins.open", mock_open(read_data=mock_content)) as mock_file:
        result = tools.edit_file("test.py", "pass", "return True")
        assert result == "File updated successfully."
        # Check that it writes the correct replaced content
        mock_file().write.assert_called_once_with("def test():\n    return True\n")

def test_edit_file_not_found(tools):
    mock_content = "def test():\n    pass\n"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        with pytest.raises(ValueError, match="not found"):
            tools.edit_file("test.py", "return False", "return True")

def test_edit_file_multiple_matches(tools):
    mock_content = "pass\npass\n"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        with pytest.raises(ValueError, match="matched multiple times"):
            tools.edit_file("test.py", "pass", "return True")

@patch("subprocess.run")
def test_search_codebase(mock_run, tools):
    mock_run.return_value.stdout = "file.py:1:print('hello')"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    result = tools.search_codebase("hello", ".")
    mock_run.assert_called_once()
    assert result["stdout"] == "file.py:1:print('hello')"
    assert result["exit_code"] == 0

@patch("subprocess.run")
def test_search_codebase_truncate(mock_run, tools):
    mock_run.return_value.stdout = "a" * 25000
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    result = tools.search_codebase("hello", ".")
    assert len(result["stdout"]) < 25000
    assert "...[OUTPUT TRUNCATED]..." in result["stdout"]

@patch("subprocess.run")
def test_run_command(mock_run, tools):
    mock_run.return_value.stdout = "test output"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    result = tools.run_command("echo 'test output'")
    mock_run.assert_called_once_with("echo 'test output'", shell=True, capture_output=True, text=True)
    assert result["stdout"] == "test output"
    assert result["exit_code"] == 0
