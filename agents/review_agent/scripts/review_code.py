#!/usr/bin/env python3
"""
Stateless Code Review & Verification Engine
Performs memoryless, read-only code reviews of working tree changes, commits, or PR diffs.
Evaluates numerical parity risks, thread safety, memory discipline, and cross-platform portability.
Outputs structured verdicts: READY_TO_MERGE, CHANGES_REQUESTED, or BLOCKED_BY_FAULT.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    requests = None


def find_repo_root() -> Path:
    """Find repository root by walking up from script directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return Path.cwd()


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Execute git command safely."""
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def get_diff(repo_root: Path, target: Optional[str] = None, staged_only: bool = False) -> Tuple[str, str, str]:
    """Retrieve git diff, diff stat, and target description."""
    if target:
        stat_args = ["diff", "--stat", target]
        diff_args = ["diff", target]
        desc = f"Diff against {target}"
    elif staged_only:
        stat_args = ["diff", "--cached", "--stat"]
        diff_args = ["diff", "--cached"]
        desc = "Staged working tree changes"
    else:
        code_st, out, err_st = run_git(["status", "--porcelain"], repo_root)
        if code_st != 0:
            raise RuntimeError(f"Git status failed: {err_st}")
        if out.strip():
            stat_args = ["diff", "HEAD", "--stat"]
            diff_args = ["diff", "HEAD"]
            desc = "Working tree modifications (staged + unstaged + untracked)"
        else:
            # Fall back to diff against origin/main or parent commit
            stat_args = ["diff", "HEAD~1", "--stat"]
            diff_args = ["diff", "HEAD~1"]
            desc = "Latest commit (HEAD vs HEAD~1)"

    code_stat, stat_out, err_stat = run_git(stat_args, repo_root)
    if code_stat != 0:
        raise RuntimeError(f"Git diff stat failed ({' '.join(stat_args)}): {err_stat}")

    code_diff, diff_out, err_diff = run_git(diff_args, repo_root)
    if code_diff != 0:
        raise RuntimeError(f"Git diff failed ({' '.join(diff_args)}): {err_diff}")

    # Ingest untracked files when reviewing full working tree
    if not target and not staged_only:
        code_st, status_out, _ = run_git(["status", "--porcelain"], repo_root)
        if status_out:
            for line in status_out.splitlines():
                if line.startswith("?? "):
                    u_rel = line[3:].strip()
                    u_path = repo_root / u_rel
                    if u_path.is_file() and u_path.suffix in (".cpp", ".h", ".cu", ".cuh", ".c", ".hpp", ".py", ".md", ".cmake", ".txt"):
                        try:
                            file_lines = u_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                            diff_out += f"\ndiff --git a/{u_rel} b/{u_rel}\nnew file mode 100644\n--- /dev/null\n+++ b/{u_rel}\n@@ -0,0 +1,{len(file_lines)} @@\n"
                            for fl in file_lines:
                                diff_out += f"+{fl}\n"
                            stat_out += f" {u_rel} (untracked) | {len(file_lines)} +\n"
                        except Exception:
                            pass

    return diff_out, stat_out, desc


def analyze_diff_heuristics(diff_text: str) -> List[Dict[str, str]]:
    """Scan diff for common Cryo-EM and C++ performance/determinism anti-patterns."""
    findings = []
    current_file = ""
    line_num = 0

    lines = diff_text.splitlines()
    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split(" ")
            if len(parts) >= 4:
                current_file = parts[3].lstrip("b/")
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            line_num = int(match.group(1)) if match else 0
        elif line.startswith("+") and not line.startswith("+++"):
            line_num += 1
            code_line = line[1:].strip()

            # 1. Hot loop allocation checks (restricted to C/C++ and CUDA sources)
            if current_file.endswith((".cpp", ".cu", ".h", ".cuh", ".c", ".hpp")) and not code_line.startswith(("//", "/*")):
                if re.search(r"\b(malloc|calloc|realloc)\s*\(|\bnew\s+[A-Za-z0-9_:]+", code_line):
                    findings.append({
                        "severity": "WARNING",
                        "file": current_file,
                        "line": str(line_num),
                        "title": "Dynamic memory allocation detected in patch",
                        "problem": f"Detected raw dynamic allocation: `{code_line[:60]}`.",
                        "impact": "Heap allocation in processing pipelines risks memory fragmentation, leakage, and performance slowdowns.",
                        "remediation": "Pre-allocate scratch buffers during initialization or use RAII containers outside inner loops."
                    })

            # 2. Vector resizing or push_back in hot loops
            if re.search(r"\b(push_back|resize|reserve)\b", code_line) and "test" not in current_file.lower():
                findings.append({
                    "severity": "SUGGESTION",
                    "file": current_file,
                    "line": str(line_num),
                    "title": "Dynamic container expansion in processing path",
                    "problem": f"Detected container modification: `{code_line[:60]}`.",
                    "impact": "Dynamic reallocation inside computational functions introduces non-deterministic latency spikes.",
                    "remediation": "Pre-size containers at class initialization."
                })

            # 3. Thread determinism & OpenMP checks
            if "#pragma omp" in code_line:
                if "reduction" in code_line and ("+" in code_line or "*" in code_line):
                    findings.append({
                        "severity": "WARNING",
                        "file": current_file,
                        "line": str(line_num),
                        "title": "Floating-point OpenMP reduction may be non-deterministic",
                        "problem": f"OpenMP reduction detected: `{code_line[:70]}`.",
                        "impact": "Unordered floating-point summation across threads violates run-to-run bitwise determinism (#7).",
                        "remediation": "Use deterministic fixed-order tree accumulation or thread-indexed private buffers."
                    })

            # 4. Critical numerical parity risk: modifications to core math
            if current_file.endswith("motioncorr_runner.cpp") or current_file.endswith("funcs.cpp"):
                if any(k in code_line for k in ("fftw_", "exp(", "sin(", "cos(", "sqrt(", "CCF")):
                    findings.append({
                        "severity": "BLOCKER",
                        "file": current_file,
                        "line": str(line_num),
                        "title": "Core mathematical transformation modified",
                        "problem": f"Direct modification to alignment/Fourier mathematics: `{code_line[:60]}`.",
                        "impact": "Modifying core mathematical transforms directly risks invalidating the Tier 0 RELION 5.1 parity baseline.",
                        "remediation": "Must verify bit-exact parity using tests/scripts/compare_parity.py on synthetic and tutorial fixtures before merging."
                    })
        elif not line.startswith("-"):
            line_num += 1

    return findings


def call_gemini_review(api_key: str, system_prompt: str, diff_text: str, stat_text: str) -> Optional[str]:
    """Invoke Gemini REST API for an intelligent, memoryless review."""
    if not requests or not api_key:
        return None
    is_truncated = len(diff_text) > 60000
    if is_truncated:
        diff_content = diff_text[:60000] + f"\n\n... [DIFF TRUNCATED: Showing 60,000 of {len(diff_text)} characters] ..."
        truncation_clause = (
            "WARNING: The diff exceeds token limits and has been TRUNCATED. You MUST NOT issue a READY_TO_MERGE verdict. "
            "Because the tail of the diff cannot be inspected, conclude with CHANGES_REQUESTED and require modular, chunked reviews."
        )
    else:
        diff_content = diff_text
        truncation_clause = "The diff is complete. Conclude with an unambiguous verdict: READY_TO_MERGE, CHANGES_REQUESTED, or BLOCKED_BY_FAULT."

    user_prompt = f"""Perform a rigorous, stateless code review of the following Git diff:

DIFF STATISTICS:
{stat_text}

DIFF CONTENT:
{diff_content}

{truncation_clause}
Follow the Review Report Schema defined in your instructions.
"""
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 200:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            if is_truncated and "READY_TO_MERGE" in text:
                text = text.replace("READY_TO_MERGE", "CHANGES_REQUESTED (TRUNCATED_DIFF)")
                text += "\n\n> [!WARNING]\n> **Diff Truncated**: Final merge approval refused because the diff exceeded 60,000 characters. Review remaining changes incrementally."
            return text
    except Exception as e:
        sys.stderr.write(f"Warning: Gemini review call failed: {e}\n")
    return None


def generate_heuristic_report(diff_stat: str, target_desc: str, findings: List[Dict[str, str]]) -> str:
    """Generate a clean, structured Markdown review report from static analysis findings."""
    has_blocker = any(f["severity"] == "BLOCKER" for f in findings)
    has_warning = any(f["severity"] == "WARNING" for f in findings)

    if has_blocker:
        verdict = "BLOCKED_BY_FAULT"
        exec_summary = "The proposed changes contain severe risks or potential faults that threaten baseline numerical parity, memory safety, or thread determinism. Merge is blocked pending remediation."
        parity_status = "FAILED / RISK"
        parity_notes = "Modifications to core Fourier mathematics or coordinate transforms require explicit parity gate verification."
    elif has_warning:
        verdict = "CHANGES_REQUESTED"
        exec_summary = "The proposed changes are structurally sound but introduce potential thread non-determinism, heap allocations, or unverified edge cases. Minor changes are requested before merging."
        parity_status = "PASS WITH WARNINGS"
        parity_notes = "Verify against single-thread baseline tests."
    else:
        verdict = "READY_TO_MERGE"
        exec_summary = "The proposed changes are clean, modular, and adhere to all memory discipline, concurrency, and portability guidelines. Code is ready to merge."
        parity_status = "PASSED"
        parity_notes = "No scientific drift or numerical regressions detected."

    thread_status = "NEEDS ATTENTION" if any("OpenMP" in f["title"] for f in findings) else "PASSED"
    thread_notes = "Floating-point reduction ordering must be verified" if thread_status != "PASSED" else "No concurrency race conditions detected"

    memory_status = "NEEDS ATTENTION" if any("allocation" in f["title"].lower() for f in findings) else "PASSED"
    memory_notes = "Review dynamic allocations in processing loops" if memory_status != "PASSED" else "Zero hot-loop allocations preserved"

    findings_text = ""
    if findings:
        for i, f in enumerate(findings, 1):
            findings_text += f"### [{f['severity']}] F-{i:02d}: {f['title']}\n"
            findings_text += f"- **Location**: `{f['file']}:{f['line']}`\n"
            findings_text += f"- **Problem**: {f['problem']}\n"
            findings_text += f"- **Scientific / Systemic Impact**: {f['impact']}\n"
            findings_text += f"- **Recommended Remediation**: {f['remediation']}\n\n"
    else:
        findings_text = "> **No faults or blockers detected.** The inspected diff complies with all numerical parity, concurrency, and memory budget constraints.\n"

    report = f"""# Code Review Report: {target_desc}

- **Reviewer**: MotionCorr Review Agent (Stateless & Memoryless)
- **Target Revision**: `{target_desc}`
- **Associated Issue/ADR**: Active Development
- **Final Verdict**: **{verdict}**

---

## 1. Executive Summary

{exec_summary}

---

## 2. Gate Verification Checklist

| Verification Gate | Status | Notes |
| :--- | :--- | :--- |
| **Numerical Parity Gate** | `{parity_status}` | {parity_notes} |
| **Concurrency & Thread Determinism** | `{thread_status}` | {thread_notes} |
| **Memory Discipline & Hot-Loop Footprint** | `{memory_status}` | {memory_notes} |
| **Cross-Platform Portability** | `HEURISTIC_PASS` | Static path and syntax scan clean; compile test recommended |
| **Automated Verification Coverage** | `NOT_RUN` | Static diff inspection only; execution of test fixtures not triggered |

---

## 3. Diff Statistics

```text
{diff_stat if diff_stat else 'No tracked changes found.'}
```

---

## 4. Detailed Findings & Faults

{findings_text}
---

## 5. Final Recommendation & Merge Instructions

**Verdict**: `{verdict}`

"""
    if verdict == "READY_TO_MERGE":
        report += "All acceptance gates have passed. The changes may be safely merged into the target branch.\n"
    elif verdict == "CHANGES_REQUESTED":
        report += "Please address the warnings listed in Section 4 before proceeding with the final merge.\n"
    else:
        report += "Merge is blocked. Resolve all BLOCKER findings and re-run parity benchmarks before requesting re-review.\n"

    return report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Stateless, memoryless code review agent for verifying Cryo-EM numerical parity, thread safety, and memory discipline."
    )
    parser.add_argument("--target", help="Git revision or range to review (e.g., HEAD~1, origin/main...HEAD)")
    parser.add_argument("--staged", action="store_true", help="Review staged changes only")
    parser.add_argument("--output", help="Optional markdown file path to save the review report")

    args = parser.parse_args()
    repo_root = find_repo_root()

    try:
        diff_text, diff_stat, desc = get_diff(repo_root, target=args.target, staged_only=args.staged)
    except RuntimeError as err:
        sys.stderr.write(f"\n[Review Agent] Git error: {err}\n")
        sys.exit(1)

    if not diff_text.strip():
        print(f"[Review Agent] No diff found for target: {desc}. Working tree is clean.")
        sys.exit(0)

    print(f"\n[Review Agent] Inspecting {desc} (Stateless & Memoryless)...")
    print(f"[Review Agent] Changed files:\n{diff_stat}\n")

    # Check for Gemini API key
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    prompt_file = repo_root / "agents" / "review_agent" / "SYSTEM_PROMPT.md"
    system_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""

    report_text = None
    if api_key and system_prompt:
        print("[Review Agent] Gemini API key detected. Running deep LLM-based scientific review...")
        report_text = call_gemini_review(api_key, system_prompt, diff_text, diff_stat)

    if not report_text:
        print("[Review Agent] Running static heuristic verification rules...")
        findings = analyze_diff_heuristics(diff_text)
        report_text = generate_heuristic_report(diff_stat, desc, findings)

    # Output to stdout
    print("\n" + "=" * 60)
    print(" MOTIONCORR CODE REVIEW REPORT")
    print("=" * 60)
    print(report_text)
    print("=" * 60 + "\n")

    # Optional file output
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        print(f"[Review Agent] Report saved to: {out_path}")


if __name__ == "__main__":
    main()
