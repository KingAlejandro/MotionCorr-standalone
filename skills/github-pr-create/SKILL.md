---
name: github-pr-create
description: >-
  Use this skill to create Pull Requests / Merge Requests on GitHub repositories. Supports automated issue linking (Fixes #X), PR template formatting, draft PR creation, co-author attribution, and dry-run preview.
---

# GitHub Pull Request Creation Skill

This skill provides an automated, standardized tool for creating Pull Requests on GitHub repositories using the GitHub REST API. It handles automatic repository discovery, head/base branch resolution, issue linking (`Fixes #X`), structured review checklists, AI co-authorship attribution, and dry-run payload verification.

## Key Capabilities

1. **Automated Metadata Discovery**:
   - Auto-discovers repository slug from git remote origin.
   - Detects active git branch as the PR `head` branch.
   - Defaults `base` branch to `main` (or customizable via `--base`).
2. **Issue Linking & Template Synthesis**:
   - Supports `--issue <N>` to auto-link deliverables and render structured problem statements.
   - Appends standardized verification checklists and pass criteria.
   - Injects `Co-authored-by: MotionCorr AI Assistant <noreply@github.com>` trailer into description.
3. **Draft PR & Dry-Run Support**:
   - Supports `--draft` to create draft pull requests for work in progress.
   - Supports `--dry-run` to validate the JSON payload and rendered Markdown body without making network requests.
4. **Authentication**:
   - Uses `GITHUB_TOKEN` or `GH_TOKEN` environment variable.
   - Surfaces rate limit, permission (403/401), and branch collision (422) errors cleanly.

## Directory Structure

```text
github-pr-create/
├── SKILL.md                 # Skill documentation and reference
└── scripts/
    └── create_pr.py         # Pull Request creation CLI
```

## Running the PR Creation Script

The script is located at:
[`create_pr.py`](./scripts/create_pr.py)

### CLI Options Reference

| Option | Type / Choices | Default | Description |
| :--- | :--- | :--- | :--- |
| `--repo` | `str` | *Auto-discovered* | GitHub repository slug (`owner/repo`). |
| `--title` | `str` | *Required / Auto-generated* | Title of the Pull Request. |
| `--body` | `str` | *Auto-generated* | Pull Request description body. |
| `--issue` | `int` | *None* | Target issue number to link (e.g. `Fixes #10`). |
| `--head` | `str` | *Active branch* | Head branch containing changes. |
| `--base` | `str` | `main` | Base branch to merge into. |
| `--draft` | `flag` | `False` | Create as draft Pull Request. |
| `--dry-run` | `flag` | `False` | Preview PR payload without calling GitHub API. |
| `--format` | `markdown`, `json` | `markdown` | Output formatting mode. |

### Usage Examples

1. **Create PR linked to an issue (dry-run preview)**:
   ```bash
   python skills/github-pr-create/scripts/create_pr.py --issue 10 --title "feat(cpu): optimize CPU FFT scratch buffer allocation" --dry-run
   ```

2. **Create live Pull Request**:
   ```bash
   python skills/github-pr-create/scripts/create_pr.py --title "feat: implement multi-agent ecosystem" --body "Complete PR description..."
   ```

3. **Create Draft Pull Request**:
   ```bash
   python skills/github-pr-create/scripts/create_pr.py --title "WIP: CUDA kernel acceleration" --draft
   ```
