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

## PR133 clean successor — built, validated, not proposed

Branch `perf/single-gpu-pools`, head `054ed6d`, base `b4536e2` (= main + PR130 + PR131).
Pushed to origin to preserve it. **No PR opened**: its base does not exist on origin until PR130
and PR131 land. PR133 `bed17cd8` and `perf/nvcomp-next` `e3ba798e` are untouched and retain their
evidence.

Five reviewable commits, each building on its own:

| # | commit | mechanism | origin |
|---|---|---|---|
| 1 | `12b9599` | worker-lifetime device-gain retention | `7dbf963` (precondition: all four parent blobs identical to `1420c8cc`) |
| 2 | `761617b` | static defect premask cache + sparse defect traversal | `bed17cd8` end state, **not** `c801f72` |
| 3 | `9903c68` | global cuFFT plans + shared work area + inverse tile | `bed17cd8`, repaired |
| 4 | `6a20636` | batched patch R2C plan | `bed17cd8`, repaired |
| 5 | `054ed6d` | dose-weighted C2R plan + retained accounting | `bed17cd8` hunks applied **on top of** the PR131 file |

Excluded and verified absent from `git diff --name-only b4536e2 054ed6d`: `cuda_alignpatch.cu`
(PR130 owns it), `tests/cuda_alignment_sync.cpp`, `tools/single_gpu/run_alignment_mutants.py`,
`docs/post128_alignment_sync/**`, the FFT-sync experiment, prefetch and old profiling patches.

### Repairs folded in

(A) `holds_lease` is set only on a successful `acquireLease`; `ReleaseFailureGuard` captures it and
is a no-op for a non-owner, so a refused session can no longer retire the owner's pool.
(B) all three `drop()` sites check the result; no replacement plan and no publication after failed
cleanup, with a later-fatal-after-recoverable case covered.
(C) a `RetirementContext` selects the owning device and restores the caller's; each rebuild site
re-selects its requested `device_id`.
(D) `ScopedDeviceMemory::disown()` added; `fresh_work`/`fresh_tile` adopted immediately and published
only after full construction. No discarded-status raw `cudaFree` left on that path.
(E) device gain: checked frees, owning-device select, retirement on session failure,
`ensureDeviceGain(nullptr)` releases an owned buffer, and the `gainReferenceFor` →
`setGainGeneration` ordering is now asserted.
(F) stale geometry retired **before** the new movie's buffers are allocated at all four sites.
(G) premask invalidate-before-rebuild, traversal order, neighbour order and RNG draw counts
preserved; defect key strengthened to path + size + mtime.
(H) PR131's `computeDoseNormalizationKernel` and `applyDoseWeightKernel` verified byte-identical to
`3c2282fa`; `cuda_dose_normalization.cpp` retires the pool before each `empty()` without relaxing the
leak oracle.

Two powered negative controls were run: removing the `owner &&` gate fails `CudaPlanPool` on
"a refused session retired the owner's pooled entry", and restoring the allocate-before-drop order
fails it on "the stale geometry was retired only after the new movie's buffers were allocated".

### Validation (executed on 4GPUs at `054ed6d`)

ctest, independently rerun by the coordinator: CPU-only 32/32, CUDA 42/42, CUDA+nvCOMP **43/43**.
Base was 32/40/41; the two additions are `CudaDeviceGainPool` and `CudaPlanPool`. No NAME lost.
24-movie exact non-PDF tree vs main: **PASS, 0 different files**, 24 MRC / 25 STAR /
341,735,520 pixels per arm; both arms 24 global / 600 patch / 24 DW / 24 nvCOMP witnesses, 0 warnings,
109 products.

### Retained residency — the number to decide on

**269.53 MiB held per worker thread between movies**: global workspace 56,986,624 B, inverse tile
56,986,624 B, patch plan 54,710,784 B, DW plan 56,986,624 B, gain 56,955,920 B.

It is now accounted and logged, and the stale-geometry ordering defect is fixed, so an old large
geometry can no longer deny a smaller valid movie. There is still **no byte cap, no `cudaMemGetInfo`
admission check and no eviction** — the bound is observable, not enforced. The figure is appended to
the `Peak VRAM:` line, which the exactness gate drops from both arms, so it has no automated
regression guard.

### UNRUN

Genuine cross-device retirement and execution (`gpu_id` is process-wide; device-selection controls are
logic-only with an injected `cudaSetDevice`). No timed benchmarks and no speedup claim — the
"719.5 ms" figure in commit 1's message is inherited verbatim from `7dbf963` and was not re-measured.
Intermediate commits had targeted test subsets; only the head has the full three-config matrix.
Host-memory cost of the premask cache was not measured.

## 2 October — measurement and the remaining lanes

### PR135 merged into PR131

`71fee25` merged into `experiment/post128-dose-normalization`; PR131 head is now
`7f8e813`, both CI jobs pass at that head, production byte-identical to the
native-tested `2fe51dd`, and the retrospective-sealing disclosure is intact — it still
states explicitly that the old runs did not use the new marker mechanism.
PR131 is **not** merged to main.

### PR132 fixed at `2bf7ee1`

Both CI jobs pass. `arms24_json.py` missing import and uncreated output dir; silent
`except Exception: pass` around the VRAM series. `patch_nvtx.py` needed **two** fixes,
not the one the audit found — repairing the anchor strings alone still produced a tree
that failed to compile, because the per-movie replacement body re-emitted the old
`executeOwnMotionCorrection(Micrograph&)` signature. Its `assert` gates vanished under
`python -O`; now `SystemExit`. The output scope is renamed `submit output` because the
write is async on current main and that position measures a handoff.

`arms24.svg` replaced by `arms24_wall.svg` + `arms24_device.svg`. Stale captions
corrected: geometry `3838x5760` -> `3710x3838`, `abd6827` unmerged -> ancestor of main,
197 commits -> 23 against current main, the 4.21 s patch-align double attribution, two
sections numbered 9, and the README's generality claims.

`tools/nsys_analysis/selftest.py` added: 0 failures on the fixed tree, 7 real failures
on the pre-fix tree. Not CTest-registered — this lane touches no build files.

### PR136 opened — the clean PR133 successor

Base `integrate/single-gpu-release-base` = main + PR130 + PR131(`7f8e813`), pushed so
the PR shows only the five mechanism commits. **Retarget to main once #130 and #131
land.** PR133 and `perf/nvcomp-next` untouched; supersession noted on #133.

Five commits `bc695da`, `2dfcc14`, `fa3f18a`, `5bdd119`, `a118699`, plus the measurement
commit `43f578f`. Rebased from the validated `054ed6d` onto the refreshed base; the
production tree (`src/`, `tests/`, `CMakeLists.txt`) is byte-identical across that
rebase, so the earlier validation carries over unchanged.

ctest 32/42/43 (base 32/40/41, +`CudaDeviceGainPool` +`CudaPlanPool`, none lost).
24-movie exact non-PDF tree vs main: PASS, 0 different files.

### Measured result

7 independent build arms, 5 interleaved repetitions each with alternating order, 35
clean runs. Branch parent -> head: **12.312 -> 9.678 s, 21.40%**, 5/5 paired faster,
median paired saving 2.743 s. CPU-seconds 18.52 -> 15.59.

| mechanism | saving | share |
|---|---|---|
| device-gain retention | +0.650 s | 24.7% |
| premask + sparse traversal | +1.614 s | 61.3% |
| three cuFFT plan pools together | +0.370 s | 14.0% |

**The decision this forces:** the premask commit carries 61% of the gain at zero
retained-VRAM cost; the three plan pools buy 0.370 s and cost the whole 269.53 MiB.
Their individual steps are below the IQR of the arms they sit between and are not
resolvable at n=5. Dropping commits 3-5 costs 14% of the gain, not 100%.

Device side: kernel union unchanged (3.058 vs 3.061 s) — nothing here makes the GPU
compute faster. H2D 4.62 -> 3.31 GB, and the 1.31 GB difference matches
56,955,920 B x 23 avoided gain re-uploads exactly. GPU still idle ~two thirds of the
span. Host stages: `fix defect` 1.758 -> 0.019 s dominates; `patch align` is 0.180 s
**slower**, on a single instrumented capture per arm, recorded not explained.

Measurement integrity: the box is shared. Two runs were caught with a co-tenant and
re-run. An earlier harness version compared GPU **UUIDs**, which cannot see a
neighbour on the same GPU; two observations passed that check before it was corrected
to compare PIDs, and they are excluded.

Evidence: `docs/profiling_20261002/` on `perf/single-gpu-pools`. Raw nsys captures
retained on the host at `/home/alex/mc-release-20261002/prof/`.
