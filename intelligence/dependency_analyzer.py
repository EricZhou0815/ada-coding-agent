"""
intelligence/dependency_analyzer.py

Extracts relationships (edges) between graph nodes from parsed imports,
class hierarchy, and call patterns.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from intelligence.ast_parser import ParsedFile, ParsedImport
from intelligence.symbol_extractor import GraphNode


@dataclass
class GraphEdge:
    """An edge in the repository knowledge graph."""
    source: str   # Source node_id
    target: str   # Target node_id
    kind: str     # "imports", "calls", "extends", "contains", "depends_on", "tests"

    def to_dict(self) -> Dict:
        return {"source": self.source, "target": self.target, "kind": self.kind}

    @staticmethod
    def from_dict(d: Dict) -> "GraphEdge":
        return GraphEdge(source=d["source"], target=d["target"], kind=d["kind"])


class DependencyAnalyzer:
    """
    Analyzes parsed files to extract edges between graph nodes.
    
    Handles:
      - File-to-file imports
      - Symbol containment (class contains method, file contains class)
      - Class extends/implements
      - Test file detection
    """

    def analyze(
        self,
        parsed_files: Dict[str, ParsedFile],
        nodes: Dict[str, GraphNode],
    ) -> List[GraphEdge]:
        """
        Analyze all parsed files and extract edges.

        Args:
            parsed_files: Dict of file_path → ParsedFile.
            nodes: Dict of node_id → GraphNode (all known nodes).

        Returns:
            List of GraphEdge representing all discovered relationships.
        """
        edges: List[GraphEdge] = []

        # Build lookup indices
        file_node_index = self._build_file_index(nodes)
        symbol_index = self._build_symbol_index(nodes)

        for file_path, parsed in parsed_files.items():
            file_node_id = f"file:{file_path}"

            # Containment edges: file → class, file → function
            edges.extend(self._containment_edges(file_node_id, parsed, nodes))

            # Import edges: file → imported file (or symbol)
            edges.extend(self._import_edges(
                file_path, file_node_id, parsed, file_node_index, symbol_index, nodes
            ))

            # Method containment: class → method
            edges.extend(self._method_containment_edges(parsed, file_path, nodes))

            # Test relationship edges
            edges.extend(self._test_edges(file_path, file_node_id, parsed, file_node_index))

        return edges

    def _build_file_index(self, nodes: Dict[str, GraphNode]) -> Dict[str, str]:
        """Build a mapping of file basename → file node_id for import resolution."""
        index: Dict[str, str] = {}
        for node_id, node in nodes.items():
            if node.kind == "file" and node.file:
                # Index by full path
                index[node.file] = node_id
                # Index by basename without extension
                basename = os.path.splitext(node.file.split("/")[-1])[0]
                index[basename] = node_id
                # Index by module-style path (dots instead of slashes, no extension)
                module_path = node.file.replace("/", ".").replace("\\", ".")
                if module_path.endswith(".py"):
                    module_path = module_path[:-3]
                index[module_path] = node_id
        return index

    def _build_symbol_index(self, nodes: Dict[str, GraphNode]) -> Dict[str, List[str]]:
        """Build a mapping of symbol name → list of node_ids."""
        index: Dict[str, List[str]] = {}
        for node_id, node in nodes.items():
            if node.kind in ("class", "function", "method"):
                index.setdefault(node.name, []).append(node_id)
        return index

    def _containment_edges(
        self, file_node_id: str, parsed: ParsedFile, nodes: Dict[str, GraphNode]
    ) -> List[GraphEdge]:
        """Generate containment edges: file contains classes and top-level functions."""
        edges = []
        file_path = parsed.path

        for cls in parsed.classes:
            cls_node_id = f"class:{file_path}:{cls.name}"
            if cls_node_id in nodes:
                edges.append(GraphEdge(source=file_node_id, target=cls_node_id, kind="contains"))

        for func in parsed.functions:
            if not func.parent:  # Top-level functions only
                func_node_id = f"function:{file_path}:{func.name}"
                if func_node_id in nodes:
                    edges.append(GraphEdge(source=file_node_id, target=func_node_id, kind="contains"))

        return edges

    def _method_containment_edges(
        self, parsed: ParsedFile, file_path: str, nodes: Dict[str, GraphNode]
    ) -> List[GraphEdge]:
        """Generate containment edges: class contains methods."""
        edges = []
        for func in parsed.functions:
            if func.parent:
                cls_node_id = f"class:{file_path}:{func.parent}"
                method_node_id = f"method:{file_path}:{func.parent}.{func.name}"
                if cls_node_id in nodes and method_node_id in nodes:
                    edges.append(GraphEdge(source=cls_node_id, target=method_node_id, kind="contains"))
        return edges

    def _import_edges(
        self,
        file_path: str,
        file_node_id: str,
        parsed: ParsedFile,
        file_index: Dict[str, str],
        symbol_index: Dict[str, List[str]],
        nodes: Dict[str, GraphNode],
    ) -> List[GraphEdge]:
        """Generate import edges from import statements."""
        edges = []

        for imp in parsed.imports:
            # Try to resolve the import to a known file
            target_file_id = self._resolve_import(imp.module, file_path, file_index)

            if target_file_id:
                edges.append(GraphEdge(source=file_node_id, target=target_file_id, kind="imports"))

                # If specific names are imported, link to those symbols too
                for name in imp.names:
                    name = name.strip()
                    if name in symbol_index:
                        for sym_node_id in symbol_index[name]:
                            sym_node = nodes.get(sym_node_id)
                            if sym_node and sym_node.file and f"file:{sym_node.file}" == target_file_id:
                                edges.append(GraphEdge(
                                    source=file_node_id, target=sym_node_id, kind="imports"
                                ))

        return edges

    def _resolve_import(
        self, module: str, source_file: str, file_index: Dict[str, str]
    ) -> Optional[str]:
        """Resolve an import module string to a file node_id."""
        # Direct match
        if module in file_index:
            return file_index[module]

        # Try the last segment (e.g., "utils.logger" → "logger")
        parts = module.split(".")
        if len(parts) > 1:
            last = parts[-1]
            if last in file_index:
                return file_index[last]

        # Try joining with slash for path-style resolution
        path_style = "/".join(parts)
        for ext in [".py", ".js", ".ts", ".go", ".java"]:
            candidate = path_style + ext
            if candidate in file_index:
                return file_index[candidate]

        return None

    def _test_edges(
        self,
        file_path: str,
        file_node_id: str,
        parsed: ParsedFile,
        file_index: Dict[str, str],
    ) -> List[GraphEdge]:
        """Detect test files and link them to tested modules."""
        edges = []
        filename = file_path.split("/")[-1]

        # Check if this is a test file
        is_test = (
            filename.startswith("test_")
            or filename.endswith("_test.py")
            or filename.endswith(".test.js")
            or filename.endswith(".test.ts")
            or filename.endswith("_test.go")
            or "/tests/" in file_path
            or "/test/" in file_path
            or "/__tests__/" in file_path
        )

        if not is_test:
            return edges

        # Try to guess what this test file tests
        # test_user_service.py → user_service
        # user_service.test.ts → user_service
        base = filename
        for prefix in ["test_"]:
            if base.startswith(prefix):
                base = base[len(prefix):]
        for suffix in [".test.js", ".test.ts", "_test.py", "_test.go"]:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        # Remove remaining extension
        base = os.path.splitext(base)[0]

        if base in file_index:
            target_id = file_index[base]
            edges.append(GraphEdge(source=file_node_id, target=target_id, kind="tests"))

        # Also check imports — test files often import the module they test
        for imp in parsed.imports:
            target_id = self._resolve_import(imp.module, file_path, file_index)
            if target_id and target_id != file_node_id:
                edges.append(GraphEdge(source=file_node_id, target=target_id, kind="tests"))

        return edges
