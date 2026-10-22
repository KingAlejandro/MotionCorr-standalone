# Residual CCF capture and replay, 2026-10-22

Observation-only package on `diag/residual-ccf-capture-20261022`, based at PR273
`805d9de27898b4a10e6212e65098d5995a40fdb1`. Numerical/native source is
`d751ff28594902eca75d665ff116e662653481aa`; 805 adds evidence. All changes here
are under this new directory. Production tracked files are unchanged.
`diagnostic.patch` is an additions-only overlay applied to a fresh archived build
tree, never the checkout. No numerical expression, estimator, DC policy,
iteration/convergence policy, default, gate, tolerance or dependency changed.
FILE-ONLY #258/#262–266/#268 remain file-only. GPL-2.0-or-later; no publication,
merge, push, GitHub comment or Notion write. Parent owns independent review.

**Result: 16/16 native processes exit 0; 8/8 strict neutral pairs PASS;
16/16 unchanged truth-checker field gates FAIL.** Native exit is not truth.
No new production bug or native fix is claimed. The captures establish numerical
sensitivity at the CCF boundary on these inputs, not a complete error budget.

## Admission, source and inputs

The live PR273 head matches 805d9de2. Live PR271 evidence head is
`12339b6bbaa8c05ba0cb7109e792412b6e5bcf07`; diagnostic tooling ref is
`95e9d9136c67fd108b9010acf7df72c345388ce4`, historical native source
`afba50a4cebf5238ec2d267ff3ec07d272b13395`. PR bodies/discussion and current
#262/#238 discussions were read; selected snapshots are in `live/`. Observation
concepts were reused; none of PR271's DC/double/override arms were imported.
No old capture is presented as fresh and no 600-run census was repeated.

`DESIGN.md` froze four cases × CPU/CUDA × capture-disabled/enabled = **16 maximum
MotionCorr processes** before launch. Exactly 16 ran, sequentially. The original
NumPy 2.5.3 files were found under the old d751 scratch, copied read-only into
new scratch and verified. No fixture regeneration or old evidence overwrite.
Original MANIFEST SHA256:
`9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc`.
Geometry 128×96×5, 0.885 Å/px, seed 238262, fixed ROI `[12:84,12:116]`.
The native seed remains 1. Integer/fractional use 1×1 patches; affine/noisy 3×3.
The source generator/checker and all saved fixture members are hash-bound in
the receipts, including wavevector, landmark, frame/group/reference identities.
That recipe is used only for identity and unchanged truth evaluation, never as
a known-template CCF oracle.

Source archive SHA256 `1df4099244aca2b09a59df39c732f94640dfcf1fae9c3ca18b390dd669b9d8dc`.
Overlay patch SHA256 `061c5c5be6b427cb6643605ac1473e21beeb9e45fea1bd022500eec651a787e4`.
CPU diagnostic binary SHA256 `778ca7d5fd4ff70bb7162598940ae6a60a12afa0f6cb129a13eca7d46dfb5df1`.
CUDA diagnostic binary SHA256 `09fef94869d1ca4ae9fbd1b17672a8621cc67fbb0cbf672c60602b647d1ef095`.
`source-binding.json`, `overlay-binding.json`, `reference-binding.json` and
`verification.json` retain the exact identities and source-file bindings.

## What was observed

Every global call is captured for the four cases. Selected local calls are
CPU/CUDA affine `(2,1)` and noisy `(1,3)`, including both CUDA attempts. Source
and logs verify labels are 1-based **(y,x)**, flattened `iy*patch_x+ix`; batch
chunk offsets are taken from the actual call site. Affine bounds are
X `[0,42)`, Y `[32,64)`, center `(20,47)`; noisy X `[84,126)`, Y `[0,32)`,
center `(104,15)`. Both CUDA first attempts use batched window spectra, followed
by full-spectrum retry calls. Each invocation gets its own call identity.

Fresh capture totals: **14 calls, 60 iterations, 300 frame records**. Captured
arrays include current cropped complex frame spectra, actual reference,
weights, actual C2R input, float CCF maps and raw candidates, plus accumulated
shifts before/after frame anchoring. C2R scratch is saved before inverse
transforms can destroy it, after the existing CUDA Hermitian projection.
Geometry/crop/search/scale/B and iteration/frame identities are explicit.
Final global trajectories and pre-write polynomial coefficients are retained
at 17 digits in both arms. Logs and STAR preserve accepted/excluded patches,
convergence, metadata and model presence.

**Neutrality PASS:** every paired MRC byte matches except its exact Relion
label timestamp; all STAR bytes match after only output-prefix normalization;
per-movie STAR, pre-write coefficients and trajectories are exact. Expanded
verification covers aggregate STAR too. All eight disabled controls also match
historical d751 per-movie STAR and MRC core/payload bytes. These are observed
byte comparisons, not a transferable result across toolchains.

## Independent numerical replay

Sign/axis/zero/known-shift controls, fractional quadratic/scale controls,
full-complex direct-DFT/Hermitian/unnormalized-inverse control and flat-tie
control **PASS**. Local NumPy 2.4.2 direct-DFT control max error is
1.06e-12; remote controls use NumPy 2.5.3. The source-faithful stored-map replay
matches **all 300 actual native candidates exactly**. All **60 actual native
updates** match, including CUDA's float candidate subtraction before RFLOAT
accumulation. CPU row-major/CUDA 256-lane strict tie rules, search bounds,
periodic fit neighbours, promoted scalar arithmetic, actual scales and CUDA
candidate narrowing are retained. No new peak acceptance threshold is applied.

The alternatives are:

- `inverse_double`: independent full-complex double inverse of the **identical
  saved C2R spectrum**. This isolates inverse/map/fit loss at that boundary.
- `rounded_inverse`: that double map cast to float before the same peak rule;
  separates a correctly rounded float map from the native float FFT result.
- `product_double`: double product using actual captured float reference,
  frames and weights.
- `reference_double`: double reaccumulation/product from the captured float
  frames, retaining weights and current native state.

These are conditional numerical oracles, **not native alternate trajectories,
estimator floors or physical forward-double references**. Captured float
frames already contain preprocessing/forward-FFT/prior-state errors. Every
conditional update starts from the measured native previous state. The final
source-faithful replay supersedes the first analysis only for update anchoring
and the added rounded-map observation; initial artifacts remain immutable.

For global integer motion, `inverse_double` changes integer winners in
10/25 CPU and 7/25 CUDA frame records; maximum raw-candidate vector differences
are **1.2211272 / 1.2211272 px**. For fractional motion, counts are 8/25 CPU and
0/10 CUDA, with maxima **1.1506314 / 0.1604878 px**. Even an unchanged integer
winner can have a different vertex. These are same-state candidate differences,
not final field errors or native improvements. Native stored maps have up to
four exact maxima; all 300 native winners are inside the search boundary.

Affine CUDA `(2,1)` has 2/25 changed integer winners and maximum **0.5561085 px**
candidate difference per attempt; noisy CUDA `(1,3)` has 6/25 and **1.1599114 px**.
Both attempts run five iterations and remain nonconverged/excluded. Their
captured input/reference/spectrum/map/candidate/state/weight sets match
**36/36 files byte-for-byte between attempts** in each case. Thus the retry
repeats this measurement, rather than supplying independent evidence of recovery.
CPU selected-patch maxima are 0.4518210 px affine and 0.9432239 px noisy.

The integer CUDA iteration-1/frame-1 witness also proves that reference/product
rounding can matter near a tie. Native map peak is ~40004.72 with search contrast
~1.98. In the saved-spectrum inverse, `(2,-5)` exceeds `(3,-5)` by
**6.90990e-9**; reaccumulation/product in long double reverses the gap to
**2.06475e-9**. Independent direct Fourier sums (63-bit long-double mantissa)
corroborate the reversal. The separable quadratic candidates differ by
**0.904413 px**. Most other captured inverse-versus-reference candidate
comparisons are below 6.2e-7 px, but this exception prevents claiming that
reference accumulation is universally negligible.

Rounding the ideal double map to float can itself choose different tied peaks.
The largest `rounded_inverse` candidate difference is 14.2759 px in the noisy
CUDA patch, with the unchanged search/fit convention. This is an offline
counterfactual, not an observed native boundary failure or a proposed #263 fix.
All maxima, competing local maxima, curvature, ties, boundaries, raw/anchored
shifts and truth-relative trajectories are retained in the indexed details.

## Accuracy interpretation and retained failures

The unchanged checker reports FAIL for all selected arms. Noisy retains
`OUTSIDE_FIXED_ROI` and null estimated-motion image metrics in all four arms.
All affine/noisy models remain present. Historical eight-case totals remain
2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; flat/repeated were not rerun or relabelled.
Pre-write state and serialized outputs are retained separately; no FILE-ONLY
#265/#268 serialization change was made.

Conditional inverse updates sometimes reduce and sometimes increase truth
error. For example, at the final native integer state, global vector RMS is
0.2978685 CPU / 0.2850250 CUDA px; the single conditional inverse update gives
0.3348182 / 0.2870642 px. Fractional values are native 0.5921542 / 0.3794253,
conditional 0.4847594 / 0.3444939 px. This does **not** compare completed native
solvers. Affine/noisy point-truth residuals are descriptive: a patch correlation
does not necessarily measure displacement at its center.

The evidence rules out treating the observed residual as exclusively a
reference/objective bias with numerically exact CCF evaluation. It does **not**
show that numerical loss accounts for all residual error, that any particular
precision/default/policy change recovers truth, or that a universal new defect
has been demonstrated. Forward-double physical reference, an all-double native
solver, scientific outcomes, full suites and controlled performance are
**UNRUN**. No DC-conditioned native or offline arm was added.

Retained setup/analysis defects:

- Local overlay generation first exited 1 on a duplicate source-anchor assertion;
  it wrote no overlay or native product. The corrected unique anchor passed.
- First detached analysis omitted its exit wrapper. Its process was reconciled
  absent with complete output and empty log; exit remains **UNOBSERVED**, not 0.
  A receipt-bearing recomputation then exited 0 and reproduced that JSON exactly.
- Initial direct-witness helper import failed, exit 1. Its source/traceback are
  retained; the self-contained replacement exited 0. No MotionCorr retry or
  build followed any analysis defect. Both native builds and the sole frozen
  native campaign have recorded exit 0.

## Resources and exact commands

Fresh scratch on `4-gpu-vm`:
`/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2`.
Prior d751 scratch and all inputs/evidence/caches/services were preserved.
Root remains c8844894 with only its pre-existing untracked
`pr117-fix-measure-20260929/`; see `root-preservation.json`.

Access: `ssh -J ccp4-gateway 4GPUs`. Detached build PID **3030366** acquired
`/tmp/motioncorr-build.lock` exclusively/nonblocking at 16:25:16 UTC and released
it at completion. CPU/GPU drivers and all children are restricted to CPUs10–13;
CMake compile parallelism2, native `--j 1`, numerical threads1, bytecode off.
Builds are Release, nvCOMP off, CUDA sm_80, GCC13.3, CMake3.28.3, CUDA12.8.61.
Exact configure/build argv, flags, link commands/libraries and exits are retained.
Only CPU and CUDA `motioncorr` targets were built. No new build is needed.

The driver commands are (ROOT is the scratch above):

```sh
taskset -c 10-13 /home/alex/.mc-venv/bin/python3 ROOT/build.py ROOT
taskset -c 10-13 /home/alex/.mc-venv/bin/python3 ROOT/run.py ROOT
taskset -c 10-13 /home/alex/.mc-venv/bin/python3 ROOT/final_analysis.py ROOT
```

Every native arm uses this exact argv shape, with CASE in the four frozen cases,
P=1 or3, and `--gpu 0` only on the CUDA binary:

```sh
ROOT/build-BACKEND/motioncorr --i CASE.star --o ROOT/runs/BACKEND-CASE-MODE/out \
  --use_own --j 1 --patch_x P --patch_y P --bin_factor 1 --seed 1 --skip_defect \
  --save_noDW --first_frame_sum 1 --last_frame_sum 5 --skip_logfile
```

Cwd is `ROOT/fixtures`. Existing max_iter=5 is unchanged. Every arm sets
`MC_CCF_STATE`; enabled arms additionally set `MC_CCF_CAPTURE` and the selected
local `MC_CCF_PATCH`. No `MC_DIAG_*` survives environment cleanup. Exact expanded
argv, allowed environment, PID/start/exit and inherited CPU affinity are in
`run-logs/`. No app process was launched outside these 16 arms.

Campaign PID **3033095** acquired canonical
`/tmp/motioncorr-gpu3-correctness.lock` nonblocking at 16:29:55 UTC, probed and
released `/tmp/motioncorr-bench.lock`, and admitted only GPU3 UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`. Fresh UUID/apps/idle/full-health and
corrected/uncorrected volatile ECC samples were taken before and after CUDA
work. Both ECC counts remained zero. Final health **PASS** at 16:30:10 UTC:
GPU3 idle, 1 MiB used, no compute app. GPU lock released at
2026-10-22T16:30:10.528436+00:00. No settling sample, reset, foreign kill, hardware waiver,
shared installation, full suite or performance/science campaign was used.
Intrinsic application duration fields remain raw logs, not timing claims.
The concurrent host-oracle task's lock-busy exit75 remains its own evidence;
this package never waited/retried a busy build lock or altered its CPU8–9 lane.

## Evidence inventory

`receipts.tar.gz` is **511 files / 225045 bytes**, SHA256
`7cda1e89b9c5a1f06f3c6fd87fd701d5b8e7e72d317972cd87952e4936ace5db`. `receipt-index.json` binds every member; local validation
checked all members plus recomputed the 60 compact trajectory metrics.
`file-index.json` inside the archive binds **1274 remote artifacts**,
including the raw arrays, all products, first/final analyses and failures.
Raw arrays and bulk products remain remote. Compact receipt verification does
not imply an independent local rehash of every remote raw array.

Start with `analysis-summary.json`, `verification.json`, `direct-witness.json`,
`DESIGN.md`, and the receipts' `witnesses.json`/`trajectories.json`. Full per-frame
peak detail is remote `analysis-final.json`, SHA256
`de65cbd9b98726ba93650a98600fd899e71c92430644242ffaec8325e4197fed`. The original scripts/first results remain hash-indexed;
local `replay_initial.py` corresponds to remote original `replay.py`, while local
`replay.py` corresponds to remote `replay-final.py`. No evidence revision is
silently substituted for an earlier measured identity.

Bounded local receipt verification (no native execution, numerical threads1):

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
 /Users/alex.konstantinov/.local/bin/python3 \
 docs/post_rc0/s1/residual_ccf_20261022/verify_local.py
```

This exits 0 and verifies all 511 archived receipt members, compact arithmetic,
local/remote script bindings and the pinned base/overlay hashes. Final local
oracle controls were rerun with the same one-thread environment, exit0 and
byte-identical control JSON. No extra MotionCorr process or build was launched.
