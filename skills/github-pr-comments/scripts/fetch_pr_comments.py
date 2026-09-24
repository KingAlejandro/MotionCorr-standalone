#!/usr/bin/env python3
"""
GitHub Pull Request Comments & Feedback Skill
Fetches, itemizes, and displays all official reviews, inline code remarks,
and PR discussion comments without truncation.
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


def get_default_repo() -> str:
    """Detect repo slug from git remote origin or return default."""
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True
        )
        url = proc.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+/[^/.]+)(?:\.git)?", url)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "KingAlejandro/MotionCorr-standalone"


def make_github_request(url: str, accept_header: str = "application/vnd.github.v3+json", allow_empty: bool = True) -> Tuple[int, bytes]:
    """Make HTTP request to GitHub API using urllib with optional token."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "Accept": accept_header,
        "User-Agent": "MotionCorr-PRComments/1.0",
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


def fetch_paginated_list(base_url: str) -> List[Dict[str, Any]]:
    """Fetch all pages from a GitHub API endpoint."""
    items: List[Dict[str, Any]] = []
    page = 1
    sep = "&" if "?" in base_url else "?"
    while True:
        url = f"{base_url}{sep}per_page=100&page={page}"
        _, raw = make_github_request(url)
        batch = json.loads(raw.decode("utf-8"))
        if not batch or not isinstance(batch, list):
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def fetch_all_comments(repo: str, pr_number: int) -> Dict[str, Any]:
    """Retrieve PR details, official reviews, inline code comments, and discussion comments."""
    # 1. PR overview
    pr_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    _, pr_raw = make_github_request(pr_url, allow_empty=False)
    pr_meta = json.loads(pr_raw.decode("utf-8"))

    # 2. Top-level reviews with pagination
    reviews = fetch_paginated_list(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews")

    # 3. Inline code review comments with pagination
    review_comments = fetch_paginated_list(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments")

    # 4. General conversation comments with pagination
    issue_comments = fetch_paginated_list(f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments")

    return {
        "pr_meta": pr_meta,
        "reviews": reviews,
        "review_comments": review_comments,
        "issue_comments": issue_comments,
    }


def format_markdown(data: Dict[str, Any], repo: str, pr_number: int) -> str:
    """Format full reviewer feedback into an untruncated markdown report."""
    pr = data["pr_meta"]
    title = pr.get("title", "")
    author = pr.get("user", {}).get("login", "unknown")
    state = pr.get("state", "").upper()
    base = pr.get("base", {}).get("ref", "unknown")
    head = pr.get("head", {}).get("ref", "unknown")

    reviews = data["reviews"]
    review_comments = data["review_comments"]
    issue_comments = data["issue_comments"]

    lines = [
        f"# Reviewer Comments & Feedback: PR #{pr_number}",
        "",
        f"- **Repository**: `{repo}`",
        f"- **Title**: {title}",
        f"- **Author**: `@{author}`",
        f"- **Branch**: `{base}` ← `{head}` (Status: `{state}`)",
        f"- **Official Reviews**: {len(reviews)}",
        f"- **Inline Code Comments**: {len(review_comments)}",
        f"- **Conversation Comments**: {len(issue_comments)}",
        "",
        "---",
        "",
        "## 1. Official Pull Request Reviews",
        "",
    ]

    if not reviews:
        lines.append("*No official PR reviews submitted.*")
    else:
        for idx, r in enumerate(reviews, 1):
            r_user = r.get("user", {}).get("login", "unknown")
            r_state = r.get("state", "COMMENTED")
            r_date = r.get("submitted_at") or "Unknown"
            r_body = r.get("body") or "*No body text provided.*"
            lines.extend([
                f"### Review #{idx}: `@{r_user}` (`{r_state}`)",
                f"- **Submitted At**: `{r_date}`",
                "",
                r_body,
                "",
            ])

    lines.extend([
        "---",
        "",
        "## 2. Inline Code Review Comments",
        "",
    ])

    if not review_comments:
        lines.append("*No inline code review comments posted.*")
    else:
        for idx, rc in enumerate(review_comments, 1):
            rc_user = rc.get("user", {}).get("login", "unknown")
            rc_path = rc.get("path", "unknown")
            rc_line = rc.get("line") or rc.get("original_line") or "diff"
            rc_date = rc.get("created_at") or "Unknown"
            rc_diff = rc.get("diff_hunk", "")
            rc_body = rc.get("body", "")

            lines.extend([
                f"### Comment #{idx}: `@{rc_user}` on `{rc_path}` (Line {rc_line})",
                f"- **Date**: `{rc_date}`",
                f"- **Comment URL**: [{rc_path}#{rc_line}]({rc.get('html_url', '#')})",
                "",
                "**Diff Context**:",
                "```diff",
                rc_diff.strip(),
                "```",
                "",
                "**Reviewer Feedback**:",
                "",
                rc_body,
                "",
            ])

    lines.extend([
        "---",
        "",
        "## 3. General Conversation & Discussion Comments",
        "",
    ])

    if not issue_comments:
        lines.append("*No conversation thread comments posted.*")
    else:
        for idx, ic in enumerate(issue_comments, 1):
            ic_user = ic.get("user", {}).get("login", "unknown")
            ic_date = ic.get("created_at") or "Unknown"
            ic_body = ic.get("body", "")

            lines.extend([
                f"### Thread Comment #{idx}: `@{ic_user}`",
                f"- **Date**: `{ic_date}`",
                "",
                ic_body,
                "",
            ])

    return "\n".join(lines)


def format_summary_table(comments: List[Dict[str, Any]], file_filter: Optional[str] = None) -> str:
    lines = [
        "| # | File:Line | Reviewer | Date | Summary / Excerpt |",
        "|---|---|---|---|---|"
    ]
    count = 0
    for idx, c in enumerate(comments, 1):
        path = c.get("path") or ""
        if file_filter and file_filter not in path:
            continue
        count += 1
        line_num = c.get("line") or c.get("original_line") or "-"
        user = c.get("user", {}).get("login", "unknown")
        created = (c.get("created_at") or "")[:19]
        body = c.get("body", "").replace("\n", " ").replace("|", "\\|")
        first_sentence = body.split(". ")[0].strip()
        if len(first_sentence) > 90:
            first_sentence = first_sentence[:87] + "..."
        lines.append(f"| {idx} | `{path}:{line_num}` | `@{user}` | `{created}` | {first_sentence} |")
    return f"Total matching comments: {count}\n\n" + "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Fetch and display all reviewer feedback and inline comments on a GitHub PR."
    )
    parser.add_argument("--repo", default=None, help="GitHub repository slug (e.g. KingAlejandro/MotionCorr-standalone)")
    parser.add_argument("--pr", type=int, required=True, help="Pull Request number to inspect")
    parser.add_argument("--output", help="Optional markdown file path to save report")
    parser.add_argument("--summary", action="store_true", help="Print a concise summary table of inline comments")
    parser.add_argument("--file", help="Filter comments to a specific file substring")
    parser.add_argument("--json", action="store_true", help="Output raw JSON data")

    args = parser.parse_args()
    repo = args.repo or get_default_repo()

    data = fetch_all_comments(repo, args.pr)

    if args.json:
        out_text = json.dumps(data, indent=2)
        print(out_text)
    elif args.summary:
        out_text = format_summary_table(data.get("review_comments", []), file_filter=args.file)
        print(out_text)
    else:
        out_text = format_markdown(data, repo, args.pr)
        print(out_text)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_text, encoding="utf-8")
        sys.stderr.write(f"\n[github-pr-comments] Comments saved to: {out_path}\n")


if __name__ == "__main__":
    main()
