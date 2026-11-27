# Parent response to decision-packet review round 1

Reviewed packet: `6f78f16d4f5a98da1bf8be1acf4fe773e33625f8`.
The complete Opus report is retained verbatim as `REVIEW.md`, SHA-256
`328d6d3a98154546397418940c6b03e4c44232dabe43422377c0d8e7c7d01d6c`.
These are parent responses, not the independent reviewer's acceptance.

| Finding | Correction | Remaining boundary |
| --- | --- | --- |
| F1, M4 completeness | M4 now explicitly covers global and local paths, the existing CUDA resident retry with shift reset, dropped unconverged patches and stderr-only global fallback. It proposes separate local attempt/drop/fallback states, records asymmetric backend logging and convergence, and requires backend-divergence controls and RELION `ad0b230` parity sign-off for changed refusal/retry behavior. Zero-frame `true` cannot encode not-run. | No prototype, schema or behavior is adopted; proposed controls remain UNRUN and M4/M5 unapproved. |
| F2, retention accounting | Sonnet's bounded commit `af96d24721d14f60e5485aea47cff236674521c0`, integrated as `a23403de`, sizes #273/#274 unique trees and records C1 reachable history, tip/history-only blobs, packed-size limits and #269 ancestry. The explicit-input recipe replaces the uncommitted sibling dependency and reproduces the original tip inventory exactly. The brief distinguishes identical-tree squash from compact-tree changes and flags conflict with the current normal-merge plan; its widening question makes no retention choice. | No archive opened, retrieval demonstrated, history rewritten, deletion or merge-mode change; 57 docs-reference hits are unclassified, not proof that every path is required. M2 remains a maintainer decision. |
| F3, development exposure | Corrected all family-specific audit fields. All 114 sweep movies are development-exposed by #243; the original 30 carry #255/#261/#271 campaign metadata. The frozen 51 DC Tier-C selections and their historical snapshot statuses are labelled selected/planned versus completed. The separate two-movie #73/PR87 pilot is already exposed and outside this inventory. M6 now explicitly asks about disjoint movies, hashes, collection/session independence and a later bounded acquisition proposal. | Only existing IDs/status metadata were read for these corrections, no new scientific endpoints or raw payloads. Snapshot status is not current completion. All cohorts remain INCOMPLETE; no confirmatory cohort, acquisition or harm margin admitted. |
| F4, W7 diff semantics | Each row records GitHub base tip, actual merge base and exact three-dot command. #250's merge base is `c8844894` while its GitHub base tip is `36913740`; its PR-contribution paths are not the two-dot whole-tip difference. | Original path/byte evidence preserved; neither docs-only contributions nor metadata sizes establish source qualification or retrieval. |
| F5, #256 wording | Parent changed the dated live body note to “#260's scalar repair does not remove the principal S1 discrepancy”, then read it back with head `f62572947572259abd197c1deaa024c3a1020e13` unchanged. New `sources/pr256-round2-after.json` retains the capture; the earlier after-snapshot remains untouched. | Body clarification only; no source, outcome, PR-state or historical-report change. |

The original report's M8 readiness and W7 direction-only assessment remain
recommendations for the maintainer, not adopted dispositions. All drafts remain
UNAPPROVED, C1 qualification remains incomplete, C2 unfrozen, and prospective
native/scientific/policy controls remain UNRUN. No new held-out outcomes were
inspected by these corrections. Round 2 must independently assess the integrated
packet and any unresolved objections; it is a fresh delegated task.
