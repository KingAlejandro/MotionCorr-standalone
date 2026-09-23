---
name: github-issues-parser
description: >-
  Use this skill to fetch, inspect, summarize, and evaluate GitHub issues and pull requests from a GitHub repository or cached JSON file. Analyzes task dependencies, pass criteria, owner fit, and computes implementation difficulty ratings.
---

# GitHub Issues Parser & Difficulty Estimator

This skill provides a standardized tool and workflow for parsing GitHub repository issues and pull requests, extracting structured metadata (priority, dependencies, objectives, acceptance criteria), and estimating technical implementation difficulty for planning.

## Key Capabilities

1. **API & File Ingestion**: Fetches directly from GitHub REST API (`--repo <owner>/<repo>`) or ingests local cached JSON / Markdown responses (`--file <path>`).
2. **Metadata Extraction**: Extracts structured attributes including `Priority`, `Owner fit`, `Dependency`, `Why this task exists`, and `Pass criteria`.
3. **Difficulty Estimation**: Assesses implementation complexity (from `Low` to `Very High`) based on domain requirements (e.g. CUDA kernels, JAX vectorization, numerical convergence, OpenMP determinism, CI configuration).
4. **Markdown & JSON Output**: Emits structured reports ready for implementation planning and roadmap creation.

## Directory Structure

```text
github-issues-parser/
├── SKILL.md                 # Main instructions and reference
└── scripts/
    └── parse_issues.py      # Core parser and analysis CLI tool
```

## Running the Parser Script

The Python script is located at:
[`parse_issues.py`](./scripts/parse_issues.py)

### Usage Examples

1. **Parse from cached JSON / markdown file**:
   ```bash
   python .agents/skills/github-issues-parser/scripts/parse_issues.py --file path/to/issues.json --format markdown
   ```

2. **Fetch and parse directly from a GitHub repository**:
   ```bash
   python .agents/skills/github-issues-parser/scripts/parse_issues.py --repo KingAlejandro/MotionCorr-standalone --state all --format markdown
   ```

3. **Export structured JSON for automated pipelines**:
   ```bash
   python .agents/skills/github-issues-parser/scripts/parse_issues.py --repo KingAlejandro/MotionCorr-standalone --format json --output issues_summary.json
   ```

## Workflow for Implementation Planning

When asked to summarize repository issues and construct an implementation plan:
1. Run `parse_issues.py` to generate the issue inventory and technical difficulty ranking.
2. Group the issues logically by track:
   - **Validation & Baseline Gates**: Reference datasets, parity checks, acceptance gates.
   - **Infrastructure & CI**: Linux builds, smoke tests, release packaging.
   - **CPU Core & Stability**: Multi-threading determinism, memory profiling, bottleneck tuning.
   - **Algorithmic Extensions**: EER handling, patch fit robustness, dose weighting.
   - **Experimental Acceleration**: JAX array prototype, CUDA kernel prototype.
   - **Research Explorations**: Bayesian trajectory smoothing.
3. Establish a phased dependency graph where reference gates and CI precede optimizations and accelerated backends.
