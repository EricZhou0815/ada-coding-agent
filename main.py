from pathlib import Path
import subprocess

def run_atomic_task_in_docker(task_file: str, repo_snapshot: str, container_name: str):
    task_path = str(Path(task_file).resolve())
    repo_path = str(Path(repo_snapshot).resolve())

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{task_path}:/app/tasks/{Path(task_file).name}:ro",
        "-v", f"{repo_path}:/app/repo_snapshot:rw",
        "--name", container_name,
        "ada_agent_mvp",
        f"/app/tasks/{Path(task_file).name}",
        "/app/repo_snapshot"
    ]

    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    task_file = Path("tasks/example_task.json")
    repo_snapshot = Path("repo_snapshot")
    run_atomic_task_in_docker(task_file, repo_snapshot, container_name="ada_task_1")