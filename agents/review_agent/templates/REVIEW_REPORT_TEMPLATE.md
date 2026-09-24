# Code Review Report: {{TARGET_TITLE}}

- **Reviewer**: MotionCorr Review Agent (Stateless & Memoryless)
- **Target Revision**: `{{REVISION}}`
- **Associated Issue/ADR**: {{ASSOCIATED_ISSUE}}
- **Final Verdict**: **{{VERDICT}}**

---

## 1. Executive Summary

{{EXECUTIVE_SUMMARY}}

---

## 2. Gate Verification Checklist

| Verification Gate | Status | Notes |
| :--- | :--- | :--- |
| **Numerical Parity Gate** | `{{PARITY_STATUS}}` | {{PARITY_NOTES}} |
| **Concurrency & Thread Determinism** | `{{THREAD_STATUS}}` | {{THREAD_NOTES}} |
| **Memory Discipline & Hot-Loop Footprint** | `{{MEMORY_STATUS}}` | {{MEMORY_NOTES}} |
| **Cross-Platform Portability** | `{{PORTABILITY_STATUS}}` | {{PORTABILITY_NOTES}} |
| **Automated Verification Coverage** | `{{TEST_STATUS}}` | {{TEST_NOTES}} |

---

## 3. Detailed Findings & Faults

{{FINDINGS}}

*(If no issues are identified)*:
> **No blockers or warnings identified.** All numerical parity, thread safety, and memory management constraints are satisfied.

---

## 4. Final Recommendation & Merge Instructions

**Verdict**: `{{VERDICT}}`

{{MERGE_RECOMMENDATIONS}}
