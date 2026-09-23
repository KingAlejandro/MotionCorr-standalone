---
name: ai-git-commit
description: >-
  Use this skill when you need to inspect modified files, intelligently stage relevant changes (ignoring temporary/cache files), generate conventional commit messages, and commit them to Git with explicit AI authorship metadata for git blame.
---

# AI Git Commit Skill

This skill allows the agent to automatically inspect working tree modifications, select relevant code/doc/test/build files, formulate a concise conventional commit message, and commit the changes with explicit AI author attribution.

---

## What This Skill Does Automatically

When executed without extra arguments:
1. **Intelligent File Selection**:
   - Analyzes `git status`.
   - Automatically excludes temporary files, caches, `.DS_Store`, build artifacts, and scratch directories.
   - Stages modified and added files belonging to the project.
2. **Context-Aware Commit Message Generation**:
   - Detects the primary modified subsystem (`skills/`, `src/`, `test-data/`, `CMakeLists.txt`, `README.md`, etc.).
   - Classifies the change according to Conventional Commits (`feat`, `fix`, `docs`, `test`, `build`, `refactor`, `chore`).
   - Generates a clear subject line and detailed file inventory in the body.
3. **AI Attribution in `git blame` & Git Logs**:
   - Sets `Author: MotionCorr AI Assistant <ai-assistant@users.noreply.github.com>`.
   - Appends `AI-Generated: true` trailer.
   - Retains the local developer as Committer.

---

## Agent Usage Instructions

When you (the agent) are ready to commit modified files to the repository:

### 1. Fully Automated Mode (Recommended)

Simply execute:
```bash
python skills/ai-git-commit/scripts/ai_commit.py
```
*The script will automatically pick modified files, generate an appropriate commit message, stage, and commit.*

### 2. Preview / Dry-Run (Check Before Committing)

```bash
python skills/ai-git-commit/scripts/ai_commit.py --dry-run
```

### 3. Custom Message Mode

If you already know the specific commit message to use:
```bash
python skills/ai-git-commit/scripts/ai_commit.py -m "feat(runner): add patch alignment convergence diagnostics"
```

### 4. Custom File Selection Mode

If you want to only commit a specific subset of modified files:
```bash
python skills/ai-git-commit/scripts/ai_commit.py -f src/motioncorr_runner.cpp include/motioncorr_runner.h -m "refactor: isolate thread memory buffers"
```

---

## Manual Developer / CLI Usage

Developers can also configure and use the registered Git alias:

```bash
# Register alias once
python skills/ai-git-commit/scripts/ai_commit.py --setup-alias

# Use via Git CLI
git add src/motioncorr_runner.cpp
git ai-commit -m "fix: resolve OpenMP reduction race condition"
```

---

## Verification

To verify that the commit and `git blame` show the AI assistant:
```bash
git blame -e <file_path>
git log -1 --format=fuller
```
