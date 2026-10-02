# Single-GPU release ledger — 2026-10-02

No merge was performed. Main is unchanged at `c499b1d3bf1cceec5c3b194f356844d6f493e7f2`.
Merge authorization is per-PR in this repository (precedent: PR110, "This authorization
applies to 110 only"); none was given for this queue.

## Pinned heads (refetched 2026-10-02, all current)

| Candidate | Branch | Head | Base | CI |
|---|---|---|---|---|
| PR130 | experiment/post128-single-gpu-opt | `1420c8cc` | main | 2/2 pass |
| PR131 | experiment/post128-dose-normalization | `3c2282fa` | main | 2/2 pass |
| PR132 | docs/single-gpu-execution-profile | `0b58cbc0` | main (merge-base `1d7e13f`) | 2/2 pass |
| PR133 | perf/nvcomp-opt | `bed17cd8` | perf/nvcomp-next `e3ba798e` | 2/2 pass |

`main` protection: `enforce_admins=true`, 0 required approvals, **no required status checks**,
force-push and deletion disabled.

## Native validation venue

4GPUs (`4-gpu-vm`), A100 80GB PCIe `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, 124 CPUs,
THP `madvise`, CUDA 12.8, nvCOMP 5.3.0.16, cmake 3.28.3, python 3.12.3.
Builds `-DCMAKE_BUILD_TYPE=Release`, payload `taskset -c 64-71`, `OMP_NUM_THREADS=6`.
Input identity `movies.star sha256 fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`
— the same input as the retained SCARF campaign.

This venue is **not** the PR130/PR131 campaign venue (SCARF gn0004, A100 40GB). Timings here
are not comparable with the retained campaign and are not used as measurements.

## ctest NAME union (executed here)

| Tree | CPU-only | CUDA no-nvCOMP | CUDA+nvCOMP |
|---|---|---|---|
| main `c499b1d3` | 32/32 | 38/38 | 39/39 |
| PR130 `1420c8cc` | 32/32 | 39/39 | 40/40 |
| PR130+PR131 `b4536e2` | 32/32 | 40/40 | 41/41 |

Additions are exactly `CudaPatchWorkspace` (PR130) and `CudaDoseNormalization` (PR131).
No registration present at main is missing downstream.

## Exact-output gates (executed here, 24 tutorial movies, CUDA+nvCOMP)

* main vs PR130 — **PASS**, 0 different files, 24 MRC / 25 STAR / 341,735,520 pixels per arm,
  full normalized and extended headers. Both arms: 24 global, 600 patch, 24 DW witnesses,
  24 nvCOMP ingest witnesses, 0 warnings, 109 products each.
* main vs PR130+PR131 — **PASS** with PR131's own declared `--allow-added-log-line 'Peak VRAM:'`.
  Without it, 24 per-movie logs differ; the only non-timing, non-path difference is that one line.
  Measured plane cost: Peak VRAM 217.33 → 244.50 MiB, **+27.17 MiB**, matching the calculated
  28,493,312 B / 27.173 MiB exactly.

## PR130 evidence reuse

Licensed: production source (`src/` + `CMakeLists.txt` + `tests/`) is byte-identical between the
measured snapshot `8bf7c1f` and the proposed head `1420c8cc`. Independent recomputation of
`evidence/confirmation-runs.json` reproduces baseline median 13.193289663 s, candidate
12.422485125 s, **5.842398 %**, median paired saving 0.716654829 s, range 0.676221554–0.862440481,
5/5 faster.

Correction to the evidence record: `SOURCE_PIN.json` says `production_unchanged_since: 35321e1`.
The true anchor is `78853e1`, which changed `src/motioncorr_runner.cpp` and `CMakeLists.txt`
after `35321e1`. `78853e1` is an ancestor of the measured `8bf7c1f`, so the campaign is unaffected.

## PR130/PR131 composition conflicts (coordinator-owned)

1. `CMakeLists.txt` — both insert a test block at the same anchor. Additive; keep both.
2. `tools/single_gpu/summarize_campaign.py` — add/add. PR131's version is strictly stronger
   (`--phases`, COMPLETE.json inventory, completeness and duplicate checks) and PR130 has no
   caller. **Take PR131's version.** Consequence to disclose: PR130's retained campaign predates
   the COMPLETE.json mechanism and cannot be re-summarized with the merged tool; its
   `campaign-summary.json` stands as produced by the PR130-era summarizer.

Resolved composition built and validated as `b4536e2`.

## PR131 follow-up (prepared, not pushed)

Branch `experiment/post128-dose-normalization-followup`, commit `71fee25`, off `3c2282fa`.
Binds every arm's `device.csv` into `COMPLETE.json` and verifies the inventory before any sample
is read; converts all 16 bare asserts in the summary and control harness to explicit raises.
Executed on 4GPUs: new controls vs unfixed tools rc=1 (`actual summary accepted changed-device`);
vs fixed tools rc=0; fixed tools under `PYTHONOPTIMIZE=1` rc=0. Production byte-identical to
the native-tested `2fe51dd`.
