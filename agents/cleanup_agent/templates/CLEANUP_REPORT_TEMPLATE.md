# Repository Cleanup & Hygiene Report

- **Auditor**: Cleanup & Repository Hygiene Agent (`agents/cleanup_agent/`)
- **Execution Timestamp**: `{{TIMESTAMP}}`
- **Execution Mode**: **{{EXECUTION_MODE}}** (`DRY_RUN` | `APPLIED`)
- **Overall Status**: **{{OVERALL_STATUS}}** (`CLEANUP_COMPLETED` | `PENDING_CONFIRMATION` | `NOTHING_TO_CLEAN`)

---

## 1. Executive Summary

{{EXECUTIVE_SUMMARY}}

---

## 2. Identified Artifacts for Removal

| Category | File / Directory Path | Size (Bytes) | Action Planned / Taken |
| :--- | :--- | :--- | :--- |
{{ARTIFACTS_TABLE}}

---

## 3. Protected Zones Verification

The following protected paths were verified as untouched and fully preserved:
- [x] **Source Code**: `src/`, `include/`, `CMakeLists.txt`
- [x] **Agent Core Tooling**: `SYSTEM_PROMPT.md`, `templates/`, `scripts/*.py`
- [x] **Permanent Designs**: `agents/designs/issue_*_design.md`
- [x] **Test Baselines**: `test-data/`

---

## 4. Git Workspace Impact

- **Files Removed / Scheduled**: {{TOTAL_FILES}}
- **Total Disk Space Reclaimed**: {{RECLAIMED_BYTES}}
- **Git Working Tree Status**: {{GIT_STATUS_SUMMARY}}
