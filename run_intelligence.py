#!/usr/bin/env python3
"""
Standalone runner for the Repository Intelligence Layer (Phase 4).

Scans a repository, builds the knowledge graph, and queries context for a task.
No LLM or API keys required — runs entirely locally.

Usage:
    python run_intelligence.py <repo_path> [--query "task description"] [--save graph.json]

Examples:
    # Scan a repo and print the graph summary
    python run_intelligence.py ./my_repo

    # Scan and query context for a specific task
    python run_intelligence.py ./my_repo --query "Add password reset endpoint"

    # Save the graph to JSON for inspection
    python run_intelligence.py ./my_repo --save repo_graph.json

    # Load an existing graph and query it (skip re-scan)
    python run_intelligence.py ./my_repo --load repo_graph.json --query "Fix auth bug"
"""

import argparse
import os
import sys
import time

from intelligence.repo_graph_builder import RepoGraphBuilder
from intelligence.context_retriever import ContextRetriever


def main():
    parser = argparse.ArgumentParser(
        description="Ada Intelligence Layer — scan repos, build knowledge graphs, query context"
    )
    parser.add_argument("repo_path", help="Path to the repository to scan")
    parser.add_argument("--query", "-q", help="Task description to retrieve context for")
    parser.add_argument("--save", "-s", help="Save the graph to a JSON file")
    parser.add_argument("--load", "-l", help="Load an existing graph from JSON instead of re-scanning")
    parser.add_argument("--top-k", "-k", type=int, default=10, help="Number of top files to return (default: 10)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed node/edge listings")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"Error: Not a directory: {repo_path}")
        sys.exit(1)

    print("=" * 70)
    print("Ada - Repository Intelligence Layer (Phase 4)")
    print("=" * 70)
    print(f"Repository: {repo_path}")
    print()

    builder = RepoGraphBuilder()

    # Build or load graph
    if args.load and os.path.exists(args.load):
        print(f"Loading graph from: {args.load}")
        graph = builder.load(args.load)
        if not graph:
            print("Error: Failed to load graph file.")
            sys.exit(1)
        # Run incremental update to catch changes
        print("Running incremental update...")
        graph = builder.incremental_update(repo_path, graph)
    else:
        print("Scanning repository and building knowledge graph...")
        start = time.time()
        graph = builder.build(repo_path)
        elapsed = time.time() - start
        print(f"Graph built in {elapsed:.2f}s")

    print()

    # Print summary
    print(graph.summary())
    print()

    # File breakdown by language
    files = graph.files()
    lang_counts = {}
    for f in files:
        lang = f.language or "unknown"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    if lang_counts:
        print("Files by language:")
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
            print(f"  {lang}: {count}")
        print()

    # Verbose: list all nodes
    if args.verbose:
        print("-" * 70)
        print("Classes:")
        for cls in sorted(graph.classes(), key=lambda n: n.file or ""):
            print(f"  {cls.name} ({cls.file}:{cls.line})")

        print()
        print("Functions/Methods:")
        for func in sorted(graph.functions(), key=lambda n: n.file or ""):
            parent = f" [{func.parent.split(':')[-1]}]" if func.parent else ""
            print(f"  {func.name}{parent} ({func.file}:{func.line})")

        print()
        print("Import edges:")
        for edge in graph.edges:
            if edge.kind == "imports":
                src = graph.nodes.get(edge.source)
                tgt = graph.nodes.get(edge.target)
                if src and tgt:
                    print(f"  {src.file or src.name} → {tgt.file or tgt.name}")
        print()

    # Save graph
    if args.save:
        builder.save(graph, args.save)
        print(f"Graph saved to: {args.save}")
        print()

    # Query context
    if args.query:
        print("-" * 70)
        print(f"Querying context for: \"{args.query}\"")
        print("-" * 70)
        print()

        retriever = ContextRetriever(top_k=args.top_k)
        ctx = retriever.get_context(args.query, graph)

        print(f"Keywords extracted: {ctx.keywords}")
        print()

        if ctx.relevant_files:
            print(f"Top {len(ctx.relevant_files)} relevant files:")
            for i, f in enumerate(ctx.relevant_files, 1):
                symbols = ", ".join(f["symbols"][:5]) if f["symbols"] else "-"
                print(f"  {i}. {f['path']} (score: {f['score']:.3f})")
                print(f"     symbols: {symbols}")
            print()

        if ctx.related_symbols:
            print(f"Related symbols ({len(ctx.related_symbols)}):")
            for s in ctx.related_symbols[:15]:
                loc = f"{s['file']}:{s.get('line', '?')}" if s.get("file") else ""
                print(f"  * {s['kind']}: {s['name']} ({loc})")
            print()

        if ctx.dependencies:
            print("Dependency relationships:")
            seen = set()
            for d in ctx.dependencies[:15]:
                key = f"{d['source']} → {d['target']}"
                if key not in seen:
                    seen.add(key)
                    print(f"  {d['source']} --[{d['kind']}]--> {d['target']}")
            print()

        print("-" * 70)
        print("Prompt context (what the LLM would receive):")
        print("-" * 70)
        print(ctx.to_prompt_context())

    # Interactive mode if no query provided
    if not args.query:
        print("-" * 70)
        print("Interactive mode -- enter task descriptions to query context (Ctrl+C to exit)")
        print("-" * 70)
        retriever = ContextRetriever(top_k=args.top_k)
        while True:
            try:
                query = input("\nQuery> ").strip()
                if not query:
                    continue
                ctx = retriever.get_context(query, graph)
                print(f"\nKeywords: {ctx.keywords}")
                if ctx.relevant_files:
                    print(f"\nTop files:")
                    for i, f in enumerate(ctx.relevant_files, 1):
                        print(f"  {i}. {f['path']} (score: {f['score']:.3f})")
                else:
                    print("  No matching files found.")
            except (KeyboardInterrupt, EOFError):
                print("\nDone.")
                break


if __name__ == "__main__":
    main()
