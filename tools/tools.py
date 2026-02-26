import os
import subprocess
from typing import List, Dict

class AdaTools:
    """
    Tools exposed to Ada.
    """

    def read_file(self, path: str) -> str:
        with open(path, "r") as f:
            return f.read()

    def write_file(self, path: str, content: str):
        with open(path, "w") as f:
            f.write(content)

    def delete_file(self, path: str):
        os.remove(path)

    def list_files(self, directory: str) -> List[str]:
        return os.listdir(directory)

    def run_command(self, command: str) -> Dict:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }

    def apply_patch(self, patch_text: str):
        # Placeholder for git patch apply
        pass