"""
intelligence/repo_graph_builder.py

Orchestrates the full scan → parse → extract → analyze pipeline.
Builds, stores, loads, and incrementally updates the repository knowledge graph.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from intelligence.ast_parser import ASTParser, ParsedFile
from intelligence.dependency_analyzer import DependencyAnalyzer, GraphEdge
from intelligence.repo_scanner import RepoScanner, ScanResult, ScannedFile
from intelligence.symbol_extractor import GraphNode, SymbolExtractor
from utils.logger import logger


@dataclass
class RepoGraph:
    """
    The complete repository knowledge graph.
    
    Contains nodes (files, classes, functions) and edges (imports, contains, tests).
    Supports serialization to/from JSON for persistence.
    """
    repo_path: str
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    file_hashes: Dict[str, str] = field(default_factory=dict)  # path → SHA256
    built_at: float = 0.0

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def files(self) -> List[GraphNode]:
        """Return all file nodes."""
        return [n for n in self.nodes.values() if n.kind == "file"]

    def classes(self) -> List[GraphNode]:
        """Return all class nodes."""
        return [n for n in self.nodes.values() if n.kind == "class"]

    def functions(self) -> List[GraphNode]:
        """Return all function/method nodes."""
        return [n for n in self.nodes.values() if n.kind in ("function", "method")]

    def neighbors(self, node_id: str, edge_kinds: Optional[Set[str]] = None) -> List[GraphNode]:
        """Get nodes connected to the given node via outgoing edges."""
        result = []
        for edge in self.edges:
            if edge.source == node_id:
                if edge_kinds is None or edge.kind in edge_kinds:
                    target = self.nodes.get(edge.target)
                    if target:
                        result.append(target)
        return result

    def reverse_neighbors(self, node_id: str, edge_kinds: Optional[Set[str]] = None) -> List[GraphNode]:
        """Get nodes with edges pointing to the given node."""
        result = []
        for edge in self.edges:
            if edge.target == node_id:
                if edge_kinds is None or edge.kind in edge_kinds:
                    source = self.nodes.get(edge.source)
                    if source:
                        result.append(source)
        return result

    def to_dict(self) -> Dict:
        return {
            "repo_path": self.repo_path,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "file_hashes": self.file_hashes,
            "built_at": self.built_at,
        }

    @staticmethod
    def from_dict(d: Dict) -> "RepoGraph":
        return RepoGraph(
            repo_path=d.get("repo_path", ""),
            nodes={nid: GraphNode.from_dict(nd) for nid, nd in d.get("nodes", {}).items()},
            edges=[GraphEdge.from_dict(ed) for ed in d.get("edges", [])],
            file_hashes=d.get("file_hashes", {}),
            built_at=d.get("built_at", 0.0),
        )

    def summary(self) -> str:
        """Generate a human-readable summary of the graph."""
        by_kind: Dict[str, int] = {}
        for n in self.nodes.values():
            by_kind[n.kind] = by_kind.get(n.kind, 0) + 1

        edge_kinds: Dict[str, int] = {}
        for e in self.edges:
            edge_kinds[e.kind] = edge_kinds.get(e.kind, 0) + 1

        parts = [f"Repository Graph: {self.repo_path}"]
        parts.append(f"Nodes: {self.node_count} ({', '.join(f'{k}={v}' for k, v in sorted(by_kind.items()))})")
        parts.append(f"Edges: {self.edge_count} ({', '.join(f'{k}={v}' for k, v in sorted(edge_kinds.items()))})")
        return "\n".join(parts)


class RepoGraphBuilder:
    """
    Orchestrates the full graph-building pipeline:
      1. Scan repository for source files
      2. Parse each file with ASTParser
      3. Extract symbols into GraphNodes
      4. Analyze dependencies into GraphEdges
      5. Store graph as JSON
    
    Supports incremental updates by tracking per-file SHA-256 hashes.
    """

    def __init__(
        self,
        scanner: Optional[RepoScanner] = None,
        parser: Optional[ASTParser] = None,
        extractor: Optional[SymbolExtractor] = None,
        analyzer: Optional[DependencyAnalyzer] = None,
    ):
        self.scanner = scanner or RepoScanner()
        self.parser = parser or ASTParser()
        self.extractor = extractor or SymbolExtractor()
        self.analyzer = analyzer or DependencyAnalyzer()

    def build(self, repo_path: str) -> RepoGraph:
        """
        Build a complete repository graph from scratch.

        Args:
            repo_path: Absolute path to the repository.

        Returns:
            Fully populated RepoGraph.
        """
        logger.info("RepoGraphBuilder", f"Building graph for: {repo_path}")
        start = time.time()

        # Step 1: Scan
        scan_result = self.scanner.scan(repo_path)

        # Step 2-3: Parse + Extract
        all_nodes: Dict[str, GraphNode] = {}
        parsed_files: Dict[str, ParsedFile] = {}
        file_hashes: Dict[str, str] = {}

        for scanned_file in scan_result.files:
            # Hash the file for incremental tracking
            file_hash = self._hash_file(scanned_file.abs_path)
            file_hashes[scanned_file.path] = file_hash

            # Parse
            parsed = self.parser.parse_file(scanned_file.abs_path, scanned_file.language)
            parsed.path = scanned_file.path  # Normalize to relative path
            parsed_files[scanned_file.path] = parsed

            # Extract nodes
            nodes = self.extractor.extract_all(scanned_file, parsed)
            for node in nodes:
                all_nodes[node.node_id] = node

        # Add directory nodes
        dir_nodes = self._collect_directory_nodes(scan_result)
        for node in dir_nodes:
            all_nodes[node.node_id] = node

        # Step 4: Analyze dependencies
        edges = self.analyzer.analyze(parsed_files, all_nodes)

        # Add directory containment edges
        dir_edges = self._directory_edges(all_nodes)
        edges.extend(dir_edges)

        graph = RepoGraph(
            repo_path=repo_path,
            nodes=all_nodes,
            edges=edges,
            file_hashes=file_hashes,
            built_at=time.time(),
        )

        elapsed = time.time() - start
        logger.info("RepoGraphBuilder", f"Graph built in {elapsed:.2f}s: {graph.summary()}")
        return graph

    def incremental_update(self, repo_path: str, existing_graph: RepoGraph) -> RepoGraph:
        """
        Incrementally update a graph by only re-parsing changed files.

        Args:
            repo_path: Path to the repository.
            existing_graph: Previously built graph.

        Returns:
            Updated RepoGraph.
        """
        logger.info("RepoGraphBuilder", "Running incremental graph update...")
        start = time.time()

        scan_result = self.scanner.scan(repo_path)

        # Find changed and new files
        current_paths = {f.path for f in scan_result.files}
        old_paths = set(existing_graph.file_hashes.keys())

        added = current_paths - old_paths
        removed = old_paths - current_paths
        possibly_changed = current_paths & old_paths

        changed: Set[str] = set()
        for f in scan_result.files:
            if f.path in possibly_changed:
                new_hash = self._hash_file(f.abs_path)
                if new_hash != existing_graph.file_hashes.get(f.path):
                    changed.add(f.path)

        files_to_reparse = added | changed

        if not files_to_reparse and not removed:
            logger.info("RepoGraphBuilder", "No changes detected, graph is up to date.")
            return existing_graph

        logger.info(
            "RepoGraphBuilder",
            f"Incremental update: {len(added)} added, {len(changed)} changed, {len(removed)} removed"
        )

        # Remove old nodes/edges for changed and removed files
        stale_files = removed | changed
        stale_node_ids: Set[str] = set()
        for node_id, node in existing_graph.nodes.items():
            if node.file and node.file in stale_files:
                stale_node_ids.add(node_id)

        # Start with existing data minus stale entries
        new_nodes = {nid: n for nid, n in existing_graph.nodes.items() if nid not in stale_node_ids}
        new_edges = [
            e for e in existing_graph.edges
            if e.source not in stale_node_ids and e.target not in stale_node_ids
        ]
        new_hashes = {p: h for p, h in existing_graph.file_hashes.items() if p not in stale_files}

        # Parse new/changed files
        files_by_path = {f.path: f for f in scan_result.files}
        parsed_files_new: Dict[str, ParsedFile] = {}

        for path in files_to_reparse:
            scanned_file = files_by_path.get(path)
            if not scanned_file:
                continue

            new_hashes[path] = self._hash_file(scanned_file.abs_path)
            parsed = self.parser.parse_file(scanned_file.abs_path, scanned_file.language)
            parsed.path = path
            parsed_files_new[path] = parsed

            nodes = self.extractor.extract_all(scanned_file, parsed)
            for node in nodes:
                new_nodes[node.node_id] = node

        # Re-analyze dependencies for new/changed files
        # We need to re-run on all parsed files to get correct cross-file edges
        all_parsed = {}
        for path in current_paths:
            if path in parsed_files_new:
                all_parsed[path] = parsed_files_new[path]
            # For unchanged files, we'd need their parse data — re-parse them too
            # This is a trade-off: full re-analysis for correct edges vs speed
        
        # For correctness, re-analyze all edges
        if parsed_files_new:
            # Re-parse unchanged files for dependency analysis
            for path in (current_paths - files_to_reparse):
                sf = files_by_path.get(path)
                if sf:
                    parsed = self.parser.parse_file(sf.abs_path, sf.language)
                    parsed.path = path
                    all_parsed[path] = parsed

            all_edges = self.analyzer.analyze(all_parsed, new_nodes)
            dir_edges = self._directory_edges(new_nodes)
            all_edges.extend(dir_edges)
        else:
            all_edges = new_edges

        graph = RepoGraph(
            repo_path=repo_path,
            nodes=new_nodes,
            edges=all_edges,
            file_hashes=new_hashes,
            built_at=time.time(),
        )

        elapsed = time.time() - start
        logger.info("RepoGraphBuilder", f"Incremental update in {elapsed:.2f}s: {graph.summary()}")
        return graph

    def save(self, graph: RepoGraph, output_path: str) -> None:
        """Save graph to a JSON file."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(graph.to_dict(), f, indent=2)
        logger.info("RepoGraphBuilder", f"Graph saved to {output_path}")

    def load(self, input_path: str) -> Optional[RepoGraph]:
        """Load graph from a JSON file."""
        if not os.path.exists(input_path):
            return None
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            graph = RepoGraph.from_dict(data)
            logger.info("RepoGraphBuilder", f"Graph loaded from {input_path}: {graph.summary()}")
            return graph
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("RepoGraphBuilder", f"Failed to load graph from {input_path}: {e}")
            return None

    def _hash_file(self, abs_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        try:
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def _collect_directory_nodes(self, scan_result: ScanResult) -> List[GraphNode]:
        """Create directory nodes for all directories containing source files."""
        dirs: Set[str] = set()
        for f in scan_result.files:
            parts = f.path.split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))

        return [self.extractor.extract_directory_node(d) for d in sorted(dirs)]

    def _directory_edges(self, nodes: Dict[str, GraphNode]) -> List[GraphEdge]:
        """Create directory → file and directory → directory containment edges."""
        edges = []
        dir_ids = {n.file: n.node_id for n in nodes.values() if n.kind == "directory" and n.file}

        for node in nodes.values():
            if node.kind == "file" and node.file:
                parent_dir = "/".join(node.file.split("/")[:-1])
                if parent_dir in dir_ids:
                    edges.append(GraphEdge(
                        source=dir_ids[parent_dir],
                        target=node.node_id,
                        kind="contains",
                    ))

            elif node.kind == "directory" and node.file:
                parts = node.file.split("/")
                if len(parts) > 1:
                    parent_dir = "/".join(parts[:-1])
                    if parent_dir in dir_ids:
                        edges.append(GraphEdge(
                            source=dir_ids[parent_dir],
                            target=node.node_id,
                            kind="contains",
                        ))

        return edges
