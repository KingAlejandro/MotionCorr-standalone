# Confirmatory timing for tutG and e10216L (#228, D14): FROZEN DESIGN (round-7 revision, 202fd5bf follow-up), NOT RUN

The maintainer chose to run it (option a). Venue: **4GPUs GPU3 only**. **No timed pair runs before the coordinator's "GO"**, which follows a re-check by R-D11. After GO the four windows run once and the results are committed as evidence.

| File | Role |
|---|---|
| `rule.txt` | The declared design. Frozen; corrections go in dated notes only. |
| `confirm_pairs.py` | Driver. `freeze` writes the manifest; `run` executes one window under the deadline, verifying everything first; `combine` validates the evidence and assigns the D14 label. |
| `vendor/` | Byte copies of `tools/profiling/lib/stats.py` and `identity.py`, hashed in the manifest. |
| `confirm_4gpus.sh` | Launcher: `freeze`, then `windows` (tutG-1, e10216L-1, tutG-2, e10216L-2, then combine). |
| `control_unreapable.py` | Integrated unreapable-payload control (`timed_payload` → `run_window` finally); also run against the `202fd5bf` driver. |
| `controls.py`, `controls/` | Synthetic and dry-run controls and their output. No GPU payload; locks only on a private temporary file. |

## Frozen state

| Item | Value |
|---|---|
| Frozen source | `21b19aac0099acb27b70507090bb83e463cded33`, clean checkout `W-D11/src-confirm`; it stays clean |
| `confirm_pairs.py` | sha256 `785736739b41e1f619db660e0d8ee97bb62a3763442447cfab0e58a2506e2516` |
| `rule.txt` | sha256 `c3b55a0a66024512d64b6721e890035d494a2a61732451a243e42011a38bf85a` |
| `vendor/stats.py`, `vendor/identity.py` | sha256 `8d61e054…173c7c`, `e44cfd0f…be4645` (unchanged) |
| `manifest.json` | sha256 `cb3c396b077d01aff368e9188cb2056ad6c724e4e0322e0a6d1596d1e24782cf` (copy here; the run uses `W-D11/confirm4/manifest.json`) |
| Window budget | 2700 s total lock tenure: work by 2690 s, release by 2700 s; an unreapable payload ends the window INCOMPLETE and does not hold the locks |
| Frozen masks and locks | payload 88–95, runner 120–123; `/tmp/motioncorr-bench.lock`, `/tmp/motioncorr-gpu3-correctness.lock` |
| Binaries | main `c2263c22…f8dd`; fix `29b894f0…c185`, built from `78aae2d3`, source-equivalent to `21b19aac` |
| Inputs | tutG 26 files, e10216L 4; `verify` passed for both after freezing, with no lock taken |
| Superseded | designs frozen at `38fbfa6f`, `8aed9b0b`, `6b797438` and `202fd5bf`, kept in `superseded-*/` |

Later evidence commits on the branch do not change the frozen files. Every window re-verifies them before taking a lock.

## Change for the 14:33Z review of `202fd5bf` (supersedes the design frozen at `202fd5bf`)

| Finding | Change | Where | Control (author-reported) |
|---|---|---|---|
| After the watchdog's SIGKILL, an unreapable payload left the caller in an unbounded `p.wait()`, so `run_window`'s `finally: release()` was never reached and the locks stayed held past 2700 s | A waiter thread does the blocking `wait()` and records the reap time, so successful runs keep exact wall times with no polled `wait(timeout)`. The supervisor waits on the waiter's event for at most timeout + `REAP_GRACE_S` (2 s), with the payload budget reduced by that grace so it ends inside the work deadline. A payload still unreaped is recorded as failure `unreaped` ("GPU state unknown") and ends the window INCOMPLETE; `release()` retries its reap, records it in `unreaped_pids` and releases the locks. Reaping stops `UNLOCK_RESERVE_S` (0.5 s) before the release deadline, so the unlock lands inside the budget | `confirm_pairs.py` :136–170 (`timed_payload`, waiter :149, bounded supervisor :165), :175, :193, :291, :487, :527; `rule.txt` :43–49 | `control_unreapable.py`: the real `run` with only the payload replaced by a process SIGKILL cannot reap. **Against the `202fd5bf` driver: FAIL**: lock acquired at 0.21 s, never released in 35 s, driver blocked, no marker. **Against this driver: PASS**: lock released at 19.6 s of a 20 s budget (driver `released_after_s` 19.5), INCOMPLETE, payload in `unreaped_pids`. Timing control still exact (25 ms recorded as 24.9 ms) |

## Change for review R-D11 round 7 (supersedes the design frozen at `6b797438`)

| Finding | Change | Where | Control (`controls/ctl-run.txt`) |
|---|---|---|---|
| Cleanup sat outside the 45-min budget; the 10 s margin was not enforced | The 2700 s budget is the total lock tenure: work ends at `start + 2700 − 10` (the deadline every bounded step uses) and release must finish by `start + 2700` (`confirm_pairs.py:419–422`, `CLEANUP_MARGIN_S` :162, `RELEASE_DEADLINE` :163). `release()` sends SIGKILL to every registered process group (payload, samplers, children) first, then reaps all of them against that one shared deadline. Unreapable processes are recorded and the locks released regardless (:272–281). The post-SIGKILL reap in `run_child` is bounded by the same deadline (:181). `complete.json` requires release by the deadline and nothing unreaped (:309, :563); the marker records `unreaped_pids` (:573) and `combine` requires it empty (:703). `rule.txt:45–55` | `confirm_pairs.py` :162–163, :181, :246, :272–281, :309, :419–422, :563, :573, :703; `rule.txt` :45–55 | With a 15 s budget standing for 2700 s, locks were released at **5.010 s** (delayed product check), **5.008 s** (delayed deletion) and **5.012 s** (aggregate: pending `mpstat` and `nvidia-smi` samplers plus a stalled registered child). All are within 15 s with ~10 s to spare, INCOMPLETE, nothing unreaped, no orphans. Unit control: three unreapable processes reaped against one 2 s deadline in **2.02 s** (5 s each before), unreaped recorded, lock released. A marker with an unreaped process gives INCOMPLETE |

Full suite on 4GPUs CPUs 24–39 with no GPU payload, using the frozen driver and rule: **75/75 as required**.

## Changes for review R-D11 round 6 (supersedes the design frozen at `8aed9b0b`)

Only the two findings. Line numbers are in `confirm_pairs.py`.

| # | Finding | Change | Where | Control (`controls/ctl-run.txt`) |
|---|---|---|---|---|
| 1 | `combine` accepted contradictory evidence | CPU masks and locks are frozen in the manifest (:349) and read from it by `run` (:410, :429). The header must equal them: disjoint masks, non-empty locks, deadline = start + budget (:593). Every retained payload must carry an observed mask equal to the frozen payload mask and the expected PDF page count (:634). There must be exactly one identity record in the stream, at position 1, identical, with no problems and at least one (MRC) comparison (:652). The completion marker must match the header's start and deadline, the workload, window, positions and budget, with remaining ≥ 0, end ≤ deadline and release within the budget (:689) | :349, :410, :429, :593, :634, :652, :689 | At N = 256 each of the reviewer's cases gives INCOMPLETE: every payload with mask `0`; mask and page observations removed; a header with overlapping masks and no locks; identity true but with problems, zero comparisons and position 99; a marker deadline beyond the header's. All round-5 cases still give INCOMPLETE, and complete data still gives PASS, FAIL or UNRESOLVED |
| 2 | Deadline did not bound all lock-held work | `run_child` (:165) runs a child in its own process group, registered for `release()`, and kills it at the remaining time. The whole product check (structure and PDF, :507) and identity (:532) run through `child_json` (:186); per-run deletion is a bounded `rm` (:515); GPU queries use it too. `release()` kills registered children as well as payloads and samplers (:263). Identity-failure evidence is copied only after release (:536, :553). The completion verdict is taken at release (:549). Declared cleanup margin: 10 s | :165–197, :263, :507, :515, :532, :536, :549, :553 | Delayed product check (a slow `gs` on `PATH`) and delayed cleanup (a slow `rm` on `PATH`), each with a 15 s budget: resources released at **15.021 s** and **15.018 s** (≤ budget + 10 s), INCOMPLETE, lock free, no orphans |

Control suite (groups A–E plus the new cases) on 4GPUs CPUs 24–39 with no GPU payload, using the frozen driver and rule: **72/72 as required**. Timing control: 25 ms recorded as 24.94 ms; the legacy polled wait gave 50.10 ms.

## Changes for review R-D11 round 5 (supersedes the design frozen at `38fbfa6f`)

Only what the six findings require. Line numbers are in `confirm_pairs.py`.

| # | Finding | Change | Where | Control (`controls/ctl-run.txt`) |
|---|---|---|---|---|
| 1 | `combine` accepted incomplete or contradictory streams | Strict chronological validation of each window: exactly one header matching the manifest (venue, GPU, masks, locks) with `dry_run` explicitly false; the lock record; two successful warm-ups; per position its attempts (payload, payload, pair record) with consecutive `seq`, pair records consistent with their payloads (including `seqs`), retained walls equal to the payload walls; exactly one successful identity record after the first retained pair; nothing after the last position | `validate_window` :528–607, called from `combine` :610 | At N = 256, each of the reviewer's cases gives INCOMPLETE: headers removed, identity removed, payloads removed, every payload a resource failure, order reversed, retained walls ≠ payload walls. So do: another venue in the header, one position out of order, truncation, zero pairs, a malformed record, a missing window, a dry-run header and a warm-up failure. A real dry-run stream from the driver passes every check except the dry-run flag |
| 2 | Polled `wait(timeout)` quantised completion to 50 ms | `timed_payload`: blocking `p.wait()`, wall = monotonic at reap − monotonic at spawn; the timeout is a watchdog thread that kills the process group | :136–157 (`p.wait()` :154, watchdog :144) | Completions 25 ms apart recorded **24.99 ms** apart (error ≤ 1 ms; 12 alternating repetitions of `sleep 0.300`/`0.325`). The legacy polled wait records **50.40 ms** on the same payloads, so the control can fail. A hung payload is killed by the watchdog at 3.0–4.0 s with a 3 s timeout |
| 3 | Deadline not enforced across lock-held work | `left()` bounds GPU queries, the product/PDF check (:464) and the identity check, which runs in a child process with `timeout=left()` (:490); sampler joins are bounded (:456); release waits ≤ 5 s after SIGKILL; `completion_status` (:262, used at :514) never writes `complete.json` after the deadline; `combine` rejects a negative remaining budget or an end time after the deadline (:634) | :378, :456, :464, :490, :262, :514, :634 | `completion_status` gives incomplete after the deadline. Synthetic markers with −2.0 s remaining, or written after the deadline, give INCOMPLETE. Dry-run deadline window: payload killed, incomplete, lock released, no orphans |
| 4 | Source not re-verified per window; helpers importable from mutable paths | `verify` (:318) checks before any lock: `source_head`, clean tree, driver location in the frozen tree, build-equivalence statement, and hashes of `confirm_pairs.py`, `rule.txt` and the vendored `vendor/stats.py`/`identity.py` (byte copies of `tools/profiling/lib`, :30). Git and setup errors are fatal. No bytecode is written, so the tree stays clean (:18). `combine` uses the vendored, hash-checked stats | :18, :30, :318–345 | A throwaway git repository with the frozen directory: clean head accepted; wrong head, invalid source path, changed equivalence, changed vendored stats and an untracked file are all fatal before any resource. This control found a real defect: importing the helpers wrote `__pycache__` into the checkout, so window 2 would have failed. Fixed by `dont_write_bytecode` |
| 5 | Warm-up failures bypassed the failure rule | Any unsuccessful warm-up ends the window as INCOMPLETE; `combine` also rejects a failed warm-up | :475–478, :573 | Dry run: a fix warm-up product failure gives incomplete.json ("warm-up fix failed"). Synthetic: a warm-up failure gives INCOMPLETE |
| 6 | Missing CPU-mask evidence accepted | The watcher observes the executable and its mask first, polling `/proc` every 2 ms before any GPU query (:425); `classify` (:244) makes a run invalid without an observation, if the sampler did not finish, or if the mask differs | :244–259, :425–434, :460 | `classify`: no observation, unfinished sampler and a different mask are invalid; a valid observation is valid. Dry run: every timed payload has an observed mask equal to the payload mask |

Control suite (all groups A–E) on 4GPUs CPUs 24–39 with no GPU payload, using the frozen driver and rule: **65/65 as required**.

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
