"""
Async LLM Client for Ada - Non-blocking LLM calls for high-scale deployments

This async version allows FastAPI to handle thousands of concurrent planning sessions
without blocking worker threads during LLM API calls.
"""

import os
import json
import asyncio
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional

from agents.api_key_pool import (
    APIKeyPool, 
    is_rate_limit_error, 
    is_quota_exhausted_error, 
    is_invalid_key_error
)

# Groq models available via OpenAI-compatible API
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
OPENAI_DEFAULT_MODEL = "gpt-4-turbo-preview"


class AsyncLLMClient:
    """
    Async LLM client wrapper for Ada - enables non-blocking LLM calls.
    
    Key differences from sync LLMClient:
    - Uses AsyncOpenAI for non-blocking HTTP requests
    - Uses asyncio.sleep instead of time.sleep
    - All methods are async (use with await)
    
    Benefits:
    - Single FastAPI worker can handle 100+ concurrent planning sessions
    - No thread blocking during LLM API calls (2-3s each)
    - 10-50x better throughput than synchronous version
    
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
        max_context_tokens: int = None,
    ):
        """
        Initializes the Async LLM Client.

        Args:
            api_key (str, optional): An explicit API key. Defaults to fetching from environment.
            model (str, optional): The specific model name to use. Defaults to provider generic defaults.
            provider (str, optional): Which platform to use ('groq' or 'openai'). Defaults to "groq".
            key_pool (APIKeyPool, optional): Pool of API keys for rotation. Takes precedence over api_key.
            max_context_tokens (int, optional): Maximum tokens to keep in conversation history.
                Defaults to 80000 (safe for GPT-4/Claude). Set via ADA_MAX_CONTEXT_TOKENS env var.

        Raises:
            ValueError: If the API key for the requested provider is missing.
            ValueError: If the provider requested is unsupported.
        """
        self.provider = provider.lower()
        self.key_pool = key_pool
        self._current_api_key: Optional[str] = None
        self._client: Optional[AsyncOpenAI] = None
        
        # Token budget for context management
        if max_context_tokens is None:
            max_context_tokens = int(os.getenv("ADA_MAX_CONTEXT_TOKENS", "80000"))
        self.max_context_tokens = max_context_tokens

        if self.provider == "groq":
            if key_pool:
                self._current_api_key = key_pool.get_key()
            else:
                self._current_api_key = api_key or os.getenv("GROQ_API_KEY")
            if not self._current_api_key:
                raise ValueError("Groq API key not provided (set GROQ_API_KEY or use key_pool).")
            self.model = model or GROQ_DEFAULT_MODEL
            self._client = AsyncOpenAI(
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
            self._client = AsyncOpenAI(api_key=self._current_api_key)
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
                # Try once more in case it's round-robin
                new_key = self.key_pool.get_key()
            
            self._current_api_key = new_key
            self.api_key = new_key
            
            # Recreate client with new key
            if self.provider == "groq":
                self._client = AsyncOpenAI(api_key=new_key, base_url=GROQ_BASE_URL)
            else:
                self._client = AsyncOpenAI(api_key=new_key)
            
            self.client = self._client
            return True
        except RuntimeError:
            # All keys exhausted
            return False

    async def generate(self, prompt: str, tools: Any = None) -> Dict:
        """
        Generates a response from the LLM asynchronously (non-blocking).
        
        This is the KEY difference from sync LLMClient:
        - Uses 'await' for API calls
        - Doesn't block the thread while waiting for LLM response
        - Allows FastAPI to handle other requests concurrently

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
            tool_call = last_message["tool_calls"][0]
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

        # Trim conversation to stay within token budget
        self._trim_to_budget()

        max_api_retries = 5
        api_retry_count = 0
        last_exception = None
        
        while api_retry_count < max_api_retries:
            try:
                # ✨ ASYNC API CALL - Non-blocking!
                response = await self._client.chat.completions.create(
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
                    if self.key_pool:
                        self.key_pool.mark_invalid(self._current_api_key)
                        if self._rotate_key():
                            continue
                    raise ValueError(f"Invalid API key: {e}")
                
                elif is_quota_exhausted_error(e):
                    if self.key_pool:
                        self.key_pool.mark_quota_exhausted(self._current_api_key)
                        if self._rotate_key():
                            continue
                    raise e
                
                elif is_rate_limit_error(e):
                    if self.key_pool:
                        self.key_pool.mark_rate_limited(self._current_api_key)
                        if self._rotate_key():
                            continue
                    
                    # No pool or no available keys - do exponential backoff
                    if api_retry_count >= max_api_retries:
                        raise e
                    wait_time = min(2 ** api_retry_count, 30)
                    # ✨ ASYNC SLEEP - Non-blocking!
                    await asyncio.sleep(wait_time)
                
                else:
                    # Unknown error - standard retry with backoff
                    if api_retry_count >= max_api_retries:
                        raise e
                    wait_time = 2 ** api_retry_count
                    # ✨ ASYNC SLEEP - Non-blocking!
                    await asyncio.sleep(wait_time)
        
        if api_retry_count >= max_api_retries and last_exception:
            raise last_exception

        message = response.choices[0].message

        # Extract tool calls
        tool_calls = getattr(message, "tool_calls", None)
        function_call = None
        if tool_calls and len(tool_calls) > 0:
            function_call = tool_calls[0].function

        # Serialize tool calls for storage
        serializable_tool_calls = None
        if tool_calls:
            serializable_tool_calls = []
            for tc in tool_calls:
                if hasattr(tc, "model_dump"):
                    serializable_tool_calls.append(tc.model_dump())
                else:
                    serializable_tool_calls.append({
                        "id": getattr(tc, "id", None),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

        # Add assistant response to history
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
        """Convert tools to OpenAI API format (same as sync version)."""
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
                    "description": "Replaces exactly one occurrence of `target_content` with `replacement_content` in the file.",
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
        """Clears the conversation history stored in this client instance."""
        self.conversation_history = []

    def get_conversation_history(self) -> List[Dict]:
        """Returns the current conversation history."""
        return self.conversation_history

    def set_conversation_history(self, history: List[Dict]):
        """Overrides the current conversation history."""
        self.conversation_history = history

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """
        Estimates token count for a list of messages.
        Uses conservative estimate: 1 character ≈ 0.25 tokens (4 chars per token).
        """
        return sum(len(json.dumps(msg)) for msg in messages) // 4

    def _trim_to_budget(self):
        """
        Removes oldest messages to stay within max_context_tokens budget.
        Always keeps system messages and at least 10 recent messages.
        """
        if not self.conversation_history:
            return
        
        estimated_tokens = self._estimate_tokens(self.conversation_history)
        
        while estimated_tokens > self.max_context_tokens and len(self.conversation_history) > 10:
            removed = False
            for i, msg in enumerate(self.conversation_history):
                if msg.get("role") != "system":
                    self.conversation_history.pop(i)
                    removed = True
                    break
            
            if not removed:
                break
            
            estimated_tokens = self._estimate_tokens(self.conversation_history)
