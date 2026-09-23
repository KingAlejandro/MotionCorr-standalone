#!/usr/bin/env python3
"""
AI Git Commit Helper Script
Automatically selects relevant modified files, generates appropriate conventional commit
messages from diffs/status, prints changes made (diff stat and diff preview), and requests
approval before committing with explicit AI authorship metadata for git blame.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_AI_NAME = "MotionCorr AI Assistant"
DEFAULT_AI_EMAIL = "ai-assistant@users.noreply.github.com"
DEFAULT_TRAILER = "AI-Generated: true"

IGNORED_PATTERNS = [
    r"^\.agents/?",
    r".*\.tmp$",
    r".*\.bak$",
    r".*\.swp$",
    r".*\.DS_Store$",
    r".*Thumbs\.db$",
    r".*__pycache__.*",
    r".*\.pyc$",
    r".*build/.*",
    r".*CMakeFiles/.*",
    r".*\.log$",
    r".*scratch/.*",
]


def run_git_command(args: List[str], cwd: Optional[Path] = None, env: Optional[dict] = None) -> Tuple[int, str, str]:
    """Execute a git command with safe directory configuration."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*"] + args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=full_env,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 1, "", "Git executable not found on system PATH."
    except Exception as e:
        return 1, "", str(e)


def find_git_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find repository root by querying git or walking upwards."""
    current = (start_path or Path.cwd()).resolve()
    code, out, _ = run_git_command(["rev-parse", "--show-toplevel"], cwd=current)
    if code == 0 and out:
        return Path(out).resolve()
    
    p = current
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return None


def is_relevant_file(file_path: str) -> bool:
    """Check if file should be included in automatic commits."""
    normalized = file_path.replace("\\", "/")
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return False
    return True


def get_status(repo_root: Path) -> List[Tuple[str, str]]:
    """Return list of (status_code, file_path) for working tree changes."""
    code, out, err = run_git_command(["status", "--porcelain"], cwd=repo_root)
    if code != 0:
        sys.stderr.write(f"Failed to get git status: {err}\n")
        return []
    
    changes = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status_code = line[:2]
        file_path = line[2:].strip()
        # Handle rename format: "R  old -> new"
        if " -> " in file_path:
            file_path = file_path.split(" -> ")[1].strip()
        changes.append((status_code, file_path))
    return changes


def stage_files(repo_root: Path, files_to_stage: List[str]) -> bool:
    """Stage specified files."""
    if not files_to_stage:
        return False
    code, out, err = run_git_command(["add", "--"] + files_to_stage, cwd=repo_root)
    if code != 0:
        sys.stderr.write(f"Failed to stage files: {err}\n")
        return False
    return True


def unstage_files(repo_root: Path, files: Optional[List[str]] = None) -> bool:
    """Unstage specified files or all staged files."""
    args = ["reset", "HEAD"]
    if files:
        args += ["--"] + files
    code, _, err = run_git_command(args, cwd=repo_root)
    if code != 0:
        sys.stderr.write(f"Failed to unstage files: {err}\n")
        return False
    return True


def get_diff_stat(repo_root: Path, cached: bool = True) -> str:
    """Return diff statistics."""
    args = ["diff", "--stat"]
    if cached:
        args.append("--cached")
    code, out, _ = run_git_command(args, cwd=repo_root)
    return out if code == 0 else ""


def get_diff_preview(repo_root: Path, max_lines: int = 80, cached: bool = True) -> str:
    """Return a unified diff preview truncated to max_lines."""
    if max_lines <= 0:
        return ""
    args = ["diff"]
    if cached:
        args.append("--cached")
    code, out, _ = run_git_command(args, cwd=repo_root)
    if code != 0 or not out:
        return ""
    lines = out.splitlines()
    if len(lines) > max_lines:
        preview = "\n".join(lines[:max_lines])
        preview += f"\n... [diff truncated; {len(lines) - max_lines} more lines]"
        return preview
    return out


def categorize_files(files: List[str]) -> Dict[str, List[str]]:
    """Group files by architectural domain."""
    categories: Dict[str, List[str]] = {
        "skills": [],
        "agents": [],
        "src": [],
        "tests": [],
        "build": [],
        "ci": [],
        "docs": [],
        "other": []
    }
    
    for f in files:
        norm = f.replace("\\", "/")
        if norm.startswith("skills/"):
            categories["skills"].append(norm)
        elif norm.startswith("agents/"):
            categories["agents"].append(norm)
        elif norm.startswith("src/") or norm.startswith("include/"):
            categories["src"].append(norm)
        elif norm.startswith("test-data/") or norm.startswith("test/") or norm.startswith("tests/"):
            categories["tests"].append(norm)
        elif norm == "CMakeLists.txt" or norm.endswith(".cmake"):
            categories["build"].append(norm)
        elif norm.startswith(".github/") or norm.startswith("automation/"):
            categories["ci"].append(norm)
        elif norm.endswith(".md") or norm.startswith("doc/") or norm in ("AUTHORS", "LICENSE", "COPYING"):
            categories["docs"].append(norm)
        else:
            categories["other"].append(norm)
            
    return categories


def auto_generate_commit_message(repo_root: Path, files_to_stage: List[str], status_list: List[Tuple[str, str]]) -> str:
    """Analyze modified files and status to generate a descriptive conventional commit message."""
    categories = categorize_files(files_to_stage)
    status_dict = {f: s for s, f in status_list}
    
    # 1. Skill changes
    if categories["skills"] and not categories["src"]:
        skill_names = set()
        for f in categories["skills"]:
            parts = f.split("/")
            if len(parts) >= 2:
                skill_names.add(parts[1])
            else:
                skill_names.add("skill")
        names_str = ", ".join(sorted(skill_names))
        all_new = all(status_dict.get(f, "").startswith("??") or status_dict.get(f, "").startswith("A") for f in categories["skills"])
        action = "add" if all_new else "update"
        subject = f"feat(skills): {action} {names_str} skill{'s' if len(skill_names) > 1 else ''}"

    # 1b. Agent changes
    elif categories["agents"] and not categories["src"]:
        all_new = all(status_dict.get(f, "").startswith("??") or status_dict.get(f, "").startswith("A") for f in categories["agents"])
        action = "add" if all_new else "update"
        subject = f"feat(agents): {action} architecture agent and design tooling"

    # 2. Source code changes
    elif categories["src"]:
        modules = set()
        for f in categories["src"]:
            base = Path(f).stem
            modules.add(base)
        mod_str = ", ".join(sorted(modules)[:2])
        if len(modules) > 2:
            mod_str += f" (+{len(modules)-2} files)"
            
        has_new = any(status_dict.get(f, "").startswith("??") or status_dict.get(f, "").startswith("A") for f in categories["src"])
        has_mod = any("M" in status_dict.get(f, "") for f in categories["src"])
        
        if has_new:
            subject = f"feat(core): implement {mod_str}"
        elif has_mod:
            subject = f"refactor(core): update {mod_str}"
        else:
            subject = f"chore(core): update {mod_str}"

    # 3. Tests / Test Data
    elif categories["tests"]:
        subject = "test: update test fixtures and validation data"

    # 4. Build / CMake
    elif categories["build"]:
        subject = "build: update CMake build configuration"

    # 5. CI / Automation
    elif categories["ci"]:
        subject = "ci: update CI workflow and automation scripts"

    # 6. Documentation
    elif categories["docs"]:
        subject = "docs: update documentation and project guides"

    # 7. Mixed or General
    else:
        subject = "chore: update project files"

    # Build commit body detailing modified files
    body_lines = ["\nModified files:"]
    for f in sorted(files_to_stage)[:10]:
        st = status_dict.get(f, "").strip()
        flag = "Added" if "??" in st or "A" in st else "Deleted" if "D" in st else "Modified"
        body_lines.append(f"- [{flag}] {f}")
    if len(files_to_stage) > 10:
        body_lines.append(f"- ... and {len(files_to_stage) - 10} more files")

    return subject + "\n" + "\n".join(body_lines)


def format_commit_message(base_message: str, add_trailer: bool = True, co_author: Optional[str] = None) -> str:
    """Format commit message with AI trailer and optional co-authorship metadata."""
    lines = [base_message.strip(), ""]
    if add_trailer:
        lines.append(DEFAULT_TRAILER)
    if co_author:
        lines.append(f"Co-authored-by: {co_author}")
    return "\n".join(lines).strip()


def setup_git_alias(ai_name: str, ai_email: str) -> bool:
    """Configure git alias 'ai-commit' in local git configuration."""
    alias_cmd = (
        f'!f() {{ git -c user.name="{ai_name}" -c user.email="{ai_email}" '
        f'commit --trailer "{DEFAULT_TRAILER}" "$@"; }}; f'
    )
    code, _, err = run_git_command(["config", "alias.ai-commit", alias_cmd])
    if code == 0:
        print(f"Git alias 'git ai-commit' successfully created.")
        print(f"Author identity set to: {ai_name} <{ai_email}>")
        return True
    else:
        sys.stderr.write(f"Failed to configure git alias: {err}\n")
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Select modified files, display changes, ask for approval, and commit with AI attribution."
    )
    parser.add_argument("-m", "--message", help="Explicit commit message (auto-generated if omitted)")
    parser.add_argument("-f", "--files", nargs="+", help="Specific files to stage (auto-detected if omitted)")
    parser.add_argument("-a", "--all", action="store_true", help="Stage all tracked modified files")
    parser.add_argument("-y", "--yes", action="store_true", help="Bypass interactive approval and commit directly")
    parser.add_argument("--diff", "--show-diff", action="store_true", help="Display full unified diff preview in addition to summary")
    parser.add_argument("--diff-limit", type=int, default=80, help="Maximum lines of diff preview to display when --diff is enabled (default: 80)")
    parser.add_argument("--author-name", default=DEFAULT_AI_NAME, help=f"AI Author name (default: {DEFAULT_AI_NAME})")
    parser.add_argument("--author-email", default=DEFAULT_AI_EMAIL, help=f"AI Author email (default: {DEFAULT_AI_EMAIL})")
    parser.add_argument("--co-author", help="Optional human co-author in 'Name <email>' format")
    parser.add_argument("--no-trailer", action="store_true", help="Omit 'AI-Generated: true' commit trailer")
    parser.add_argument("--dry-run", action="store_true", help="Simulate staging and diff display without committing")
    parser.add_argument("--setup-alias", action="store_true", help="Register 'git ai-commit' alias in git config")
    parser.add_argument("--repo", help="Path to git repository root (auto-detected if omitted)")

    args = parser.parse_args()

    if args.setup_alias:
        success = setup_git_alias(args.author_name, args.author_email)
        sys.exit(0 if success else 1)

    target_repo = Path(args.repo).resolve() if args.repo else find_git_root()
    if not target_repo or not (target_repo / ".git").exists():
        sys.stderr.write("Error: Not inside a git repository or repository root not found.\n")
        sys.exit(1)

    status_list = get_status(target_repo)
    if not status_list:
        print("Working tree is clean. Nothing to commit.")
        sys.exit(0)

    # 1. Determine files to stage
    if args.files:
        files_to_stage = args.files
    elif args.all:
        files_to_stage = [f for status, f in status_list if status[0] in (" M", "M ", "MM", " D", "D ") and is_relevant_file(f)]
    else:
        files_to_stage = [f for _, f in status_list if is_relevant_file(f)]

    if not files_to_stage:
        print("No relevant modified files found to stage.")
        sys.exit(0)

    # 2. Determine or generate commit message
    if args.message:
        raw_message = args.message
    else:
        print("Analyzing changes to generate commit message...")
        raw_message = auto_generate_commit_message(target_repo, files_to_stage, status_list)

    commit_msg = format_commit_message(
        raw_message,
        add_trailer=not args.no_trailer,
        co_author=args.co_author
    )

    git_env = {
        "GIT_AUTHOR_NAME": args.author_name,
        "GIT_AUTHOR_EMAIL": args.author_email,
    }

    # Stage files to examine exact diff
    if not stage_files(target_repo, files_to_stage):
        sys.exit(1)

    diff_stat = get_diff_stat(target_repo, cached=True)
    diff_preview = get_diff_preview(target_repo, max_lines=args.diff_limit, cached=True)

    # Display Commit Plan & Changes
    print("\n==================================================")
    print(" AI Git Commit Plan")
    print("==================================================")
    print(f"Repository: {target_repo}")
    print(f"Author:     {args.author_name} <{args.author_email}>")
    print(f"Files to Stage ({len(files_to_stage)}):")
    for f in files_to_stage:
        print(f"  - {f}")
    print("\nCommit Message:")
    for line in commit_msg.splitlines():
        print(f"  {line}")

    if diff_stat:
        print("\n==================================================")
        print(" Changes Summary (git diff --stat)")
        print("==================================================")
        print(diff_stat)

    if args.diff and diff_preview:
        print("==================================================")
        print(f" Diff Preview (first {args.diff_limit} lines)")
        print("==================================================")
        print(diff_preview)

    print("==================================================\n")

    # If dry-run, unstage and exit
    if args.dry_run:
        unstage_files(target_repo, files_to_stage)
        print("[Dry Run] Preview complete. Files unstaged and no commit made.")
        sys.exit(0)

    # Interactive approval check
    if not args.yes:
        approved = False
        try:
            prompt_text = "Do you approve these changes and want to proceed with the commit? [y/N]: "
            # If standard input is available, prompt user
            if sys.stdin.isatty():
                ans = input(prompt_text).strip().lower()
                approved = ans in ("y", "yes")
            else:
                # Read from piped stdin if provided
                ans = sys.stdin.readline().strip().lower()
                approved = ans in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            approved = False

        if not approved:
            print("\nCommit not approved. Unstaging files...")
            unstage_files(target_repo, files_to_stage)
            print("Commit aborted. Working tree preserved.")
            sys.exit(0)

    # Commit with AI author attribution
    print("Committing changes...")
    commit_args = ["commit", "-m", commit_msg]
    code, out, err = run_git_command(commit_args, cwd=target_repo, env=git_env)

    if code == 0:
        print("\nCommit successful!")
        print(out)
    else:
        sys.stderr.write(f"\nCommit failed (exit code {code}):\n{err}\n")
        sys.exit(code)


if __name__ == "__main__":
    main()
