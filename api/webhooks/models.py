from pydantic import BaseModel, BaseModel as PydanticBaseModel
from typing import Dict, Any, Optional, List

class GitHubProviderPayload(BaseModel):
    """
    Payload model for GitHub-specific webhooks.
    """
    action: Optional[str] = None
    repository: Dict[str, Any]
    workflow_run: Optional[Dict[str, Any]] = None
    issue: Optional[Dict[str, Any]] = None
    comment: Optional[Dict[str, Any]] = None
    pull_request: Optional[Dict[str, Any]] = None

# Future models for other providers can be added here
# class BitbucketProviderPayload(BaseModel):
#     ...
