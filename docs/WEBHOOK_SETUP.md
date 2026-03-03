# Webhook Setup Guide

This guide explains how to set up webhooks from your VCS platform (GitHub or GitLab) to enable Ada's automated workflows.

## Overview

Ada responds to webhook events from your VCS platform to:
- Auto-fix CI/CD pipeline failures
- Process PR comments with `@ada-ai` mentions
- Trigger automated code reviews and improvements

## Prerequisites

- Ada backend service running and accessible via HTTPS
- VCS platform account with admin/owner access to repositories
- Valid webhook secret configured in your Ada environment

## GitHub Webhook Setup

### 1. Navigate to Repository Settings

Go to your repository → **Settings** → **Webhooks** → **Add webhook**

### 2. Configure Webhook

- **Payload URL**: `https://your-ada-instance.com/api/v1/webhooks/github`
- **Content type**: `application/json`
- **Secret**: Use the value from your `GITHUB_WEBHOOK_SECRET` environment variable

### 3. Select Events

Choose **"Let me select individual events"** and enable:

- ✅ **Pull requests** - For PR comment handling
- ✅ **Issue comments** - For `@ada-ai` mentions in PR comments
- ✅ **Workflow runs** - For CI/CD failure detection and auto-fix

### 4. Activate Webhook

- ✅ Check **"Active"**
- Click **"Add webhook"**

### 5. Verify Setup

After saving, GitHub will send a test `ping` event. Check:
- Recent Deliveries tab shows green checkmark
- Response status is `200 OK`

## GitLab Webhook Setup

### 1. Navigate to Project Settings

Go to your project → **Settings** → **Webhooks**

### 2. Configure Webhook

- **URL**: `https://your-ada-instance.com/api/v1/webhooks/gitlab`
- **Secret token**: Use the value from your `GITLAB_WEBHOOK_SECRET` environment variable

### 3. Select Trigger Events

Enable the following triggers:

- ✅ **Merge request events** - For MR comment handling
- ✅ **Comments** - For `@ada-ai` mentions in MR comments  
- ✅ **Pipeline events** - For CI/CD failure detection and auto-fix

### 4. SSL Verification

- ✅ **Enable SSL verification** (recommended for production)
- If using self-signed certificates, you may need to disable this temporarily

### 5. Add Webhook

Click **"Add webhook"**

### 6. Test Webhook

- Click **"Test"** → **"Pipeline events"** to verify connectivity
- Check that the response shows `HTTP 200`
- Review webhook execution logs at the bottom of the page

## Environment Configuration

### GitHub Setup

```bash
# Required
VCS_PLATFORM=github
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Optional scope controls
ADA_BRANCH_PREFIX=ada-ai/
ADA_HANDLE_ALL_PRS=false
ADA_AUTO_FIX_CI_ALL=false
```

### GitLab Setup

```bash
# Required
VCS_PLATFORM=gitlab
GITLAB_TOKEN=glpat_your_access_token
GITLAB_WEBHOOK_SECRET=your_webhook_secret_here

# Optional for self-hosted GitLab
GITLAB_URL=https://gitlab.company.com

# Optional scope controls
ADA_BRANCH_PREFIX=ada-ai/
ADA_HANDLE_ALL_PRS=false
ADA_AUTO_FIX_CI_ALL=false
```

## Webhook Endpoints

Ada provides the following webhook endpoints:

| Endpoint | Platform | Purpose |
|----------|----------|---------|
| `/api/v1/webhooks/github` | GitHub | Handles GitHub webhook events |
| `/api/v1/webhooks/gitlab` | GitLab | Handles GitLab webhook events |

## Security Best Practices

### 1. Use Webhook Secrets

Always configure webhook secrets to verify request authenticity:

```bash
# Generate a secure random secret (example)
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. HTTPS Only

Configure your Ada instance to use HTTPS with valid SSL certificates. Webhook payloads may contain sensitive information.

### 3. IP Allowlisting (Optional)

For additional security, restrict webhook traffic to official VCS platform IP ranges:

- **GitHub**: https://api.github.com/meta (check `hooks` field)
- **GitLab.com**: https://docs.gitlab.com/ee/user/gitlab_com/#ip-range

### 4. Scope Management

Use Ada's scope controls to limit which PRs/pipelines Ada can interact with:

```bash
# Safe default: Ada only handles branches she created
ADA_BRANCH_PREFIX=ada-ai/
ADA_HANDLE_ALL_PRS=false
ADA_AUTO_FIX_CI_ALL=false

# Open mode: Ada handles all PRs/pipelines (team collaboration)
ADA_HANDLE_ALL_PRS=true
ADA_AUTO_FIX_CI_ALL=true
```

## Webhook Event Flow

### Auto-Fix CI Failure

1. Pipeline/workflow fails on a PR
2. VCS platform sends webhook event to Ada
3. Ada checks if branch matches scope (`ada-ai/*` by default)
4. If match: Ada analyzes logs, generates fix, commits to branch
5. New pipeline run starts automatically

### PR Comment Processing

1. User comments `@ada-ai please optimize this function` on PR
2. VCS platform sends webhook event to Ada
3. Ada checks if PR branch matches scope
4. If match: Ada parses instruction, processes code, posts response
5. Ada creates follow-up commits if needed

## Troubleshooting

### Webhook Not Triggering

**Check webhook delivery logs:**
- GitHub: Repository → Settings → Webhooks → Recent Deliveries
- GitLab: Project → Settings → Webhooks → [Your webhook] → Recent events

**Common issues:**
- ❌ Ada backend not accessible (firewall, DNS)
- ❌ Wrong webhook URL or secret
- ❌ SSL certificate issues (especially self-hosted GitLab)
- ❌ Required events not selected

### Webhook Returns Error

**4xx errors:**
- `401/403`: Webhook secret mismatch or missing `VCS_TOKEN`
- `404`: Wrong endpoint URL
- `422`: Invalid payload format

**5xx errors:**
- `500`: Check Ada backend logs for Python exceptions
- `502/503`: Backend service down or unreachable

**Fix checklist:**
1. Verify `VCS_PLATFORM` matches webhook endpoint
2. Check webhook secret matches environment variable
3. Ensure VCS token has required permissions
4. Review Ada backend logs: `docker-compose logs -f api`

### Ada Not Responding to Comments

**Verify trigger format:**
- ✅ Correct: `@ada-ai please fix this`
- ✅ Correct: `Can you @ada-ai help with this?`
- ❌ Wrong: `@ada please fix` (old trigger)

**Check scope configuration:**
- If branch is `feature/new-thing`, Ada ignores by default
- If branch is `ada-ai/new-thing`, Ada processes
- Set `ADA_HANDLE_ALL_PRS=true` to handle all branches

### Ada Not Auto-Fixing CI

**Verify event selection:**
- GitHub: "Workflow runs" event must be enabled
- GitLab: "Pipeline events" must be enabled

**Check scope:**
- Verify pipeline runs on `ada-ai/*` branch
- Or set `ADA_AUTO_FIX_CI_ALL=true`

**Check collaborator permissions:**
- Ada's VCS token user must have write access to repository
- GitHub: Must be repo collaborator
- GitLab: Must have access_level >= 30 (Developer+)

## Testing Webhooks Locally

For local development, use a tunnel service to expose your local Ada instance:

### Using ngrok

```bash
# Start ngrok tunnel
ngrok http 8000

# Use the ngrok URL as webhook URL
# Example: https://abc123.ngrok.io/api/webhooks/github
```

### Using VS Code Port Forwarding

If using GitHub Codespaces or VS Code Remote:
1. Forward port 8000
2. Set visibility to "Public"
3. Use the forwarded URL for webhooks

## Multi-Repository Setup

To use Ada across multiple repositories:

### Option 1: Repository-Level Webhooks

Configure webhooks individually for each repository (as shown above).

**Pros:** Fine-grained control per repository  
**Cons:** Repetitive setup

### Option 2: Organization-Level Webhooks (GitHub)

1. Go to Organization → Settings → Webhooks
2. Configure same settings as repository webhook
3. Events apply to all organization repositories

**Pros:** Single setup for all repos  
**Cons:** Requires organization admin access

### Option 3: System Hooks (GitLab Self-Hosted)

GitLab self-hosted instances can use system hooks:

1. Admin Area → System Hooks
2. Configure webhook URL and events
3. Applies to all projects on instance

**Pros:** Single setup for entire GitLab instance  
**Cons:** Requires GitLab administrator access

## Advanced Configuration

### Custom Webhook Handler

You can extend Ada's webhook processing by modifying:

- [api/webhooks/vcs.py](../api/webhooks/vcs.py) - Main webhook handlers
- [worker/tasks.py](../worker/tasks.py) - Background processing tasks

### Event Filtering

Ada automatically filters events based on:
- Branch naming (`ADA_BRANCH_PREFIX`)
- PR scope (`ADA_HANDLE_ALL_PRS`)
- CI scope (`ADA_AUTO_FIX_CI_ALL`)

Customize this logic in [config.py](../config.py):
```python
@staticmethod
def should_handle_pr_comment(branch_name: str) -> bool:
    """Determine if Ada should respond to PR comment"""
    # Add custom logic here
```

## Next Steps

- [Architecture Overview](../design_doc/design.md) - Understanding Ada's components
- [Configuration Reference](../README.md#configuration) - All environment variables
- [Worker Setup](../README_WORKER.md) - Configuring background task processing

## Support

For webhook issues not covered here:
1. Check Ada backend logs: `docker-compose logs -f api`
2. Review webhook delivery logs in your VCS platform
3. Verify environment configuration matches this guide
