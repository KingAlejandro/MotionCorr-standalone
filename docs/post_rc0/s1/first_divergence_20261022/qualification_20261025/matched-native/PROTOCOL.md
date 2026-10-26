# W4 matched-native-input diagnostic, protocol w4-matched-native/v1

Frozen 2026-10-25, before any output exists. Prepared on the Mac without numerics (hashing, parsing,
`compile()`, tar only). Offline CPU pass over the nine retained CPU patch captures; no native, GPU, SSH,
branch or publication work. Labels below are diagnostic routing, not gates. Unchanged: #273 totals, field
limits 0.20/0.40/0.80 Å, the five-frame failures and the N=20 11.833 px counterexample (both mandatory
before any proposed weight repair), C2/M6/held-out/noisy cohorts held. Does not touch Luna's
45-row after→obs/lstsq closure (no STAR, observation table or fit is read or computed here).

## Question

Phase D labelled CPU `native − R_pipe_loo` 0.228 px RMS, but R_pipe used reconstructed windows. With the
native stored inputs for all nine patches, how does that residual split into float32/tie, integer
winner + parabola, stopping, and input-window fidelity?

## Inputs (all hash-pinned; `manifest/MANIFEST.json` sha256 `b1f044ef…c381`, pinned in the script)

| Item | Source and record |
|---|---|
| (2,1) captures, 2 iterations | `parent/w4-control21-original/…/capture`; hashes from `w4-control21-collection.json` `inputs` (original #275 index) |
| (1,1), 1 iteration | `parent/w4-cpu-capture-collected/campaign/patch-1-1/capture`; hashes from `w4-cpu-capture-RESULT.json` (v2 campaign FAIL is log-only and stays; separate v3 regrade PASS_VERSION3_REUSE_ONLY) |
| (1,2) (1,3) (2,2) (2,3) (3,1) (3,2) (3,3) | `parent/w4-cpu-capture-v3-collected/campaign/patch-Y-X/capture`; hashes from v3 `RESULT.json` launches |
| `fixtures/affine.mrcs` `1cf918d5…260a`, CPU `state/global.txt` `7ea5a840…c1e3` | pinned fixture; #275 receipts |
| `ref/attempt02.json` `0bcf6879…bb72` | reviewed (2,1) oracle output (83db13d2) |
| `ref/w4_objective_oracle.json` `67fa892c…888c` | Phase D v1.1 output (R_pipe_loo, known) |

213 capture files (`c2.json` + `c2-*`; per iteration: input, reference, 5 spectra, 5 float32 maps, raw
candidate, before, after) all matched the parent's records when staged. Iterations: 2 for (1,3) (2,1)
(2,3) (3,1); 1 for the other five. All nine converged natively.

## Computation (`scripts/w4_matched_native.py` `2aab5d88…ef01`; reviewed helpers copied verbatim)

Per patch and per captured iteration k (stored arrays, double recomputation):
1. Same-sample estimator split per frame, exactly the reviewed steps generalised: `n` = native raw candidate;
   `b` = native rule (CPU row-major winner + separable 3-point parabola) on the double map of the stored
   input's leave-one-out objective; `c` = local Newton stationary point from that winner. Anchored terms
   `n − b` (float32 map/tie) and `b − c` (integer + parabola). Also reported: winner equality,
   exact float ties, stored-vs-double map ULPs.
2. End-to-end chain from the stored iteration-1 frames (the native's own window spectra), alignPatch
   iteration in double: `R_stop_par` (native peak rule, native stop: RMSD < 0.5 px, ≤ 5), `R_stop_cont`
   (continuous peaks, native stop), `R_inf` (continuous peaks, fixed point, increment RMSD < 1e-9, ≤ 60).
   Telescoping over frames 1–4, with `native_final` = captured final `after`:
   `native_final − R_pipe_loo = (native_final − R_stop_par)` float32/ties `+ (R_stop_par − R_stop_cont)` integer/parabola
   `+ (R_stop_cont − R_inf)` stopping `+ (R_inf − R_pipe_loo)` input-window fidelity.
   `R_inf − known` (Phase D known) is reported as the objective-on-native-inputs residual.
3. Input-window witness (report only): stored iteration-1 input against the Phase D pipeline window
   (pinned frames, global Fourier shift by CPU g, crop) per frame, `rel_ac` and DC. It is not an acceptance
   test; the existing G-E bound 1e-3 is only cited for comparison.

## Controls (existing bounds only; any FAIL marks results "not credited")

| ID | Check | Bound (source) |
|---|---|---|
| C-PIN | every manifest file sha256 + size | exact |
| G-W | stored patch weight vs formula, 9 patches | 1e-6 (reviewed G-W) |
| G-N / N-N | native rule on each stored float32 map reproduces the stored candidate, all patches/iterations/frames; axis-swapped replay must exceed it in every patch | 1e-6 px (reviewed G-N) |
| G-M | continuous map vs irfft2 at lattice points, every objective | 1e-9 rel (reviewed) |
| C-NEWTON | every local refinement converged | — |
| C-REF, C-SPEC | stored Fref vs Σ stored inputs; stored spectrum vs (Fref − F_f)·conj(F_f)·w | rel_ac 1e-3 (reviewed G-E) |
| C-CHAIN / N-CHAIN | iteration-k input = iteration-(k−1) input shifted by the anchored candidate (frame 0 unchanged); sign-flipped shift must exceed in every 2-iteration patch | rel_ac 1e-3 |
| C-STATE | `after = before + (cand − cand₀)` and `before_k = after_{k−1}`, bitwise (double, `cur_xshifts` is RFLOAT, captured before "Set origin", `motioncorr_runner.cpp:4674,4824`) | exact |
| C-STOP | native stop replayed from candidates: last RMSD < 0.5, earlier ≥ 0.5, ≤ 5 iterations | exact rule |
| C-IDENT | telescoping identity per patch | 1e-8 (Phase D reg21) |
| C-REG21 | (2,1) iteration 1: `n − b`, `b − c` equal attempt02 decomposition terms; pipeline `rel_ac` equals attempt02 `pipeline_from_stored_mrcs` | 1e-8 |

## Frozen predictions and routing (before execution)

A chain term is **material** if its RMS over 9 patches × frames 1–4 is ≥ 0.15 px (REPORT §6 lower
threshold, reused). Route = the single material term, `MIXED:<terms>` if several, `DISTRIBUTED_BELOW_0.15`
if none, `UNDETERMINED_NO_FIXED_POINT` if any `R_inf` did not converge.
- float32_ties → next small test is float32-vs-double winner/tie analysis on these stored maps (no native).
- integer_parabola → candidate #280 peak-estimator branch experiment.
- stopping → candidate #280 iteration/stopping branch experiment.
- input_window → Phase D's reconstructed-window attribution is relabelled. Next: per-patch stage-E/edge-wrap analysis on stored inputs; no estimator change.
- none → the residual sits at objective level (`R_inf − known`); candidate #279 weight/window branch experiment.
Any branch experiment must carry the N=5 failures and the N=20 counterexample as mandatory regression controls.
Expectation, not a criterion: (2,1) already showed `n − b` of about 0.42–0.49 px in y at iteration 1
(attempt02), so float32_ties is expected to be material at least for (2,1). No aggregate route is predicted.

## Interpretation limits (binding)

- "Continuous"/`c`/`R_inf` are stationary points from local Newton refinement started at the best
  integer sample, not certified global maxima.
- Each chain term is path-dependent: alternative arms can take different iteration counts and winners. The
  terms are an ordered telescoping, not independent causes, and none is a sole cause.
- `R_pipe_loo − known` is not pure objective error, and `R_inf − known` is not either: both depend on the
  B=150 weight, the hard window and the leave-one-out objective as inherited.
- CPU only; one noise-free affine realisation, N=5; no CUDA (no reviewed CUDA capture protocol).

## Execution (parent, cpu64, once, after fresh admission; no retry)

`run_matched_once.py` (`33382cc1…17d0`; copied from runner r3: CPU 62, both locks, busy < 0.5, RLIMIT_AS 2 GiB,
RLIMIT_FSIZE 16 MiB, outputs < 64 MiB, 120 s job, BLAS threads 1, fresh namespace).
Input `package/matched-inputs.tar` sha256 `300a406ca0534acbff649fa3f4d7069b70335962041a222c8da024260a7894c2`
(219 files). Expected cost a few CPU-seconds; unmeasured.

```sh
M=/tmp/motioncorr-20261025-w4-matched-native
ssh cpu64 'cat > /tmp/run_matched_once-33382cc1.py && sha256sum /tmp/run_matched_once-33382cc1.py' < $M/scripts/run_matched_once.py
ssh cpu64 "taskset -c 62 /usr/bin/python3 -I -B /tmp/run_matched_once-33382cc1.py /tmp/motioncorr-w4-matched-$(uuidgen | tr A-Z a-z) 300a406ca0534acbff649fa3f4d7069b70335962041a222c8da024260a7894c2" < $M/package/matched-inputs.tar
```
