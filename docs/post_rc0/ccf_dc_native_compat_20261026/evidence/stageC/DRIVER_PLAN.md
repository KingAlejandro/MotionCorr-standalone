# Stage C driver: plan and test criteria (written before the code; nothing here has run)

Scope: draft the minimal driver, frozen pins and tests only. No Stage C row has been produced; no producer, SSH, GPU or CI action. A parent release file is required to run it for real, and I do not create one. Source and tools stay at `96e7e7be`; binaries are the attempt-2 `def`/`exp`/`iso` binaries (no rebuild). Stage A/B records are immutable; the `chain.out` manifest amendment stands.

## What the driver runs (exact, from the frozen ledger)

160 jobs from `ledger.csv` (K267 96, N 64; M 16 excluded and held), 96 comparison pairs (`pairs.csv` K 32 + N 64; the 16 M pairs excluded), 16 C-REPRO rows (`repro.csv`). Counts, ledger/pairs/repro/counts sha256, the 33 K267 and 26 N input files (checked against their manifests, whose sha256 are pinned: K267 `9697c203...`, N `6e7b19bd...`), retained references, source/archive, tools files, three binary hashes, interpreter path and versions, recorded compiler/CUDA versions, CPUs 80-87, GPU2 UUID, OMP K267 8 / N 2, thresholds and the C-REPRO tolerance 1e-5 are all in `STAGEC_PINS.json` (hashed); the driver refuses to start on any mismatch.

## Order (fixed before outcomes; honours the original plan: B4 first)

1. The 12 B4 rows (K267 `affine`/`pedestal`/`noisy`, CUDA, `exp`, arms none/global/local/both), each graded and checked for strictly positive `cuda_single` global and `cuda_batched` local counters before the driver advances.
2. CPU-backend rows (80), ledger order within: K267 (48, the B3 triples' CPU members), then N: production-weight arm none (8), C-REPRO for production; isotropic arm none (8), C-REPRO for isotropic; then production arm both (8) and isotropic arm both (8). A failed C-REPRO stops the affected weight set (its remaining CPU and CUDA jobs are recorded `NOT_RUN`) without relaxing the tolerance; the other weight set continues.
3. Remaining CUDA rows (68), ledger order, N rows of a stopped weight set skipped.
B3 identity (`def` unset = `exp` unset = `exp` none, pairwise against `def`, through the actual `identity_report`) is evaluated as soon as the three rows of a (ID, backend) exist, so the CPU triples after step 2 and the CUDA triples after step 3.

## Stop and continue rules

STOP the campaign (no later row runs; everything so far is kept): tool/pin/input/binary/interpreter identity mismatch, a guard stop (foreign GPU2 compute other than PID 3983855, GPU2 utilisation > 50 %, a core of 80-87 > 50 % busy, a busy lock or an unreadable resource), a producer that does not exit 0 with complete publication, any row whose grade is not SCORED, a B3 failure, a B4 or SEL row whose coverage differs from the declared one, an unexpected site or fallback, duplicate or extra case, ledger mismatch, scratch above 20 GiB. A scientific FAIL or UNIDENTIFIABLE field verdict is a result: recorded, run continues, never deletes evidence, blocks promotion if newly harmful.

## Per job

Fresh unique run directory (never overwritten, never retried). Child working directory holds only the case STAR and MRC (no truth file). Argv from `k267_argv`/`n_argv`, environment from `run_env`, both rebuilt from the ledger row and compared with the actual spawn; all inherited `MC_EXPERIMENT*`, `MC_DIAG*`, `MOTIONCORR*`, `OMP_*`, `CUDA_*`, `NVIDIA_*` variables are removed first; CPU rows get the GPU hidden, CUDA rows only GPU2 visible plus `--gpu 0`. Binary sha256 checked at spawn. stdout and stderr separate, actual exit status recorded even on failure, full recursive file inventory (path, size, sha256) before and after. Graded with the actual `grade_k267`/`grade_n` (no rewrite, tolerance, gauge, ROI or normalisation change); `def` rows are STAR-only (`NOT_REQUESTED`), `unset` rows grade as arm none. Receipt per job binds ledger id, argv, env, cwd, binary hash, pins hash, run path.

## Resource guard

The existing StageAB guard logic, extracted unchanged into `tools/stageC_guard.sh` (pinned), runs before every job against live `nvidia-smi`, `/proc/stat`, `ps`, `df`, `free`, in addition to non-blocking `flock` on the three lock files (`dcnative-gpu2-cpu80-87`, `cuda-boundary-cpu80-87`, then `gpu2-correctness`). The foreign PID 3983855 is allowed unchanged. Stage C directory new, at most 20 GiB. Correctness only, no timing.

## Outputs and manifest hygiene

Pair report (runtime and STAR separately, convergence, `local_enabled` and witness counters kept apart), C-REPRO report, coverage (exactly 160 jobs, 96 pairs, 16 repro rows; shortfall is INCOMPLETE, never PASS), final status. Events are appended by open-write-close; the driver's own stdout stays outside the hashed directory; the manifest is written last over closed files and verified by re-hashing (the Stage A/B `chain.out` pattern cannot recur). K267/N only: no statement about M or whole-movie parity.

## Entry and authority

`ccf_dc_stagec_driver.py run --pins ... --release ... --outdir ...` refuses without a release file that names the driver sha256, the pins sha256, ledger sha256, source commit, run id and outdir, with `authorized_by` set and `test_fixture` false, and refuses fake pins. `dryrun` accepts only pins marked `fake` and never a release. I write no release file.

## Test criteria (dry run: fake producer and fake pins in a temp directory, at most 2 threads, scratch about 100 MB, no real MotionCorr row)

Must pass: exactly 160 unique jobs and the 96/16 coverage on a clean fake run; the three phases in the stated order with B4 first; B4/SEL/N counter checks; B3 through the real `identity_report` (identical passes; one pixel, STAR or exit difference stops); pair evaluation and C-REPRO at the fixed 1e-5 (just inside passes, just outside stops the weight set, other set continues; no tolerance input exists); stop logic for each of: wrong ledger/pairs/repro hash, wrong arm, wrong binary hash, wrong input hash, non-finite value, missing tap, failed exit after a tap exists, wrong stage, zero eligible, fallback site, extra case, guard busy, grader/consumer exception, duplicate run path; scrubbed environment (injected `MC_EXPERIMENT_*`, `OMP_*`, `CUDA_*` never reach the child); child cwd without truth files; release-file refusals (missing, wrong hash, test fixture, fake pins); manifest closure (modifying a file after writing is detected; a live-appended file is refused); real-grader wiring checked with a spy that the driver calls `grade_k267`/`grade_n`/`identity_report` with the ledger-derived arguments. Not covered by the dry run: the graders on real products (`CcfDcRowsNative` does that) and any GPU behaviour.
