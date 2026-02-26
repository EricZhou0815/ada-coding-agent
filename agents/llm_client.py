import os
import json
from openai import OpenAI
from typing import List, Dict, Any


class OpenAIClient:
    """
    OpenAI LLM client wrapper for Ada.
    Supports function calling for tool execution.
    """

    def __init__(self, api_key: str = None, model: str = "gpt-4-turbo-preview"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.conversation_history = []

    def generate(self, prompt: str, tools: Any = None) -> Dict:
        """
        Generate response from LLM with optional tool calling.
        Returns the complete response including tool calls.
        """
        # Add user message to conversation
        self.conversation_history.append({
            "role": "user",
            "content": prompt
        })

        # Convert tools to OpenAI function format if provided
        functions = None
        if tools:
            functions = self._tools_to_functions(tools)

        # Make API call
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.conversation_history,
            functions=functions if functions else None,
            function_call="auto" if functions else None,
            temperature=0.7,
            max_tokens=2000
        )

        message = response.choices[0].message
        
        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": message.content,
            "function_call": message.function_call if hasattr(message, 'function_call') else None
        })

        return {
            "content": message.content,
            "function_call": message.function_call if hasattr(message, 'function_call') else None,
            "finish_reason": response.choices[0].finish_reason
        }

    def _tools_to_functions(self, tools: Any) -> List[Dict]:
        """
        Convert AdaTools to OpenAI function calling format.
        """
        return [
            {
                "name": "read_file",
                "description": "Read the contents of a file at the given path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file at the given path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Content to write to file"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "delete_file",
                "description": "Delete a file at the given path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to delete"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "list_files",
                "description": "List all files in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Directory path to list"}
                    },
                    "required": ["directory"]
                }
            },
            {
                "name": "run_command",
                "description": "Execute a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"}
                    },
                    "required": ["command"]
                }
            }
        ]

    def reset_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []
