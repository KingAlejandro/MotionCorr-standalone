# B2 cross-feed offline screen (result, independent audit, disposition)

Status: **NOT_A_CANDIDATE** (offline counterfactual; no native run, no acceptance). Independent audit verdict: SUPPORTED, bounded.

Noisy B2 + full-width: 0.8249 / 1.6520 / 3.2167 Å (rms / p95 / max) against limits 0.20 / 0.40 / 0.80 Å, so it fails on both fields. The five retained passes (affine, pedestal, zero, integer, fractional) hold; flat and repeated stay UNIDENTIFIABLE. The old noisy B2 harm reproduces (1.9026 / 4.2003 / 9.2948 Å). Four max-metric PASS→PASS increases against native ON are retained, none against native OFF. Not established: a genuine refit STAR serialization, any native compound run, applied-image or real-data accuracy.

## Contents
| Path | What |
|---|---|
| `screen/` | Frozen PLAN, PINS, FREEZE, the stage-1/seal/stage-2/table scripts, three pinned W8 sources, `out/` (stage-1 fit, seal, open log, staged manifest, stage-2 result, candidates, `attempt1/`), RESULT, RESULT_TABLES, ATTEMPTS |
| `audit/` | Independent Opus audit: REPORT.md, HASHES.sha256, scripts, results (including the preserved failed first run) |
| `AUDIT_DISPOSITION.md` | Additive bounds on the audit's low findings; frozen files unchanged |
| `NEXT_OBSERVATION_PROPOSAL.md` | Draft only; nothing run or authorized |
| `PACKAGE_MANIFEST.json`, `PACKAGE_SHA256SUMS` | Precise manifest of this directory |

## Integrity and what is not in this directory
`PACKAGE_SHA256SUMS` verifies every other file here: `cd b2_crossfeed_screen && shasum -a 256 -c PACKAGE_SHA256SUMS`.
`screen/SOURCE_MANIFEST.json` is the original 101-file manifest of the working directory (sha256 36b5253d…). This compact subset does **not** contain all of those files, so the source manifest does not verify here. Omitted: `stage1_root/` (40 staged duplicates of the bundle's runtime.json and STAR files; their hashes are in `screen/out/stage1_staged_manifest.json`, and the authority is the read-only audit bundle `Native-local-full-width-AUDIT-BUNDLE-r1`, manifest 49698c7c…) and the unused W8 sources. Several copied files embed the working path `/tmp/mc-lfw-b2-crossfeed-20261026-r1`.

Durable originals (additive, each with a verified `COPY_INDEX.tsv`), under `~/Documents/MotionCorr-evidence/20261026/`:
- `B2-crossfeed-screen-archive-r2/` full working directory including `stage1_root/` (102-line index)
- `B2-crossfeed-opus-audit-r1/` audit originals (12-line index)
- `B2-crossfeed-screen-r1/` earlier copy, unchanged (index sha256 4de4c522…)

Pins: PLAN `df804f52…`, PINS `18841057…`, stage-1 seal `41fed948…` (2026-10-27T00:04:11Z), stage-2 result `c5520cf3…`, audit REPORT `98425f53…`, audit HASHES `5ef781c6…`. Source, tests and CMake are unchanged by this directory.
