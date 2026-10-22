# M4/M5 quality-state options — unapproved working brief

This prepares the decisions required by the revised Notion plan. It adopts no
policy, changes no source or output, and contains no newly executed native test.
The three active workers own C1, DC conditioning and first-divergence diagnosis.

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

Convergence, observability and evaluation validity must remain separate:

| Proposed field | States | Meaning and provenance |
| --- | --- | --- |
| `global_alignment` | `converged`, `iteration_limit`, `operator_error`, `not_run`, `unknown_legacy` | Actual solver result; retain iteration count and final incremental RMSD. |
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

The retained #273 checker reports four UNIDENTIFIABLE arms: flat CPU/CUDA have
VALID sampling; repeated-pattern CPU/CUDA leave the ROI. Noisy CPU/CUDA also
leave the ROI but are FAIL. All field metrics and original verdicts remain.
These are checker characterization states, not implemented production abstentions.

## M4 — nonconvergence

| Option | Products and exit behavior to decide | Evidence needed | Present readiness |
| --- | --- | --- | --- |
| Report only | Preserve correction and process success behavior, but publish explicit per-movie and aggregate quality status/warnings. | Capture the real return value on CPU/resident/streaming routes; prove healthy MRC/trajectory identity and accurate mixed-batch status; define old-resume handling. | Smallest prospective prototype; native behavior UNRUN. This can make nonconvergence visible but does not improve motion recovery. |
| Refuse | Treat iteration limit as a failed movie before corrected-image/STAR completion publication; retain healthy movies and fail the dataset. | Define treatment of earlier auxiliary products; exercise writer draining, aggregate exclusion, rerun/resume and mixed healthy/failing jobs. | Existing failure path is available, but rerouting quality into it is an intentional publication change, not an already qualified fix. |
| Retry | Retry only under a separately specified recovery condition and hard resource/attempt bound; expose both attempts and final disposition. | A prospectively justified recovery method and truth/reconstruction evidence, not another identical-state attempt. Define restoration, source/input identity and final report/refusal behavior. | Not ready to adopt. W4 must establish which altered input/objective could recover information. No iteration/search increase or coarse tracker is selected here. |
| Document | Preserve current code and document the limitation. | Accurate user-facing limitations and compatibility record. | Available as a disposition, but alone does **not** satisfy the phase requirement that nonconvergence is no longer silent in machine-readable outcomes. |

No complete four-policy implementation is proposed. Start with one minimal
observation prototype only if needed to resolve M4, then test the selected policy
after maintainer disposition. Reporting and refusal are not scientific accuracy
certificates. A retry must not conceal the original iteration-limit event.

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
