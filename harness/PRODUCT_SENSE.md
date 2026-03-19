# Product Sense (`PRODUCT_SENSE.md`)

This document defines the core user experience and product goals of Ada. AI engineers working on this repository must align architectural decisions with this vision.

## The Goal
Ada is not just an autocomplete or a chat assistant; she is designed as a **Longitudinal Autonomous Engineer**. 
The golden path is: Provide a repository and a User Story backlog. Run Ada. Get a high-quality Pull Request. 

## Key Tenets
1. **Zero Human Intervention per Task**: Once an Implementation Plan is created, Ada must explore the codebase, edit files, fix test failures, and resolve linters completely autonomously. 
2. **Deterministic, Not Just Probabilistic**: We don’t just trust LLM outputs blindly. Code goes through a mandatory `QualityGate` phase before completion. Do not allow LLM hallucinated code to silently merge.
3. **High Autonomy**: We prioritize providing Ada with a very large tool-call budget and access to multi-file modifications over optimizing execution time or token cost (within reason), under the premise that accuracy and completeness is paramount.
4. **Resilience over Speed**: Software engineering takes time. It's better for a user to wait 15 minutes for a correct, fully-tested PR than 2 minutes for a broken one. We build resilient pipelines (retries, validations, plan-driven loops).
5. **Real-Time Auditability**: The product must ensure the human user can follow Ada’s thought process. We expose internal monologues, context resolutions, and tool logs to the UI console in real-time. If it feels like a "black box," that is a bug.
6. **Robust Error Handling**: Humans understand that tests fail. When a tool or script fails, the agent must capture the error output, adapt, and rewrite the code, exactly like a human engineer would.

## When Designing Or Refactoring Core features
- **Will this make Ada more autonomous?**
- **Will this reduce the likelihood of a silent failure?**
- **Can a human review the reason behind this action via the existing UI logs?**
- **Is this action safe to execute on the end user's machine? (If not, enforce isolation).**
