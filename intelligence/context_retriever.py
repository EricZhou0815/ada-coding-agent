"""
intelligence/context_retriever.py

Task-aware context retrieval engine.
Given a task description and repository graph, returns the most relevant
files, symbols, and dependencies as structured context.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from intelligence.repo_graph_builder import RepoGraph
from intelligence.symbol_extractor import GraphNode
from utils.logger import logger

# Common English stopwords to ignore in keyword extraction
_STOPWORDS: Set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "and", "or", "but", "if", "then", "else", "when", "while", "for",
    "to", "from", "in", "on", "at", "by", "with", "about", "of",
    "this", "that", "these", "those", "it", "its", "not", "no",
    "all", "each", "every", "any", "some", "new", "add", "create",
    "implement", "update", "make", "use", "using",
}


@dataclass
class RetrievedContext:
    """Structured context returned by the retriever."""
    task_description: str
    relevant_files: List[Dict] = field(default_factory=list)    # [{path, score, symbols}]
    related_symbols: List[Dict] = field(default_factory=list)   # [{name, kind, file, line}]
    dependencies: List[Dict] = field(default_factory=list)      # [{source, target, kind}]
    keywords: List[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Format as text suitable for injection into an LLM prompt."""
        parts = []

        if self.relevant_files:
            parts.append("Relevant files (by relevance):")
            for f in self.relevant_files[:15]:
                symbols = f.get("symbols", [])
                sym_str = f" — symbols: {', '.join(symbols)}" if symbols else ""
                parts.append(f"  - {f['path']} (score: {f['score']:.2f}){sym_str}")

        if self.related_symbols:
            parts.append("\nKey symbols:")
            for s in self.related_symbols[:20]:
                loc = f" ({s['file']}:{s.get('line', '?')})" if s.get("file") else ""
                parts.append(f"  - {s['kind']}: {s['name']}{loc}")

        if self.dependencies:
            parts.append("\nDependency relationships:")
            seen = set()
            for d in self.dependencies[:15]:
                key = f"{d['source']} → {d['target']}"
                if key not in seen:
                    seen.add(key)
                    parts.append(f"  - {d['source']} --[{d['kind']}]--> {d['target']}")

        return "\n".join(parts)

    def to_dict(self) -> Dict:
        return {
            "task_description": self.task_description,
            "relevant_files": self.relevant_files,
            "related_symbols": self.related_symbols,
            "dependencies": self.dependencies,
            "keywords": self.keywords,
        }


class ContextRetriever:
    """
    Retrieves task-specific context from the repository knowledge graph.
    
    Algorithm:
      1. Extract keywords from task description
      2. Match keywords against graph node names
      3. Traverse dependency edges (1-2 hops)
      4. Score nodes by relevance
      5. Return top-k files and symbols
    """

    def __init__(self, top_k: int = 15, max_hops: int = 2):
        """
        Args:
            top_k: Maximum number of files to return.
            max_hops: Maximum edge traversal depth for expanding context.
        """
        self.top_k = top_k
        self.max_hops = max_hops

    def get_context(self, task_description: str, graph: RepoGraph) -> RetrievedContext:
        """
        Retrieve relevant context for a task.

        Args:
            task_description: Description of the task/story.
            graph: The repository knowledge graph.

        Returns:
            RetrievedContext with relevant files, symbols, and dependencies.
        """
        keywords = self._extract_keywords(task_description)
        logger.info("ContextRetriever", f"Extracted keywords: {keywords}")

        # Score all nodes by keyword relevance
        node_scores: Dict[str, float] = {}
        matched_nodes: Set[str] = set()

        for node_id, node in graph.nodes.items():
            score = self._score_node(node, keywords)
            if score > 0:
                node_scores[node_id] = score
                matched_nodes.add(node_id)

        # Expand via graph traversal (1-2 hops)
        expanded = self._expand_context(graph, matched_nodes, node_scores)
        node_scores.update(expanded)

        # Aggregate scores by file
        file_scores = self._aggregate_file_scores(graph, node_scores)

        # Build result
        sorted_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)
        top_files = sorted_files[: self.top_k]

        context = RetrievedContext(
            task_description=task_description,
            keywords=keywords,
        )

        # Populate relevant files with their symbols
        for file_path, score in top_files:
            file_node_id = f"file:{file_path}"
            symbols = self._get_file_symbols(graph, file_node_id)
            context.relevant_files.append({
                "path": file_path,
                "score": round(score, 3),
                "symbols": [s.name for s in symbols],
            })

            for sym in symbols:
                context.related_symbols.append({
                    "name": sym.name,
                    "kind": sym.kind,
                    "file": sym.file,
                    "line": sym.line,
                })

        # Collect dependency edges between relevant files
        relevant_file_ids = {f"file:{f['path']}" for f in context.relevant_files}
        for edge in graph.edges:
            if edge.source in relevant_file_ids or edge.target in relevant_file_ids:
                if edge.kind in ("imports", "tests", "depends_on"):
                    source_name = self._node_display(graph, edge.source)
                    target_name = self._node_display(graph, edge.target)
                    context.dependencies.append({
                        "source": source_name,
                        "target": target_name,
                        "kind": edge.kind,
                    })

        logger.info(
            "ContextRetriever",
            f"Retrieved {len(context.relevant_files)} files, "
            f"{len(context.related_symbols)} symbols for task"
        )
        return context

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from task description."""
        # Split into tokens, keeping camelCase and snake_case parts
        tokens: List[str] = []

        # First split by whitespace and punctuation
        raw_tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)

        for token in raw_tokens:
            lower = token.lower()
            if lower in _STOPWORDS or len(lower) < 3:
                continue

            tokens.append(lower)

            # Split camelCase: "UserService" → ["user", "service"]
            camel_parts = re.findall(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)", token)
            for part in camel_parts:
                p = part.lower()
                if p not in _STOPWORDS and len(p) >= 3 and p != lower:
                    tokens.append(p)

            # Split snake_case: "user_service" → ["user", "service"]
            if "_" in token:
                for part in token.split("_"):
                    p = part.lower()
                    if p not in _STOPWORDS and len(p) >= 3 and p != lower:
                        tokens.append(p)

        # Deduplicate while preserving order
        seen: Set[str] = set()
        result: List[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)

        return result

    def _score_node(self, node: GraphNode, keywords: List[str]) -> float:
        """Score a node based on keyword matching."""
        score = 0.0
        name_lower = node.name.lower()
        file_lower = (node.file or "").lower()

        for kw in keywords:
            # Exact name match
            if name_lower == kw:
                score += 1.0
            # Name contains keyword
            elif kw in name_lower:
                score += 0.6
            # File path contains keyword
            elif kw in file_lower:
                score += 0.3

        # Bonus for kind relevance
        if node.kind == "class":
            score *= 1.2
        elif node.kind == "function":
            score *= 1.1

        return score

    def _expand_context(
        self,
        graph: RepoGraph,
        seed_nodes: Set[str],
        existing_scores: Dict[str, float],
    ) -> Dict[str, float]:
        """Expand context by traversing edges from matched nodes."""
        expanded: Dict[str, float] = {}

        for hop in range(1, self.max_hops + 1):
            decay = 0.5 ** hop  # 0.5 for hop 1, 0.25 for hop 2
            current_frontier = seed_nodes if hop == 1 else set(expanded.keys())

            for node_id in current_frontier:
                base_score = existing_scores.get(node_id, 0) or expanded.get(node_id, 0)
                if base_score <= 0:
                    continue

                # Outgoing edges
                for edge in graph.edges:
                    if edge.source == node_id and edge.target not in existing_scores:
                        hop_score = base_score * decay
                        if edge.target not in expanded or expanded[edge.target] < hop_score:
                            expanded[edge.target] = hop_score

                # Incoming edges (reverse traversal)
                for edge in graph.edges:
                    if edge.target == node_id and edge.source not in existing_scores:
                        hop_score = base_score * decay * 0.8  # Slightly lower for reverse
                        if edge.source not in expanded or expanded[edge.source] < hop_score:
                            expanded[edge.source] = hop_score

        return expanded

    def _aggregate_file_scores(
        self, graph: RepoGraph, node_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """Aggregate node scores by file path."""
        file_scores: Dict[str, float] = {}

        for node_id, score in node_scores.items():
            node = graph.nodes.get(node_id)
            if not node or not node.file:
                continue

            file_path = node.file
            # For directory nodes, skip
            if node.kind == "directory":
                continue

            file_scores[file_path] = file_scores.get(file_path, 0) + score

        # Bonus for files that have multiple matched symbols
        for file_path in list(file_scores.keys()):
            file_node_id = f"file:{file_path}"
            symbols = self._get_file_symbols(graph, file_node_id)
            matched_symbol_count = sum(
                1 for s in symbols if s.node_id in node_scores
            )
            if matched_symbol_count > 1:
                file_scores[file_path] *= 1 + (matched_symbol_count * 0.1)

        return file_scores

    def _get_file_symbols(self, graph: RepoGraph, file_node_id: str) -> List[GraphNode]:
        """Get all symbols contained in a file."""
        return graph.neighbors(file_node_id, edge_kinds={"contains"})

    def _node_display(self, graph: RepoGraph, node_id: str) -> str:
        """Get a human-readable display name for a node."""
        node = graph.nodes.get(node_id)
        if not node:
            return node_id
        if node.kind == "file":
            return node.file or node.name
        return f"{node.name} ({node.kind})"
