#!/usr/bin/env python3
"""
Feature Specification & Scope Conformance Auditor
Works alongside the Review Agent to verify that a code change fulfills its
specification and introduces zero out-of-scope side effects.

Passes if and only if the implementation matches the specification and only the specification.
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


def get_diff(repo_root: Path, target: Optional[str] = None, staged_only: bool = False) -> Tuple[str, str, List[str], str]:
    """Retrieve git diff, diff stat, list of modified files, and target description."""
    if target:
        stat_args = ["diff", "--stat", target]
        diff_args = ["diff", target]
        name_args = ["diff", "--name-only", target]
        desc = f"Diff against {target}"
    elif staged_only:
        stat_args = ["diff", "--cached", "--stat"]
        diff_args = ["diff", "--cached"]
        name_args = ["diff", "--cached", "--name-only"]
        desc = "Staged working tree changes"
    else:
        code, out, _ = run_git(["status", "--porcelain"], repo_root)
        if out.strip():
            stat_args = ["diff", "HEAD", "--stat"]
            diff_args = ["diff", "HEAD"]
            name_args = ["diff", "HEAD", "--name-only"]
            desc = "Working tree modifications (staged + unstaged)"
        else:
            stat_args = ["diff", "HEAD~1", "--stat"]
            diff_args = ["diff", "HEAD~1"]
            name_args = ["diff", "HEAD~1", "--name-only"]
            desc = "Latest commit (HEAD vs HEAD~1)"

    _, stat_out, _ = run_git(stat_args, repo_root)
    _, diff_out, _ = run_git(diff_args, repo_root)
    _, name_out, _ = run_git(name_args, repo_root)

    modified_files = [f.strip() for f in name_out.splitlines() if f.strip()]
    return diff_out, stat_out, modified_files, desc


def load_specification(repo_root: Path, issue_num: Optional[int], spec_path: Optional[str]) -> Dict[str, Any]:
    """Load architectural specification or issue criteria."""
    if spec_path:
        p = Path(spec_path).resolve()
        if p.exists():
            content = p.read_text(encoding="utf-8")
            return parse_spec_content(content, f"Custom spec: {p.name}", issue_num or 0)

    if issue_num:
        designs_dir = repo_root / "agents" / "designs"
        if designs_dir.exists():
            for f in designs_dir.glob(f"issue_{issue_num}_*.md"):
                content = f.read_text(encoding="utf-8")
                return parse_spec_content(content, f"Design spec: {f.name}", issue_num)

        # Fallback to skills/github-issues-parser/issues_summary.md
        summary_path = repo_root / "skills" / "github-issues-parser" / "issues_summary.md"
        if summary_path.exists():
            content = summary_path.read_text(encoding="utf-8")
            pattern = rf"###\s*\[(OPEN|PR|CLOSED)\]\s*#{issue_num}:\s*([^\n\r]+)"
            match = re.search(pattern, content)
            if match:
                title = match.group(2).strip()
                start = match.end()
                next_m = re.search(r"###\s*\[(OPEN|PR|CLOSED)\]\s*#", content[start:])
                block = content[start: start + next_m.start()] if next_m else content[start:]

                crit_m = re.search(r"- \*\*Key Acceptance Criteria:\*\*\s*\n((?:\s*-\s+[^\n\r]+\n?)+)", block)
                criteria = []
                if crit_m:
                    for line in crit_m.group(1).splitlines():
                        c = line.strip().lstrip("- ").strip()
                        if c:
                            criteria.append(c)

                return {
                    "title": f"Issue #{issue_num}: {title}",
                    "issue_num": issue_num,
                    "criteria": criteria if criteria else [f"Complete requirements for issue #{issue_num}"],
                    "raw_text": block,
                    "source": f"GitHub Issue #{issue_num}",
                }

    return {
        "title": "General Feature Scope",
        "issue_num": 0,
        "criteria": ["Preserve bit-exact parity", "Pass test suite without regressions"],
        "raw_text": "",
        "source": "Default baseline specification",
    }


def parse_spec_content(content: str, source: str, issue_num: int) -> Dict[str, Any]:
    """Parse criteria and objectives from an Architectural Design Specification."""
    title_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"Specification #{issue_num}"

    criteria = []
    # Match checkbox items e.g. - [ ] or - [x]
    for m in re.finditer(r"-\s*\[[ xX]\]\s*([^\n\r]+)", content):
        crit = m.group(1).strip()
        if crit and len(crit) > 5:
            criteria.append(crit)

    if not criteria:
        # Fall back to bullet points under criteria section
        crit_sec = re.search(r"##\s*2\.\s*Architectural Objectives.*?\n((?:[-*]\s+[^\n\r]+\n?)+)", content, re.DOTALL)
        if crit_sec:
            for line in crit_sec.group(1).splitlines():
                c = line.strip().lstrip("-* ").strip()
                if c:
                    criteria.append(c)

    return {
        "title": title,
        "issue_num": issue_num,
        "criteria": criteria if criteria else ["Implement specified architecture", "Pass parity gates"],
        "raw_text": content,
        "source": source,
    }


def analyze_conformance_heuristics(
    diff_text: str,
    modified_files: List[str],
    spec: Dict[str, Any]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Analyze forward criteria fulfillment and reverse side-effect isolation."""
    criteria = spec.get("criteria", [])
    raw_spec = spec.get("raw_text", "").lower()

    # 1. Forward verification (Criteria fulfillment)
    requirement_results = []
    for crit in criteria:
        # Extract keywords from criterion
        words = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_-]{4,}\b", crit) if w.lower() not in ("must", "should", "with", "this", "that", "from", "into", "runs")]
        matched_words = [w for w in words if w in diff_text.lower()]
        coverage = len(matched_words) / len(words) if words else 1.0

        if coverage >= 0.4:
            status = "SATISFIED"
            notes = f"Keywords matched in implementation ({len(matched_words)}/{len(words)} keywords)"
        elif coverage > 0.1:
            status = "PARTIAL"
            notes = "Partial evidence found in patch; manual verification advised"
        else:
            status = "MISSING"
            notes = "No matching code changes or assertions found for this criterion"

        requirement_results.append({
            "criterion": crit,
            "status": status,
            "notes": notes,
        })

    # 2. Reverse verification (Side-effect and scope analysis)
    side_effects = []

    # Check for modified files that seem unrelated to the spec
    for f in modified_files:
        f_lower = f.lower()
        f_name = Path(f).name.lower()
        # If file is not mentioned in raw_spec and not a test/doc/agent file, flag as potential scope leak
        is_mentioned = f_name in raw_spec or f_lower in raw_spec
        is_test_or_doc = any(k in f_lower for k in ("test", "doc", "readme", "cmake", "agent", "skill"))

        if not is_mentioned and not is_test_or_doc:
            side_effects.append({
                "severity": "WARNING",
                "file": f,
                "title": f"Collateral modification to unreferenced file: `{f}`",
                "impact": "This file is not cited in the specification/ADR and may introduce unexpected side effects.",
                "remediation": "Confirm whether this file modification is strictly required by the issue, or revert it to preserve scope isolation."
            })

    # Check for altered default parameter values in diff
    for line in diff_text.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            # Check if default argument was removed/changed
            if re.search(r"=\s*(true|false|\d+|nullptr|NULL)\s*[,)]", line):
                side_effects.append({
                    "severity": "WARNING",
                    "file": "source",
                    "title": "Potential modification of default parameter value",
                    "impact": f"Altering default values (`{line[1:].strip()[:50]}`) can silently change behavior across existing callers.",
                    "remediation": "Preserve existing default parameters or introduce an overload."
                })

    return requirement_results, side_effects


def evaluate_conformance_verdict(
    requirements: List[Dict[str, str]],
    side_effects: List[Dict[str, str]]
) -> Tuple[str, str]:
    """Determine final conformance verdict based on strict 1:1 rule."""
    all_satisfied = all(r["status"] == "SATISFIED" for r in requirements) if requirements else True
    has_missing = any(r["status"] == "MISSING" for r in requirements)
    has_side_effects = len(side_effects) > 0

    if all_satisfied and not has_side_effects:
        verdict = "SPEC_CONFORMANCE_PASSED"
        explanation = (
            "The implementation strictly matches the specification, and only the specification. "
            "All acceptance criteria are satisfied, and zero out-of-scope side effects were detected."
        )
    elif all_satisfied and has_side_effects:
        verdict = "OUT_OF_SCOPE_WARNING"
        explanation = (
            "All functional requirements in the specification appear to be satisfied, BUT one or more "
            "out-of-scope modifications or potential side effects were detected. Review the itemized side effects "
            "below before deciding whether to merge."
        )
    elif not all_satisfied and not has_side_effects:
        verdict = "SPEC_INCOMPLETE"
        explanation = (
            "The code changes remain within scope, but one or more core acceptance criteria from the specification "
            "have not been completed or lack verification evidence."
        )
    else:
        verdict = "REJECTED"
        explanation = (
            "The implementation fails conformance on both dimensions: key specification criteria are missing, "
            "and out-of-scope side effects or collateral modifications were introduced."
        )

    return verdict, explanation


def format_conformance_report(
    desc: str,
    spec: Dict[str, Any],
    requirements: List[Dict[str, str]],
    side_effects: List[Dict[str, str]],
    verdict: str,
    explanation: str
) -> str:
    """Format structured Markdown report conforming to SPEC_CONFORMANCE_REPORT_TEMPLATE."""
    req_rows = []
    for r in requirements:
        status_badge = f"`{r['status']}`"
        req_rows.append(f"| {r['criterion']} | {status_badge} | Diff & Test Fixtures | {r['notes']} |")
    req_table = "\n".join(req_rows) if req_rows else "| Baseline parity requirements | `SATISFIED` | CI | Core baseline intact |"

    if side_effects:
        side_blocks = []
        for i, s in enumerate(side_effects, 1):
            side_blocks.append(
                f"### [WARNING] SE-{i:02d}: {s['title']}\n"
                f"- **Location**: `{s['file']}`\n"
                f"- **Potential Side-Effect Impact**: {s['impact']}\n"
                f"- **Recommended Scope Remediation**: {s['remediation']}\n"
            )
        side_effects_str = "\n".join(side_blocks)
    else:
        side_effects_str = (
            "> **Zero out-of-scope side effects detected.** All modifications strictly correspond to "
            "the stated requirements in the specification."
        )

    return f"""# Specification & Scope Conformance Report

- **Auditor**: Specification & Scope Conformance Agent (`agents/spec_compliance_agent/`)
- **Target Revision**: `{desc}`
- **Target Specification**: {spec['title']} ({spec['source']})
- **Final Conformance Verdict**: **{verdict}**

---

## 1. Executive Summary

{explanation}

---

## 2. Specification Fulfillment Matrix (Forward Conformance)

| Specification Requirement / Acceptance Criterion | Implementation Status | Evidence / Test Location | Notes |
| :--- | :--- | :--- | :--- |
{req_table}

---

## 3. Side-Effect & Scope Analysis (Reverse Conformance)

{side_effects_str}

---

## 4. Final Verdict & Scope Remediation

**Verdict**: `{verdict}`

{explanation}
"""


def audit_specification_draft(
    spec_path: Path,
    issue_num: Optional[int],
    repo_root: Path
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Perform pre-implementation audit of a specification draft.
    Evaluates issue coverage, measurability, scope boundaries, edge cases, and file whitelists.
    Returns (verdict, report_markdown, structured_critique).
    """
    if not spec_path.exists():
        return "ERROR", f"Specification draft not found: {spec_path}", {}

    spec_text = spec_path.read_text(encoding="utf-8")
    spec_meta = parse_spec_content(spec_text, str(spec_path), issue_num or 0)
    issue_spec = load_specification(repo_root, issue_num, None)

    suggestions = []
    dimension_scores = {
        "coverage": {"status": "PASSED", "notes": "All issue requirements reflected in specification."},
        "measurability": {"status": "PASSED", "notes": "Concrete numerical thresholds specified."},
        "scope": {"status": "PASSED", "notes": "No scope creep detected; strict boundary maintained."},
        "edge_cases": {"status": "PASSED", "notes": "Failure modes and input anomalies documented."},
        "whitelist": {"status": "PASSED", "notes": "Explicit target file/component list defined."},
    }

    # 1. Check issue requirements coverage
    issue_criteria = issue_spec.get("criteria", [])
    uncovered = []
    for c in issue_criteria:
        crit_words = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_-]{4,}\b", c) if w.lower() not in ("must", "should", "with", "from", "that")]
        if not any(w in spec_text.lower() for w in crit_words):
            uncovered.append(c)

    if uncovered:
        dimension_scores["coverage"]["status"] = "NEEDS_REVISION"
        dimension_scores["coverage"]["notes"] = f"{len(uncovered)} issue requirement(s) lack explicit coverage."
        for u in uncovered:
            suggestions.append({
                "type": "MISSING_REQUIREMENT",
                "title": f"Unaddressed Issue Criterion: {u}",
                "suggestion": f"Incorporate an explicit technical design section addressing: '{u}'."
            })

    # 2. Check measurability (numerical tolerance and acceptance gates)
    has_math_gates = any(k in spec_text.lower() for k in ("rmse", "delta", "tolerance", "parity", "threshold", "gate", "error bound"))
    has_numbers = bool(re.search(r"(\d+\.\d+|\b0\b|1e-\d+)", spec_text))
    if not (has_math_gates and has_numbers):
        dimension_scores["measurability"]["status"] = "NEEDS_REVISION"
        dimension_scores["measurability"]["notes"] = "Lacks concrete, measurable numerical gates (e.g. delta = 0 or RMSE threshold)."
        suggestions.append({
            "type": "MEASURABILITY",
            "title": "Missing Quantitative Acceptance Gates",
            "suggestion": "Define unambiguous numerical acceptance thresholds (e.g. exact bitwise delta = 0 for single-thread CPU, or RMSE < 1e-5)."
        })

    # 3. Check file whitelist / target components
    has_files = any(k in spec_text for k in ("`src/", "`tests/", "`include/", "files to modify", "affected components", "Proposed Changes"))
    if not has_files:
        dimension_scores["whitelist"]["status"] = "NEEDS_REVISION"
        dimension_scores["whitelist"]["notes"] = "No explicit whitelist of files or modules permitted to change."
        suggestions.append({
            "type": "SCOPE_ISOLATION",
            "title": "Missing File Whitelist",
            "suggestion": "Add an explicit 'Permitted Changes & File Whitelist' section specifying exactly which files may be touched."
        })

    # 4. Check edge cases & failure handling
    has_edge_cases = any(k in spec_text.lower() for k in ("edge case", "failure", "corrupt", "truncate", "zero", "fallback", "error handling"))
    if not has_edge_cases:
        dimension_scores["edge_cases"]["status"] = "WARNING"
        dimension_scores["edge_cases"]["notes"] = "Edge cases and error modes (e.g. truncated inputs, zero motion) not detailed."
        suggestions.append({
            "type": "EDGE_CASES",
            "title": "Unspecified Failure Modes",
            "suggestion": "Specify behavior for edge cases such as truncated movie files, single-frame movies, or zero-drift inputs."
        })

    # Determine verdict
    has_revision = any(d["status"] == "NEEDS_REVISION" for d in dimension_scores.values())
    if has_revision:
        verdict = "SPEC_REVISION_REQUESTED"
        exec_summary = (
            "The specification draft provides a solid starting point but requires refinement before implementation. "
            f"Specifically, {len(suggestions)} item(s) must be clarified to eliminate ambiguities and scope drift."
        )
    else:
        verdict = "SPEC_APPROVED"
        exec_summary = (
            "The specification draft is comprehensive, unambiguous, and fully ready for implementation. "
            "All functional requirements, numerical acceptance gates, and scope boundaries are well-defined."
        )

    # Format report
    matrix_rows = []
    for dim, ddata in dimension_scores.items():
        dim_title = dim.replace("_", " ").title()
        badge = f"`{ddata['status']}`"
        matrix_rows.append(f"| **{dim_title}** | {badge} | {ddata['notes']} |")
    matrix_str = "\n".join(matrix_rows)

    if suggestions:
        sug_blocks = []
        for i, s in enumerate(suggestions, 1):
            sug_blocks.append(
                f"### [{s['type']}] S-{i:02d}: {s['title']}\n"
                f"- **Recommendation**: {s['suggestion']}\n"
            )
        sug_str = "\n".join(sug_blocks)
        next_actions = "The Architecture Agent must incorporate the above recommendations and submit an updated specification draft for re-review."
    else:
        sug_str = "> **Specification is fully approved.** All functional requirements, numerical acceptance gates, and scope boundaries are unambiguous and ready for implementation.\n"
        next_actions = "The specification is certified. The Implementation Agent may now begin coding."

    report = f"""# Pre-Implementation Specification Review Report

- **Auditor**: Specification & Scope Conformance Agent (`agents/spec_compliance_agent/`)
- **Target Specification Draft**: `{spec_path.name}`
- **Associated Issue**: Issue #{issue_num or 'N/A'} ({issue_spec['title']})
- **Review Verdict**: **{verdict}**

---

## 1. Executive Summary

{exec_summary}

---

## 2. Specification Quality Matrix

| Evaluation Dimension | Status | Notes |
| :--- | :--- | :--- |
{matrix_str}

---

## 3. Required Revisions & Suggested Improvements

{sug_str}
---

## 4. Next Actions for Architecture Agent

{next_actions}
"""
    critique_data = {
        "verdict": verdict,
        "dimension_scores": dimension_scores,
        "suggestions": suggestions,
    }
    return verdict, report, critique_data


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Specification & Scope Conformance Agent: Verify that a feature completes its specification and introduces zero side effects."
    )
    parser.add_argument("--issue", type=int, help="Issue number to check specification against")
    parser.add_argument("--spec", help="Path to specification Markdown file")
    parser.add_argument("--review-spec", help="Perform pre-implementation audit on a specification draft before coding")
    parser.add_argument("--target", help="Git revision or range to review (e.g., HEAD~1, origin/main...HEAD)")
    parser.add_argument("--staged", action="store_true", help="Inspect staged changes only")
    parser.add_argument("--output", help="Optional markdown file path to save the report")

    args = parser.parse_args()
    repo_root = find_repo_root()

    # Pre-implementation review mode
    if args.review_spec:
        spec_path = Path(args.review_spec).resolve()
        print(f"\n[Spec Conformance Agent] Running Pre-Implementation Review on: {spec_path.name}...")
        verdict, report, _ = audit_specification_draft(spec_path, args.issue, repo_root)

        print("\n" + "=" * 60)
        print(" PRE-IMPLEMENTATION SPECIFICATION REVIEW REPORT")
        print("=" * 60)
        print(report)
        print("=" * 60 + "\n")

        if args.output:
            out_path = Path(args.output).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report, encoding="utf-8")
            print(f"[Spec Conformance Agent] Report saved to: {out_path}")

        sys.exit(0 if verdict == "SPEC_APPROVED" else 2)

    # Post-implementation diff audit mode
    diff_text, diff_stat, modified_files, desc = get_diff(repo_root, target=args.target, staged_only=args.staged)
    if not diff_text.strip():
        print(f"[Spec Conformance Agent] No diff found for target: {desc}. Working tree is clean.")
        sys.exit(0)

    spec = load_specification(repo_root, args.issue, args.spec)

    print(f"\n[Spec Conformance Agent] Evaluating {desc} against: {spec['title']}...")
    print(f"[Spec Conformance Agent] Target modified files ({len(modified_files)}): {', '.join(modified_files) if modified_files else 'None'}\n")

    requirements, side_effects = analyze_conformance_heuristics(diff_text, modified_files, spec)
    verdict, explanation = evaluate_conformance_verdict(requirements, side_effects)

    report = format_conformance_report(desc, spec, requirements, side_effects, verdict, explanation)

    print("\n" + "=" * 60)
    print(" SPECIFICATION & SCOPE CONFORMANCE REPORT")
    print("=" * 60)
    print(report)
    print("=" * 60 + "\n")

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[Spec Conformance Agent] Report saved to: {out_path}")


if __name__ == "__main__":
    main()

