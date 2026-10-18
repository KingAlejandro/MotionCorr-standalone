# DRAFT / NOT RUN: confirmatory timing for tutG and e10216L (#228, D14)

Prepared 2026-10-18 after review R-D11 round 3. **No timing has been run with these files.** The maintainer decides between running this design (option a) and accepting D14 as unmet with an explicit exception (option b).

- `rule.txt`: the declared design. It is frozen once run; corrections go in a dated note.
- `confirm_pairs.py`: the driver. `run` executes one window; `combine` merges a workload's windows and applies the D14 labels.
- `wd11_confirm.sbatch`: SCARF exclusive-node job (primary venue). Set `FIX_SHA` to the PR head and refresh the staged bundle at submission.
- `confirm_4gpus.sh`: 4GPUs GPU3 fallback. One bench-lock window per segment.

## What changes against the executed 4GPUs design

| Gap found in review | Draft |
|---|---|
| Last null block not after the last comparison block when N/2 is not a multiple of 8 (e10216L, N = 72) | Null block j follows comparison block ceil(j·B/K) inside each window, so the last always follows the last comparison block. Checked for N = 256, 176, 72, 200 and 64. |
| Arm label `A'` in the output path broke the unquoted `gs` call, and the run still exited 0 | Labels are `main`, `fix`, `mainb` ([a-z]+ only). |
| Exit 0 was taken as a complete product | Each run must have: per movie a structurally complete MRC and a non-empty STAR; the joint STAR; and `logfile.pdf` with exactly 3 + movies pages, counted by Ghostscript. Otherwise the run is invalid and its pair is rerun in the same position (≤ 3 attempts). Every run's stdout/stderr is kept. |
| Pilot-based N undershot (e10216L: 0.70% achieved against 0.49% expected) | Sized from the completed 4GPUs definitive runs, which serve as the pilot, by scaling the observed CI upper bound by √N, with a 1.25 margin: tutG N = 256, e10216L N = 176. Fixed in advance and not extended. |
| One window per workload | Two equal windows per workload, each balanced and with its own 4 null blocks, run in the order tutG-1, e10216L-1, tutG-2, e10216L-2. |

The completeness check was exercised on a kept 4GPUs output tree whose MRCs had been deleted. It reported both missing MRCs and counted the 5-page `logfile.pdf` of that 2-movie job. That was a code check, not a timing run.

## Estimated wall time

Per-run cost is taken from the executed 4GPUs windows: tutG 26.5 min for 302 runs (5.3 s each), e10216L 19.3 min for 190 runs (6.1 s each). About 0.3 s per run is added for the product and PDF checks.

| Window | Runs (2 warm-up + 2 × pairs) | Estimate |
|---|---|---|
| tutG 1 or 2 (64 AB + 64 BA + 8 null pairs) | 274 | ~26 min |
| e10216L 1 or 2 (44 AB + 44 BA + 8 null pairs) | 194 | ~21 min |

- **4GPUs GPU3:** 4 windows, each ≤ 45 min with margin. About 94 min of window time, plus waits for other workers' bench-lock windows between windows. Builds are already recorded.
- **SCARF exclusive node:** the same 4 windows back to back, about 94 min if a SCARF A100 runs at 4GPUs speed. Add staging and two in-allocation builds (~10–15 min). The job requests 3 h. Queue wait (`QOSGrpNodeLimit`) is not included.

Reruns of invalid pairs add about 11 s (tutG) or 13 s (e10216L) each.
