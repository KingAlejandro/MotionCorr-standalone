---
name: ai-git-commit
description: >-
  Use this skill to inspect modified files, print diff statistics and diff previews of changes made, request user approval, and commit them to Git with explicit AI authorship metadata for git blame.
---

# AI Git Commit Skill

This skill allows the agent or developer to inspect working tree modifications, display change summaries and diff previews, request confirmation, and commit changes with explicit AI author attribution.

---

## What This Skill Does

1. **Intelligent File Selection**:
   - Analyzes `git status`.
   - Automatically excludes temporary files, caches, `.DS_Store`, build artifacts, and scratch directories.
   - Stages relevant code, test, documentation, or configuration changes.
2. **Prints Changes Summary Before Committing**:
   - Displays file list with modification statuses (`[Modified]`, `[Added]`, `[Deleted]`).
   - Prints `git diff --stat` showing line additions/deletions summary.
   - Optional unified diff preview via `--diff` / `--show-diff`.
3. **Approval Verification**:
   - Requests user approval (`[y/N]`) before applying the commit.
   - If aborted or rejected, cleanly unstages all files and leaves the working tree intact.
   - Supports `-y` / `--yes` flag to bypass the prompt during non-interactive or automated workflows.
4. **Context-Aware Conventional Commit Message Generation**:
   - Classifies changes (`feat`, `fix`, `docs`, `test`, `build`, `refactor`, `chore`).
   - Formulates a concise subject line and itemized file inventory.
5. **Collaborator Authorship & AI Attribution**:
   - Preserves the local developer/collaborator as the primary `Author` (from `git config` or `git var GIT_AUTHOR_IDENT`).
   - Appends standard `AI-Generated: true` trailer.
   - Appends `Co-authored-by: MotionCorr AI Assistant <noreply@github.com>` trailer to maintain transparent provenance without polluting profile links.

---

## Agent Usage Instructions

### 1. Interactive Approval Mode (Default)
```bash
python skills/ai-git-commit/scripts/ai_commit.py
```
*Prints the commit plan, diff summary, and diff preview, then prompts: `Do you approve these changes and want to proceed with the commit? [y/N]: `*

### 2. Auto-Approved Commit (`-y` / `--yes`)
When running in unattended scripts or automated agent sequences:
```bash
python skills/ai-git-commit/scripts/ai_commit.py -y
```

### 3. Dry-Run / Preview Only
```bash
python skills/ai-git-commit/scripts/ai_commit.py --dry-run
```

### 4. Custom Message with Changes Display
```bash
python skills/ai-git-commit/scripts/ai_commit.py -m "fix(runner): isolate per-thread FFTW plan state"
```

### 5. GitHub Issue Linking & Branch Tagging
- **Link Commit to an Issue**:
  ```bash
  python skills/ai-git-commit/scripts/ai_commit.py -y -i 4 -m "feat(validation): implement reference acceptance gates"
  ```
- **Auto-Close Issue on GitHub Merge**:
  ```bash
  python skills/ai-git-commit/scripts/ai_commit.py -y --closes 4
  ```
- **Tag the Issue with Git Tag (`issue-4`)**:
  ```bash
  python skills/ai-git-commit/scripts/ai_commit.py -y -i 4 --tag-issue
  ```
- **Create & Switch to Standardized Issue Branch (`feat/issue-4-reference-gates`)**:
  ```bash
  python skills/ai-git-commit/scripts/ai_commit.py --branch-issue 4 reference-gates
  ```

---

## Verification

* Verify `git blame` author:
  ```bash
  git blame -e <file_path>
  ```
* Verify commit log:
  ```bash
  git log -1 --format=fuller
  ```
