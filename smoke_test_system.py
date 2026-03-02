import os
import json
import time
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force environment variables for the mock run
os.environ["LLM_PROVIDER"] = "mock"
os.environ["GITHUB_TOKEN"] = "mock-token"
# Use an in-memory SQLite for the smoke test to avoid permission/pollution issues
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Now import the components that use these env variables
from worker.tasks import execute_sdlc_story
from api.database import SessionLocal, StoryJob, Base, engine

def setup_test_db():
    # Ensure tables are created in the in-memory DB
    Base.metadata.create_all(bind=engine)

def run_smoke_test():
    job_id = "smoke-job-" + str(int(time.time()))
    repo_url = "https://github.com/mock-user/mock-repo"
    story = {
        "title": "Implement JWT Authentication",
        "story_id": "STORY-123",
        "acceptance_criteria": [
            "Users can login and get a token",
            "Protected routes require a valid token"
        ],
        "description": "Add JWT auth to our Flask app."
    }

    print(f"🚀 Starting System Smoke Test...")
    print(f"   Job ID:    {job_id}")
    print(f"   Provider:  MOCK (Safe for testing)")

    setup_test_db()

    # Pre-create the job entry as the API would
    db = SessionLocal()
    new_job = StoryJob(id=job_id, repo_url=repo_url, status="PENDING", logs="[]")
    db.add(new_job)
    db.commit()
    db.close()

    # Create a temporary 'remote' repository structure for Ada to 'clone'
    with tempfile.TemporaryDirectory() as temp_remote_dir:
        remote_path = Path(temp_remote_dir)
        (remote_path / "app.py").write_text("print('hello world')")
        (remote_path / "auth.py").write_text("# auth logic here")

        # Mock GitManager and GitHubClient to keep the test local and fast
        with patch("tools.git_manager.GitManager.clone") as mock_clone, \
             patch("tools.github_client.GitHubClient.create_pull_request") as mock_pr, \
             patch("tools.github_client.GitHubClient.get_pull_requests") as mock_get_prs, \
             patch("redis.from_url") as mock_redis:
            
            # Setup mock git behavior (just copy files instead of actual git clone)
            def side_effect_clone(url, target_path):
                shutil.copytree(temp_remote_dir, target_path)
                mock_git_instance = MagicMock()
                return mock_git_instance
            
            mock_clone.side_effect = side_effect_clone
            mock_pr.return_value = {"html_url": "https://github.com/mock-user/mock-repo/pull/1", "number": 1}
            mock_get_prs.return_value = []
            
            # Mock Redis publish to avoid needing a live server
            mock_redis.return_value.publish.return_value = True

            print("🛠 Executing SDLC Task (this simulates Ada's full process)...")
            
            # Run the worker task directly
            # This will: 
            # 1. Update status to RUNNING
            # 2. Call SDLCOrchestrator -> EpicOrchestrator -> CodingAgent (Mock mode)
            # 3. Use MockLLM steps to 'edit' files
            # 4. Push and Open PR (mocked)
            # 5. Finish with SUCCESS
            execute_sdlc_story(job_id, repo_url, story)

    # Verify Final State
    db = SessionLocal()
    job = db.query(StoryJob).filter(StoryJob.id == job_id).first()
    
    print("\n📊 --- SMOKE TEST SUMMARY ---")
    print(f"Status:      {job.status}")
    
    try:
        logs = json.loads(job.logs)
        print(f"Log Count:   {len(logs)}")
        # Print a few logs to verify content
        if logs:
            print(f"First Log:   {logs[0]['message']}")
            print(f"Last Log:    {logs[-1]['message']}")
    except Exception as e:
        print(f"Error parsing logs: {e}")

    if job.status == "SUCCESS":
        print("\n✅ SYSTEM SMOKE TEST PASSED!")
        print("   Ada successfully navigated the SDLC and generated a mock PR.")
        db.close()
        return True
    else:
        print("\n❌ SYSTEM SMOKE TEST FAILED!")
        db.close()
        return False

if __name__ == "__main__":
    run_smoke_test()
