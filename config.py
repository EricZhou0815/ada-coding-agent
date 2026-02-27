import os

class Config:
    """Central configuration for the Ada project."""

    @classmethod
    def get_llm_provider(cls) -> str:
        """
        Determine which LLM provider to use.
        Priority:
        1. LLM_PROVIDER from environment
        2. "groq" if GROQ_API_KEY is available
        3. "openai" if OPENAI_API_KEY is available
        4. "mock" fallback if no keys or set to mock
        """
        provider = os.getenv("LLM_PROVIDER")
        if provider:
            return provider.lower()

        if os.getenv("GROQ_API_KEY"):
            return "groq"
        elif os.getenv("OPENAI_API_KEY"):
            return "openai"
        return "mock"

    @classmethod
    def get_llm_client(cls, force_mock: bool = False):
        """
        Instantiate and return the appropriate LLM client based on configuration.
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
            return LLMClient(provider=provider)
