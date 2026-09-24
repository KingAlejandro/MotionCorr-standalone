---
name: github-pr-query
description: >-
  Use this skill to discover, query, list, and fetch Pull Requests from GitHub repositories. Supports inspecting PR metadata, diffs, changed files, linked issues, and commit histories from the GitHub REST API or local git branches.
---

# GitHub Pull Request Query Skill

This skill provides a standardized tool and workflow for querying Pull Requests on a GitHub repository. It allows discovery of open/closed PRs, detailed inspection of individual PRs (including patch diffs, changed files, commit histories, and review comments), and supports both online API queries and local git PR branch inspection.

## Key Capabilities

1. **PR Discovery & Listing**:
   - Lists pull requests (`--state open|closed|all`, `--limit <N>`).
   - Retrieves PR number, title, author, base branch, head branch, update timestamps, and labels.
2. **Detailed PR Inspection**:
   - Fetches full PR description, linked issue references (e.g. `Fixes #4`, `Resolves #10`).
   - Retrieves file change statistics (additions, deletions, modified files).
   - Fetches unified diff/patch directly (`--diff`) for code review and verification agents.
3. **Flexible Authentication & Offline Fallback**:
   - Uses `GITHUB_TOKEN` or `GH_TOKEN` environment variable if present.
   - Works without authentication for public repositories.
   - Supports local branch / git ref inspection (`--target <branch>`).

## Directory Structure

```text
github-pr-query/
├── SKILL.md                 # Skill documentation and reference
└── scripts/
    └── query_prs.py         # Pull Request query and inspection CLI
```

## Running the Query Script

The script is located at:
[`query_prs.py`](./scripts/query_prs.py)

### Usage Examples

1. **List all open Pull Requests for the repository**:
   ```bash
   python skills/github-pr-query/scripts/query_prs.py --repo KingAlejandro/MotionCorr-standalone --state open
   ```

2. **Inspect a specific Pull Request**:
   ```bash
   python skills/github-pr-query/scripts/query_prs.py --repo KingAlejandro/MotionCorr-standalone --pr 1
   ```

3. **Fetch unified diff for automated agent review**:
   ```bash
   python skills/github-pr-query/scripts/query_prs.py --repo KingAlejandro/MotionCorr-standalone --pr 1 --diff --output pr_1.patch
   ```

4. **Export PR details as structured JSON**:
   ```bash
   python skills/github-pr-query/scripts/query_prs.py --repo KingAlejandro/MotionCorr-standalone --pr 1 --format json --output pr_1.json
   ```
