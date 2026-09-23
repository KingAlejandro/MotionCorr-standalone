#!/usr/bin/env python3
"""
GitHub Issues Parser Script
Parses issues from GitHub REST API or local JSON export and generates structured summaries,
difficulty ratings, and implementation dependencies.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def fetch_issues_from_api(repo: str, state: str = "all") -> List[Dict[str, Any]]:
    """Fetch all issues for a repo using GitHub REST API."""
    url = f"https://api.github.com/repos/{repo}/issues?state={state}&per_page=100"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MotionCorr-IssueParser/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP Error {e.code}: {e.reason}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Failed to fetch issues: {e}\n")
        sys.exit(1)


def load_issues_from_file(file_path: str) -> List[Dict[str, Any]]:
    """Load issues from a local JSON or raw markdown cache file."""
    path = Path(file_path)
    if not path.exists():
        sys.stderr.write(f"File not found: {file_path}\n")
        sys.exit(1)
    content = path.read_text(encoding="utf-8")
    
    # Handle files that might have HTTP / frontmatter header (e.g. content.md with --- separator)
    if "---" in content and not content.strip().startswith("["):
        parts = content.split("---", 1)
        raw_json = parts[1].strip()
    else:
        raw_json = content.strip()

    return json.loads(raw_json)


def parse_issue_body(body: Optional[str]) -> Dict[str, Any]:
    """Extract metadata sections from structured issue body."""
    if not body:
        return {}
    
    parsed = {}
    
    # Priority
    priority_match = re.search(r"\*\*Priority:\*\*\s*(P[0-9]+)", body, re.IGNORECASE)
    if priority_match:
        parsed["priority"] = priority_match.group(1).upper()
        
    # Owner fit
    owner_match = re.search(r"\*\*Owner fit:\*\*\s*([^\n\r]+)", body, re.IGNORECASE)
    if owner_match:
        parsed["owner_fit"] = owner_match.group(1).strip()
        
    # Dependency
    dep_match = re.search(r"\*\*Dependency:\*\*\s*([^\n\r]+)", body, re.IGNORECASE)
    if dep_match:
        parsed["dependency"] = dep_match.group(1).strip()

    # Why this task exists
    why_match = re.search(r"## Why this task exists\s*\n+([^#]+)", body)
    if why_match:
        raw_why = why_match.group(1).strip()
        # Remove trailing priority/owner/dependency if present before next section
        clean_why = re.split(r"\*\*Priority:\*\*", raw_why)[0].strip()
        parsed["why"] = clean_why

    # Pass criteria
    pass_match = re.search(r"## Pass criteria\s*\n+([^#]+)", body)
    if pass_match:
        criteria_lines = [
            line.strip("- [ ] ").strip("- [x] ").strip()
            for line in pass_match.group(1).strip().splitlines()
            if line.strip().startswith("- [")
        ]
        parsed["pass_criteria"] = criteria_lines

    return parsed


def estimate_difficulty(issue: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, str]:
    """Estimate implementation difficulty based on labels, dependencies, and scope."""
    labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    title = issue.get("title", "").lower()
    
    # Heuristics for difficulty
    if any(l in labels for l in ["track:cuda"]) or "cuda" in title:
        if "patch" in title or "dose-weight" in title:
            return {
                "level": "Very High",
                "score": "5/5",
                "rationale": "Requires custom CUDA kernels for grouped patches, 2D/3D spline/polynomial interpolation, FFT/CCF memory staging, and GPU dose weighting with numerical parity constraints."
            }
        return {
            "level": "High",
            "score": "4/5",
            "rationale": "GPU global alignment kernels (batched cuFFT, cross-correlation, subpixel peak finding) requiring precise floating-point parity with C++ reference."
        }
    elif any(l in labels for l in ["track:jax"]) or "jax" in title:
        if "patch" in title:
            return {
                "level": "High",
                "score": "4/5",
                "rationale": "Array-oriented patch cross-correlations, polynomial surface fitting in JAX, JIT compilation tuning, and MRC/STAR I/O."
            }
        return {
            "level": "Medium-High",
            "score": "3.5/5",
            "rationale": "Vectorized global shift estimation, 2D FFT, Hermitian symmetry layout handling, and JAX JIT compilation parity."
        }
    elif "bayesian" in title:
        return {
            "level": "High",
            "score": "4/5",
            "rationale": "Mathematical formulation of state-space/Gaussian process trajectory smoothing, hyperparameter selection, and edge condition handling without degrading default output."
        }
    elif "four-thread" in title or "deterministic" in title:
        return {
            "level": "Medium-High",
            "score": "3.5/5",
            "rationale": "Debugging non-deterministic OpenMP reductions, parallel FFTW plan concurrency, defect correction state, and floating-point associativity."
        }
    elif "optimize" in title or "bottleneck" in title:
        return {
            "level": "Medium",
            "score": "3/5",
            "rationale": "Profiling-guided single bottleneck optimization in CPU runner (e.g. FFT buffer reuse, threading, SIMD) preserving bit-exact single-thread output."
        }
    elif "patch fit failures" in title:
        return {
            "level": "Medium",
            "score": "3/5",
            "rationale": "Improving diagnostics, logging valid patch count and RMSD, robust fallback mechanism when 18-parameter polynomial fit diverges."
        }
    elif "dose-weighting" in title:
        return {
            "level": "Medium",
            "score": "3/5",
            "rationale": "Testing and validating critical dose-weighting curves (100/200/300 kV), odd/even sum outputs, and MRC/STAR output contracts."
        }
    elif "eer" in title:
        return {
            "level": "Medium-High",
            "score": "3.5/5",
            "rationale": "Falcon 4 EER event decoding/rendering, frame grouping, upsampling, and gain application across variable format edge cases."
        }
    elif "linux ci" in title or "ci" in title:
        return {
            "level": "Low-Medium",
            "score": "2/5",
            "rationale": "Setting up GitHub Actions Linux runner with CMake, FFTW3, OpenMP, LibTIFF, and running a smoke fixture."
        }
    elif "document" in title or "release" in title:
        return {
            "level": "Low",
            "score": "1.5/5",
            "rationale": "Documentation, license notices, clean checkout validation, and release checklist definition."
        }
    elif "profile" in title:
        return {
            "level": "Low-Medium",
            "score": "2/5",
            "rationale": "Executing benchmark suite on representative movies, collecting stage timer metrics, RSS, and writing profile report."
        }
    elif "reference outputs" in title:
        return {
            "level": "Medium",
            "score": "2.5/5",
            "rationale": "Establishing baseline ground truth fixtures, normalization scripts, and numerical parity metrics."
        }
    elif "compare all 24" in title:
        return {
            "level": "Medium",
            "score": "2.5/5",
            "rationale": "Automated dataset test harness running 24 RELION SPA tutorial movies and comparing STAR files and MRC RMSE against RELION 5.1."
        }
    else:
        return {
            "level": "Medium",
            "score": "2.5/5",
            "rationale": "Standard development and validation task."
        }


def format_markdown_summary(issues: List[Dict[str, Any]]) -> str:
    """Format issues into a comprehensive markdown summary."""
    lines = []
    lines.append("# GitHub Issues Summary: MotionCorr-standalone\n")
    lines.append(f"Total entries: **{len(issues)}**\n")
    
    # Separate PRs and Issues
    prs = [i for i in issues if "pull_request" in i]
    open_issues = [i for i in issues if "pull_request" not in i and i.get("state") == "open"]
    closed_issues = [i for i in issues if "pull_request" not in i and i.get("state") == "closed"]

    lines.append("## Overview\n")
    lines.append(f"- **Open Issues:** {len(open_issues)}")
    lines.append(f"- **Closed Issues:** {len(closed_issues)}")
    lines.append(f"- **Pull Requests (Merged/Closed):** {len(prs)}\n")

    lines.append("## Detailed Issue Breakdown\n")

    sorted_issues = sorted(issues, key=lambda x: x.get("number", 0))
    for issue in sorted_issues:
        num = issue.get("number")
        title = issue.get("title")
        state = issue.get("state")
        is_pr = "pull_request" in issue
        body = issue.get("body", "")
        meta = parse_issue_body(body)
        diff = estimate_difficulty(issue, meta)
        labels = [l.get("name") for l in issue.get("labels", [])]

        item_type = "PR" if is_pr else "Issue"
        status_icon = "[OPEN]" if state == "open" else "[PR]" if is_pr else "[CLOSED]"
        
        lines.append(f"### {status_icon} #{num}: {title} ({item_type} - {state.upper()})")
        lines.append(f"- **Type / State:** `{item_type}` | `{state}`")
        if labels:
            lines.append(f"- **Labels:** {', '.join([f'`{l}`' for l in labels])}")
        if meta.get("priority"):
            lines.append(f"- **Priority:** `{meta['priority']}`")
        if meta.get("dependency"):
            lines.append(f"- **Dependencies:** `{meta['dependency']}`")
        if meta.get("owner_fit"):
            lines.append(f"- **Owner Fit:** {meta['owner_fit']}")
        
        lines.append(f"- **Estimated Difficulty:** **{diff['level']}** ({diff['score']})")
        lines.append(f"  - *Rationale:* {diff['rationale']}")

        if meta.get("why"):
            lines.append(f"- **Objective:** {meta['why']}")

        if meta.get("pass_criteria"):
            lines.append("- **Key Acceptance Criteria:**")
            for crit in meta["pass_criteria"][:4]:
                lines.append(f"  - {crit}")

        lines.append("")

    return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Parse GitHub issues and assess implementation difficulty.")
    parser.add_argument("--repo", help="GitHub repo in 'owner/repo' format")
    parser.add_argument("--file", help="Path to local JSON / cached markdown file")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="all", help="Issue state filter")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    parser.add_argument("--output", help="Output destination file (stdout if omitted)")

    args = parser.parse_args()

    if not args.repo and not args.file:
        parser.error("Either --repo or --file must be provided.")

    if args.file:
        issues = load_issues_from_file(args.file)
    else:
        issues = fetch_issues_from_api(args.repo, state=args.state)

    if args.state != "all":
        issues = [i for i in issues if i.get("state") == args.state]

    if args.format == "json":
        enriched = []
        for issue in issues:
            meta = parse_issue_body(issue.get("body", ""))
            diff = estimate_difficulty(issue, meta)
            item = {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "is_pr": "pull_request" in issue,
                "labels": [l.get("name") for l in issue.get("labels", [])],
                "metadata": meta,
                "difficulty": diff,
            }
            enriched.append(item)
        out_content = json.dumps(enriched, indent=2)
    else:
        out_content = format_markdown_summary(issues)

    if args.output:
        Path(args.output).write_text(out_content, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(out_content)


if __name__ == "__main__":
    main()
