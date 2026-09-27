# Worker status — Issue 73 — Independent dataset scientific validation

Session: headless Opus, isolated checkout `work/headless-opus-20260927/issue-73`.
Branch `opus/issue-73-headless-20260927`, base `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26`
(verified identical to live `origin/main` at 2026-09-27; no base update needed).
Draft PR #87.

## State: protocol frozen and amended, CPU feasibility pilot running

| Step | State |
| --- | --- |
| Verify starting commit, fetch live origin | DONE — HEAD == origin/main, 0 ahead / 0 behind |
| Read AGENTS.md, ADR #66, issues #73/#61/#60, PRs #65/#64 | DONE |
| Host survey for already-staged independent data | DONE — none exists (`docs/issue73/HOST_DATA_SURVEY.md`) |
| Identify legal/shareable independent collection | DONE — EMPIAR-12963, CC0 |
| Verify raw movies + gain + particles + downstream | DONE — all present and read |
| Verify native format support | DONE — EER decoded, 8192² grid rendered (see below) |
| Derive margins from collection physics | DONE — `tools/science_issue73/i73_margins.py` |
| Storage/compute estimate | DONE — confirmatory set 270 GiB raw / ~445 GiB working |
| **Freeze protocol** | DONE — `4766f20` |
| Acquire ≤ 2 GiB feasibility subset | DONE — **1575.5 MiB of 2048 MiB**, hashed in `acquisition_manifest.json`. Acquisition closed. |
| CPU-only build at pinned commit | DONE — `20b12ef4…`, zero CUDA linkage |
| Fix `--eer_grouping` / `--dose_per_frame` | DONE — `PROTOCOL AMENDMENT` `e9a5f84` |
| CPU pilot on 2 development movies | DONE — both exit 0, `results/PILOT.md` |
| Fix gain orientation | DONE — `PROTOCOL AMENDMENT` 3; no rotation/flip needed |
| Paired native-CUDA pilot | RUNNING — SCARF Slurm job `3510296`, dedicated GPU allocation |
| Confirmatory 350-movie study | **BLOCKED — not authorized** (see below) |

## Result claims so far

**None.** No scientific pass/fail is claimed. Nothing here establishes signal equivalence
between backends. The pilot is a plumbing and orientation check on two development movies with
~104 particles and is declared incapable of the primary endpoint by `PROTOCOL.md` §10.

## What the pilot has confirmed so far (plumbing, not science)

From the running CPU arm's own log, on genuinely independent data:

- `Movie size: X = 8192 Y = 8192 N = 40` — `--eer_upsampling 2` renders the 8192² grid the
  deposited particles were picked on, and `--eer_grouping 47` yields exactly the depositors'
  40 fractions. Both amendment values are confirmed by execution, not assumed.
- Global alignment converges 2.85 → 0.32 px; all 25 patches converge to 0.14–0.85 px.
- 85 hot pixels detected and corrected; polynomial fit RMSD X 1.96 / Y 1.54 px.

Then checked and passed (`tools/science_issue73/i73_check_pilot.py`, raw output in
`results/pilot_cpu_check_*.json`): corrected micrographs are 8192² at 0.485 Å with zero
non-finite pixels, and the deposited coordinates discriminate particles from random positions at
AUC 0.912 / 0.946, with the y-flipped control at chance (0.452 / 0.489) — so the gain orientation
is right as-is and the test is not one that returns a high value for any input.

The arm comparator was itself self-tested before use: identical input gives exact zeros and
bitwise identity, two different movies raise three blocking failures.

## Build provenance

- Source: fresh clone at `1d7e13f`, `src/` + `CMakeLists.txt` verified identical to the pin.
  None of the ten pre-existing `cpu64` binaries lives in a git repo, so their provenance is
  unverifiable and none was used.
- `cmake` 4.4.3 from the pre-existing `~/.mc-venv`; no package installed, no sudo.
- Configured `-DCMAKE_BUILD_TYPE=Release -DCUDA=OFF` against the distro library stack
  (libtiff 4.5.1, fftw 3.3.10, libpng 1.6.43, libjpeg 80). An initial attempt pointed at
  miniforge's libtiff and failed to link against system libjpeg; the all-system stack is used
  instead, so no mixed-ABI build is in play.
- `build-cpu/motioncorr` sha256 `20b12ef4dae275e331cf19c19ddbedd99f8626d8405a6dfc9f86903eda7600db`,
  `ldd` shows no CUDA library.

## Compute used

- `cpu64` (`small-refmac-machine`): load checked before each step (2.0–3.1 of 64), everything
  pinned `taskset -c 48-55`, build `-j 8`. One sequential pilot, `--j 1`. No benchmark.
- `4GPUs`: built both arms (`-j 8`, `taskset -c 96-103`) and staged data, then **did not run**.
  The shared `flock /tmp/motioncorr-bench.lock` was held by another agent's `/home/alex/matrix.sh`
  (1 d 15 h, 0.1 % CPU, sleep loop). My queued waiter was cancelled — my own process only.
  `matrix.sh` was left untouched, and so was the other user's GPU process on device 1. Bypassing
  the lock because the holder looked idle would defeat the coordination it exists for, so the
  run moved to the protocol-preferred route instead.
- `scarf`: the GPU route actually used. One multiplexed connection, no retry loop, no login-node
  build — clone, build and run all inside Slurm jobs on `gpu-devel`, which has a separate QOS
  from the `gpu` partition where other agents' `mc-i83e`, `mc-i74` and `mcfaults` jobs sit, so
  this work neither shares nor delays their allocations. CUDA 12.4 was found already installed at
  `/apps20/.../generic/software/CUDA/12.4.0`; nothing was installed.
- No sudo. No other user's home or permission-restricted mount read. No credential change, no
  new account, no paid service.

## Blocker requiring Alex's decision

The confirmatory set (350 movies, ~4492 particles, matching PR #65's statistical weight) needs
**270 GiB downloaded from EBI** and **~445 GiB working space**. That is two orders of magnitude
over this issue's ≤ 2 GiB cap, so it is not taken. `cpu64` has only 200 GiB free; SCARF
(`/home/vol05`, 2.4 TiB free) is the only host that fits, and the GPU arm needs a coordinated
exclusive SCARF Slurm window (no concurrent benchmark with the active #85 I/O work).

**Concrete next action if authorized:** stage the frozen 350-movie draw
(`tools/science_issue73/i73_select_movies.py --seed 73 --n 350`) to SCARF, run the CPU arm under a
bounded mask, then the CUDA arm in a dedicated Slurm allocation.

**If not authorized:** the deliverable stops at the frozen protocol plus the 2-movie feasibility
pilot, which reports image-level diagnostics on independent data and explicitly establishes no
signal equivalence.
