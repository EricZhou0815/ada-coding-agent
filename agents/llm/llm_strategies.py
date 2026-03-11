import os
from abc import ABC, abstractmethod
from typing import Optional
from openai import OpenAI

# Groq models
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"

# DeepSeek models
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

# OpenAI models
OPENAI_DEFAULT_MODEL = "gpt-4-turbo-preview"

class LLMStrategy(ABC):
    """
    Abstract base strategy for different LLM providers using OpenAI-compatible APIs.
    """
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def env_key(self) -> str:
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        pass

    @property
    def base_url(self) -> Optional[str]:
        return None

    def get_api_key(self, api_key: Optional[str] = None) -> Optional[str]:
        """
        Resolves the API key from override or environment.
        """
        return api_key or os.getenv(self.env_key)

    def create_client(self, api_key: str) -> OpenAI:
        """
        Instantiates an OpenAI-compatible client.
        """
        return OpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )

class GroqStrategy(LLMStrategy):
    @property
    def provider_name(self) -> str:
        return "Groq"

    @property
    def env_key(self) -> str:
        return "GROQ_API_KEY"

    @property
    def default_model(self) -> str:
        return GROQ_DEFAULT_MODEL

    @property
    def base_url(self) -> str:
        return GROQ_BASE_URL

class DeepSeekStrategy(LLMStrategy):
    @property
    def provider_name(self) -> str:
        return "DeepSeek"

    @property
    def env_key(self) -> str:
        return "DEEPSEEK_API_KEY"

    @property
    def default_model(self) -> str:
        return DEEPSEEK_DEFAULT_MODEL

    @property
    def base_url(self) -> str:
        return DEEPSEEK_BASE_URL

class OpenAIStrategy(LLMStrategy):
    @property
    def provider_name(self) -> str:
        return "OpenAI"

    @property
    def env_key(self) -> str:
        return "OPENAI_API_KEY"

    @property
    def default_model(self) -> str:
        return OPENAI_DEFAULT_MODEL

class LLMProviderFactory:
    """
    Factory to resolve the correct strategy based on the provider name.
    """
    _strategies = {
        "groq": GroqStrategy(),
        "deepseek": DeepSeekStrategy(),
        "openai": OpenAIStrategy(),
    }

    @classmethod
    def get_strategy(cls, provider: str) -> LLMStrategy:
        strategy = cls._strategies.get(provider.lower())
        if not strategy:
            raise ValueError(f"Unsupported provider: '{provider}'. Use 'groq', 'deepseek', or 'openai'.")
        return strategy
