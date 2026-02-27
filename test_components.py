"""
Test script to verify Ada components work without actually calling OpenAI API.
This tests the structure and imports.
"""

import sys
from agents.coding_agent import CodingAgent
from agents.validation_agent import ValidationAgent
from tools.tools import Tools

def test_imports():
    """Test all imports work correctly."""
    print("✓ All imports successful")

def test_tools():
    """Test Tools can be instantiated and used."""
    tools = Tools()
    
    # Test list_files
    files = tools.list_files("repo_snapshot")
    print(f"✓ Tools work - Found {len(files)} files in repo_snapshot")
    
    # Test read_file
    content = tools.read_file("repo_snapshot/README.md")
    print(f"✓ Can read files - README.md is {len(content)} characters")

def test_validation_agent():
    """Test ValidationAgent."""
    validator = ValidationAgent()
    result = validator.validate("repo_snapshot")
    print(f"✓ Validation agent works - Result: {result}")

def main():
    print("=" * 60)
    print("Testing Ada Components (without API calls)")
    print("=" * 60)
    
    try:
        test_imports()
        test_tools()
        test_validation_agent()
        
        print("\n" + "=" * 60)
        print("✅ All basic tests passed!")
        print("=" * 60)
        print("\nTo run Ada with a real task, you need:")
        print("1. Set GROQ_API_KEY or OPENAI_API_KEY environment variable")
        print("2. Run: python run_local.py tasks/example_task.json repo_snapshot")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
