"""
intelligence/symbol_extractor.py

Converts AST parse results into graph nodes.
Each symbol (class, function, method, file) becomes a node with a unique ID.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from intelligence.ast_parser import ParsedFile, ParsedSymbol
from intelligence.repo_scanner import ScannedFile


@dataclass
class GraphNode:
    """A node in the repository knowledge graph."""
    node_id: str
    name: str
    kind: str     # "repository", "directory", "file", "class", "function", "method"
    file: Optional[str] = None    # Relative file path (None for repo/dir nodes)
    line: Optional[int] = None    # 1-based line number
    end_line: Optional[int] = None
    parent: Optional[str] = None  # Enclosing class node_id for methods
    language: Optional[str] = None

    def to_dict(self) -> Dict:
        d = {"node_id": self.node_id, "name": self.name, "kind": self.kind}
        if self.file:
            d["file"] = self.file
        if self.line:
            d["line"] = self.line
        if self.end_line:
            d["end_line"] = self.end_line
        if self.parent:
            d["parent"] = self.parent
        if self.language:
            d["language"] = self.language
        return d

    @staticmethod
    def from_dict(d: Dict) -> "GraphNode":
        return GraphNode(
            node_id=d["node_id"],
            name=d["name"],
            kind=d["kind"],
            file=d.get("file"),
            line=d.get("line"),
            end_line=d.get("end_line"),
            parent=d.get("parent"),
            language=d.get("language"),
        )


class SymbolExtractor:
    """
    Converts ParsedFile results into GraphNode instances.
    
    Generates unique node IDs based on file path + symbol name to ensure
    stable identifiers across incremental rebuilds.
    """

    def extract_file_node(self, scanned_file: ScannedFile) -> GraphNode:
        """Create a file-level graph node."""
        return GraphNode(
            node_id=f"file:{scanned_file.path}",
            name=scanned_file.path.split("/")[-1],
            kind="file",
            file=scanned_file.path,
            language=scanned_file.language,
        )

    def extract_directory_node(self, dir_path: str) -> GraphNode:
        """Create a directory-level graph node."""
        name = dir_path.rstrip("/").split("/")[-1] if "/" in dir_path else dir_path
        return GraphNode(
            node_id=f"dir:{dir_path}",
            name=name,
            kind="directory",
            file=dir_path,
        )

    def extract_symbols(self, parsed_file: ParsedFile) -> List[GraphNode]:
        """
        Extract all symbols from a parsed file as graph nodes.

        Args:
            parsed_file: The parse result from ASTParser.

        Returns:
            List of GraphNode for each class, function, and method.
        """
        nodes: List[GraphNode] = []
        file_path = parsed_file.path

        for cls in parsed_file.classes:
            node_id = f"class:{file_path}:{cls.name}"
            nodes.append(GraphNode(
                node_id=node_id,
                name=cls.name,
                kind="class",
                file=file_path,
                line=cls.line,
                end_line=cls.end_line or cls.line,
                language=parsed_file.language,
            ))

        for func in parsed_file.functions:
            if func.parent:
                node_id = f"method:{file_path}:{func.parent}.{func.name}"
                parent_node_id = f"class:{file_path}:{func.parent}"
            else:
                node_id = f"function:{file_path}:{func.name}"
                parent_node_id = None

            nodes.append(GraphNode(
                node_id=node_id,
                name=func.name,
                kind=func.kind,
                file=file_path,
                line=func.line,
                end_line=func.end_line or func.line,
                parent=parent_node_id,
                language=parsed_file.language,
            ))

        return nodes

    def extract_all(self, scanned_file: ScannedFile, parsed_file: ParsedFile) -> List[GraphNode]:
        """
        Extract file node + all symbol nodes for a single file.

        Args:
            scanned_file: The scan result.
            parsed_file: The parse result.

        Returns:
            List of GraphNode including the file node and all symbols.
        """
        nodes = [self.extract_file_node(scanned_file)]
        nodes.extend(self.extract_symbols(parsed_file))
        return nodes
