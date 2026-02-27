#!/usr/bin/env python3
"""
Unified runner for Ada with pluggable isolation backends.
Usage: python run_ada.py <task_file> <repo_path> [--backend sandbox|docker]

Examples:
    python run_ada.py tasks/example_task.json repo_snapshot --backend sandbox
    python run_ada.py tasks/example_task.json repo_snapshot --backend docker
    python run_ada.py tasks/example_task.json repo_snapshot  # defaults to sandbox
"""

import sys
import os
import json
import argparse
from pathlib import Path

from isolation import SandboxBackend, DockerBackend
from config import Config


def main():
    # Automatically load .env file if it exists
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    if key not in os.environ:
                        os.environ[key] = val.strip(' "\'')

    parser = argparse.ArgumentParser(
        description='Ada - Autonomous AI Software Engineer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with sandbox isolation (default, no Docker needed)
  python run_ada.py tasks/example_task.json repo_snapshot
  
  # Run with Docker isolation
  python run_ada.py tasks/example_task.json repo_snapshot --backend docker
  
  # Use mock LLM (no API key needed)
  python run_ada.py tasks/example_task.json repo_snapshot --mock
        """
    )
    
    parser.add_argument('task_file', help='Path to task JSON file')
    parser.add_argument('repo_path', help='Path to repository snapshot')
    parser.add_argument(
        '--backend',
        choices=['sandbox', 'docker'],
        default='sandbox',
        help='Isolation backend to use (default: sandbox)'
    )
    parser.add_argument(
        '--mock',
        action='store_true',
        help='Use mock LLM instead of OpenAI (no API key needed)'
    )
    parser.add_argument(
        '--keep-workspace',
        action='store_true',
        help='Keep sandbox workspace after execution (for debugging)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.task_file):
        print(f"Error: Task file not found: {args.task_file}")
        sys.exit(1)
    
    if not os.path.exists(args.repo_path):
        print(f"Error: Repo path not found: {args.repo_path}")
        sys.exit(1)
    
    # Check API key if not using mock
    llm_provider = Config.get_llm_provider()
    if not args.mock and llm_provider == "mock" and args.backend == 'sandbox':
        print("Warning: No API key found. Falling back to mock LLM.")
        print("Set GROQ_API_KEY (recommended) or OPENAI_API_KEY, e.g.:")
        print("  export GROQ_API_KEY='your-groq-key-here'")
        args.mock = True
    
    # Load task
    with open(args.task_file) as f:
        task = json.load(f)
    
    # Print header
    print("=" * 70)
    print("Ada - Autonomous AI Software Engineer")
    print("=" * 70)
    print(f"Backend:     {args.backend.upper()}")
    display_provider = "Mock (Demo)" if args.mock else Config.get_llm_provider().capitalize()
    print(f"LLM Mode:    {display_provider}")
    print(f"Task:        {task['title']}")
    print(f"Description: {task['description']}")
    print(f"Repo Path:   {args.repo_path}")
    print("=" * 70)
    print()
    
    # Initialize backend
    if args.backend == 'docker':
        backend = DockerBackend()
    else:  # sandbox
        backend = SandboxBackend()
    
    # If using mock mode with sandbox, temporarily clear API key
    original_keys = {}
    if args.mock and args.backend == 'sandbox':
        for key in ('GROQ_API_KEY', 'OPENAI_API_KEY'):
            original_keys[key] = os.environ.pop(key, None)
    
    try:
        # Setup
        print(f"Setting up {backend.get_name()} environment...")
        backend.setup(task, args.repo_path)
        print()
        
        # Execute
        print(f"Executing task in {backend.get_name()}...")
        print("-" * 70)
        
        completed_tasks = []
        success = backend.execute(task, args.repo_path, completed_tasks)
        
        print("-" * 70)
        print()
        
        # Result
        if success:
            print("✅ Task completed successfully!")
            print(f"\nCheck {args.repo_path}/ for Ada's changes")
        else:
            print("❌ Task execution failed")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # Restore API keys if they were temporarily removed
        for key, val in original_keys.items():
            if val:
                os.environ[key] = val
        
        # Cleanup
        if not args.keep_workspace:
            print(f"\nCleaning up {backend.get_name()} environment...")
            backend.cleanup()
        else:
            print(f"\nWorkspace preserved (--keep-workspace flag)")


if __name__ == "__main__":
    main()
