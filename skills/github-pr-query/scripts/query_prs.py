#!/usr/bin/env python3
"""
GitHub Pull Request Query CLI
Discovers, queries, and inspects Pull Requests from GitHub repositories.
Fetches PR metadata, changed files, commit histories, and unified diffs.
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
from typing import Any, Dict, List, Optional, Tuple


def find_repo_slug_from_git() -> Optional[str]:
    """Detect owner/repo slug from local git origin remote."""
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True
        )
        url = proc.stdout.strip()
        # Match git@github.com:owner/repo.git or https://github.com/owner/repo(.git)
        m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return "KingAlejandro/MotionCorr-standalone"


def make_github_request(url: str, accept_header: str = "application/vnd.github.v3+json", allow_empty: bool = False) -> Tuple[int, bytes]:
    """Make HTTP request to GitHub API using urllib with optional token."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "Accept": accept_header,
        "User-Agent": "MotionCorr-PRQuery/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        if allow_empty and e.code in (404, 422):
            return e.code, b"[]"
        err_body = str(e.read() or "").lower()
        sys.stderr.write(f"GitHub API Error [{e.code}]: {e.reason} ({url})\n")
        if e.code == 403 and "rate limit" in err_body:
            sys.stderr.write("API rate limit exceeded. Set GITHUB_TOKEN environment variable.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Network request error: {e}\n")
        sys.exit(1)


def list_pull_requests(repo: str, state: str = "all", limit: int = 30) -> List[Dict[str, Any]]:
    """List pull requests for a given repository."""
    url = f"https://api.github.com/repos/{repo}/pulls?state={state}&per_page={limit}"
    _, data = make_github_request(url)
    return json.loads(data.decode("utf-8"))


def fetch_paginated_list(base_url: str, allow_empty: bool = True) -> List[Dict[str, Any]]:
    """Fetch all pages from a GitHub API endpoint."""
    items: List[Dict[str, Any]] = []
    page = 1
    sep = "&" if "?" in base_url else "?"
    while True:
        url = f"{base_url}{sep}per_page=100&page={page}"
        _, raw = make_github_request(url, allow_empty=allow_empty)
        batch = json.loads(raw.decode("utf-8"))
        if not batch or not isinstance(batch, list):
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def get_pull_request_details(repo: str, pr_number: int) -> Dict[str, Any]:
    """Fetch full details, files, and commits for a specific PR."""
    pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    _, pr_raw = make_github_request(pr_url)
    pr_data = json.loads(pr_raw.decode("utf-8"))

    # Fetch changed files with pagination
    pr_data["files"] = fetch_paginated_list(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files", allow_empty=False)

    # Fetch commits
    commits_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/commits?per_page=50"
    _, commits_raw = make_github_request(commits_url)
    pr_data["commits"] = json.loads(commits_raw.decode("utf-8"))

    # Fetch official PR reviews with pagination
    pr_data["reviews"] = fetch_paginated_list(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews", allow_empty=True)

    # Fetch inline code review comments with pagination
    pr_data["review_comments"] = fetch_paginated_list(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments", allow_empty=True)

    # Fetch general PR discussion comments with pagination
    pr_data["issue_comments"] = fetch_paginated_list(f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments", allow_empty=True)

    return pr_data


def get_pull_request_diff(repo: str, pr_number: int) -> str:
    """Fetch unified patch diff for a PR."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    _, diff_raw = make_github_request(url, accept_header="application/vnd.github.v3.diff")
    return diff_raw.decode("utf-8", errors="replace")


def format_pr_list_markdown(prs: List[Dict[str, Any]], repo: str) -> str:
    """Format PR list into a structured markdown table."""
    if not prs:
        return f"No pull requests found for repository `{repo}`."

    lines = [
        f"# Pull Requests: `{repo}`",
        f"\nTotal Pull Requests: {len(prs)}\n",
        "| PR # | Title | Author | State | Base -> Head | Created / Updated |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for p in prs:
        num = p.get("number")
        title = p.get("title", "").replace("|", "\\|")
        author = p.get("user", {}).get("login", "unknown")
        state = p.get("state", "").upper()
        base = p.get("base", {}).get("ref", "unknown")
        head = p.get("head", {}).get("ref", "unknown")
        updated = (p.get("updated_at") or "")[:10]
        lines.append(f"| [#{num}]({p.get('html_url')}) | {title} | `{author}` | `{state}` | `{base}` ← `{head}` | {updated} |")

    return "\n".join(lines)


def format_pr_detail_markdown(pr: Dict[str, Any], repo: str) -> str:
    """Format single PR details into a detailed markdown document."""
    num = pr.get("number")
    title = pr.get("title")
    author = pr.get("user", {}).get("login")
    state = pr.get("state", "").upper()
    merged = pr.get("merged", False)
    mergeable = pr.get("mergeable")
    base = pr.get("base", {}).get("ref")
    head = pr.get("head", {}).get("ref")
    created = pr.get("created_at")
    updated = pr.get("updated_at")
    body = pr.get("body") or "*No description provided.*"
    files = pr.get("files", [])
    commits = pr.get("commits", [])

    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    changed_files_count = pr.get("changed_files", len(files))

    # Linked issues extraction
    linked_issues = re.findall(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", body, re.IGNORECASE)
    linked_str = ", ".join([f"#{i}" for i in linked_issues]) if linked_issues else "None explicitly cited"

    doc = [
        f"# Pull Request #{num}: {title}",
        "",
        f"- **Repository**: `{repo}`",
        f"- **Author**: `{author}`",
        f"- **Status**: `{state}`" + (" (MERGED)" if merged else ""),
        f"- **Branch**: `{base}` ← `{head}`",
        f"- **Mergeable**: `{mergeable}`",
        f"- **Linked Issues**: {linked_str}",
        f"- **Created**: `{created}` | **Updated**: `{updated}`",
        f"- **Diff Impact**: +{additions} / -{deletions} across {changed_files_count} file(s)",
        "",
        "## Description",
        "",
        body,
        "",
        "## Changed Files",
        "",
        "| File | Status | Additions | Deletions | Changes |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for f in files:
        f_name = f.get("filename")
        f_status = f.get("status")
        f_adds = f.get("additions", 0)
        f_dels = f.get("deletions", 0)
        f_chgs = f.get("changes", 0)
        doc.append(f"| `{f_name}` | `{f_status}` | +{f_adds} | -{f_dels} | {f_chgs} |")

    doc.extend([
        "",
        "## Commits",
        "",
        "| SHA | Author | Commit Message |",
        "| :--- | :--- | :--- |",
    ])
    for c in commits:
        sha = c.get("sha", "")[:8]
        c_author = c.get("commit", {}).get("author", {}).get("name", "unknown")
        msg = c.get("commit", {}).get("message", "").split("\n")[0].replace("|", "\\|")
        doc.append(f"| `{sha}` | {c_author} | {msg} |")

    # Reviewer Feedback Section
    reviews = pr.get("reviews", [])
    review_comments = pr.get("review_comments", [])
    issue_comments = pr.get("issue_comments", [])

    doc.extend([
        "",
        "## Reviewer Feedback & Discussions",
        "",
    ])

    if not reviews and not review_comments and not issue_comments:
        doc.append("*No reviews or comments posted yet on this pull request.*")
    else:
        if reviews:
            doc.extend([
                "### Official PR Reviews",
                "",
                "| Reviewer | State | Submitted At | Summary / Body |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for r in reviews:
                r_user = r.get("user", {}).get("login", "unknown")
                r_state = r.get("state", "COMMENTED")
                r_time = (r.get("submitted_at") or "")[:10]
                r_body = (r.get("body") or "*No body text*").replace("\n", " ").replace("|", "\\|")[:120]
                doc.append(f"| `@{r_user}` | `{r_state}` | {r_time} | {r_body} |")
            doc.append("")

        if review_comments:
            doc.extend([
                "### Inline Code Review Comments",
                "",
                "| Commenter | File & Line | Comment Snippet |",
                "| :--- | :--- | :--- |",
            ])
            for rc in review_comments:
                rc_user = rc.get("user", {}).get("login", "unknown")
                rc_path = rc.get("path", "unknown")
                rc_line = rc.get("line") or rc.get("original_line") or "diff"
                rc_body = (rc.get("body") or "").replace("\n", " ").replace("|", "\\|")[:120]
                doc.append(f"| `@{rc_user}` | `{rc_path}:{rc_line}` | {rc_body} |")
            doc.append("")

        if issue_comments:
            doc.extend([
                "### Conversation & Thread Comments",
                "",
                "| Commenter | Date | Comment Snippet |",
                "| :--- | :--- | :--- |",
            ])
            for ic in issue_comments:
                ic_user = ic.get("user", {}).get("login", "unknown")
                ic_time = (ic.get("created_at") or "")[:10]
                ic_body = (ic.get("body") or "").replace("\n", " ").replace("|", "\\|")[:120]
                doc.append(f"| `@{ic_user}` | {ic_time} | {ic_body} |")
            doc.append("")

    return "\n".join(doc)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="GitHub Pull Request Query Tool: List or inspect pull requests from a GitHub repository."
    )
    parser.add_argument("--repo", default=None, help="GitHub repository slug (e.g. KingAlejandro/MotionCorr-standalone)")
    parser.add_argument("--pr", type=int, help="Specific Pull Request number to inspect")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="all", help="Filter PRs by state")
    parser.add_argument("--limit", type=int, default=30, help="Maximum number of PRs to return")
    parser.add_argument("--diff", action="store_true", help="Fetch and return the raw unified patch diff for the PR")
    parser.add_argument("--format", choices=["markdown", "json", "summary"], default="markdown", help="Output format")
    parser.add_argument("--output", help="Optional output file path to write results")

    args = parser.parse_args()
    repo = args.repo or find_repo_slug_from_git()

    if args.pr:
        if args.diff:
            diff_text = get_pull_request_diff(repo, args.pr)
            if args.output:
                Path(args.output).write_text(diff_text, encoding="utf-8")
                print(f"[PR Query] Diff saved to {args.output}")
            else:
                print(diff_text)
            return

        pr_data = get_pull_request_details(repo, args.pr)
        if args.format == "json":
            out_str = json.dumps(pr_data, indent=2)
        else:
            out_str = format_pr_detail_markdown(pr_data, repo)

        if args.output:
            Path(args.output).write_text(out_str, encoding="utf-8")
            print(f"[PR Query] PR #{args.pr} details saved to {args.output}")
        else:
            print(out_str)

    else:
        # Listing PRs
        prs = list_pull_requests(repo, state=args.state, limit=args.limit)
        if args.format == "json":
            out_str = json.dumps(prs, indent=2)
        elif args.format == "summary":
            out_str = f"Found {len(prs)} {args.state} pull request(s) on {repo}."
        else:
            out_str = format_pr_list_markdown(prs, repo)

        if args.output:
            Path(args.output).write_text(out_str, encoding="utf-8")
            print(f"[PR Query] PR list saved to {args.output}")
        else:
            print(out_str)


if __name__ == "__main__":
    main()
