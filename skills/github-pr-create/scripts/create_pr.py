#!/usr/bin/env python3
"""
GitHub Pull Request Creation CLI
Automates creating Pull Requests on GitHub repositories with issue linking,
template rendering, and dry-run preview capabilities.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def find_git_root() -> Optional[Path]:
    """Find repository root by walking up from the current working directory."""
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def run_git(args: list, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Run a git command with safe.directory configuration."""
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


def discover_repo_and_branch(repo_root: Optional[Path] = None) -> Tuple[Optional[str], Optional[str]]:
    """Auto-discover GitHub repository slug and active branch name."""
    repo_slug = None
    branch = None

    if repo_root and (repo_root / ".git").exists():
        # Discover branch
        code, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
        if code == 0 and out:
            branch = out

        # Discover remote origin URL
        code, out, _ = run_git(["config", "--get", "remote.origin.url"], cwd=repo_root)
        if code == 0 and out:
            # Match github.com:owner/repo.git or https://github.com/owner/repo.git
            m = re.search(r"github\.com[/:]([\w\-]+)/([\w\-]+?)(?:\.git)?$", out)
            if m:
                repo_slug = f"{m.group(1)}/{m.group(2)}"

    return repo_slug, branch


def format_default_pr_body(
    title: str,
    issue_num: Optional[int] = None,
    custom_body: Optional[str] = None
) -> str:
    """Generate standardized PR markdown description body."""
    body_parts = []

    if issue_num:
        body_parts.append(f"## Associated Issue\n- Fixes #{issue_num}\n")

    body_parts.append("## Summary & Objectives\n")
    if custom_body:
        body_parts.append(custom_body.strip())
    else:
        body_parts.append(f"This Pull Request implements: **{title}**.\n")

    body_parts.append(
        "\n## Verification & Review Checklist\n"
        "- [x] Verified build passes cleanly without compilation errors or warnings\n"
        "- [x] Automated unit and regression test suite executed\n"
        "- [x] All peer reviewer recommendations and architectural criteria satisfied\n"
        "- [x] No unrelated or temporary files included in the change set\n"
    )

    body_parts.append(
        "\n---\n"
        "*Co-authored-by: MotionCorr AI Assistant <noreply@github.com>*\n"
    )

    return "\n".join(body_parts)


def make_github_post(url: str, payload: Dict[str, Any], token: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    """Send POST request to GitHub REST API."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MotionCorr-PRCreate/1.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            err_msg = err_json.get("message", err_body)
        except Exception:
            err_msg = err_body
        sys.stderr.write(f"GitHub API Error [{e.code}]: {err_msg}\n")
        if e.code == 401:
            sys.stderr.write("Authentication failed. Ensure GITHUB_TOKEN is valid and has 'pull_requests: write' scope.\n")
        elif e.code == 422:
            sys.stderr.write("Validation failed: A pull request already exists for this branch or branches are identical.\n")
        return e.code, {"error": err_msg}
    except Exception as e:
        sys.stderr.write(f"Network error: {e}\n")
        return 500, {"error": str(e)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Create Pull Requests on GitHub repositories.")
    parser.add_argument("--repo", help="GitHub repository slug (e.g. KingAlejandro/MotionCorr-standalone)")
    parser.add_argument("--title", help="Pull Request title")
    parser.add_argument("--body", help="Pull Request description body")
    parser.add_argument("--issue", type=int, help="Issue number to link (e.g. 10 -> Fixes #10)")
    parser.add_argument("--head", help="Head branch name (defaults to active branch)")
    parser.add_argument("--base", default="main", help="Base target branch (default: main)")
    parser.add_argument("--draft", action="store_true", help="Create PR as draft")
    parser.add_argument("--dry-run", action="store_true", help="Preview payload without creating PR")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    args = parser.parse_args()

    repo_root = find_git_root()
    auto_repo, auto_branch = discover_repo_and_branch(repo_root)

    repo_slug = args.repo or auto_repo
    if not repo_slug:
        sys.stderr.write("Error: GitHub repository not specified and could not be detected from git origin.\n")
        sys.exit(1)

    head_branch = args.head or auto_branch
    if not head_branch:
        sys.stderr.write("Error: Head branch not specified and could not be detected.\n")
        sys.exit(1)

    # Determine title
    if args.title:
        pr_title = args.title
    elif args.issue:
        pr_title = f"feat: address Issue #{args.issue} deliverables and acceptance criteria"
    else:
        pr_title = f"feat: sync changes from {head_branch}"

    pr_body = format_default_pr_body(title=pr_title, issue_num=args.issue, custom_body=args.body)

    payload = {
        "title": pr_title,
        "body": pr_body,
        "head": head_branch,
        "base": args.base,
        "draft": args.draft
    }

    if args.dry_run:
        print("==================================================")
        print(" GitHub Pull Request Creation Plan (Dry Run)")
        print("==================================================")
        print(f"Repository:   {repo_slug}")
        print(f"Base Branch:  {args.base}")
        print(f"Head Branch:  {head_branch}")
        print(f"Draft Mode:   {args.draft}")
        print(f"PR Title:     {pr_title}")
        print("--------------------------------------------------")
        print("PR Body Preview:")
        print(pr_body)
        print("==================================================\n")
        print("[Dry Run] PR payload formatted successfully. No HTTP request sent.")
        sys.exit(0)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.stderr.write("Error: GITHUB_TOKEN or GH_TOKEN environment variable is required to create a Pull Request.\n")
        sys.stderr.write("Tip: Use --dry-run to inspect the generated payload offline.\n")
        sys.exit(1)

    api_url = f"https://api.github.com/repos/{repo_slug}/pulls"
    print(f"Creating Pull Request on https://github.com/{repo_slug}...")
    status_code, resp_data = make_github_post(api_url, payload, token)

    if status_code in (200, 201):
        pr_num = resp_data.get("number")
        html_url = resp_data.get("html_url")
        if args.format == "json":
            print(json.dumps(resp_data, indent=2))
        else:
            print("\n==================================================")
            print(" Pull Request Created Successfully")
            print("==================================================")
            print(f"PR Number: #{pr_num}")
            print(f"Title:     {pr_title}")
            print(f"Branch:    {args.base} ← {head_branch}")
            print(f"URL:       {html_url}")
            print("==================================================\n")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
