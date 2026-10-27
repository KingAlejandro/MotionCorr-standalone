# Publication checks

- All packet manifest entries verify before the evidence comment is published, including the unchanged original four-entry manifest.
- All 20 entries in the primary `local_ccf_capture_20261026/SHA256SUMS` still verify. The primary packet is unchanged.
- `src/`, `tests/` and `CMakeLists.txt` have no delta from sealed `63d73581`.
- `git diff --cached --check` exits2 on four trailing-double-space Markdown hard line breaks in the original worker PLAN/REPORT. These original bytes are intentionally retained to preserve their SHA-256 provenance; this is not a scientific or source-test failure. No formatting repair is applied to the originals.
- No new native producer, test run, pixel-scoring campaign or numerical calculation occurred during this documentation-only publication. The separately retained parent reproduction ran once and exited0.
