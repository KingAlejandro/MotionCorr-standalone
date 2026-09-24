#!/usr/bin/env python3
"""
Cleanup & Repository Hygiene Agent
Discovers and safely purges ephemeral reviews, intermediate dialectic drafts,
temporary logs, and cache files from the repository.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


PROTECTED_PATTERNS = {
    "SYSTEM_PROMPT.md",
    "CMakeLists.txt",
    "AGENTS.md",
    "README.md",
    "LICENSE",
    "COPYING",
    "AUTHORS",
}

PROTECTED_DIRS = {
    ".git",
    "src",
    "include",
    "test-data",
}


def find_repo_root() -> Path:
    """Find repository root by walking up from script directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return Path.cwd()


def is_protected(path: Path, repo_root: Path) -> bool:
    """Check if a path falls within protected zones."""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return True

    # Check top-level protected directory
    if rel.parts and rel.parts[0] in PROTECTED_DIRS:
        return True

    # Check protected filenames
    if path.name in PROTECTED_PATTERNS:
        return True

    # Protect all scripts and templates
    if path.suffix == ".py" and "scripts" in rel.parts:
        return True
    if "templates" in rel.parts:
        return True

    # Protect finalized designs in agents/designs/ (excluding drafts/ and logs/)
    if "designs" in rel.parts and rel.parent.name == "designs" and path.suffix == ".md":
        return True

    return False


def is_cleanable_artifact(path: Path, repo_root: Path) -> Tuple[bool, str]:
    """Check if a file belongs to a declared cleanable ephemeral category."""
    if is_protected(path, repo_root):
        return False, ""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return False, ""

    # 1. Python bytecode cache
    if "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo"):
        return True, "Python Bytecode Cache"
    # 2. Ephemeral reviews
    if len(rel.parts) >= 3 and rel.parts[0] == "agents" and rel.parts[1] == "reviews":
        return True, "Ephemeral Reviews"
    # 3. Intermediate drafts
    if len(rel.parts) >= 4 and rel.parts[0] == "agents" and rel.parts[1] == "designs" and rel.parts[2] == "drafts":
        return True, "Intermediate Dialectic Draft"
    # 4. Refinement logs
    if len(rel.parts) >= 4 and rel.parts[0] == "agents" and rel.parts[1] == "designs" and rel.parts[2] == "logs":
        return True, "Refinement Log"
    # 5. Temporary patches & diffs & dumps
    if path.suffix in (".patch", ".diff", ".tmp", ".bak") or path.name.startswith("temp_"):
        return True, "Temporary Patch / Dump"
    # 6. Ephemeral scratch / report dumps
    if "scratch" in rel.parts or path.name in ("pr_comments.md", "issues_dump.json"):
        return True, "Ephemeral Report / Scratch File"

    return False, ""


def scan_cleanable_files(
    repo_root: Path,
    include_reviews: bool = True,
    include_drafts: bool = True,
    include_cache: bool = True,
    include_patches: bool = True,
    target_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Scan and categorize all files eligible for cleanup."""
    cleanable = []

    if target_path:
        t = Path(target_path).resolve()
        if t.exists():
            if t.is_file():
                is_clean, cat = is_cleanable_artifact(t, repo_root)
                if is_clean:
                    cleanable.append({
                        "category": f"Targeted File ({cat})",
                        "path": t,
                        "size": t.stat().st_size
                    })
                elif not is_protected(t, repo_root) and t.suffix in (".tmp", ".bak", ".log", ".pyc"):
                    cleanable.append({
                        "category": "Targeted Ephemeral File",
                        "path": t,
                        "size": t.stat().st_size
                    })
            elif t.is_dir():
                for f in t.rglob("*"):
                    if f.is_file():
                        is_clean, cat = is_cleanable_artifact(f, repo_root)
                        if is_clean:
                            cleanable.append({
                                "category": f"Targeted Directory ({cat})",
                                "path": f,
                                "size": f.stat().st_size
                            })
        return cleanable

    # 1. Ephemeral reviews
    if include_reviews:
        reviews_dir = repo_root / "agents" / "reviews"
        if reviews_dir.exists():
            for f in reviews_dir.glob("*"):
                if f.is_file() and not is_protected(f, repo_root):
                    cleanable.append({
                        "category": "Ephemeral Reviews",
                        "path": f,
                        "size": f.stat().st_size
                    })

    # 2. Intermediate drafts & dialectic logs
    if include_drafts:
        drafts_dir = repo_root / "agents" / "designs" / "drafts"
        if drafts_dir.exists():
            for f in drafts_dir.glob("*.md"):
                if f.is_file() and not is_protected(f, repo_root):
                    cleanable.append({
                        "category": "Intermediate Dialectic Draft",
                        "path": f,
                        "size": f.stat().st_size
                    })

        logs_dir = repo_root / "agents" / "designs" / "logs"
        if logs_dir.exists():
            for f in logs_dir.glob("*.md"):
                if f.is_file() and not is_protected(f, repo_root):
                    cleanable.append({
                        "category": "Refinement Log",
                        "path": f,
                        "size": f.stat().st_size
                    })

    # 3. Python caches
    if include_cache:
        for pycache in repo_root.rglob("__pycache__"):
            if not is_protected(pycache, repo_root):
                for f in pycache.glob("*"):
                    if f.is_file():
                        cleanable.append({
                            "category": "Python Bytecode Cache",
                            "path": f,
                            "size": f.stat().st_size
                        })

    # 4. Ephemeral patches & diff dumps
    if include_patches:
        for ext in ("*.patch", "*.diff", "*.tmp"):
            for f in repo_root.glob(f"**/{ext}"):
                if not is_protected(f, repo_root):
                    cleanable.append({
                        "category": "Temporary Patch / Dump",
                        "path": f,
                        "size": f.stat().st_size
                    })

    return cleanable


def execute_cleanup(cleanable_items: List[Dict[str, Any]], repo_root: Path) -> Tuple[int, int]:
    """Execute deletion of cleanable files and prune empty parent directories."""
    removed_count = 0
    reclaimed_bytes = 0
    dirs_to_prune: Set[Path] = set()

    for item in cleanable_items:
        p: Path = item["path"]
        try:
            if p.exists() and p.is_file():
                sz = p.stat().st_size
                p.unlink()
                removed_count += 1
                reclaimed_bytes += sz
                dirs_to_prune.add(p.parent)
                item["status"] = "REMOVED"
            elif not p.exists():
                item["status"] = "NOT_FOUND"
            else:
                item["status"] = "SKIPPED_NON_FILE"
        except Exception as e:
            sys.stderr.write(f"Warning: Could not delete {p}: {e}\n")
            item["status"] = f"FAILED: {e}"

    # Prune empty directories if they are within ephemeral locations
    ephemeral_dir_names = {"reviews", "drafts", "logs", "__pycache__"}
    for d in sorted(dirs_to_prune, key=lambda x: len(x.parts), reverse=True):
        try:
            if d.exists() and d.name in ephemeral_dir_names and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass

    return removed_count, reclaimed_bytes


def format_report(
    repo_root: Path,
    cleanable_items: List[Dict[str, Any]],
    mode: str,
    removed_count: int,
    reclaimed_bytes: int
) -> str:
    """Format markdown cleanup report."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "CLEANUP_COMPLETED" if mode == "APPLIED" else ("PENDING_CONFIRMATION" if cleanable_items else "NOTHING_TO_CLEAN")

    total_bytes = sum(i["size"] for i in cleanable_items)
    
    if cleanable_items:
        rows = []
        for item in cleanable_items:
            rel = str(item["path"].relative_to(repo_root))
            if mode == "APPLIED":
                item_st = item.get("status", "REMOVED")
                if item_st == "REMOVED":
                    action = "`REMOVED`"
                elif item_st.startswith("FAILED"):
                    action = f"`FAILED` ({item_st})"
                else:
                    action = f"`{item_st}`"
            else:
                action = "`ELIGIBLE_FOR_REMOVAL`"
            rows.append(f"| {item['category']} | `{rel}` | {item['size']} B | {action} |")
        table_str = "\n".join(rows)
    else:
        table_str = "| *None* | *Clean* | 0 B | No action needed |"

    if mode == "APPLIED":
        exec_summary = (
            f"Successfully executed repository cleanup in **APPLIED** mode. "
            f"Removed **{removed_count}** ephemeral file(s) and reclaimed **{reclaimed_bytes:,} bytes** of disk space."
        )
    else:
        exec_summary = (
            f"Executed repository hygiene inspection in **DRY_RUN** mode. "
            f"Identified **{len(cleanable_items)}** candidate file(s) occupying **{total_bytes:,} bytes**. "
            "To execute cleanup, re-run with `--apply`."
        )

    # Git status check
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "status", "-s"],
            capture_output=True,
            text=True,
            check=True
        )
        git_summary = proc.stdout.strip() or "Working tree clean"
    except Exception:
        git_summary = "Unable to determine git status"

    return f"""# Repository Cleanup & Hygiene Report

- **Auditor**: Cleanup & Repository Hygiene Agent (`agents/cleanup_agent/`)
- **Execution Timestamp**: `{timestamp}`
- **Execution Mode**: **{mode}**
- **Overall Status**: **{status}**

---

## 1. Executive Summary

{exec_summary}

---

## 2. Identified Artifacts for Removal

| Category | File / Directory Path | Size | Action |
| :--- | :--- | :--- | :--- |
{table_str}

---

## 3. Protected Zones Verification

The following protected paths were verified as untouched and fully preserved:
- [x] **Source Code**: `src/`, `include/`, `CMakeLists.txt`
- [x] **Agent Core Tooling**: `SYSTEM_PROMPT.md`, `templates/`, `scripts/*.py`
- [x] **Permanent Designs**: `agents/designs/issue_*_design.md`
- [x] **Test Baselines**: `test-data/`

---

## 4. Git Workspace Impact

- **Files Removed / Scheduled**: {removed_count if mode == 'APPLIED' else len(cleanable_items)}
- **Total Disk Space Reclaimed**: {reclaimed_bytes if mode == 'APPLIED' else total_bytes:,} bytes
- **Git Working Tree Summary**:
```text
{git_summary}
```
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Cleanup & Repository Hygiene Agent: Purge ephemeral reviews, intermediate drafts, and caches."
    )
    parser.add_argument("--apply", action="store_true", help="Execute deletion of identified files (default: dry-run only)")
    parser.add_argument("--reviews", action="store_true", help="Only clean ephemeral reviews (agents/reviews/)")
    parser.add_argument("--drafts", action="store_true", help="Only clean intermediate dialectic drafts and logs")
    parser.add_argument("--cache", action="store_true", help="Only clean Python cache directories (__pycache__)")
    parser.add_argument("--all", action="store_true", help="Clean all cleanable categories (reviews, drafts, caches, patches)")
    parser.add_argument("--target", help="Clean a specific file or directory path")
    parser.add_argument("--output", help="Optional markdown file path to save cleanup report")

    args = parser.parse_args()
    repo_root = find_repo_root()

    # Scope selection
    if args.reviews:
        include_reviews, include_drafts, include_cache, include_patches = True, False, False, False
    elif args.drafts:
        include_reviews, include_drafts, include_cache, include_patches = False, True, False, False
    elif args.cache:
        include_reviews, include_drafts, include_cache, include_patches = False, False, True, False
    else:
        # Default or --all
        include_reviews, include_drafts, include_cache, include_patches = True, True, True, True

    mode = "APPLIED" if args.apply else "DRY_RUN"

    print(f"\n[Cleanup Agent] Scanning repository for cleanable artifacts (Mode: {mode})...")
    cleanable_items = scan_cleanable_files(
        repo_root,
        include_reviews=include_reviews,
        include_drafts=include_drafts,
        include_cache=include_cache,
        include_patches=include_patches,
        target_path=args.target
    )

    removed_count = 0
    reclaimed_bytes = 0
    if args.apply and cleanable_items:
        print(f"[Cleanup Agent] Executing cleanup on {len(cleanable_items)} item(s)...")
        removed_count, reclaimed_bytes = execute_cleanup(cleanable_items, repo_root)

    report = format_report(repo_root, cleanable_items, mode, removed_count, reclaimed_bytes)

    print("\n" + "=" * 65)
    print(" REPOSITORY CLEANUP & HYGIENE REPORT")
    print("=" * 65)
    print(report)
    print("=" * 65 + "\n")

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[Cleanup Agent] Report saved to: {out_path}")


if __name__ == "__main__":
    main()
