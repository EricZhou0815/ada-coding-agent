import os
import json
import time
from openai import OpenAI
from typing import List, Dict, Any, Optional

from agents.api_key_pool import (
    APIKeyPool, 
    is_rate_limit_error, 
    is_quota_exhausted_error, 
    is_invalid_key_error
)

# Groq models available via OpenAI-compatible API
# See: https://console.groq.com/docs/openai
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
OPENAI_DEFAULT_MODEL = "gpt-4-turbo-preview"


class LLMClient:
    """
    LLM client wrapper for Ada.
    Supports Groq (default) and OpenAI via the OpenAI-compatible client.
    Supports function calling for tool execution.
    
    Features:
        - Multi-key support with automatic rotation on failures
        - Automatic retry with exponential backoff
        - Rate limit and quota exhaustion handling

    Providers:
        - "groq"
        - "openai"
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        provider: str = "groq",
        key_pool: Optional[APIKeyPool] = None,
    ):
        """
        Initializes the LLMClient.

        Args:
            api_key (str, optional): An explicit API key. Defaults to fetching from environment.
            model (str, optional): The specific model name to use. Defaults to provider generic defaults.
            provider (str, optional): Which platform to use ('groq' or 'openai'). Defaults to "groq".
            key_pool (APIKeyPool, optional): Pool of API keys for rotation. Takes precedence over api_key.

        Raises:
            ValueError: If the API key for the requested provider is missing.
            ValueError: If the provider requested is unsupported.
        """
        self.provider = provider.lower()
        self.key_pool = key_pool
        self._current_api_key: Optional[str] = None
        self._client: Optional[OpenAI] = None

        if self.provider == "groq":
            if key_pool:
                self._current_api_key = key_pool.get_key()
            else:
                self._current_api_key = api_key or os.getenv("GROQ_API_KEY")
            if not self._current_api_key:
                raise ValueError("Groq API key not provided (set GROQ_API_KEY or use key_pool).")
            self.model = model or GROQ_DEFAULT_MODEL
            self._client = OpenAI(
                api_key=self._current_api_key,
                base_url=GROQ_BASE_URL,
            )
        elif self.provider == "openai":
            if key_pool:
                self._current_api_key = key_pool.get_key()
            else:
                self._current_api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not self._current_api_key:
                raise ValueError("OpenAI API key not provided (set OPENAI_API_KEY or use key_pool).")
            self.model = model or OPENAI_DEFAULT_MODEL
            self._client = OpenAI(api_key=self._current_api_key)
        else:
            raise ValueError(f"Unsupported provider: '{provider}'. Use 'groq' or 'openai'.")

        # Keep backward-compatible alias
        self.api_key = self._current_api_key
        self.client = self._client
        self.conversation_history = []
    
    def _rotate_key(self) -> bool:
        """
        Rotate to the next available API key.
        
        Returns:
            True if rotation succeeded, False if no pool or no available keys.
        """
        if not self.key_pool:
            return False
        
        try:
            new_key = self.key_pool.get_key()
            if new_key == self._current_api_key:
                # Same key returned, might be the only available one
                # Try once more in case it's round-robin
                new_key = self.key_pool.get_key()
            
            self._current_api_key = new_key
            self.api_key = new_key
            
            # Recreate client with new key
            if self.provider == "groq":
                self._client = OpenAI(api_key=new_key, base_url=GROQ_BASE_URL)
            else:
                self._client = OpenAI(api_key=new_key)
            
            self.client = self._client
            return True
        except RuntimeError:
            # All keys exhausted
            return False

    def generate(self, prompt: str, tools: Any = None) -> Dict:
        """
        Generates a response from the LLM, managing conversation history and optional tool calls.

        If the most recent message in the chat history was an assistant tool call, this method 
        automatically appends the incoming `prompt` as a `role: tool` message to fulfill the API requirements.
        
        Implements automatic key rotation on rate limits or quota exhaustion when using a key pool.

        Args:
            prompt (str): The user's prompt or the serialized result from a previous tool call.
            tools (Any, optional): The list of callable tools available to the LLM. Defaults to None.

        Returns:
            Dict: Result mapping containing `content`, `function_call`, and `finish_reason`.
        """
        # Check if the last message was a tool call
        last_message = self.conversation_history[-1] if self.conversation_history else None
        
        if last_message and last_message.get("role") == "assistant" and last_message.get("tool_calls"):
            # The prompt is actually the result of the tool call
            # We must pass it as a `role: "tool"` message.
            tool_call = last_message["tool_calls"][0]
            # Handle both dictionary (serialized) and object (live) formats
            if isinstance(tool_call, dict):
                tool_call_id = tool_call.get("id")
                function_name = tool_call.get("function", {}).get("name")
            else:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name

            self.conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": function_name,
                "content": prompt
            })
        else:
            # Add user message to conversation normally
            self.conversation_history.append({
                "role": "user",
                "content": prompt
            })

        api_tools = None
        if tools:
            api_tools = self._tools_to_tools_api_format(tools)

        max_api_retries = 5  # Increased to allow for key rotation
        api_retry_count = 0
        last_exception = None
        
        while api_retry_count < max_api_retries:
            try:
                # Make API call (same interface for both Groq and OpenAI)
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=api_tools if api_tools else None,
                    tool_choice="auto" if api_tools else None,
                    temperature=0.7,
                    max_tokens=2000,
                )
                
                # Success - mark key as healthy if using pool
                if self.key_pool:
                    self.key_pool.mark_success(self._current_api_key)
                
                break
                
            except Exception as e:
                last_exception = e
                api_retry_count += 1
                
                # Classify the error and handle accordingly
                if is_invalid_key_error(e):
                    # Key is permanently bad
                    if self.key_pool:
                        self.key_pool.mark_invalid(self._current_api_key)
                        if self._rotate_key():
                            continue  # Retry immediately with new key
                    raise ValueError(f"Invalid API key: {e}")
                
                elif is_quota_exhausted_error(e):
                    # Quota exhausted - try rotating to another key
                    if self.key_pool:
                        self.key_pool.mark_quota_exhausted(self._current_api_key)
                        if self._rotate_key():
                            continue  # Retry immediately with new key
                    # No more keys available, propagate error
                    raise e
                
                elif is_rate_limit_error(e):
                    # Rate limited - mark and try rotating
                    if self.key_pool:
                        self.key_pool.mark_rate_limited(self._current_api_key)
                        if self._rotate_key():
                            continue  # Retry immediately with new key
                    
                    # No pool or no available keys - do exponential backoff
                    if api_retry_count >= max_api_retries:
                        raise e
                    wait_time = min(2 ** api_retry_count, 30)  # Cap at 30s
                    time.sleep(wait_time)
                
                else:
                    # Unknown error - standard retry with backoff
                    if api_retry_count >= max_api_retries:
                        raise e
                    wait_time = 2 ** api_retry_count
                    time.sleep(wait_time)
        
        if api_retry_count >= max_api_retries and last_exception:
            raise last_exception


        message = response.choices[0].message

        # Groq/OpenAI 'tools' API responses have `message.tool_calls`
        tool_calls = getattr(message, "tool_calls", None)
        
        # We'll extract the first tool call to match the old 'function_call' interface for Ada
        function_call = None
        if tool_calls and len(tool_calls) > 0:
            function_call = tool_calls[0].function

        # Add assistant response to history
        serializable_tool_calls = None
        if tool_calls:
            serializable_tool_calls = []
            for tc in tool_calls:
                # Use model_dump if it's a Pydantic model (OpenAI V1+)
                if hasattr(tc, "model_dump"):
                    serializable_tool_calls.append(tc.model_dump())
                else:
                    # Manual mapping for older SDKs or Groq
                    serializable_tool_calls.append({
                        "id": getattr(tc, "id", None),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

        self.conversation_history.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": serializable_tool_calls,
        })

        return {
            "content": message.content,
            "function_call": function_call,
            "finish_reason": response.choices[0].finish_reason,
        }

    def _tools_to_tools_api_format(self, tools: Any) -> List[Dict]:
        """
        Converts the internal Ada toolset into the strict modern JSON schema expected by OpenAI's 'tools' API.

        Args:
            tools (Any): Instance of the active tool class (e.g. `Tools`).

        Returns:
            List[Dict]: A list of tool schemas mapping function names to descriptions and parameters.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file at the given path",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"}
                        },
                        "required": ["path"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file at the given path",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to write"},
                            "content": {"type": "string", "description": "Content to write to file"},
                        },
                        "required": ["path", "content"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_file",
                    "description": "Delete a file at the given path",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to delete"}
                        },
                        "required": ["path"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Replaces exactly one occurrence of `target_content` with `replacement_content` in the file. Useful for editing segments of large files without rewriting everything.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to write"},
                            "target_content": {"type": "string", "description": "The EXACT string to replace."},
                            "replacement_content": {"type": "string", "description": "The exact string doing the replacing."},
                        },
                        "required": ["path", "target_content", "replacement_content"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_codebase",
                    "description": "Searches for a keyword or regex pattern in the directory workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string", "description": "The query string to search for using grep"},
                            "directory": {"type": "string", "description": "The directory to search inside (default is '.')"},
                        },
                        "required": ["keyword"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List all files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {"type": "string", "description": "Directory path to list"}
                        },
                        "required": ["directory"],
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Shell command to execute"}
                        },
                        "required": ["command"],
                    },
                }
            },
        ]

    def reset_conversation(self):
        """
        Clears the conversation history stored in this client instance.
        """
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict]:
        """
        Returns the current conversation history.
        """
        return self.conversation_history

    def set_conversation_history(self, history: List[Dict]):
        """
        Overrides the current conversation history.
        """
        self.conversation_history = history


# Backward-compatible alias
OpenAIClient = LLMClient
