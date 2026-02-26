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


def main():
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
    if not args.mock and not os.getenv("OPENAI_API_KEY") and args.backend == 'sandbox':
        print("Warning: OPENAI_API_KEY not set. Falling back to mock LLM.")
        print("Set it with: $env:OPENAI_API_KEY='your-api-key-here'")
        args.mock = True
    
    # Load task
    with open(args.task_file) as f:
        task = json.load(f)
    
    # Print header
    print("=" * 70)
    print("Ada - Autonomous AI Software Engineer")
    print("=" * 70)
    print(f"Backend:     {args.backend.upper()}")
    print(f"LLM Mode:    {'Mock (Demo)' if args.mock else 'OpenAI'}")
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
    original_key = None
    if args.mock and args.backend == 'sandbox':
        original_key = os.environ.pop('OPENAI_API_KEY', None)
    
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
        # Restore API key if it was temporarily removed
        if original_key:
            os.environ['OPENAI_API_KEY'] = original_key
        
        # Cleanup
        if not args.keep_workspace:
            print(f"\nCleaning up {backend.get_name()} environment...")
            backend.cleanup()
        else:
            print(f"\nWorkspace preserved (--keep-workspace flag)")


if __name__ == "__main__":
    main()
