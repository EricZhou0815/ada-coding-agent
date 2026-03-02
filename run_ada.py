#!/usr/bin/env python3
"""
Unified runner for Ada with pluggable isolation backends.
Usage: python run_ada.py <input_file> <repo_path> [--backend sandbox|docker]

Examples:
    python run_ada.py stories/example_story.json repo_snapshot --backend sandbox
    python run_ada.py stories/example_story.json repo_snapshot --backend docker
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
                    key_val = line.split('=', 1)
                    if len(key_val) == 2:
                        key, val = key_val
                        if key not in os.environ:
                            os.environ[key] = val.strip(' "\'')

    parser = argparse.ArgumentParser(
        description='Ada - Autonomous AI Software Engineer (Direct Story mode)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument('input_file', help='Path to User Story JSON file')
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
        help='Use mock LLM instead of configured provider'
    )
    parser.add_argument(
        '--keep-workspace',
        action='store_true',
        help='Keep sandbox workspace after execution (for debugging)'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found: {args.input_file}")
        sys.exit(1)
    
    if not os.path.exists(args.repo_path):
        print(f"Error: Repo path not found: {args.repo_path}")
        sys.exit(1)
    
    llm_provider = Config.get_llm_provider()
    if not args.mock and llm_provider == "mock" and args.backend == 'sandbox':
        args.mock = True
    
    # Load Story
    with open(args.input_file) as f:
        story = json.load(f)
    
    print("=" * 70)
    print("Ada - Autonomous AI Software Engineer [DIRECT MODE]")
    print("=" * 70)
    print(f"Backend:     {args.backend.upper()}")
    display_provider = "Mock (Demo)" if args.mock else Config.get_llm_provider().capitalize()
    print(f"LLM Mode:    {display_provider}")
    print(f"Story:       {story.get('title', 'Untitled')}")
    print(f"Repo Path:   {args.repo_path}")
    print("=" * 70)
    print()
    
    if args.backend == 'docker':
        backend = DockerBackend()
    else:
        backend = SandboxBackend()
    
    original_keys = {}
    if args.mock and args.backend == 'sandbox':
        for key in ('GROQ_API_KEY', 'OPENAI_API_KEY'):
            original_keys[key] = os.environ.pop(key, None)
    
    try:
        print(f"Setting up {backend.get_name()} environment...")
        backend.setup(story, args.repo_path)
        
        print(f"Executing story in {backend.get_name()}...")
        print("-" * 70)
        
        success = backend.execute(story, args.repo_path)
        
        print("-" * 70)
        
        if success:
            print("✅ Story completed successfully!")
            print(f"\nCheck {args.repo_path}/ for Ada's changes")
        else:
            print("❌ Story execution failed")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        for key, val in original_keys.items():
            if val:
                os.environ[key] = val
        
        if not args.keep_workspace:
            print(f"\nCleaning up {backend.get_name()} environment...")
            backend.cleanup()


if __name__ == "__main__":
    main()
