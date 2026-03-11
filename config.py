import os

class Config:
    """Central configuration for the Ada project."""

    @classmethod
    def get_llm_provider(cls) -> str:
        """
        Determine which LLM provider to use.
        Priority:
        1. LLM_PROVIDER from environment
        2. "groq" if GROQ_API_KEY or GROQ_API_KEYS is available
        3. "deepseek" if DEEPSEEK_API_KEY or DEEPSEEK_API_KEYS is available
        4. "openai" if OPENAI_API_KEY or OPENAI_API_KEYS is available
        5. "mock" fallback if no keys or set to mock
        """
        provider = os.getenv("LLM_PROVIDER")
        if provider:
            return provider.lower()

        if os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEYS"):
            return "groq"
        elif os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEYS"):
            return "deepseek"
        elif os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEYS"):
            return "openai"
        return "mock"

    @classmethod
    def get_llm_model(cls) -> str | None:
        """
        Get the specific LLM model to use from the environment.
        Returns None to use the provider's default model.
        """
        return os.getenv("LLM_MODEL")
    
    @classmethod
    def get_api_key_pool(cls, provider: str):
        """
        Get an APIKeyPool for the specified provider.
        
        Supports:
        - GROQ_API_KEYS / GROQ_API_KEY (comma-separated or single)
        - DEEPSEEK_API_KEYS / DEEPSEEK_API_KEY (comma-separated or single)
        - OPENAI_API_KEYS / OPENAI_API_KEY (comma-separated or single)
        
        Args:
            provider: The LLM provider ("groq", "deepseek", or "openai")
            
        Returns:
            APIKeyPool instance, or None if only single key is available.
        """
        from agents.llm import APIKeyPool
        
        provider = provider.lower()
        
        # Check for multi-key environment variable first
        if provider == "groq":
            multi_key_var = "GROQ_API_KEYS"
            single_key_var = "GROQ_API_KEY"
        elif provider == "deepseek":
            multi_key_var = "DEEPSEEK_API_KEYS"
            single_key_var = "DEEPSEEK_API_KEY"
        elif provider == "openai":
            multi_key_var = "OPENAI_API_KEYS"
            single_key_var = "OPENAI_API_KEY"
        else:
            return None
        
        # Try multi-key variable first
        keys_str = os.getenv(multi_key_var, "")
        if keys_str:
            keys = [k.strip() for k in keys_str.split(",") if k.strip()]
            if len(keys) > 1:
                return APIKeyPool(keys)
            elif len(keys) == 1:
                return APIKeyPool(keys)
        
        # Fallback to single key - still wrap in pool for consistent interface
        single_key = os.getenv(single_key_var)
        if single_key:
            return APIKeyPool([single_key])
        
        return None

    @classmethod
    def get_llm_client(cls, force_mock: bool = False):
        """
        Instantiate and return the appropriate LLM client based on configuration.
        
        Automatically uses APIKeyPool for multi-key rotation when multiple
        keys are configured via GROQ_API_KEYS or OPENAI_API_KEYS.
        """
        if force_mock:
            provider = "mock"
        else:
            provider = cls.get_llm_provider()

        if provider == "mock":
            from agents.llm import MockLLMClient
            return MockLLMClient()
        else:
            from agents.llm import LLMClient
            
            # Try to get a key pool for rotation
            key_pool = cls.get_api_key_pool(provider)
            
            return LLMClient(
                provider=provider, 
                model=cls.get_llm_model(),
                key_pool=key_pool
            )

    @classmethod
    def get_async_llm_client(cls, force_mock: bool = False):
        """
        Instantiate and return the appropriate async LLM client based on configuration.
        
        Automatically uses APIKeyPool for multi-key rotation when multiple
        keys are configured via GROQ_API_KEYS or OPENAI_API_KEYS.
        """
        if force_mock:
            provider = "mock"
        else:
            provider = cls.get_llm_provider()

        if provider == "mock":
            from agents.llm import MockLLMClient
            return MockLLMClient()
        else:
            from agents.llm import AsyncLLMClient
            
            # Try to get a key pool for rotation
            key_pool = cls.get_api_key_pool(provider)
            
            return AsyncLLMClient(
                provider=provider, 
                model=cls.get_llm_model(),
                key_pool=key_pool
            )

    @classmethod
    def get_isolation_backend_type(cls) -> str:
        """
        Determine which isolation backend to use.
        Options: "sandbox" (default), "docker", "ecs"
        """
        return os.getenv("ADA_ISOLATION_BACKEND", "sandbox").lower()

    @classmethod
    def get_isolation_backend(cls, workspace_root: str = None):
        """
        Instantiate and return the configured isolation backend.
        """
        backend_type = cls.get_isolation_backend_type()
        
        if backend_type == "docker":
            from isolation.docker_backend import DockerBackend
            return DockerBackend()
        elif backend_type == "ecs":
            from isolation.ecs_backend import ECSBackend
            return ECSBackend()
        else:
            from isolation.sandbox import SandboxBackend
            return SandboxBackend(workspace_root=workspace_root)

    @classmethod
    def get_vcs_platform(cls) -> str:
        """
        Determine which VCS platform to use.
        Options: "github" (default), "gitlab"
        """
        return os.getenv("VCS_PLATFORM", "github").lower()

    @classmethod
    def get_vcs_client(cls):
        """
        Instantiate and return the configured VCS client.
        
        Uses VCS_PLATFORM env var to select between:
        - "github" (default): Uses GITHUB_TOKEN
        - "gitlab": Uses GITLAB_TOKEN and optionally GITLAB_URL
        
        Returns:
            VCSClient implementation for the configured platform.
        """
        from tools.vcs_client import VCSClientFactory
        
        # Import clients to register them with the factory
        # This import has side effects (registration)
        from tools.github_client import GitHubClient  # noqa: F401
        
        platform = cls.get_vcs_platform()
        
        # Import GitLab client only if needed (lazy loading)
        if platform == "gitlab":
            from tools.gitlab_client import GitLabClient  # noqa: F401
        
        return VCSClientFactory.create(platform)

    # ─────────────────────────────────────────────────────────────────────────
    # Ada Management Scope Configuration
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_ada_branch_prefix(cls) -> str:
        """
        Get the branch prefix for Ada-managed branches.
        Default: "ada-ai/" (aligns with @ada-ai mention)
        """
        return os.getenv("ADA_BRANCH_PREFIX", "ada-ai/")

    @classmethod
    def is_ada_managed_branch(cls, branch_name: str) -> bool:
        """
        Check if a branch is managed by Ada based on naming convention.
        
        Args:
            branch_name: The branch name to check
            
        Returns:
            True if branch follows Ada's naming pattern
        """
        prefix = cls.get_ada_branch_prefix()
        return branch_name.startswith(prefix)

    @classmethod
    def should_handle_all_prs(cls) -> bool:
        """
        Check if Ada should respond to @ada-ai on ALL PRs.
        
        Returns:
            True if ADA_HANDLE_ALL_PRS=true, False otherwise (default)
        """
        return os.getenv("ADA_HANDLE_ALL_PRS", "false").lower() == "true"

    @classmethod
    def should_auto_fix_all_ci(cls) -> bool:
        """
        Check if Ada should auto-fix CI failures on ALL branches.
        
        Returns:
            True if ADA_AUTO_FIX_CI_ALL=true, False otherwise (default)
        """
        return os.getenv("ADA_AUTO_FIX_CI_ALL", "false").lower() == "true"

    @classmethod
    def should_handle_pr_comment(cls, branch_name: str) -> bool:
        """
        Determine if Ada should respond to a @ada-ai comment on this PR.
        
        Args:
            branch_name: The PR's head branch name
            
        Returns:
            True if Ada should handle the comment
        """
        if cls.should_handle_all_prs():
            return True
        return cls.is_ada_managed_branch(branch_name)

    @classmethod
    def should_auto_fix_ci(cls, branch_name: str) -> bool:
        """
        Determine if Ada should auto-fix CI failures on this branch.
        
        Args:
            branch_name: The branch name where CI failed
            
        Returns:
            True if Ada should attempt to fix the CI failure
        """
        if cls.should_auto_fix_all_ci():
            return True
        return cls.is_ada_managed_branch(branch_name)

    @classmethod
    def get_app_version(cls) -> str:
        """
        Get the application version for documentation and monitoring.
        
        This is separate from API versioning (/api/v1/) which stays hardcoded.
        Use semantic versioning: MAJOR.MINOR.PATCH
        
        Returns:
            Version string (e.g., "1.0.0")
        """
        return os.getenv("APP_VERSION", "1.0.0")
