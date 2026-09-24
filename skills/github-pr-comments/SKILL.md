---
name: github-pr-comments
description: Fetch, display, and itemize all reviewer comments, inline diff remarks, and discussions on a GitHub Pull Request.
---

# GitHub Pull Request Comments & Feedback Skill

This skill retrieves and formats all feedback left by peer reviewers and automated review bots on a given GitHub Pull Request.

## Features

- **Official Reviews**: Displays overall review verdicts (`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`) with full markdown review text.
- **Inline Code Comments**: Displays file paths, diff hunk contexts, line numbers, author logins, and full comment bodies.
- **Discussion Threads**: Displays general PR comments and thread conversations in chronological order.
- **Non-Destructive**: Read-only GitHub REST API interaction. Supports optional `GITHUB_TOKEN` or `GH_TOKEN` for higher rate limits.

## Usage

```bash
# Fetch and display all review feedback for a specific PR
python skills/github-pr-comments/scripts/fetch_pr_comments.py --pr 21

# Output as formatted JSON
python skills/github-pr-comments/scripts/fetch_pr_comments.py --pr 21 --json

# Save to a markdown file
python skills/github-pr-comments/scripts/fetch_pr_comments.py --pr 21 --output agents/reviews/pr_21_comments.md
```
