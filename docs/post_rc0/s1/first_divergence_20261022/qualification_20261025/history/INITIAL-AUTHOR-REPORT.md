# W4 attribution handback: remaining capture jobs, protocol gap, accuracy contract, offline decomposition

Research sub-agent report for the 6.1 Sol orchestrator, 2026-10-25. Read-only: no native process, build,
SSH, push, GitHub post or Notion write. Historical #273 totals stay **2 PASS / 10 FAIL / 4 UNIDENTIFIABLE**;
the five-frame failures and the N=20 isotropic-weight 11.833 px counterexample are retained unchanged.
Nothing here relabels a verdict or proposes adopting an estimator, default or gate.

## 1. Result

1. **Real full-precision runtime coefficients and global state already exist** for the affine (and noisy)
   case on both backends: `state/model.txt` and `state/global.txt` written at `%.17g` by the #275 overlay
   at `skip_fitting:` (after the fit and its guards, before reconstruction/STAR). They are in the committed
   #275 receipts. Full-precision *per-patch observation trajectories and float32 CCF maps* exist only for
   patch (2,1).
2. **All-patch observations exist at STAR print precision** (CPU 45 rows = 9 patches, CUDA 40 rows =
   8 patches; (2,1) is absent from CUDA because it did not converge on the batched path or the full retry).
   Refitting them offline with the runtime convention reproduces the runtime field to ≤ 4.4e-6 px, so the
   observation table that entered the fit is now known to print precision on both backends.
3. **The reviewed CPU protocol is ready and does fill the CPU per-patch gap**, but not by writing the fit
   input directly: each process captures the selected patch's double-precision `before/candidate/after`
   shifts per iteration, and the fit input is the exact function `obs[g] = after_final[g] + 0.5·after_final[1]`
   at `z = g + 0.5` (section 3). No source or protocol amendment is needed for CPU. The CUDA half has no
   reviewed protocol, and the CPU driver cannot be reused unchanged for it (section 2.2).
4. **New offline attribution for the affine local field (separate from the jobs, section 4):** even exact
   patch observations, fed through the inherited observation/fit time convention, fail the unchanged field
   gate for both backends' own global trajectories: 0.242 px (CPU) and 0.333 px (CUDA) RMS vs 0.226 px.
   With true global motion the same path is exact (0.000 px). The native field error is exactly (linear,
   residual 2e-14) this floor plus the propagated observation error (0.382 / 0.384 px RMS alone), and the
   observations show systematic shrinkage, mostly in y. Runtime vs STAR differs by ≤ 1.8e-4 px, so #265
   serialization does not affect this verdict.
5. Consequence for sequencing: the eight CPU captures answer *why* individual observations shrink
   (window/weight objective vs tie/parabola/anchor arithmetic). They are not needed to locate the earliest
   divergence of the affine field, which is now: global trajectory error → (inherited time convention +
   shrunken patch observations) → fit reproduces exactly what it was given → STAR adds ≤ 1.8e-4 px.
   The smallest next discriminating test is offline (section 6) and decides whether the captures are needed.

## 2. Exact remaining W4 jobs

### 2.1 Eight CPU captures: READY pending fresh admission (reviewed, unspent)

| Field | Value |
|---|---|
| Case / fixture | `affine` (128×96×5, model 1, 3×3 patches, group 1); MANIFEST `9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc`; `affine.mrcs` `1cf918d5…260a`; `affine.star` `0a08c285…6491` |
| Source | #273 `805d9de2` archive `1df4099244aca2b09a59df39c732f94640dfcf1fae9c3ca18b390dd669b9d8dc` + #275 overlay archive `655e7fe7…386c` (patch `061c5c5b…87e4`, Git-retained at #275 `6ae48678`) |
| Binary | retained `build-cpu/motioncorr` `778ca7d5fd4ff70bb7162598940ae6a60a12afa0f6cb129a13eca7d46dfb5df1` (Release, double FFTW, `RFLOAT` double) under `/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2` (read in place, never written) |
| Protocol | freeze `7d203929`, cleanup amendment `0a4ef2ce`, iteration 2 `b9bfcb5c`; `protocol.json` sha256 `c2e7712bb4c16bf4a4e80ce69694177e0961e0a8a608b5e8d62ae217693db15f` |
| Driver | `capture_cpu_v2.py` at `fb5b0b05` (unchanged at #278 head `83db13d2`), sha256 `884e7424fbb49d1c887301129a20f29ae89467839defcd919810bfa1f17bf1b2`; Codex prelaunch review NO MATERIAL FINDINGS (`REVIEW.md` `faf6c715…b707`) |
| Jobs (serial, no retry) | selectors (y,x) = (1,1) (1,2) (1,3) (2,2) (2,3) (3,1) (3,2) (3,3); (2,1) is the retained control |
| argv | `OLD/build-cpu/motioncorr --i affine.star --o NEW/campaign/patch-Y-X/out --use_own --j 1 --patch_x 3 --patch_y 3 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 5 --skip_logfile`, cwd `OLD/fixtures`, `MC_CCF_CAPTURE/STATE/PATCH`, `CUDA_VISIBLE_DEVICES=` , threads 1, `LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64` |
| Venue / lease | 4-gpu-vm, UID 1004, `taskset -c 13`, nonblocking `/tmp/motioncorr-w4-cpu13.lock`, fresh canonical `/mnt/clathrin/<new>` (must not exist; failed namespace `…-20261023-f73eb930` stays retained), cap 64 MiB, ≥ 1 GiB free, 120 s per process |
| Expected | 8 launches, each exit 0; `capture/` = `c1.json` (`cpu-global`) + `c2.json` (`cpu`, selector); byte neutrality vs `runs/cpu-affine-on`: `global.txt` `7ea5a840…c1e3`, `model.txt` `ca59f476…2523`, `affine.log` `793124b0…5dd4`, STAR (prefix-normalized), MRC (timestamp-regex labels only); `RESULT.json` PASS |
| Expected size | ≈ 3.75 MB per process from the #275 index (c1 3.21 MB, c2 0.18–0.36 MB, out 0.36 MB): ≈ 30 MB total, inside the 64 MiB cap (the proposal's 2 MB/process was an underestimate) |
| Launch | copy the committed `capture_cpu_v2.py` and `protocol.json` (hashes above; bundle with `COPYFILE_DISABLE=1` to avoid AppleDouble members) into the new root, then `taskset -c 13 python3 -B ROOT/capture_cpu_v2.py ROOT`; record driver exit and `RESULT.json` hash |

The #277 guard read-only grade on CPU13 is reported complete, so no CPU13 conflict remains. Venue: the
inputs and binary are venue-bound to 4GPUs; moving to cpu64 would need an explicit amendment (copy or
rebuild changes the binary identity), so keeping CPU13 on 4GPUs follows the plan's venue rule.

### 2.2 Eight CUDA captures: NOT READY (no reviewed protocol or driver)

Same eight selectors, same argv plus `--gpu 0`, binary `build-cuda/motioncorr`
`09fef94869d1ca4ae9fbd1b17672a8621cc67fbb0cbf672c60602b647d1ef095`; neutrality baseline
`runs/cuda-affine-on`: `global.txt` `16fecf0f…87a1`, `model.txt` `1872f9ba…69a5`, STAR `c9e5ab36…0b7f`,
log `06f62cf4…81fb`. All eight are accepted (converged) CUDA patches. Smallest amendment set before any run:

1. **Capture inventory:** a converged selected patch produces `c1.json` `cuda-global` + `c2.json`
   `cuda-batched`; a nonconverged one adds `c3.json` `cuda-full` (the retry). The CPU `captures()` check
   (`tag == 'cpu'`, exactly two calls) would reject CUDA.
2. **Log neutrality:** the CUDA log contains run-variable lines (`free device memory … MiB`,
   `Total GPU alignment time: … ms`), so the CPU rule "affine.log byte-identical" will fail by design. Compare
   only the `Patch (y, x)`, `Iteration n: RMSD`, `converged=` and `Polynomial fit RMSD` lines, or mask the
   variable fields; state that change explicitly.
3. **Device identity:** byte neutrality is established only for the same binary on the #275 device
   (`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`). Pin that UUID, or declare a mismatch on another A100 a stop
   condition (a determinism finding, not a capture).
4. Per-GPU correctness lock and health (UUID, ECC, no compute apps) before/after; `CUDA_VISIBLE_DEVICES` by UUID.
5. Independent prelaunch review of that CUDA protocol/driver, then GPU admission.

Recommendation on sequencing: hold the CUDA half until the offline test in section 6 shows that estimator
arithmetic (not the window/weight objective) dominates the CUDA observation error.

## 3. Protocol vs gap

| Needed for attribution | Already retained (#275 receipts, `7cda1e89…e5db`) | Added by the 8 CPU captures | Still not recorded anywhere |
|---|---|---|---|
| Global state, full precision | yes, both backends | redundant copy per run (determinism check) | — |
| Runtime (pre-write) coefficients, full precision | yes, both backends | redundant copy | — |
| Accepted/rejected membership | yes: STAR rows + log (CPU 9/9, CUDA 8/9; CUDA log has explicit `converged=`) | per-patch RMSD recomputable from candidates | no machine-readable record (derivable) |
| All-patch fit input | print precision (≤ 5e-6 px; negatives 5 decimals; STAR frame column truncates `g+1.5` to `g+1`) | exact for CPU via final `after` vectors | the explicit table and its `z = g+0.5` (derivable; derivation validated offline at print precision) |
| Per-patch per-iteration float32 maps, candidates, before/after | (2,1) only, both backends (raw arrays only in the remote #275 scratch) | 8 other CPU patches | 8 other CUDA patches (needs 2.2) |
| Applied runtime field | derivable from `global.txt` + `model.txt` | — | no native model-1 applied-image witness (application at integer z is source-read, `motioncorr_runner.cpp:4406`) |

Verdict: the CPU protocol genuinely fills the CPU per-patch precision gap without amendment. The fit input
is not written directly; a downstream admission step should check (a) 9/9 final `after` vectors present,
(b) derived `obs` equal the STAR rows within print precision, (c) refit equals `model.txt` to ~1e-10. That is
analysis admission, not a protocol change. The stop rule ("all-patch full-precision observations absent")
is not triggered for CPU.

## 4. Offline matched-input decomposition (affine, retained data only)

Same-state comparisons only: each backend's observations are compared with known residuals computed for
that backend's own global trajectory; no CPU-vs-CUDA causal comparison of different upstream maps.

Production conventions read from source at `805d9de2` (inherited from the RELION 5.1 extraction `4499be23`):
default path (`--interpolate_shifts` off, `--group_frames 1`) stores `local[g] − interp[0]` with
`interp[0] = 1.5·local[0] − 0.5·local[1] = −0.5·local[1]`, at `z = group_start + group_size/2.0 = g + 0.5`
(`:3829–3832`, `:4250–4280`); reconstruction and the checker evaluate the model at integer `z = g`
(`:4406`, `tools/motion_field.py`). The two time coordinates agree only for residual motion linear in time.

| Quantity (field over the fixed ROI, px RMS unless stated) | CPU | CUDA |
|---|---|---|
| Retained checker on STAR (reproduced exactly) | 0.454743 FAIL | 0.323146 FAIL |
| Runtime field (`global.txt` + `model.txt`) | 0.454731 FAIL | 0.323140 FAIL |
| Runtime − STAR field, max / RMS | 1.76e-4 / 5.1e-5 | 1.63e-4 / 3.8e-5 |
| Refit of STAR observations at `z = g+0.5`: field − runtime, max | 4.4e-6 | 4.1e-6 |
| Same refit at naive integer `z`: field − runtime, max | 0.383 | 0.492 |
| Global − centre truth, frames 1–4 (px, x/y) | (−0.19,−0.22) (0.27,−0.33) (0.56,−0.79) (0.36,−0.37) | (−0.38,0.57) (−0.14,0.24) (0.04,−0.13) (−0.20,0.33) |
| **Known patch observations, production convention, own global** | **0.242 FAIL** (per frame 0, .113, .327, .237, .342) | **0.333 FAIL** (0, .165, .496, .529, .023) |
| Same, all 9 patches / window-centroid coordinates | 0.242 / 0.242 | 0.333 / 0.332 |
| Same, true global trajectory (negative control) | 0.000 | 0.000 |
| Diagnostic counterfactual: known observations at integer `z` | 0.097 PASS | 0.017 PASS |
| Field from observation error alone | 0.382 (max 0.79) | 0.384 (max 0.91) |
| Native local vs known local: slope x / y (corr) | 0.81 / 0.47 (0.90 / 0.68) | 0.98 / 0.32 (0.85 / 0.77) |
| Local error norm by patch, worst frame | 0.23–0.89 px (frame 3 everywhere) | 0.19–0.93 px |

The floor is spatially uniform (local component exactly 0): it is the time-only misfit of the global-stage
error. An independent five-line time-only calculation reproduces it to 1e-6. The integer-time row is a
diagnostic counterfactual on an inherited, parity-relevant behaviour, not a proposed change; its residual
is the cubic's capacity limit (3 temporal parameters for 4 nonzero frames).

## 5. Case-level account (16 arms; statuses unchanged)

| Case (#273 CPU / CUDA field px) | Known | Unresolved → next |
|---|---|---|
| zero PASS/PASS | control | none |
| integer FAIL 0.298/0.285 | global iteration-1 subpixel estimate; weight shape × separable parabola × N=5 nonconvergence; fixed-template native arms exact | quantization share not bounded natively → contract decision, then E1 |
| fractional FAIL 0.592/0.379 | same co-causes; bias persists with an ideal template; CUDA fixed-template 0.495 NOT MET retained | CUDA tie flip inferred (no map) → optional map capture |
| affine FAIL 0.455/0.323 | **new:** global error × inherited time convention (floor 0.242/0.333) + shrunken observations (0.382/0.384); fit reproduces runtime from its inputs; STAR ≤ 1.8e-4 px; (2,1) tie/window/anchor split as in #278 | why observations shrink (objective window/weight vs estimator arithmetic) → offline test §6, then CPU captures only if needed; global-stage mechanism for affine still descriptive; no native model-1 application witness |
| pedestal FAIL 2.395/2.395 | inferred float32 map resolution under the pedestal; zero model | no native map; #264/#265 not excluded by proof → W2 DC arms |
| noisy FAIL, OUTSIDE_FIXED_ROI 2.647/2.978 | global appears noise-limited | not localized; the same offline decomposition can run on the retained noisy `model.txt`/STAR (not run here) → plan C seeds after contract |
| flat UNIDENTIFIABLE, VALID | intrinsic (constant map) | no quality state emitted → M4 |
| repeated UNIDENTIFIABLE, OUTSIDE_FIXED_ROI | periodic aliases among 475–1710 tied maxima | tie-order alias choice → M4 |

Counter-evidence retained: isotropic weight passes both five-frame replays but gives 11.833 px on the N=20
fractional probe; longer iteration converges at N=9/13/20 without meeting 1e-9.

## 6. Smallest next discriminating test (offline, no native)

**All-patch objective maximum.** Generalise the reviewed (2,1) oracle's `R_fm` (continuous maximum of the
production-weighted CCF between an independently rendered window and the target window) to all nine
patches for each backend's own `global.txt`, then split each native observation error into
`R_fm − known` (objective/window/weight) and `native − R_fm` (estimator arithmetic). An oracle of the
inherited objective, not a new estimator. Freeze predictions before computing:

- **Objective dominates** if `native − R_fm` ≤ 0.15 px RMS and `R_fm` reproduces the y shrinkage
  (slope ≤ 0.6): captures are not needed to attribute the dominant term; it becomes a contract/E1 question
  (window treatment, weight #279).
- **Arithmetic dominates** if `R_fm` slope ≥ 0.9 and `native − R_fm` ≥ 0.3 px RMS: run the eight CPU
  captures, then decide on the CUDA protocol, to split tie/parabola/anchor per patch on float32 maps.
- Otherwise mixed: run CPU captures only.

Limit: without native inputs, the render's fidelity for patches other than (2,1) is unverified (G-E was
2.1e-5 for (2,1)); edge patches see the global Fourier-shift wrap differently. The CPU captures would close
that check. Estimated cost: < 1 CPU-minute on the Mac.

## 7. Accuracy-contract decision (question for Alex; prospective, gates unchanged)

The question should be decided before more estimator work or new outcomes are inspected.

**B1 Supported domain for W4/E1 acceptance**
- (a) Current diagnostic family as is: 128×96, N=5, 3×3 patches (42×32 px windows), group 1, B=150,
  noise-free multiband+landmark signal. Every gate-role case must meet the unchanged field criterion.
- (b) Geometry fixed a priori from #186 corpus metadata (frame size, patch window in px, frame count,
  grouping), chosen from metadata before any new outcome; same signal families and criterion. The current
  small cases stay as reported out-of-domain characterization.
- (c) (b) as acceptance plus a mandatory non-regression set: the current family, N = 5/9/13/20 probes and
  the 11.833 px counterexample, each not worse than its retained error by more than a margin fixed now.
- Risk to state with the question: (b)/(c) chosen *because* small windows fail would be post-hoc; the
  justification must be real-acquisition geometry, and the retained failures stay visible.

**B2 Targets for identifiable in-model cases**
- Field: unchanged 0.20 Å RMS / 0.40 Å p95 / 0.80 Å max over the fixed ROI (0.226/0.452/0.904 px at
  0.885 Å/px), measured separately on the runtime model and on the STAR round trip.
- Signal retention: (i) report-only (published-sum vs true-motion bilinear oracle) until #60/#61
  calibration, or (ii) a ratio to the oracle fixed now.
- Noisy cases: number of seeds and required pass fraction fixed now.

**B3 Ambiguous or invalid inputs**: flat and repeated → UNIDENTIFIABLE with the M4 report-only quality
state (no field target); OUTSIDE_FIXED_ROI → invalid sampling (image metrics null, field metrics kept).

**B4 Inherited behaviours open to branch experiments (parity-breaking; adoption needs sign-off)**:
#279 weight normalization; #280 peak/iteration/stopping; the fit time convention (new, section 4; draft
file-only text in `DRAFT_HELD_ISSUE_time_convention.md`); patch window treatment (hard crop).

## 8. Blockers, authority and ancestry

- No W4 native authority granted; both capture halves need parent admission. CPU13 is free per parent.
- Pinned remote inputs must still hash-match at launch (old scratch retention is not re-verified here).
- CUDA: protocol/driver/review missing (section 2.2); GPU admission separate.
- No ancestry check exists in driver v2 beyond host/UID/affinity, fresh namespace, pins, lock and
  occupancy; the parent must launch it directly (no spoofed lineage needed or implied). Exact `fb5b0b05`
  was local/unpublished at review; #278 head `83db13d2` is published and contains it unchanged.
- The raw #275 arrays (needed for any same-input tie/parabola/anchor replay beyond what the (2,1) packet
  already froze) exist only in the remote scratch; a read-only collection would need parent coordination.
- Accuracy contract (section 7) blocks #279/#280 and any E1 work; M6 + C2 precede held-out outcomes.
- The time-convention finding is RELION-inherited: file-only HELD under current policy; no fix PR.

## 9. Commands, exits, artifacts, limitations

- Read: AGENTS.md, `docs/gate_contract.md`, POST_FREEZE_TEST_PLAN §0/§9, Notion page 644bae9e (fetched with
  `~/.local/bin/ntn pages get`, exit 0, copy `notion_plan_644bae9e.md` `fece50aa…c2f9`), #238 comment
  6348535145, PR #278 body; worktrees t3-6c3dca0d (`83db13d2`, clean), t3-2bde2d1f (`22675db7`, clean),
  t3-7d38e82d (#275 `6ae48678`), t3-01f535cb (#273 `805d9de2`). No file in those worktrees was modified.
- `tar -xzf receipts.tar.gz` (#275, sha256 `7cda1e89…e5db`) → `r275/`; every input used is checked against
  the committed `file-index.json` (`31255dab…65c3`) and the protocol pins inside the script.
- Exact-revision sources via `git show 805d9de2:<path>` → `src805/` (`BLOBS.txt` has blob and sha256).
- `python3 -I -B scripts/w4_allpatch_decomposition.py r275 src805 out/allpatch-attempt01.json` exit 0
  (NumPy 2.4.2, Python 3.13.7, one numeric thread); regenerated `affine_field.npy`/`affine_target.npy`
  match the pinned hashes in memory.
- `python3 -I -B scripts/w4_shrinkage.py r275 src805 out/shrinkage-attempt01.json` exit 0.
- Inline time-only floor check (section 4) reproduced the floor; command in the parent transcript.
- `SHA256SUMS` binds every report artifact.
- Limits: one affine realisation, noise-free, N=5, 42×32 windows; STAR precision (≤ 5e-6 px) bounds the
  observation table; application at integer z is from source and the checker, not a native witness;
  `R_fm` for other patches not computed; noisy/pedestal decompositions not run; numpy `lstsq` is not the
  #276 native fit path (agreement 4e-6 px is consistent with it, not a rerun of it).
