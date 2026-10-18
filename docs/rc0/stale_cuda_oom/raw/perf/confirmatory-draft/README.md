# Confirmatory timing for tutG and e10216L (#228, D14): FROZEN DESIGN, NOT RUN

The maintainer chose to run it (option a). Venue: **4GPUs GPU3 only**. **No timed pair runs before the coordinator's "GO"**, which follows a re-check by R-D11. After GO the four windows run once and the results are committed as evidence.

| File | Role |
|---|---|
| `rule.txt` | The declared design. Frozen; corrections go in dated notes only. |
| `confirm_pairs.py` | Driver. `freeze` writes the manifest; `run` executes one window under the deadline, verifying everything first; `combine` validates the evidence and assigns the D14 label. |
| `confirm_4gpus.sh` | Launcher: `freeze`, then `windows` (tutG-1, e10216L-1, tutG-2, e10216L-2, then combine). |
| `controls.py`, `controls/` | Synthetic and dry-run controls and their output. No GPU payload; locks only on a private temporary file. |

## Frozen state

| Item | Value |
|---|---|
| Frozen source | `72152947c2fa8240541447fbefc360016958366e`, clean checkout `W-D11/src-confirm` |
| `confirm_pairs.py` sha256 | `ab4e68edd3388ed2baf2203d65be6342b454680a0c4338777289c08ec46aced2` |
| `rule.txt` sha256 | `346399f8d324f4820490b0ed0ab871ae7e91b205bff7b087094118fe0bc215b8` |
| `manifest.json` sha256 | `c6b92eee15bf5593fca4e22cdfba9d727152a98321457ec01b5709445b0b52d9` (copy here; the run uses `W-D11/confirm4/manifest.json`) |
| Binaries | main `c2263c22…f8dd`; fix `29b894f0…c185`, built from `78aae2d3`, source-equivalent to `72152947` (checked by `freeze`) |
| Plan | tutG: 136 positions per window (64 AB + 64 BA + 8 null pairs); e10216L: 96 per window (44 + 44 + 8) |
| Inputs hashed | tutG 26 files (24 movies, gain, STAR); e10216L 4 files |

Later evidence commits on the branch do not change these files. The frozen hashes are verified again at the start of every window.

## Changes for review R-D11 round 4

| # | Finding | Change | Control (`controls/ctl-run.txt`) |
|---|---|---|---|
| 1 | PDF expectation wrong for more than 3 movies | `expected_pdf_pages = 3 + (3 if movies > 3) + movies`, from `motioncorr_runner.cpp:1723–1745`: tutG 30, e10216L 6 | Real CPU-build products with 4 and 3 movies: 10 and 6 pages, complete. Synthetic 24-movie tree: 30 pages accepted, 27 and 24 rejected. Synthetic e10216 tree: 6 accepted, 9 rejected |
| 2 | `combine` could PASS incomplete evidence | It validates the manifest, both windows, completion markers, every planned position and order, counts, balance and the CI first; any gap gives INCOMPLETE, never an exception | Missing window, truncated window (with and without a forged marker), zero pairs, malformed record, swapped order and missing manifest all give INCOMPLETE; complete data gives PASS, FAIL or UNRESOLVED as constructed |
| 3 | Identity failure did not block PASS | Recorded, both trees kept in `identity-failure/`, never retried, workload INCOMPLETE | Synthetic: INCOMPLETE with "product identity failed". Dry run: recorded once, evidence kept |
| 4 | Pre-existing GPU occupants; GPU/CPU mapping | Rejects occupants before each run and failed queries; samples during the run; GPU by UUID; payload mask ⊆ allowed ∩ GPU-local CPUs (sysfs `local_cpulist`), runner ⊆ allowed, disjoint, actual mask read from `/proc` | Code path only: needs the GPU, so it is not exercisable without a payload |
| 5 | 45-min window not enforced | One deadline from the first lock request covers lock waits, the idle-GPU wait and all payloads; 120 s per-payload timeout; `finally` and SIGTERM kill and reap children and samplers and release the locks; an unfinished window gives INCOMPLETE | Dry run: payload timeout kills and reaps, pair rerun; window deadline gives incomplete.json, lock released, no orphans; deadline during the lock wait gives incomplete with no payload started |
| 6 | Provenance and staging | `freeze` records driver/rule hashes, source SHAs, binary hashes, build settings, arguments, input hashes, venue and plan; `run` re-verifies before any lock; setup and git errors are fatal. A clean `src-confirm` checkout of the frozen head is used (the old `src-head` lacked the driver). The fix binary was built from `78aae2d3`, source-equivalent to the head (identical `src/`, comment-only `CMakeLists.txt`); `freeze` checks this | Dry run: a binary changed after freezing is fatal before any resource (no output, lock free) |
| 7 | Failure classification | resource / exit / timeout / product per run; attempts and failures by arm; ≥ 2 payload failures, or any on fix alone, give INCOMPLETE; 3 failed attempts at one position end the window | Synthetic: one fix product failure gives INCOMPLETE; failures on main and mainb give INCOMPLETE; one isolated main failure still gives PASS. Dry run: exit-0 product failure on fix classified "product" and rerun in the same position |
| 8 | Structural checks | Positive dimensions, `nsymbt` ≥ 0, mode 2, MAP stamp, exact size; joint STAR rows equal to the expected movie set | Real-tree mutations rejected: zero dimension, negative nsymbt, truncated MRC, empty per-movie STAR, joint STAR missing a movie, with no rows, or deleted, PDF deleted |
| 9 | Sizing wording; venue | Called a planning heuristic; N fixed; 4GPUs declared as the only venue; no switching or choosing between results | Not applicable |
| 10 | Labels | Exactly PASS / UNRESOLVED / FAIL / INCOMPLETE | Checked for every synthetic result |

Controls ran on 4GPUs CPUs 24–39 (node 0) with no GPU payload: **41/41 as required**. The two real products came from the CPU-only build `05fc48e5…`.

## Estimated window times (after GO)

Per-run cost comes from the executed 4GPUs windows (tutG 5.3 s, e10216L 6.1 s per run, including overhead), plus about 0.4 s for the product, PDF and mask checks. Each window: 2 warm-up runs, then 2 × (N/4 comparison + 8 null) pairs.

| Window | Runs | Estimate | Deadline |
|---|---|---|---|
| tutG-1, tutG-2 | 274 each | ~26 min | 45 min |
| e10216L-1, e10216L-2 | 194 each | ~22 min | 45 min |

That is about 96 min of window time in total, plus any wait for other workers' bench-lock windows. A wait counts against the window's deadline.
