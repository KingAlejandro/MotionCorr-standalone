---
name: git-branch-push
description: >-
  Use this skill to safely push local Git branches to remote repositories. Supports upstream tracking configuration, force-with-lease safety guards, dry-run simulation, and repository auto-discovery.
---

# Git Branch Push Skill

This skill provides a secure, robust tool for pushing local Git branches to remote repositories (e.g. `origin`). It automates upstream tracking configuration (`--set-upstream`), ensures safe push practices, supports dry-run simulation, and handles Windows repository ownership safe directory policies.

## Key Capabilities

1. **Automated Branch & Remote Discovery**:
   - Detects current branch name automatically.
   - Detects remote name (`origin` by default, configurable via `--remote`).
2. **Upstream Tracking Management**:
   - Automatically sets upstream tracking (`-u / --set-upstream`) if no upstream is configured.
3. **Safety Guards & Dry-Run**:
   - Supports `--dry-run` to simulate push operations without modifying remote state.
   - Supports `--force-with-lease` for safe rebasing without overwriting unseen remote commits.
4. **Environment Isolation**:
   - Injects `-c safe.directory=*` to prevent ownership errors on multi-user or shared environments.

## Directory Structure

```text
git-branch-push/
├── SKILL.md                 # Skill documentation and reference
└── scripts/
    └── push_branch.py       # Branch push automation CLI
```

## Running the Push Script

The script is located at:
[`push_branch.py`](./scripts/push_branch.py)

### CLI Options Reference

| Option | Type / Choices | Default | Description |
| :--- | :--- | :--- | :--- |
| `--branch` | `str` | *Current branch* | Branch name to push. Defaults to active branch. |
| `--remote` | `str` | `origin` | Target remote name. |
| `--set-upstream` / `-u` | `flag` | `True` if untracked | Configure upstream tracking on remote. |
| `--force-with-lease` | `flag` | `False` | Push using `--force-with-lease` safety guard. |
| `--dry-run` | `flag` | `False` | Simulate the push command without pushing bytes. |
| `--repo` | `path` | *Auto-discovered* | Local repository root path. |

### Usage Examples

1. **Push active branch with upstream configuration**:
   ```bash
   python skills/git-branch-push/scripts/push_branch.py
   ```

2. **Simulate branch push (dry-run)**:
   ```bash
   python skills/git-branch-push/scripts/push_branch.py --dry-run
   ```

3. **Push specific feature branch**:
   ```bash
   python skills/git-branch-push/scripts/push_branch.py --branch dev_milan --remote origin
   ```
