#!/usr/bin/env python3
"""
Standalone runner for the Phase 3 Planning Pipeline.

Takes a user story and repository, generates an ImplementationPlan with
atomic tasks and a DAG, then optionally executes it.

Usage:
    # Plan only (no execution) — see what tasks the planner generates
    python run_planning.py <story_file> <repo_path>

    # Plan and execute
    python run_planning.py <story_file> <repo_path> --execute

Examples:
    python run_planning.py stories/example_story.json ./my_repo
    python run_planning.py stories/example_story.json ./my_repo --execute
"""

import json
import os
import sys
import argparse

from dotenv import load_dotenv
load_dotenv()

from config import Config
from tools.tools import Tools
from planning.planner_agent import PlannerAgent
from planning.task_graph import TaskGraph, CycleError
from intelligence.repo_graph_builder import RepoGraphBuilder
from intelligence.context_retriever import ContextRetriever
from utils.logger import logger


def main():
    parser = argparse.ArgumentParser(
        description="Ada Planning Pipeline — generate and optionally execute implementation plans"
    )
    parser.add_argument("story_file", help="Path to a JSON story file")
    parser.add_argument("repo_path", help="Path to the target repository")
    parser.add_argument("--execute", "-x", action="store_true",
                        help="Execute the plan after generating it (requires LLM)")
    parser.add_argument("--workspace", "-w", default=".plan_workspace",
                        help="Workspace directory for execution (default: .plan_workspace)")
    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.story_file):
        print(f"Error: Story file not found: {args.story_file}")
        sys.exit(1)

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"Error: Not a directory: {repo_path}")
        sys.exit(1)

    with open(args.story_file) as f:
        story = json.load(f)

    provider = Config.get_llm_provider()

    print("=" * 70)
    print("Ada - Deterministic Planning Pipeline (Phase 3 + 4)")
    print("=" * 70)
    print(f"Story:      [{story.get('story_id', '?')}] {story.get('title', 'Untitled')}")
    print(f"Repository: {repo_path}")
    print(f"LLM:        {provider.upper()}")
    print(f"Mode:       {'Plan + Execute' if args.execute else 'Plan Only'}")
    print("=" * 70)
    print()

    # Step 1: Build Intelligence Graph
    print("[Step 1] Building repository intelligence graph...")
    graph_builder = RepoGraphBuilder()
    repo_graph = graph_builder.build(repo_path)
    print(f"  {repo_graph.summary()}")
    print()

    # Step 2: Generate Plan
    print("[Step 2] Generating implementation plan...")
    llm_client = Config.get_llm_client()
    tools = Tools()
    planner = PlannerAgent(llm_client, tools)
    planning_context = {"repo_summary": repo_graph.summary()}

    plan = planner.plan(story, repo_path, context=planning_context)

    if not plan or not plan.tasks:
        print("\nError: Planning failed -- no tasks generated.")
        sys.exit(1)

    print(f"\n  Plan: {plan.feature_title}")
    print(f"  Tasks: {len(plan.tasks)}")
    if plan.success_criteria:
        print(f"  Success Criteria:")
        for sc in plan.success_criteria:
            print(f"    * {sc}")
    print()

    # Step 3: Validate Task Graph
    print("[Step 3] Validating task graph (DAG)...")
    try:
        task_graph = TaskGraph(plan.tasks)
    except CycleError as e:
        print(f"\nError: Task graph has a cycle: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nError: Invalid dependencies: {e}")
        sys.exit(1)

    order = task_graph.topological_order()
    print(f"\n  Execution order ({len(order)} tasks):")
    for i, task in enumerate(order, 1):
        deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
        print(f"    {i}. [{task.task_id}] {task.title} ({task.type.value}){deps}")
        if task.success_criteria:
            for sc in task.success_criteria:
                print(f"        - {sc}")
    print()

    # Step 4: Query context for each task
    print("[Step 4] Retrieving intelligent context per task...")
    retriever = ContextRetriever(top_k=5)
    for task in order:
        ctx = retriever.get_context(f"{task.title}: {task.description}", repo_graph)
        files = [f["path"] for f in ctx.relevant_files[:5]]
        print(f"  [{task.task_id}] → {files if files else 'no matching files'}")
    print()

    # Step 5: Execute (optional)
    if args.execute:
        print("[Step 5] Executing plan...")
        print("-" * 70)

        from orchestration.plan_orchestrator import PlanOrchestrator
        from orchestrator.rule_provider import LocalFolderRuleProvider

        orchestrator = PlanOrchestrator(
            llm_client=llm_client,
            tools=tools,
            workspace_root=os.path.abspath(args.workspace),
            rule_providers=[LocalFolderRuleProvider()],
        )

        success = orchestrator.execute_story(story, repo_path)

        print("-" * 70)
        if success:
            print("\nAll tasks completed successfully!")
        else:
            print("\nSome tasks failed. Review the output above.")
            sys.exit(1)
    else:
        print("-" * 70)
        print("Plan generated successfully (dry run -- no code was executed).")
        print(f"To execute: python run_planning.py {args.story_file} {args.repo_path} --execute")
        print("-" * 70)


if __name__ == "__main__":
    main()
