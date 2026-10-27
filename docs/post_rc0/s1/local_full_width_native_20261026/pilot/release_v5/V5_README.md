# Release v5 and minimal driver: package index (HELD pending one independent delta review)

Native movie execution has **not** been launched. This package prepares the pilot for it: a re-anchored release module, a minimal producer driver, a frozen
admission that binds a real CPU build, fake-child tests and the cpu64 build/check/dry-run receipts. Scope, pins and limits are below; criteria were frozen
first in `V5_PLAN.md` (sha256 `1ce58083ebc66660...`). v1-v4 files, sealed packets and durable copies are unchanged. Source `634e4b48` and CMake `5bcfa987` are unchanged.

## Frozen pins (ADMISSION_V5.json sha256 `dae759f7f12df05af24ca75f2bdbaa7eb9e5453186c86e9df27f81a3dcb53871`; COMMANDS_V5.json `2bd36face2fed6f6a92398eb0402a63e6c6ea3624832e45c823f289a061b8081`, byte-identical to COMMANDS_DRAFT_v3.json)
| item | value |
|---|---|
| source | `git archive` of `d1c498b87123b324c027c2d8957736b9954e6326` (tree `033794b433e928723dbe7e4359b9e02651478fb6`); archive sha256 `87349cb626bad97f304e4e6b6aefdcb6ca84c429a194391bccbbcfed9780e507`; src = 634e4b48, CMake = 5bcfa987; 391 src/tests/CMake files equal the reviewed worktree |
| binary | `/tmp/motioncorr-lfw-v5-20261026/build/motioncorr` sha256 `bb92e06116f434219ae3f94c4317ea9b0ea63ee9c5169fd03c28bc00de4d19bd` (2730720 bytes) |
| build | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, cmake version 4.4.3; Release `-O3 -DNDEBUG`, CUDA OFF, MC_EXPERIMENT_CCF_DC=ON, -j2, OMP 2 / BLAS 1; 18 shared libraries hashed in the build receipt |
| build receipt | sha256 `da0681be64a607e97d8dd0f418a06083371972e73707b2420ec9116182e261d1` |
| venue | cpu64 (small-refmac-machine), Ubuntu 24.04.3, AMD EPYC 7763; CPUs 32-47; owned namespace `/tmp/motioncorr-lfw-v5-20261026`; lane.py sha256 `e0143e89fa3b6771d7f3ff873f04a7453d26f1b8c7f7b1e8f4ab4d3202b6fd66` |
| fixtures | all 33 files at `/tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures` equal the pins (read-only check) |
| baselines | all 8x19 = 152 files under `/home/ubuntu/motioncorr-evidence/native-b2-upstream-factorial-20261026/task/evidence/runs` equal the pins; the /tmp task copy also matched |
| tools | v3 pin list (comparator `53449d2d...`, six consumer/generator files, lane.py, factorial_common.py, v2/v3 modules) at remote roots |
| not pinned in the admission (bound by the parent release index) | `pair_decision_v5.py` `0826d64a29f40299b1d69f6b6776c29a5541f342c8e1f54ec5fa69bc01c9efd3`, `driver_v5.py` `676eff39d62aebdafb8623bd4c4046ba5f1367cc2d71dc07b8f1ce82fc6a5267`, `tests/test_release_v5.py` `8de7cb9b7e4008ac06ba4c697e3f71388a500babca93754b7bf97a3b257fee09` |

Remote staging also created `/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6/` (six hash-verified consumer files; the v2 module hard-codes that path) and
`/tmp/motioncorr-lfw-v5-20261026/pilot` (a copy of this packet's pilot tree before the run7 test logs were added).

## What changed from v4 (diff: `V5_DELTA_FOR_REVIEW/pair_decision_v4_to_v5.diff`)
L4: binary/source archive/build receipt checked against files on disk and each other, binary and roots come only from the admission, resolved command rows frozen by hash;
L3: OFF manipulation coverage in `pre_ON_gate`; L2: `admit_pair` re-derives baseline and OFF raw identity; L1: unique `pair/<case>/run_<k>`, so per-case `admit_pair` then
`decide_pilot` in one directory works. Driver: see `driver_v5.py` docstring and `V5_PLAN.md` section 4 (real launch needs `PARENT_RELEASE.json`).

## Receipts (receipts_cpu64/, no timing claim)
- configure rc 0; build rc 0 (peak RSS 479 MB, 1:27 wall at -j2); ctest attempt 1 rc 127 (ctest not on PATH), attempt 2 4/8 pass and 4 aborted fail-closed (arm unset in a DC build), attempt 3
  4/4 pass with `MC_EXPERIMENT_CCF_DC_ARM=none`. Together: LocalFullWidthWeight, CcfDcHook, ExperimentalFlagsCli, LocalCcfCaptureCli (arm unset) and IsotropicWeight, GlobalHalfGain, CoupledPeak,
  PatchRetryState (arm none) all pass. The plan listed "arm unset" for all eight; this deviation is recorded.
- every step ran under `lane.py` (8 overlapping leases + bench lock held, taskset 32-47), with before/after occupancy files; foreign busy cores 0.00-0.05 over 2 s at every check.
- `dryrun-1.json`: `driver_v5 --decision-dir ... ` without `--execute` on cpu64: anchors, identity, tool pins at the remote roots, 33 fixtures, 152 baseline files, the real guard (leases
  verified held by a fresh flock probe, CPUs 32-47, memory, scratch 6.44 GB of 25 GiB) all passed; 16 rows planned; nothing created (no evidence or decision directory).

## Tests (fake child; logs in `logs/`)
`tests/test_release_v5.py`: 121 checks, final run7 121/0 (run3 had 3 failures from a driver ordering defect, fixed; see `logs/ATTEMPTS_v5.md`). `tests/mutation_controls_v5.py` run2: 33 guard-removal
mutants killed, 2 shadowed as declared (driver ledger-exists vs evidence-not-empty; PAIR_BINARY vs per-arm binary checks); run1 found a test-state leak and three wrong harness fragments (fixed, kept).
The mutation run predates only the driver `--receipt` option (main() only); run7 tests passed after it.

## Not established / UNRUN
No native movie, no producer launch, no scientific, neutrality, harm, N5/9/13/20 or GPU result. The fake child proves consumer/driver logic, not that the real binary obeys the frozen contract
(for example the 9 witness lines and the log first line are source-derived predictions). `PARENT_RELEASE.json` does not exist, so `--execute` is refused. One independent delta review of correctness,
scope and license is required before the first producer; the parent also freezes the final decision directory and release index. No merge, default change, adoption or full100.
