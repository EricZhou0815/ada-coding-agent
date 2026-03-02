import os
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
import logging
from typing import Dict, Any, Optional

from worker.tasks import fix_ci_failure, apply_pr_feedback

router = APIRouter()
logger = logging.getLogger("VCSWebhooks")

# Webhook secret for HMAC validation - REQUIRED in production
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")


def verify_github_signature(payload_body: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify that the webhook payload was sent by GitHub using HMAC-SHA256.
    
    Args:
        payload_body: Raw request body bytes
        signature_header: X-Hub-Signature-256 header value
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not GITHUB_WEBHOOK_SECRET:
        # No secret configured - log warning but allow in dev mode
        logger.warning("GITHUB_WEBHOOK_SECRET not set - webhook signature verification DISABLED")
        return True
    
    if not signature_header:
        logger.error("Missing X-Hub-Signature-256 header")
        return False
    
    # GitHub sends signature as "sha256=<hex_digest>"
    if not signature_header.startswith("sha256="):
        logger.error("Invalid signature format - expected sha256=...")
        return False
    
    expected_signature = signature_header[7:]  # Remove "sha256=" prefix
    
    # Compute HMAC using our secret
    computed_hmac = hmac.new(
        key=GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_hmac, expected_signature)


def is_trusted_commenter(owner: str, repo: str, username: str) -> bool:
    """
    Check if a user is a collaborator on the repository.
    Only collaborators can trigger Ada actions via PR comments.
    
    Args:
        owner: Repository owner
        repo: Repository name
        username: GitHub username of the commenter
        
    Returns:
        True if user is a collaborator, False otherwise
    """
    from tools.github_client import GitHubClient
    
    try:
        gh = GitHubClient()
        return gh.is_collaborator(owner, repo, username)
    except Exception as e:
        logger.error(f"Failed to check collaborator status for {username}: {e}")
        # Fail closed - deny access if we can't verify
        return False


@router.post("/github")
async def github_webhook_handler(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Receives events specifically from GitHub webhooks.
    """
    
    # Step 1: Read raw body for signature verification
    payload_body = await request.body()
    
    # Step 2: Verify HMAC signature (prevents spoofed webhooks)
    if not verify_github_signature(payload_body, x_hub_signature_256):
        logger.error("Webhook signature verification failed - rejecting request")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Step 3: Parse JSON payload
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
            body = comment.get("body", "").strip()
            pr_number = issue.get("number")
            commenter = comment.get("user", {}).get("login", "")
            
            # Security: Only allow repo collaborators to trigger Ada
            if not is_trusted_commenter(owner, repo, commenter):
                logger.warning(f"Ignoring PR comment from non-collaborator: {commenter}")
                return {"status": "ignored", "reason": f"User {commenter} is not a repository collaborator"}
            
            logger.info(f"Detected PR comment from collaborator {commenter} on #{pr_number}: {body[:50]}...")
            
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
