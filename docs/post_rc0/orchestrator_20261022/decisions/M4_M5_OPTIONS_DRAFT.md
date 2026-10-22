# M4/M5 quality-state options — unapproved working brief

This prepares the decisions required by the revised Notion plan. It adopts no
policy, changes no source or output, and contains no newly executed native test.
This brief covers both global and local nonconvergence; their current handling
and consequences differ and must not be collapsed into one success flag.

## Observed boundary and separate meanings

Source inspected: `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`.
`src/motioncorr_runner.cpp:3367,3371` discards the global alignment return value;
`:3377` onward records and applies the accumulated trajectory. The CPU function
at `:4664–4866` returns whether incremental RMSD fell below the unchanged 0.5 px
threshold before the unchanged iteration limit. The GPU wrapper at `:4657`
returns the CUDA outcome. The ordinary movie-failure path at `:1051–1094` retains
successful movies, fails the job and withholds joint outputs. Dataset tooling
then requires successful worker and aggregate statuses before `dataset_ready`.
These are source observations, not native qualification of a new policy.

Existing local handling is part of M4. In CUDA builds a completed device patch
attempt that did not converge is retried once from the same input; shift vectors
are reset before the second attempt (`:3529–3545,3656–3700`). This existing
recovery path is distinct from selecting a new quality-policy retry. After the
last attempt an unconverged patch is skipped (`:3812`); too few retained local
observations cause global-only fallback with a stderr message (`:3856`). CPU-only
builds take the CPU alignment path once. CUDA logs `converged=`, while CPU logs
RMSD without that explicit verdict. A global-only sidecar would leave local
drop/fallback behavior unreported and would not satisfy the phase requirement.

Convergence can differ by backend on the same input. The retained #273 packet
at `805d9de2`, `docs/post_rc0/parallel_20261022/numerics/README.md:186–201`, records
CPU iteration limits but CUDA convergence for integer and fractional cases, and
different converged-patch counts for affine/noisy cases. These remain accuracy
failures under their original gates. A policy refusing nonconvergence could
therefore refuse CPU output while publishing CUDA output for the same movie;
convergence would still not certify accuracy. The ignored global result and
local skip/fallback also concern inherited RELION behavior (reference `ad0b230`,
issue #268). Refusal or a new numerical retry changes that compatibility and
requires the project's explicit parity sign-off as well as M4 disposition.

Convergence, observability and evaluation validity must remain separate:

| Proposed field | States | Meaning and provenance |
| --- | --- | --- |
| `global_alignment` | `converged`, `iteration_limit`, `operator_error`, `not_run`, `unknown_legacy` | Actual solver result; retain iteration count and final incremental RMSD. |
| `local_alignment` | Per-patch attempt/convergence states; attempted, retried, converged and dropped counts | Record existing retry outcomes and remaining observations separately; a dropped patch is not a successful motion estimate. |
| `local_model` | `retained`, `global_only`, `not_requested`, `unknown_legacy`, with reason | Distinguish insufficient converged observations, guard rejection and other model/fallback decisions from global convergence. |
| `motion_identifiability` | `identifiable`, `no_signal`, `ambiguous`, `not_assessed` | Requires a declared criterion/evidence. Convergence alone cannot establish it. |
| `peak_validity` | `bracketed`, `boundary_maximum`, `flat_or_degenerate`, `nonfinite`, `not_assessed` | Actual stage observations; M5 determines consequences. |
| `sampling` | `valid`, `outside_fixed_roi`, `not_evaluated` | Evaluator property. It is not an intrinsic observability or solver state. |
| `publication` | `published`, `refused`, `failed`, `not_attempted` | Actual product outcome; distinguish numerical quality from I/O success. |

Field names and serialization are proposals, not an approved public schema.
Do not invent new RELION labels without deciding compatibility. A versioned
per-movie quality sidecar and aggregate summary are one possible interface;
STAR integration is another. If introduced, status must use the movie's copied
metadata/output ownership, remain atomic, and survive batch/aggregate reporting.
Neither the existence of an image nor exit 0 may be interpreted as convergence.
Historical records without status must be `unknown_legacy`, never inferred PASS.
The resume treatment of those records requires an explicit compatibility choice.
Attempt accounting is needed to derive `not_run`: the current CUDA function can
return true for zero frames, so the existing bool alone cannot supply that state.

The retained #273 checker reports four UNIDENTIFIABLE arms: flat CPU/CUDA have
VALID sampling; repeated-pattern CPU/CUDA leave the ROI. Noisy CPU/CUDA also
leave the ROI but are FAIL. All field metrics and original verdicts remain.
These are checker characterization states, not implemented production abstentions.

## M4 — nonconvergence

| Option | Products and exit behavior to decide | Evidence needed | Present readiness |
| --- | --- | --- | --- |
| Report only | Preserve correction and process success behavior, but publish global and local attempt/drop/fallback states per movie and in aggregates. | Capture CPU/resident/streaming outcomes; prove healthy MRC/trajectory identity and accurate mixed-batch status; define old-resume handling. | Smallest prospective prototype; native behavior UNRUN. Reporting makes the states visible without improving recovery. |
| Refuse | Define which global or local failure/fallback makes a movie fail before corrected-image/STAR completion publication; retain healthy movies and fail the dataset. | Define coverage/minimum observations, earlier auxiliary products, writer draining, aggregate exclusion and resume. Exercise identical movies with backend-divergent convergence. | Can intentionally produce different publication membership by backend; inherited RELION parity needs sign-off. No rule is selected here. |
| Retry | Retry only under a separately specified recovery condition and hard resource/attempt bound; expose both attempts and final disposition. | A prospectively justified recovery method and truth/reconstruction evidence, not another identical-state attempt. Define restoration, source/input identity and final report/refusal behavior. | Not ready to adopt. W4 must establish which altered input/objective could recover information. No iteration/search increase or coarse tracker is selected here. |
| Document | Preserve current code and document the limitation. | Accurate user-facing limitations and compatibility record. | Available as a disposition, but alone does **not** satisfy the phase requirement that nonconvergence is no longer silent in machine-readable outcomes. |

No complete four-policy implementation is proposed. Start with one minimal
observation prototype only if needed to resolve M4, then test the selected policy
after maintainer disposition. Reporting and refusal are not scientific accuracy
certificates. A retry must not conceal the original iteration-limit event.
M4 must explicitly state whether its selected consequences apply to global
alignment, local patch failures, model fallback, or a declared combination. Both
global and local states must be observable even if their consequences differ.
The existing same-input local retry is preserved unless a separately reviewed
change is selected; the Retry option concerns a justified additional/changed
strategy, not a claim that production currently never retries.

Prospective controls for whichever minimal prototype is authorized:

1. Healthy textured zero/known-motion input: correct solver state, unchanged
   complete products where preservation is intended, no false quality failure.
2. A declared iteration-limit control and retained e10216-01: true nonconvergence
   remains visible even when CPU/CUDA products agree. Record actual source and
   full call result; a forced one-iteration fixture is not evidence that the
   default five-iteration case was reproduced.
3. Flat/no-signal input: possible zero incremental RMSD cannot be labelled
   identifiable solely from `converged`; preserve declared negative-control truth.
4. Boundary maximum: record peak validity independently of convergence, leaving
   its consequence to M5.
5. Mixed healthy/nonconverged batch, single-movie job and dataset aggregate:
   quality state, exit, worker status, membership, products and resume behavior
   must match the chosen contract. Include output-write failure so successful
   numerical work cannot mask failed publication.
6. Retained backend-divergent convergence and local attempt controls: distinguish
   first attempt, existing retry, final dropped patch, too-few-observations
   fallback and retained model. Verify both numerical status and intended
   publication membership on CPU/resident/streaming routes; do not infer a CPU
   verdict by parsing CUDA-only log fields.

Every new native control above is UNRUN. Do not convert this checklist into a
PASS or relax a numerical threshold to obtain the preferred state.

## M5 — peak-edge behavior

Issue #263 retains a selected integer peak on the search edge whose outside
neighbor is higher; the existing parabola can extrapolate past the search range.
The current CPU/GPU checks do not declare whether the three samples bracket a
maximum. The #260 same-sample arithmetic repair and its passing native controls
remain valid independently of which edge policy is chosen.

| Option | Consequence | Primary prospective tradeoff |
| --- | --- | --- |
| Reject frame or patch | Expose an invalid/unresolved observation; define whether enough observations remain for fitting. | Avoid unsupported interpolation while measuring loss of coverage and selection bias. |
| Integer fallback | Keep the in-window integer location and report fallback. | Bounded output does not imply accurate motion; quantify discretization bias. |
| Clamp fractional correction | Restrict the reported location to an explicitly defined interval. | Requires specifying the interval and reporting censored estimates; boundary compliance is not a truth PASS. |
| Wider search | Change the information/search domain. | Needs a new bounded algorithm/resource contract, ambiguity controls and wrap/large-motion tests; no default is selected. |

Reuse #260's existing bracketed quadratic/operator controls. Add independent
analytic cases with true maxima just inside/on/outside both search edges,
concave and convex/unbracketed triples, exact/near ties, flat and nonfinite data,
both axes, nonsquare scale factors and fractional origins. Score both truth error
for identifiable in-domain cases and honest invalid/ambiguous quality states for
negative controls. Freeze the expected outcomes before native measurement.
Keep stored-float versus independent high-precision samples separate, so a
conditioning or forward-FFT effect is not mislabelled as an edge-policy fix.

All four prospective policy outcomes remain UNRUN. M5 must name the selected
semantics, supported domain, fixtures and versioned contract before adoption.

## Decision and execution dependencies

C1 is an engineering candidate; this brief is not bundled into its production
source. M3/DC, M4 and M5 remain maintainer decisions. C2 is frozen only after the
relevant dispositions and declared truth criteria are resolved. M6 approval of
the prospective scientific protocol precedes held-out outcome inspection. If no
code change is adopted, an explicit C2 freeze is still required; M3 “no change”
alone is not sufficient. No held-out scientific outcomes were inspected here.
