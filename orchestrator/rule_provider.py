import os
from abc import ABC, abstractmethod
from typing import List

class RuleProvider(ABC):
    """Abstract interface for injecting global quality rules into agents."""
    
    @abstractmethod
    def get_rules(self, repo_path: str) -> List[str]:
        """
        Retrieves a list of global rules to be enforced by agents.
        
        Args:
            repo_path (str): The isolated workspace directory.
            
        Returns:
            List[str]: A list of rule definitions as strings.
        """
        pass

class LocalFolderRuleProvider(RuleProvider):
    """
    Reads global rules from markdown or text files within a specific folder 
    in the target repository (e.g., '.rules').
    """
    def __init__(self, folder_name: str = "rules"):
        self.folder_name = folder_name

    def get_rules(self, repo_path: str) -> List[str]:
        rules_path = os.path.join(repo_path, self.folder_name)
        rules = []
        
        if not os.path.exists(rules_path) or not os.path.isdir(rules_path):
            return rules
            
        for filename in os.listdir(rules_path):
            if filename.endswith(".md") or filename.endswith(".txt"):
                file_path = os.path.join(rules_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            rules.append(f"Rule from {filename}:\n{content}")
                except Exception as e:
                    print(f"Warning: Failed to read rule file {filename}: {e}")
                    
        return rules
