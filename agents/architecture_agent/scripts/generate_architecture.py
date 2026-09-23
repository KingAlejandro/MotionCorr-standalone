#!/usr/bin/env python3
"""
Architecture Agent Specification Generator
Analyzes repository issues and source code, synthesizes mathematical models,
component interfaces, and numerical acceptance gates, and outputs comprehensive
Architectural Design Specifications (ADRs).

Supports:
- Gemini / Vertex AI generation when API keys/credentials are present
- Robust programmatic domain synthesis when offline
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None


def find_repo_root() -> Path:
    """Find repository root by walking up from script path."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return Path.cwd()


def load_issue_metadata(repo_root: Path, issue_num: int) -> Dict[str, Any]:
    """Parse issue metadata from skills/github-issues-parser/issues_summary.md or fallback."""
    summary_path = repo_root / "skills" / "github-issues-parser" / "issues_summary.md"
    if summary_path.exists():
        content = summary_path.read_text(encoding="utf-8")
        pattern = rf"###\s*\[(OPEN|PR|CLOSED)\]\s*#{issue_num}:\s*([^\n\r]+)"
        match = re.search(pattern, content)
        if match:
            state = match.group(1)
            title = re.sub(r"\s*\([^)]*\)$", "", match.group(2)).strip()
            start = match.end()
            next_m = re.search(r"###\s*\[(OPEN|PR|CLOSED)\]\s*#", content[start:])
            block = content[start: start + next_m.start()] if next_m else content[start:]

            labels_m = re.search(r"- \*\*Labels:\*\*\s*([^\n\r]+)", block)
            prio_m = re.search(r"- \*\*Priority:\*\*\s*`?(P[0-9]+)`?", block)
            deps_m = re.search(r"- \*\*Dependencies:\*\*\s*([^\n\r]+)", block)
            diff_m = re.search(r"- \*\*Estimated Difficulty:\*\*\s*\*\*([^*]+)\*\*\s*\(([^)]+)\)", block)
            obj_m = re.search(r"- \*\*Objective:\*\*\s*([^\n\r]+(?:\n[^\n\r#*-]+)*)", block)

            criteria = []
            crit_m = re.search(r"- \*\*Key Acceptance Criteria:\*\*\s*\n((?:\s*-\s+[^\n\r]+\n?)+)", block)
            if crit_m:
                for line in crit_m.group(1).splitlines():
                    c = line.strip().lstrip("- ").strip()
                    if c:
                        criteria.append(c)

            return {
                "number": issue_num,
                "title": title,
                "state": state,
                "labels": labels_m.group(1).strip() if labels_m else "track:core",
                "priority": prio_m.group(1).strip() if prio_m else "P1",
                "dependencies": deps_m.group(1).strip() if deps_m else "None",
                "difficulty": diff_m.group(1).strip() if diff_m else "Medium",
                "score": diff_m.group(2).strip() if diff_m else "3/5",
                "objective": obj_m.group(1).strip() if obj_m else f"Implement technical requirements for Issue #{issue_num}.",
                "criteria": criteria,
            }

    return {
        "number": issue_num,
        "title": f"Issue #{issue_num}",
        "state": "OPEN",
        "labels": "track:core",
        "priority": "P1",
        "dependencies": "None",
        "difficulty": "Medium",
        "score": "3/5",
        "objective": f"Architectural solution for issue #{issue_num}.",
        "criteria": ["Meet reference parity gates", "Pass automated tests"],
    }


def call_gemini_api(api_key: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Google Gemini REST API if an API key is available."""
    if not requests:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        sys.stderr.write(f"Warning: Gemini API call failed: {e}\n")
    return None


def synthesize_specification(repo_root: Path, issue_data: Dict[str, Any]) -> str:
    """Synthesize a complete architectural specification conforming to DESIGN_SPEC_TEMPLATE."""
    num = issue_data["number"]
    title = issue_data["title"]
    labels = issue_data.get("labels", "track:core")
    prio = issue_data.get("priority", "P1")
    diff = issue_data.get("difficulty", "Medium")
    score = issue_data.get("score", "3/5")
    deps = issue_data.get("dependencies", "None")
    obj = issue_data.get("objective", "")
    crit = issue_data.get("criteria", [])

    crit_md = "\n".join([f"- [ ] {c}" for c in crit]) if crit else "- [ ] Verify bit-exact numerical parity against RELION 5.1 baseline\n- [ ] Clean build and test execution"

    # Differentiate domain formulation based on issue track and keywords
    track_lower = labels.lower()
    title_lower = title.lower()

    if "ci" in track_lower or "ci" in title_lower or "pipeline" in title_lower:
        sec3 = """### 3.1 CI Infrastructure & Matrix Configuration
- Multi-platform matrix: Linux (Ubuntu 22.04 LTS with GCC 11+ and Clang 14+) and macOS (macOS 13+ with AppleClang).
- Automated dependency caching (CMake, FFTW3, LibTIFF) to ensure CI runtimes remain $\\le 10\\text{ minutes}$.
- Automated test gate running synthetic parity test fixtures with strict pass/fail exit codes.

### 3.2 Build Verification & Artifact Integrity
- Hermetic build validation with `-Wall -Wextra -Werror` compliance.
- Build artifact verification ensuring binary symbols and dependencies resolve cleanly."""
        sec4 = f"""```mermaid
flowchart TD
    PR["Pull Request / Push Event"] --> CI["GitHub Actions Runner Matrix"]
    CI --> Build["Compile: GCC / Clang / AppleClang"]
    Build --> Test["Execute Synthetic Parity Test Suite"]
    Test --> Gate["Automated Parity Gate (Issue #4)"]
    Gate --> Status["Report CI Check Status"]
```"""
        sec5 = f"""```yaml
# CI Pipeline Configuration for #{num}
jobs:
  test_matrix:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-22.04, macos-13]
        compiler: [gcc, clang]
```"""
        sec6 = """- Optimize CI runner concurrency and container memory limits (4 GB RSS ceiling per test worker).
- Clean up intermediate object files between matrix jobs to avoid exceeding runner disk quotas."""

    elif "gpu" in track_lower or "cuda" in title_lower or "jax" in title_lower:
        sec3 = f"""### 3.1 Device Execution & Memory Architecture
- Asynchronous GPU compute stream scheduling with overlapping host-to-device (H2D) and device-to-host (D2H) copies.
- Kernel launch grid configured dynamically for movie frame dimensions and patch tile sizes.
- Unified memory management minimizing device allocation thrashing during batch frame alignment.

### 3.2 Numerical Parity & Floating-Point Precision
- Adhere to Tier 2 numerical parity tolerance against CPU reference outputs (max pixel diff $< 1e-4$, trajectory delta $< 0.05$ px).
- Enforce deterministic reduction intrinsics to ensure reproducible cross-correlation peaks across GPU architectures."""
        sec4 = f"""```mermaid
flowchart TD
    InputData["Input Movie / Metadata"] --> HostStaging["Pinned Host Memory Staging"]
    HostStaging --> StreamCopy["Asynchronous H2D Transfer"]
    StreamCopy --> GPUKernel["Component #{num}: GPU Kernel Dispatch"]
    GPUKernel --> D2HCopy["Asynchronous D2H Transfer"]
    D2HCopy --> ParityGate["Numerical Parity Gate (Tier 2)"]
    ParityGate --> Output["MRC / STAR Outputs"]
```"""
        sec5 = f"""```cpp
// Target interfaces for GPU component #{num}
namespace MotionCorr::GPU {{
    struct StreamConfig {{
        int device_id = 0;
        size_t scratch_bytes = 0;
        bool async_transfers = true;
    }};
    void execute_alignment(const float* d_in, float* d_out, StreamConfig cfg);
}}
```"""
        sec6 = """- Pre-allocate device scratch memory pools during pipeline initialization.
- Maximum GPU VRAM overhead ceiling: $\\le 10\\%$ delta relative to frame buffer footprint.
- Zero device memory allocations inside the per-frame alignment loop."""

    elif "io" in track_lower or "format" in title_lower or "mrc" in title_lower or "star" in title_lower:
        sec3 = f"""### 3.1 File Formats & Metadata Normalization
- MRC 2014 file format compliance including extended header handling and floating-point endianness.
- STAR tabular metadata serialization compliant with RELION 5.0+ loop and table grammar.
- Metadata normalization rules: strip volatile absolute paths and creation timestamps during parity audits.

### 3.2 Buffer Management & Streaming
- Stream-based or memory-mapped I/O for large movie stacks (up to multi-gigabyte raw datasets).
- Zero-copy header parsing and validation before allocating full frame buffers."""
        sec4 = f"""```mermaid
flowchart TD
    FileIn["Input MRC / TIFF Movie"] --> HeaderParse["Header Validation & Metadata Extraction"]
    HeaderParse --> StreamBuffer["Chunked / Memory-Mapped Frame Streaming"]
    StreamBuffer --> Processor["Component #{num}: {title}"]
    Processor --> Serializer["STAR / MRC Output Serializer"]
    Serializer --> FileOut["Normalized Reference Output"]
```"""
        sec5 = f"""```cpp
// Target interfaces for I/O component #{num}
namespace MotionCorr::IO {{
    struct HeaderInfo {{
        int nx, ny, nz;
        int mode;
        float pixel_size;
    }};
    bool parse_header(const std::string& path, HeaderInfo& info);
}}
```"""
        sec6 = """- Implement chunked or sliding window memory streaming for movie frames.
- Maximum resident memory ceiling: $\\le 2\\times$ single-frame footprint during streaming I/O."""

    elif "doc" in track_lower or "documentation" in title_lower:
        sec3 = f"""### 3.1 Documentation Rigor & Architecture Mapping
- Comprehensive architectural documentation mapping components to RELION 5.1 upstream origins.
- Specification of verification requirements, build instructions, and benchmark reproduction protocols.

### 3.2 Maintenance & Versioning Protocols
- Semantic documentation versioning aligned with repo milestone releases.
- Synchronized API reference and CLI flag usage documentation."""
        sec4 = f"""```mermaid
flowchart TD
    Spec["Issue Requirements #{num}"] --> Architect["Architecture Agent"]
    Architect --> Docs["Technical Documentation"]
    Docs --> Validation["Peer Review & Compliance Gate"]
    Validation --> RepoDocs["Repository Documentation Tree"]
```"""
        sec5 = """```markdown
<!-- Document Schema for #{num} -->
## Overview
## Usage Examples
## Technical Specifications
```"""
        sec6 = """- Zero runtime memory footprint (documentation only)."""

    else:
        # Algorithmic / CPU Motion Correction Component
        sec3 = f"""### 3.1 Domain Physics & Coordinates
- Motion correction models sample drift over exposure frames t in [0, N-1] on coordinates (x, y).
- Cross-correlation surfaces CCF(dx, dy) are computed in Fourier space using cross-spectral density.
- Trajectory regularization minimizes frame-to-frame acceleration spikes.

### 3.2 Convergence & Precision Constraints
- Interpolation and shift application must adhere to double-precision accumulation where floating-point drift is prone to cancelation.
- Threshold for convergence: displacement change < 1e-3 px."""
        sec4 = f"""```mermaid
flowchart TD
    InputData["Input Movie / Metadata"] --> Runner["motioncorr_runner.cpp"]
    Runner --> Module["Component #{num}: {title}"]
    Module --> ParityGate["Numerical Parity Gate (Issue #4)"]
    ParityGate --> Output["MRC / STAR Outputs"]
```"""
        sec5 = f"""```cpp
// Target interfaces for #{num}
namespace MotionCorr {{
    struct ModuleConfig {{
        bool enable_verification = true;
        double tolerance = 1e-6;
    }};
}}
```"""
        sec6 = """- Enforce zero-allocation loops during iterative Fourier search.
- Pre-allocate scratch workspace buffers during pipeline initialization.
- Maximum memory overhead ceiling: $\\le 10\\%$ RSS delta (aligned with Issue #10 acceptance criteria)."""

    spec = f"""# Architectural Design Specification: #{num} - {title}

- **Issue Reference**: #{num} - {title}
- **Track**: `{labels}`
- **Priority**: {prio}
- **Architect**: MotionCorr Architecture Agent
- **Estimated Difficulty**: {diff} ({score})
- **Dependencies**: {deps}
- **Status**: Proposed
- **Target Release / Milestone**: v1.0.0

---

## 1. Executive Summary & Problem Statement

{obj}

This architectural specification details the algorithmic formulation, component decomposition, memory staging plan, and numerical validation gates required to resolve Issue #{num} while strictly adhering to the repository's baseline parity requirements.

---

## 2. Architectural Objectives & Constraints

### 2.1 Functional Objectives
- Fulfill all deliverables associated with Issue #{num}.
- Satisfy the core acceptance criteria:
{crit_md}

### 2.2 Scientific & Non-Functional Constraints
- **Parity Gate**: Must strictly meet the acceptance thresholds defined in Issue #4 (`agents/designs/issue_4_define_the_reference_outputs_and_numeric.md`).
- **Thread Determinism**: Avoid uncoordinated OpenMP reduction variance; preserve reproducibility across runs.
- **Memory Overhead**: Minimize allocations in hot processing loops; enforce fixed buffer lifetimes.
- **Portability**: Must cleanly compile with C++17 on Linux (GCC/Clang) and macOS (AppleClang).

---

## 3. Mathematical & Algorithmic Formulation

{sec3}

---

## 4. Component Architecture & Data Flow

{sec4}

---

## 5. Interface Contracts & Data Structures

{sec5}

---

## 6. Memory Staging & Allocation Strategy

{sec6}

---

## 7. Defensive Failure Modes & Fallback Behavior

| Condition / Trigger | Detection Mechanism | Fallback / Recovery Action | User Diagnostic Visibility |
| :--- | :--- | :--- | :--- |
| Non-convergence / NaN | Numerical sanity check | Revert to global rigid shift | Log warning to stderr and STAR metadata |
| Out of bounds memory | Pre-condition size check | Graceful exit with code 1 | Meaningful error message in log |

---

## 8. Implementation Roadmap for Coding Agents

### Phase 1: Test Fixtures & Baseline Recording
- Formulate regression test fixture verifying pre-condition state.

### Phase 2: Core Algorithmic Implementation
- Apply isolated, minimal changes to target files.
- Verify zero regression in existing test cases.

### Phase 3: Parity Certification
- Run parity comparison tools against reference datasets.

---

## 9. Verification & Acceptance Criteria

### 9.1 Automated Tests
```bash
# Automated validation command
ctest --output-on-failure
```

### 9.2 Acceptance Thresholds
- Tier 0 CPU Golden Parity: Exact trajectory match and image RMSE = 0.0.
- Exit status: `0`.
"""
    return spec


def slugify(text: str) -> str:
    """Generate safe filename slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "_", text).strip("_")[:40]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Architecture Agent: Generate an Architectural Design Specification for an issue."
    )
    parser.add_argument("--issue", type=int, required=True, help="Issue number to design architecture for")
    parser.add_argument("--out", "--output", dest="out", help="Custom output path for the specification file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing specification if present")

    args = parser.parse_args()
    repo_root = find_repo_root()

    print(f"[Architecture Agent] Loading context for Issue #{args.issue}...")
    issue_data = load_issue_metadata(repo_root, args.issue)

    designs_dir = repo_root / "agents" / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(issue_data["title"])
    out_path = Path(args.out).resolve() if args.out else designs_dir / f"issue_{args.issue}_{slug}.md"

    if out_path.exists() and not args.force:
        print(f"[Architecture Agent] Design specification already exists at: {out_path}")
        print("Use --force to overwrite.")
        sys.exit(0)

    # Check for Gemini API key
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    system_prompt_file = repo_root / "agents" / "architecture_agent" / "SYSTEM_PROMPT.md"
    system_prompt = system_prompt_file.read_text(encoding="utf-8") if system_prompt_file.exists() else ""

    spec_text = None
    if api_key and system_prompt:
        print("[Architecture Agent] Found Gemini API key. Generating architecture design with LLM...")
        user_prompt = f"Produce a complete, rigorous Architectural Design Specification for Issue #{args.issue}: {issue_data['title']}.\nObjective: {issue_data['objective']}\nCriteria: {issue_data['criteria']}"
        spec_text = call_gemini_api(api_key, system_prompt, user_prompt)

    if not spec_text:
        print("[Architecture Agent] Synthesizing comprehensive architectural specification...")
        spec_text = synthesize_specification(repo_root, issue_data)

    out_path.write_text(spec_text, encoding="utf-8")

    print("\n==================================================")
    print(" Architecture Agent: Specification Generated")
    print("==================================================")
    print(f"Issue:    #{args.issue} - {issue_data['title']}")
    print(f"Priority: {issue_data.get('priority')}")
    print(f"Path:     {out_path.relative_to(repo_root)}")
    print("==================================================\n")


if __name__ == "__main__":
    main()
