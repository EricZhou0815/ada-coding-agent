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
        3. "openai" if OPENAI_API_KEY or OPENAI_API_KEYS is available
        4. "mock" fallback if no keys or set to mock
        """
        provider = os.getenv("LLM_PROVIDER")
        if provider:
            return provider.lower()

        if os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEYS"):
            return "groq"
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
        - OPENAI_API_KEYS / OPENAI_API_KEY (comma-separated or single)
        
        Args:
            provider: The LLM provider ("groq" or "openai")
            
        Returns:
            APIKeyPool instance, or None if only single key is available.
        """
        from agents.api_key_pool import APIKeyPool
        
        provider = provider.lower()
        
        # Check for multi-key environment variable first
        if provider == "groq":
            multi_key_var = "GROQ_API_KEYS"
            single_key_var = "GROQ_API_KEY"
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
            from agents.mock_llm_client import MockLLMClient
            return MockLLMClient()
        else:
            from agents.llm_client import LLMClient
            
            # Try to get a key pool for rotation
            key_pool = cls.get_api_key_pool(provider)
            
            return LLMClient(
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
