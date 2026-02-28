import os
import pytest
from orchestrator.rule_provider import LocalFolderRuleProvider

@pytest.fixture
def temp_rule_dir(tmp_path):
    # tmp_path is a pytest fixture that provides a temporary directory unique to the test invocation
    rules_dir = tmp_path / ".rules"
    rules_dir.mkdir()
    
    # Create some dummy rule files
    (rules_dir / "rule1.md").write_text("All python files must have docstrings.")
    (rules_dir / "rule2.txt").write_text("Do not use print statements. Use logging.")
    # This should be ignored:
    (rules_dir / "ignored.json").write_text('{"foo": "bar"}')
    
    return tmp_path

def test_local_folder_rule_provider(temp_rule_dir):
    provider = LocalFolderRuleProvider()
    rules = provider.get_rules(str(temp_rule_dir))
    
    assert len(rules) == 2
    
    # The order depends on os.listdir, so we check for contents
    combined_rules = "\n".join(rules)
    assert "rule1.md" in combined_rules
    assert "All python files must have docstrings." in combined_rules
    assert "rule2.txt" in combined_rules
    assert "Do not use print statements." in combined_rules
    
    # Ignored files shouldn't be loaded
    assert "ignored.json" not in combined_rules
    assert "foo" not in combined_rules

def test_local_folder_rule_provider_missing_dir(tmp_path):
    provider = LocalFolderRuleProvider()
    # tmp_path does not have .rules
    rules = provider.get_rules(str(tmp_path))
    assert len(rules) == 0
