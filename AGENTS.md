# MotionCorr Multi-Agent Development Guidelines

This project employs a multi-agent engineering workflow to safely extract, optimize, and modernize the standalone RELION motion correction engine while maintaining bit-exact numerical parity against RELION 5.1 (`commit ad0b230`).

---

## 1. Agent Roles & Responsibilities

1. **Architecture Agent (`agents/architecture_agent/`)**:
   - **Mandate**: Must be consulted for any non-trivial issue before code changes are made.
   - **Deliverable**: Architectural Decision Record / Design Specification in `agents/designs/issue_<NUM>_<slug>.md`.
   - **Key Focus**: Mathematical formulation, numerical tolerance tiers, memory staging budgets, interface contracts, and failure fallbacks.
   - **System Prompt**: [`agents/architecture_agent/SYSTEM_PROMPT.md`](agents/architecture_agent/SYSTEM_PROMPT.md)

2. **Implementation Agent**:
   - **Mandate**: Executes changes strictly according to the approved Architectural Design Specification.
   - **Deliverable**: Modular C++17, CUDA, Python, or CMake code changes with unit test fixtures.
   - **Tooling**: Uses [`skills/ai-git-commit/`](skills/ai-git-commit/SKILL.md) for clean, traceable commits.

3. **Review & Verification Agent (`agents/review_agent/`)**:
   - **Mandate**: Memoryless, isolated, strictly read-only auditor. Does NOT modify code.
   - **Deliverable**: Objective review reports concluding with an explicit verdict (`READY_TO_MERGE`, `CHANGES_REQUESTED`, `BLOCKED_BY_FAULT`).
   - **Key Focus**: Detects numerical parity regressions, OpenMP non-determinism, heap allocations in hot loops, and portability faults.
   - **System Prompt**: [`agents/review_agent/SYSTEM_PROMPT.md`](agents/review_agent/SYSTEM_PROMPT.md)

---

## 2. Standard Issue Lifecycle

```mermaid
flowchart LR
    Issue["Issue #N"] --> Arch["Architecture Agent"]
    Arch --> Spec["agents/designs/issue_N_*.md"]
    Spec --> User{"Maintainer Approval"}
    User -->|Approved| Impl["Implementation Agent"]
    Impl --> Code["Source Code & Tests"]
    Code --> Rev["Review Agent (Stateless)"]
    Rev -->|READY_TO_MERGE| Commit["ai-git-commit Skill"]
    Rev -->|CHANGES_REQUESTED| Impl
    Commit --> Merged["Merged to Branch"]
```

---

## 3. Tooling & Skills Reference

- **Stateless Code Review**: `python agents/review_agent/scripts/review_code.py`
- **Design Scaffolding & Generation**: `python agents/architecture_agent/scripts/generate_architecture.py --issue <NUM>`
- **Automated AI Commits**: `python skills/ai-git-commit/scripts/ai_commit.py`
- **Issue Parser**: `python skills/github-issues-parser/scripts/parse_issues.py`
