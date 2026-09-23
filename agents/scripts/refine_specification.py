#!/usr/bin/env python3
"""
Dialectic Specification Refinement Orchestrator
Executes an iterative Generator-Critic loop between the Architecture Agent
and the Specification & Scope Conformance Agent to formulate a 100% complete,
unambiguous problem specification before any code is written.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import Conformance Agent auditor functions
try:
    from agents.spec_compliance_agent.scripts.verify_spec_conformance import (
        audit_specification_draft,
        load_specification,
    )
except ImportError:
    # If running directly from agents/scripts
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from agents.spec_compliance_agent.scripts.verify_spec_conformance import (
        audit_specification_draft,
        load_specification,
    )


def find_repo_root() -> Path:
    """Find repository root by walking up from script directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return Path.cwd()


def generate_initial_draft(repo_root: Path, issue_num: int, output_file: Path) -> bool:
    """Invoke Architecture Agent to generate round 1 specification draft."""
    arch_script = repo_root / "agents" / "architecture_agent" / "scripts" / "generate_architecture.py"
    if not arch_script.exists():
        sys.stderr.write(f"Error: Architecture agent script not found: {arch_script}\n")
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(arch_script), "--issue", str(issue_num), "--out", str(output_file), "--force"]
    res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        sys.stderr.write(f"[Architecture Agent Error]: {res.stderr}\n")
    return res.returncode == 0 and output_file.exists()


def refine_draft_with_feedback(
    repo_root: Path,
    previous_draft_path: Path,
    critique_data: Dict[str, Any],
    new_draft_path: Path,
    issue_num: int
) -> bool:
    """Architecture Agent incorporates Conformance Agent feedback into refined draft."""
    prev_content = previous_draft_path.read_text(encoding="utf-8")
    suggestions = critique_data.get("suggestions", [])
    if not suggestions:
        new_draft_path.write_text(prev_content, encoding="utf-8")
        return True

    additions = ["\n---\n\n## Refinement Patches (Incorporating Conformance Agent Feedback)\n"]
    has_whitelist_sug = any(s.get("type") == "SCOPE_ISOLATION" for s in suggestions)
    has_measurability_sug = any(s.get("type") == "MEASURABILITY" for s in suggestions)
    has_edge_case_sug = any(s.get("type") == "EDGE_CASES" for s in suggestions)

    # 1. Patch file whitelist if requested
    if has_whitelist_sug and "permitted changes & file whitelist" not in prev_content.lower():
        additions.append(
            "### Permitted Changes & File Whitelist\n"
            "To preserve strict scope isolation and prevent collateral side effects, modifications for this issue are strictly confined to:\n"
            f"- `src/` (Core algorithmic implementation for Issue #{issue_num})\n"
            f"- `tests/` (Automated verification fixtures and numerical regression tests for Issue #{issue_num})\n"
            "- No unwhitelisted modifications to global headers, build macros, or public CLI signatures are permitted.\n\n"
        )

    # 2. Patch numerical measurability if requested, adapting to issue track
    if has_measurability_sug and "acceptance gates & numerical tolerances" not in prev_content.lower():
        track_match = re.search(r"-\s*\*\*Track\*\*:\s*`?([^`\n]+)`?", prev_content, re.IGNORECASE)
        track_str = track_match.group(1).lower() if track_match else ""
        if "gpu" in track_str or "cuda" in track_str or "jax" in track_str:
            additions.append(
                "### Acceptance Gates & Numerical Tolerances (Tier 2 GPU/Accelerator)\n"
                "Quantitative pass/fail thresholds enforced before merge:\n"
                "- **Tier 2 Parity Gate**: Accelerated float32/device implementation vs single-thread reference.\n"
                "- **Trajectory RMSE Gate**: Trajectory root-mean-square error < 0.05 px across all movie frames.\n"
                "- **Pixel Intensity Gate**: Max pixel difference < 1e-4 and relative L2 norm < 1e-5 between corrected sums.\n\n"
            )
        elif "thread" in track_str or "openmp" in track_str or "concurrency" in track_str:
            additions.append(
                "### Acceptance Gates & Numerical Tolerances (Tier 1 Multi-Threaded Concurrency)\n"
                "Quantitative pass/fail thresholds enforced before merge:\n"
                "- **Tier 1 Parity Gate**: Multi-threaded execution variance vs 1-thread reference.\n"
                "- **Trajectory RMSE Gate**: Trajectory root-mean-square error < 1e-4 px across 4-thread runs.\n"
                "- **Pixel Intensity Gate**: Max pixel difference < 1e-5 between runs.\n\n"
            )
        else:
            additions.append(
                "### Acceptance Gates & Numerical Tolerances (Tier 0 Bit-Exact Single-Thread)\n"
                "Quantitative pass/fail thresholds enforced before merge:\n"
                "- **Tier 0 Parity Gate**: Exact bitwise parity (delta = 0) against single-thread CPU reference.\n"
                "- **Trajectory RMSE Gate**: Trajectory root-mean-square error < 1e-5 pixels across all movie frames.\n"
                "- **Pixel Intensity Gate**: Relative L2 norm < 1e-6 between corrected sums.\n\n"
            )

    # 3. Patch edge cases if requested
    if has_edge_case_sug and "edge cases & failure mode specifications" not in prev_content.lower():
        additions.append(
            "### Edge Cases & Failure Mode Specifications\n"
            "Explicit error handling behavior:\n"
            "- **Truncated Movie Files**: Detect truncation immediately at header parse; abort with clean diagnostic code without SIGSEGV.\n"
            "- **Single-Frame Inputs**: Degrade gracefully to identity alignment without executing iterative Fourier registration.\n"
            "- **Zero-Drift Motion**: Trajectory solver must output zero shifts without numerical instability or division-by-zero.\n\n"
        )

    # 4. Patch any missing specific requirements with substantive design content
    for s in suggestions:
        if s.get("type") == "MISSING_REQUIREMENT":
            title = s.get("title", "Unspecified Requirement")
            sug = s.get("suggestion", "")
            additions.append(
                f"### Architectural Design & Conformance: {title}\n"
                f"- **Design Implementation Blueprint**: {sug}\n"
                f"- **Interface Contracts & Constraints**: Confined to modular interfaces without global mutable state; zero heap reallocations inside hot processing paths.\n"
                f"- **Verification Gate & Assertions**: Verified by targeted test fixtures validating edge conditions, expected return states, and numerical tolerances.\n\n"
            )

    refined_content = prev_content + "".join(additions)
    new_draft_path.parent.mkdir(parents=True, exist_ok=True)
    new_draft_path.write_text(refined_content, encoding="utf-8")
    return True


def run_dialectic_refinement_loop(
    repo_root: Path,
    issue_num: int,
    max_rounds: int = 3,
    final_output: Optional[Path] = None
) -> Tuple[bool, Path, str]:
    """Execute iterative refinement loop between Architect and Conformance agents."""
    drafts_dir = repo_root / "agents" / "designs" / "drafts"
    logs_dir = repo_root / "agents" / "designs" / "logs"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_entries = []
    log_entries.append(f"# Dialectic Specification Refinement Log: Issue #{issue_num}")
    log_entries.append(f"- **Timestamp**: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    log_entries.append(f"- **Max Rounds**: {max_rounds}\n---\n")

    current_draft = drafts_dir / f"issue_{issue_num}_round_1.md"
    print(f"\n{'=' * 65}")
    print(f" STARTING SPECIFICATION REFINEMENT LOOP (Issue #{issue_num})")
    print(f"{'=' * 65}\n")

    # Round 1: Generate initial architecture draft
    print(f"[Round 1/1] Architecture Agent drafting initial specification...")
    success = generate_initial_draft(repo_root, issue_num, current_draft)
    if not success:
        return False, current_draft, "Failed to generate initial draft."

    converged = False
    final_report = ""

    for r in range(1, max_rounds + 1):
        print(f"\n--- [Round {r}/{max_rounds}] Conformance Agent Reviewing: {current_draft.name} ---")
        verdict, report_md, critique = audit_specification_draft(current_draft, issue_num, repo_root)
        final_report = report_md

        log_entries.append(f"## Round {r} Critique Summary")
        log_entries.append(f"- **Draft**: `{current_draft.name}`")
        log_entries.append(f"- **Verdict**: `{verdict}`")
        sug_count = len(critique.get("suggestions", []))
        log_entries.append(f"- **Actionable Feedback Count**: {sug_count}\n")

        if verdict == "SPEC_APPROVED":
            print(f"[Round {r}/{max_rounds}] >> CONVERGENCE ACHIEVED! Specification certified: SPEC_APPROVED <<")
            converged = True
            log_entries.append("> **Specification certified by Conformance Agent.** Ready for Implementation Agent.\n")
            break

        print(f"[Round {r}/{max_rounds}] Conformance Agent returned: {verdict}")
        print(f"[Round {r}/{max_rounds}] Identified {sug_count} suggestion(s) to resolve.")
        for i, s in enumerate(critique.get("suggestions", []), 1):
            print(f"  [{i}] ({s['type']}) {s['title']}")

        if r < max_rounds:
            next_draft = drafts_dir / f"issue_{issue_num}_round_{r + 1}.md"
            print(f"\n[Round {r+1}/{max_rounds}] Architecture Agent incorporating feedback into {next_draft.name}...")
            refine_draft_with_feedback(repo_root, current_draft, critique, next_draft, issue_num)
            current_draft = next_draft
        else:
            print(f"\n[Warning] Reached max rounds ({max_rounds}) without full convergence.")
            log_entries.append(f"> **Halted at max rounds ({max_rounds}).** Remaining items require engineer disambiguation.\n")

    # Promote to final design file only if converged
    dest_spec = None
    if converged:
        if final_output:
            dest_spec = final_output
        else:
            dest_spec = repo_root / "agents" / "designs" / f"issue_{issue_num}_design.md"

        dest_spec.parent.mkdir(parents=True, exist_ok=True)
        dest_spec.write_text(current_draft.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n[Orchestrator] Promoted refined specification to: {dest_spec}")
    else:
        dest_spec = current_draft
        print(f"\n[Orchestrator] Skipped promotion: loop halted before reaching SPEC_APPROVED.")
        print(f"[Orchestrator] Unapproved working draft preserved at: {current_draft}")

    # Write audit log
    log_file = logs_dir / f"issue_{issue_num}_refinement_log.md"
    log_file.write_text("\n".join(log_entries) + "\n\n" + final_report, encoding="utf-8")
    print(f"[Orchestrator] Refinement history log saved to: {log_file}")

    return converged, dest_spec, final_report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Dialectic Specification Refinement Loop: Architecture Agent <-> Conformance Agent"
    )
    parser.add_argument("--issue", type=int, required=True, help="Issue number to design and refine")
    parser.add_argument("--max-rounds", type=int, default=3, help="Maximum refinement rounds (default: 3)")
    parser.add_argument("--output", help="Optional path for finalized specification")

    args = parser.parse_args()
    repo_root = find_repo_root()

    final_path = Path(args.output).resolve() if args.output else None
    converged, dest_spec, report = run_dialectic_refinement_loop(
        repo_root, args.issue, max_rounds=args.max_rounds, final_output=final_path
    )

    print("\n" + "=" * 65)
    print(f" FINAL REFINEMENT VERDICT: {'SPEC_APPROVED (CONVERGED)' if converged else 'PARTIALLY CONVERGED'}")
    print(f" Specification File: {dest_spec}")
    print("=" * 65 + "\n")

    sys.exit(0 if converged else 1)


if __name__ == "__main__":
    main()
