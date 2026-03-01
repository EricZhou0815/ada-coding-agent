from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
from typing import Dict, Any

from worker.tasks import fix_ci_failure, apply_pr_feedback

router = APIRouter()
logger = logging.getLogger("VCSWebhooks")

@router.post("/github")
async def github_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Receives events specifically from GitHub webhooks.
    """
    
    # Optional: Verify GitHub HMAC signature here for security
    
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    logger.info(f"Received GitHub webhook event: {event_type}")

    # Extract repository information
    repo_data = payload.get("repository", {})
    repo_url = repo_data.get("html_url")
    owner = repo_data.get("owner", {}).get("login")
    repo = repo_data.get("name")
    
    if not repo_url or not owner or not repo:
        return {"status": "ignored", "reason": "Missing repository tracking data."}

    # ─────────────────────────────────────────────────────────────────
    # Event: CI Pipeline Failed (`workflow_run`)
    # ─────────────────────────────────────────────────────────────────
    if event_type == "workflow_run":
        action = payload.get("action")
        workflow_run = payload.get("workflow_run", {})
        
        # We only care when a run finishes and fails
        if action == "completed" and workflow_run.get("conclusion") == "failure":
            
            # Check if this run was on an Ada-managed branch
            branch_name = workflow_run.get("head_branch", "")
            if not branch_name.startswith("ada/"):
                return {"status": "ignored", "reason": f"Branch {branch_name} is not managed by Ada."}
                
            run_id = workflow_run.get("id")
            
            logger.info(f"Detected CI failure on Ada branch: {branch_name} (Run ID: {run_id})")
            
            # Dispatch Celery worker to handle the fix
            # Note: We pass the run_id so the worker can fetch the exact terminal logs
            fix_ci_failure.delay(
                repo_url=repo_url,
                owner=owner,
                repo=repo,
                branch_name=branch_name,
                run_id=run_id
            )
            
            return {"status": "dispatched", "job": "fix_ci_failure"}

    # ─────────────────────────────────────────────────────────────────
    # Event: PR Comment Created (`issue_comment`)
    # ─────────────────────────────────────────────────────────────────
    elif event_type == "issue_comment":
        action = payload.get("action")
        issue = payload.get("issue", {})
        comment = payload.get("comment", {})
        
        # We only care about new comments on Pull Requests, not generic issues
        if action == "created" and "pull_request" in issue:
            # We must fetch the PR to ensure it's an Ada branch
            body = comment.get("body", "").strip()
            pr_number = issue.get("number")
            
            # In production we would ping the GitHub API here to check the PR's head branch.
            # If `head_branch.startswith('ada/')`, we dispatch to Ada.
            
            logger.info(f"Detected new PR comment on #{pr_number}: {body[:50]}...")
            
            apply_pr_feedback.delay(
                repo_url=repo_url,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                feedback=body
            )
            
            return {"status": "dispatched", "job": "apply_pr_feedback"}

    # We ignore all other events smoothly
    return {"status": "ignored", "event_type": event_type}
