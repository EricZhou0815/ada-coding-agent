import os
import hmac
import hashlib
import re
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
import logging
from typing import Dict, Any, Optional, Tuple

from worker.tasks import fix_ci_failure, apply_pr_feedback
from config import Config

router = APIRouter()
logger = logging.getLogger("VCSWebhooks")

# Webhook secret for HMAC validation - REQUIRED in production
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# Trigger prefix for Ada commands in PR comments
ADA_TRIGGER_PREFIX = "@ada-ai"


def parse_ada_command(comment_body: str) -> Tuple[bool, str]:
    """
    Check if comment is addressed to Ada and extract the command.
    
    If @ada-ai is present anywhere in the comment, the entire comment
    (with @ada-ai removed) is treated as the instruction.
    
    Supported formats:
        @ada-ai please fix the null check
        Please @ada-ai fix this bug
        Fix the bug @ada-ai
        
    Returns:
        (is_ada_command, extracted_instruction)
    """
    body = comment_body.strip()
    
    # Case-insensitive check for @ada-ai anywhere in the comment
    pattern = r'@ada-ai[:\s]*'
    
    if re.search(pattern, body, re.IGNORECASE):
        # Remove @ada-ai mention and optional colon/whitespace after it
        instruction = re.sub(pattern, '', body, flags=re.IGNORECASE).strip()
        
        # If there's meaningful instruction text, return it
        if instruction:
            return True, instruction
        
        # If comment was just "@ada-ai" with no instruction, ignore it
        return False, ""
    
    return False, ""


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
    try:
        vcs = Config.get_vcs_client()
        return vcs.is_collaborator(owner, repo, username)
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
            
            # Check if Ada should handle CI failures on this branch
            branch_name = workflow_run.get("head_branch", "")
            if not Config.should_auto_fix_ci(branch_name):
                return {"status": "ignored", "reason": f"Branch {branch_name} is not in Ada's auto-fix scope."}
                
            run_id = workflow_run.get("id")
            workflow_name = workflow_run.get("name", "CI")
            
            logger.info(f"Detected CI failure on Ada branch: {branch_name} (Run ID: {run_id})")
            
            # Post acknowledgment comment on the PR (if we can find it)
            try:
                vcs = Config.get_vcs_client()
                prs = vcs.get_pull_requests(owner, repo)
                pr_number = next((p["number"] for p in prs if p["head"]["ref"] == branch_name), None)
                if pr_number:
                    vcs.create_issue_comment(
                        owner, repo, pr_number,
                        f"🔍 **Ada:** CI workflow `{workflow_name}` failed. I'm analyzing the logs and will attempt a fix..."
                    )
            except Exception as e:
                logger.warning(f"Failed to post CI failure acknowledgment: {e}")
            
            # Dispatch Celery worker to handle the fix
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
            
            # Check if comment is addressed to Ada (requires @ada-ai prefix)
            is_ada_command, instruction = parse_ada_command(body)
            if not is_ada_command:
                return {"status": "ignored", "reason": "Comment not addressed to @ada-ai"}
            
            # Check if Ada should handle comments on this PR's branch
            pr_branch = issue.get("pull_request", {}).get("head", {}).get("ref", "")
            if not pr_branch:
                # Fetch PR details to get branch name
                try:
                    vcs = Config.get_vcs_client()
                    pr_data = vcs.get_pull_request(owner, repo, pr_number)
                    pr_branch = pr_data.get("head", {}).get("ref", "")
                except Exception as e:
                    logger.warning(f"Could not fetch PR branch: {e}")
                    pr_branch = ""
            
            if not Config.should_handle_pr_comment(pr_branch):
                logger.info(f"Ignoring @ada-ai comment on non-Ada branch: {pr_branch}")
                return {"status": "ignored", "reason": f"Branch {pr_branch} is not in Ada's scope."}
            
            # Security: Only allow repo collaborators to trigger Ada
            if not is_trusted_commenter(owner, repo, commenter):
                logger.warning(f"Ignoring PR comment from non-collaborator: {commenter}")
                return {"status": "ignored", "reason": f"User {commenter} is not a repository collaborator"}
            
            logger.info(f"Ada command from {commenter} on PR #{pr_number}: {instruction[:50]}...")
            
            # Post immediate acknowledgment (fire and forget)
            try:
                vcs = Config.get_vcs_client()
                vcs.create_issue_comment(
                    owner, repo, pr_number,
                    f"🤖 **Ada:** Got it, @{commenter}! Working on your request...\n\n> {instruction[:200]}{'...' if len(instruction) > 200 else ''}"
                )
            except Exception as e:
                logger.warning(f"Failed to post acknowledgment comment: {e}")
            
            apply_pr_feedback.delay(
                repo_url=repo_url,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                feedback=instruction
            )
            
            return {"status": "dispatched", "job": "apply_pr_feedback"}

    # We ignore all other events smoothly
    return {"status": "ignored", "event_type": event_type}
