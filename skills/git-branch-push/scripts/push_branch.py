#!/usr/bin/env python3
"""
Git Branch Push Automation Tool
Safely pushes local Git branches to remote repositories with upstream tracking,
safety checks, and dry-run preview capabilities.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def run_git(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Execute a git command with safe.directory configuration."""
    cmd = ["git", "-c", "safe.directory=*"] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def find_git_root() -> Optional[Path]:
    """Find repository root by walking up from the current working directory."""
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def get_current_branch(repo_root: Path) -> Optional[str]:
    """Get active git branch name."""
    code, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    if code == 0 and out:
        return out
    return None


def has_upstream(repo_root: Path, branch: str) -> bool:
    """Check if the branch has an configured upstream tracking branch."""
    code, _, _ = run_git(["rev-parse", "--abbrev-ref", f"{branch}@{{u}}"], cwd=repo_root)
    return code == 0


def push_branch(
    repo_root: Path,
    branch: str,
    remote: str = "origin",
    set_upstream: bool = False,
    force_with_lease: bool = False,
    dry_run: bool = False
) -> bool:
    """Execute branch push with specified safety parameters."""
    push_args = ["push", remote, branch]

    if dry_run:
        push_args.insert(1, "--dry-run")
    if set_upstream:
        push_args.insert(1, "--set-upstream")
    if force_with_lease:
        push_args.insert(1, "--force-with-lease")

    print("==================================================")
    print(" Git Branch Push Plan")
    print("==================================================")
    print(f"Repository:       {repo_root}")
    print(f"Branch:           {branch}")
    print(f"Remote:           {remote}")
    print(f"Set Upstream:     {set_upstream}")
    print(f"Force With Lease: {force_with_lease}")
    print(f"Dry Run Mode:     {dry_run}")
    print(f"Git Command:      git {' '.join(push_args)}")
    print("==================================================\n")

    code, out, err = run_git(push_args, cwd=repo_root)
    if code == 0:
        if out:
            print(out)
        if err:
            print(err)
        print("\nBranch push operation completed successfully.")
        return True
    else:
        sys.stderr.write(f"\nPush failed with exit code {code}:\n{err}\n")
        if out:
            sys.stderr.write(f"Output:\n{out}\n")
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Safely push local Git branches to remote repositories.")
    parser.add_argument("--repo", help="Path to local git repository (defaults to auto-discovery)")
    parser.add_argument("--branch", help="Branch name to push (defaults to current branch)")
    parser.add_argument("--remote", default="origin", help="Remote name (default: origin)")
    parser.add_argument("-u", "--set-upstream", action="store_true", help="Set upstream tracking on remote")
    parser.add_argument("--force-with-lease", action="store_true", help="Use --force-with-lease for safe overwrite")
    parser.add_argument("--dry-run", action="store_true", help="Simulate push without executing")

    args = parser.parse_args()

    repo_root = Path(args.repo).resolve() if args.repo else find_git_root()
    if not repo_root or not (repo_root / ".git").exists():
        sys.stderr.write("Error: Could not locate git repository root.\n")
        sys.exit(1)

    branch = args.branch if args.branch else get_current_branch(repo_root)
    if not branch or branch == "HEAD":
        sys.stderr.write("Error: Unable to determine active branch (detached HEAD). Please specify --branch.\n")
        sys.exit(1)

    # Determine if upstream should automatically be configured
    auto_upstream = args.set_upstream or not has_upstream(repo_root, branch)

    success = push_branch(
        repo_root=repo_root,
        branch=branch,
        remote=args.remote,
        set_upstream=auto_upstream,
        force_with_lease=args.force_with_lease,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
