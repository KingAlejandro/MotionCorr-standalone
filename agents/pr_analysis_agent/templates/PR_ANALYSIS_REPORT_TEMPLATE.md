# Pull Request Analysis & Defect Report

- **Auditor**: Pull Request Analysis Agent (`agents/pr_analysis_agent/`)
- **Audit Timestamp**: `{{TIMESTAMP}}`
- **Target PR**: `{{PR_NUMBER}}` - `{{PR_TITLE}}`
- **PR Author**: `@{{AUTHOR}}`
- **Target / Base Branch**: `{{BASE_BRANCH}}` ← `{{HEAD_BRANCH}}`
- **Merge Readiness Verdict**: **{{OVERALL_VERDICT}}** (`READY_TO_MERGE` | `CHANGES_REQUESTED` | `BLOCKED_BY_FAULT`)

---

## 1. Executive Summary

{{EXECUTIVE_SUMMARY}}

---

## 2. Pull Request Metadata & Traceability

| Attribute | Details |
| :--- | :--- |
| **PR Number** | #{{PR_NUMBER}} |
| **Repository** | `{{REPO}}` |
| **Status / Mergeable** | `{{STATE}}` (Mergeable: `{{MERGEABLE}}`) |
| **Linked Issues** | {{LINKED_ISSUES}} |
| **Code Impact** | +{{ADDITIONS}} / -{{DELETIONS}} in {{CHANGED_FILES_COUNT}} file(s) |
| **Commit Count** | {{COMMITS_COUNT}} commit(s) |

---

## 3. Multi-Agent Quality Gates Matrix

| Quality Gate | Evaluating Agent | Status | Key Observations |
| :--- | :--- | :--- | :--- |
| **Code Hygiene & Parity** | `review_agent` | `{{GATE_REVIEW_STATUS}}` | {{GATE_REVIEW_OBSERVATION}} |
| **Scope & Side-Effect Isolation** | `spec_compliance_agent` | `{{GATE_SPEC_STATUS}}` | {{GATE_SPEC_OBSERVATION}} |
| **License & IP Compliance** | `license_compliance_agent` | `{{GATE_LICENSE_STATUS}}` | {{GATE_LICENSE_OBSERVATION}} |
| **Mergeability & Freshness** | `pr_analysis_agent` | `{{GATE_MERGE_STATUS}}` | {{GATE_MERGE_OBSERVATION}} |

---

## 4. Itemized Findings & Defect Diagnostics

{{FINDINGS_BLOCK}}

---

## 5. Remediation Plan & Merge Recommendations

{{REMEDIATION_BLOCK}}
