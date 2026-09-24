#!/usr/bin/env python3
"""
Architecture Design Scaffolding Tool
Extracts issue metadata, analyzes repository context, and generates a structured
Architectural Decision Record (ADR) / Design Specification for the Architecture Agent.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DESIGN_TEMPLATE_REL_PATH = Path("agents/architecture_agent/templates/DESIGN_SPEC_TEMPLATE.md")
DESIGNS_DIR_REL_PATH = Path("agents/designs")
ISSUES_SUMMARY_REL_PATH = Path("skills/github-issues-parser/issues_summary.md")


def find_repo_root() -> Path:
    """Find repository root by walking up from this script's directory."""
    script_dir = Path(__file__).resolve().parent
    current = script_dir
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return script_dir.parents[2]


def load_issue_from_summary(repo_root: Path, issue_num: int) -> Optional[Dict[str, Any]]:
    """Parse a specific issue from skills/github-issues-parser/issues_summary.md if available."""
    summary_path = repo_root / ISSUES_SUMMARY_REL_PATH
    if not summary_path.exists():
        return None

    content = summary_path.read_text(encoding="utf-8")
    
    # Split by issue headers
    pattern = rf"###\s*\[(OPEN|PR|CLOSED)\]\s*#{issue_num}:\s*([^\n\r]+)"
    match = re.search(pattern, content)
    if not match:
        return None

    state_tag = match.group(1)
    full_title = match.group(2).strip()
    
    # Clean title (remove trailing type tags like '(Issue - OPEN)')
    clean_title = re.sub(r"\s*\([^)]*\)$", "", full_title).strip()

    # Extract block up to next issue header or end
    start_pos = match.end()
    next_match = re.search(r"###\s*\[(OPEN|PR|CLOSED)\]\s*#", content[start_pos:])
    block = content[start_pos: start_pos + next_match.start()] if next_match else content[start_pos:]

    # Parse metadata fields
    labels_match = re.search(r"- \*\*Labels:\*\*\s*([^\n\r]+)", block)
    priority_match = re.search(r"- \*\*Priority:\*\*\s*`?(P[0-9]+)`?", block)
    deps_match = re.search(r"- \*\*Dependencies:\*\*\s*([^\n\r]+)", block)
    owner_match = re.search(r"- \*\*Owner Fit:\*\*\s*([^\n\r]+)", block)
    diff_match = re.search(r"- \*\*Estimated Difficulty:\*\*\s*\*\*([^*]+)\*\*\s*\(([^)]+)\)", block)
    why_match = re.search(r"- \*\*Objective:\*\*\s*([^\n\r]+(?:\n[^\n\r#*-]+)*)", block)

    # Acceptance criteria
    criteria = []
    crit_match = re.search(r"- \*\*Key Acceptance Criteria:\*\*\s*\n((?:\s*-\s+[^\n\r]+\n?)+)", block)
    if crit_match:
        for line in crit_match.group(1).splitlines():
            line_str = line.strip().lstrip("- ").strip()
            if line_str:
                criteria.append(line_str)

    return {
        "number": issue_num,
        "title": clean_title,
        "state": state_tag,
        "labels": labels_match.group(1).strip() if labels_match else "",
        "priority": priority_match.group(1).strip() if priority_match else "P1",
        "dependencies": deps_match.group(1).strip() if deps_match else "None",
        "owner_fit": owner_match.group(1).strip() if owner_match else "Engineer",
        "difficulty": diff_match.group(1).strip() if diff_match else "Medium",
        "score": diff_match.group(2).strip() if diff_match else "3/5",
        "objective": why_match.group(1).strip() if why_match else "",
        "criteria": criteria,
    }


def slugify(text: str) -> str:
    """Convert title to filesystem-safe slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text).strip("_")
    return text[:40]


def scaffold_design_spec(repo_root: Path, issue_data: Dict[str, Any]) -> Path:
    """Create a populated architectural design specification file."""
    designs_dir = repo_root / DESIGNS_DIR_REL_PATH
    designs_dir.mkdir(parents=True, exist_ok=True)

    issue_num = issue_data["number"]
    slug = slugify(issue_data["title"])
    filename = f"issue_{issue_num}_{slug}.md"
    target_file = designs_dir / filename

    template_file = repo_root / DESIGN_TEMPLATE_REL_PATH
    template_text = template_file.read_text(encoding="utf-8") if template_file.exists() else ""

    criteria_bullets = "\n".join([f"- [ ] {c}" for c in issue_data.get("criteria", [])])
    if not criteria_bullets:
        criteria_bullets = "- [ ] Meet reference parity gates\n- [ ] Pass automated test suite"

    # Fill metadata header
    spec_content = f"""# Architectural Design Specification: #{issue_num} - {issue_data['title']}

- **Issue Reference**: #{issue_num}
- **Track**: {issue_data.get('labels', 'track:core')}
- **Priority**: {issue_data.get('priority', 'P1')}
- **Architect**: MotionCorr Architecture Agent
- **Estimated Difficulty**: {issue_data.get('difficulty', 'Medium')} ({issue_data.get('score', '3/5')})
- **Dependencies**: {issue_data.get('dependencies', 'None')}
- **Status**: Proposed
- **Target Release / Milestone**: v1.0.0

---

## 1. Executive Summary & Problem Statement

{issue_data.get('objective', 'Detailed objective for this issue.')}

---

## 2. Architectural Objectives & Constraints

### 2.1 Functional Objectives
- Implement technical deliverables for Issue #{issue_num}.
- Satisfy the core acceptance requirements:
{criteria_bullets}

### 2.2 Scientific & Non-Functional Constraints
- **Numerical Parity**: Mandatory baseline gate matching RELION 5.1 reference results (Issue #4).
- **Deterministic Execution**: Avoid non-deterministic race conditions or unordered thread reductions.
- **Memory Budget**: Peak RSS must not regress by more than 5% without documented rationale.
- **Portability**: Must build and execute cleanly on Linux (GCC/Clang) and macOS.

---

## 3. Mathematical & Algorithmic Formulation

*(To be elaborated by Architecture Agent based on domain requirements)*

1. **Core Equations / Transformations**:
   - Define coordinate frames, origin indexing, and transform matrices.
2. **Numerical Approximations & Tolerances**:
   - State floating-point precision bounds and parity convergence criteria.

---

## 4. Component Architecture & Data Flow

```mermaid
flowchart TD
    Input[Input Movie / Fixture] --> CoreRunner[MotionCorr Runner]
    CoreRunner --> Subsystem[Issue #{issue_num} Component]
    Subsystem --> Verification[Numerical Parity Gate]
    Verification --> Output[MRC & STAR Output Contract]
```

---

## 5. Interface Contracts & Data Structures

*(Architecture Agent: Specify relevant C++, CUDA, or Python interfaces)*

---

## 6. Memory Staging & Allocation Strategy

- Analyze buffer allocations and lifetime.
- Prevent dynamic allocations in hot alignment/CCF loops.

---

## 7. Defensive Failure Modes & Fallback Behavior

| Condition / Trigger | Detection Mechanism | Fallback / Recovery Action | User Diagnostic Visibility |
| :--- | :--- | :--- | :--- |
| Non-convergence / numerical anomaly | NaN/Inf check or condition number | Fall back to robust baseline / global shift | Log error & flag in STAR |

---

## 8. Implementation Roadmap for Coding Agents

### Step 1: Pre-requisites & Test Fixtures
- Prepare synthetic or reference fixtures.

### Step 2: Implementation of Core Logic
- Apply localized, clean changes to target modules.

### Step 3: Validation & Telemetry
- Run parity validation suite and record benchmark numbers.

---

## 9. Verification & Acceptance Criteria

### 9.1 Automated Tests
```bash
# Example verification command
python tests/compare_parity.py --issue {issue_num}
```

### 9.2 Acceptance Thresholds
- Trajectory error: $\\Delta x, \\Delta y \\le 10^{{-4}}\\text{{ px}}$
- Image RMSE $\\le 10^{{-6}}$
- Exact STAR metadata parity
"""

    target_file.write_text(spec_content, encoding="utf-8")
    return target_file


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Scaffold an Architectural Design Specification for an issue in MotionCorr-standalone."
    )
    parser.add_argument("--issue", type=int, required=True, help="Issue number to design architecture for (e.g. 4, 7, 16)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing design specification file if present")

    args = parser.parse_args()
    repo_root = find_repo_root()

    print(f"Loading metadata for Issue #{args.issue}...")
    issue_data = load_issue_from_summary(repo_root, args.issue)
    if not issue_data:
        print(f"Issue #{args.issue} not found in {ISSUES_SUMMARY_REL_PATH}.")
        print("Using fallback generic template populated with Issue ID.")
        issue_data = {
            "number": args.issue,
            "title": f"Issue {args.issue} Architecture",
            "state": "OPEN",
            "priority": "P1",
            "labels": "track:core",
            "dependencies": "Issue #4",
            "objective": f"Architecture specification for issue #{args.issue}.",
            "criteria": [],
        }

    slug = slugify(issue_data["title"])
    target_path = repo_root / DESIGNS_DIR_REL_PATH / f"issue_{args.issue}_{slug}.md"
    if target_path.exists() and not args.force:
        print(f"Design spec already exists at: {target_path}")
        print("Use --force to overwrite.")
        sys.exit(0)

    out_file = scaffold_design_spec(repo_root, issue_data)
    print("\n==================================================")
    print(" Architecture Design Specification Scaffolded")
    print("==================================================")
    print(f"Target Issue: #{args.issue} - {issue_data['title']}")
    print(f"Priority:     {issue_data.get('priority')}")
    print(f"File Path:    {out_file.relative_to(repo_root)}")
    print("==================================================\n")
    print("Next step: Have the Architecture Agent flesh out the detailed algorithms,")
    print("interfaces, memory staging, and verification gates.")


if __name__ == "__main__":
    main()
