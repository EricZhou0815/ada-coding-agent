"""
Mock LLM client for testing Ada without OpenAI API.
Simulates Ada's reasoning and tool usage for the JWT authentication task.
"""

import json
from typing import Any, Dict


class MockLLMClient:
    """
    Mock LLM client that simulates Ada's behavior for testing.
    """

    def __init__(self):
        self.conversation_history = []
        self.step = 0
        
    def generate(self, prompt: str, tools: Any = None) -> Dict:
        """
        Simulates an LLM generation step based on predefined internal steps.

        Args:
            prompt (str): The prompt sent by the agent.
            tools (Any, optional): The tools provided to the simulated LLM. Defaults to None.

        Returns:
            Dict: Simulation response matching the structure of OpenAI's response dict 
                  (contains `content`, `function_call`, and `finish_reason`).
        """
        self.conversation_history.append({"role": "user", "content": prompt})
        self.step += 1
        
        # Simulate Ada's step-by-step reasoning for JWT task
        if self.step == 1:
            # First step: Explore the repository
            return {
                "content": "I'll start by exploring the repository to understand the current structure.",
                "function_call": self._create_function_call("list_files", {"directory": "repo_snapshot"}),
                "finish_reason": "function_call"
            }
        
        elif self.step == 2:
            # Read the main app file
            return {
                "content": "Let me read the main Flask application file.",
                "function_call": self._create_function_call("read_file", {"path": "repo_snapshot/app.py"}),
                "finish_reason": "function_call"
            }
        
        elif self.step == 3:
            # Read the auth file
            return {
                "content": "Now I'll check the authentication module.",
                "function_call": self._create_function_call("read_file", {"path": "repo_snapshot/auth.py"}),
                "finish_reason": "function_call"
            }
        
        elif self.step == 4:
            # Update auth.py to add JWT token generation
            new_auth_content = '''"""
Authentication utilities for the Flask app.
"""
import jwt
import datetime
from typing import Optional

# Simple mock user database
USERS = {
    "admin": "password123",
    "user": "userpass"
}

# Secret key for JWT - in production, use environment variable
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"

def authenticate_user(username: str, password: str) -> bool:
    """
    Authenticate a user with username and password.
    
    Args:
        username: User's username
        password: User's password
    
    Returns:
        True if credentials are valid, False otherwise
    """
    return USERS.get(username) == password

def generate_jwt_token(username: str) -> str:
    """
    Generate a JWT token for an authenticated user.
    
    Args:
        username: Username to encode in token
    
    Returns:
        JWT token string
    """
    payload = {
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        "iat": datetime.datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def verify_jwt_token(token: str) -> Optional[str]:
    """
    Verify a JWT token and return the username if valid.
    
    Args:
        token: JWT token string
    
    Returns:
        Username if token is valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("username")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
'''
            return {
                "content": "I'll update auth.py to add JWT token generation and verification functions.",
                "function_call": self._create_function_call("write_file", {
                    "path": "repo_snapshot/auth.py",
                    "content": new_auth_content
                }),
                "finish_reason": "function_call"
            }
        
        elif self.step == 5:
            # Update app.py to use JWT
            new_app_content = '''from flask import Flask, request, jsonify
from auth import authenticate_user, generate_jwt_token, verify_jwt_token

app = Flask(__name__)

@app.route('/login', methods=['POST'])
def login():
    """Login endpoint with JWT token generation"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if authenticate_user(username, password):
        # Generate JWT token for authenticated user
        token = generate_jwt_token(username)
        return jsonify({
            "message": "Login successful",
            "token": token
        }), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/protected', methods=['GET'])
def protected_route():
    """Protected route with JWT verification"""
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing or invalid token"}), 401
    
    token = auth_header.split(' ')[1]
    username = verify_jwt_token(token)
    
    if username:
        return jsonify({
            "message": "This is a protected route",
            "user": username
        }), 200
    else:
        return jsonify({"error": "Invalid or expired token"}), 401

if __name__ == '__main__':
    app.run(debug=True, port=5000)
'''
            return {
                "content": "Now I'll update the Flask app to use JWT tokens in the login and protected routes.",
                "function_call": self._create_function_call("write_file", {
                    "path": "repo_snapshot/app.py",
                    "content": new_app_content
                }),
                "finish_reason": "function_call"
            }
        
        else:
            # Task complete
            return {
                "content": """I have successfully implemented JWT authentication for the Flask application!

Here's what I did:
1. Added JWT token generation to auth.py with generate_jwt_token() function
2. Added JWT token verification to auth.py with verify_jwt_token() function
3. Updated the /login endpoint to return a JWT token on successful authentication
4. Updated the /protected endpoint to verify JWT tokens from the Authorization header

The implementation meets both acceptance criteria:
✓ Valid tokens allow access to protected routes
✓ Requests without tokens return 401

FINISH - Task completed successfully!""",
                "function_call": None,
                "finish_reason": "stop"
            }
    
    def _create_function_call(self, name: str, arguments: dict):
        """
        Creates a mock function call object mimicking the OpenAI SDK structure.

        Args:
            name (str): The name of the function to call.
            arguments (dict): The arguments to pass to the function.

        Returns:
            FunctionCall: An object with `name` and serialized `arguments`.
        """
        class FunctionCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = json.dumps(arguments)
        
        return FunctionCall(name, arguments)
    
    def reset_conversation(self):
        """
        Clears the current conversation history and resets the mock's step counter.
        """
        self.conversation_history = []
        self.step = 0
