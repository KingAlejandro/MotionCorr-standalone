# Withdrawn claims

Claims published earlier in this issue that the evidence does not support, and
what replaces them. Raw reports under `raw/` are **not** edited: the record of
what was measured stays as it was written, and the correction lives here and in
the regenerated `support-report.md`.

Each entry names the claim, the field in the preserved raw record that
contradicts it, and the gate that now makes the claim impossible to publish
again. A withdrawal without a gate is a promise; a withdrawal with one is a
contract.

## W1 — Integrated all-24 screen certified native CUDA execution

**Published at 7098a6f** (`support-report.md`, "Integrated candidate: all 24
tutorial movies"):

> - Aggregate equality: pass
>
> | resume | 1 | 24/24 | 0 | pass |

and the closing aggregate, "The declared matrix is complete, every attempted row
passed".

**Contradicted by the same commit's raw record.**
`raw/scarf-gn0005/all24-summary.json` records, for the resume schedule:

```json
"backend_evidence": { "native_cuda_proven": false }
```

alongside `"passed": true` and a top-level `"all24_equal": true`. The witness
was collected and then never read: the pass condition did not consume it, and
the renderer printed a witness cell for `base` only, so the contradiction was
not visible in the published table.

**Withdrawn.** The integrated screen establishes that the three schedules
produce pixel-identical output. It does not establish that native CUDA executed
for every schedule. Those are separate claims and the second one is not
supported by that run.

**Now gated by** `run_all24_schedules.schedule_passed` (the witness is part of
the pass condition whenever `--gpu` is given), `report.all24_witness_holds`
(recomputed from the per-schedule evidence, never from the record's own
`all24_equal`), and `report.render_all24` (a witness cell on every row).
Negative controls `witness_is_consumed` and `report_renders_witness` assert each
of these rejects the historical record.

## W2 — The `batch` schedule's native witness

**Published at 7098a6f**: `| batch | 24 | 24/24 | 0 | pass |` with
`native_cuda_proven: true`.

**Not supported by the record.** `batch` ran 24 separate invocations, but the
pre-fix harness computed the witness from `last["stdout"]` only
(`run_all24_schedules.py:172` at that commit). Twenty-three of the twenty-four
startup markers were never examined and are not in the record. `true` there
means "the last invocation showed a startup marker", not "every invocation did".

**Withdrawn**, and **not recoverable from the preserved record** — the missing
markers are absent, not merely unaggregated. Re-deriving them would be
inventing evidence.

**Now gated by** `report.witness_coverage_gap`, which reports a multi-invocation
schedule lacking `startup_marker_per_invocation` as not covered rather than
crediting it, and by `schedule_witness`, which records the marker for every
invocation. Control: `report_renders_witness`.

## W3 — "Input provenance verified" covered the movies only

**Published at 7098a6f**: *Input provenance (fixtures vs git manifest) —
VERIFIED 5/5 on GPU; VERIFIED 4/4 on CPU.*

**Narrower than it reads.** Both preserved records,
`raw/cpu64/fixture-verify.json` and `raw/scarf-gn0005/fixture-verify.json`, are
`issue83-fixture-verify/1`, and each case entry holds exactly one digest pair:

```json
{"expected": "f9da4668…", "expected_bytes": 12583936, "status": "match"}
```

That is `movie_sha256` against the `.mrcs`. The manifest also declares
`ground_truth_sha256`, and the motion-truth verdicts — the `km_local_noisy`
FAIL and the four PASSes — are computed from the `*_ground_truth.json` files,
not from the movies. Those files were never checked at that commit, so an
edited or drifted truth could have moved a gate between PASS and FAIL while the
fixture set still reported as fully verified.

**Withdrawn as stated; restated narrowly.** The historical records establish
that the movie bytes matched the committed manifest. They establish nothing
about the truth files.

**Now gated by** `verify_fixtures.py` schema `/4`, which checks both declared
digests and fails on either. Checking the truth files for the first time found
real drift, and classifying it correctly is the subject of the next section.
Controls: `ground_truth_mutation` (a single significant digit changed in a
truth file must make the set unverified, asserted against real fixtures) and
`truth_provenance`.

### What the truth check found, and what is excused

Run on cpu64 at 8298158, four cases present. Every `movie_sha256` matched.
All four `ground_truth_sha256` did not.

| Case | Differing leaves (of ~4132) | Classification |
|---|---|---|
| `km_global_hisnr` | `/source_commit` | content equal |
| `km_local_nonsquare` | `/source_commit` | content equal |
| `km_local_noisy` | `/source_commit` | content equal |
| `km_local_hisnr` | `/source_commit`, `/noise/absolute_sigma`, `/noise/noise_free_image_std` | content equal |

Two excuses, both measured, both narrow, neither able to absorb a changed
motion value:

- The generator stamps the current commit into every truth file, so a fixture
  regenerated at `9ca8f0d` cannot match a digest recorded at `e07fdec` however
  identical the motion is. Allowed key: `source_commit`, and no other.
- `km_local_hisnr`'s two noise statistics differ by **1.8e-16 and 1.5e-16
  relative** — one unit in the last place. The movie digest for that case
  matched exactly, which is the proof that the noise actually injected is the
  same; only the statistic summarising it rounds differently between NumPy
  builds. Allowed: floats that are the same double to within 4 ULP.

Neither excuse is a numerical tolerance. `truth_provenance` asserts the
boundary directly: one ULP away is equivalent, `TRUTH_FLOAT_ULPS + 1` away is
drift, and **1e-12 relative is drift whatever the constant is set to** — that
last assertion does not scale with the knob, so widening the tolerance is
caught by behaviour and not only by the declared cap. Integers, integers
retyped as floats, added leaves, removed leaves and sign changes are never
eligible.

This is a defect in my own verifier's coverage, not a product defect, and no
scientific comparator threshold was touched.

## W4 — `gain_unity` and `gain_none` were declared byte-equal

**Declared in `matrix.NEUTRAL_EQUIVALENCES`** as an exact-equality pair, which
`run_matrix` enforced as "the comparator returns PASS".

**Contradicted on cpu64 at 93d427e**: 0 of 3 movies equal. The comparator's own
breakdown was `corrected_image: true`, `motion_trajectory: true`,
`star_fields: false`, with a single named difference —
`Field '_rlnMicrographGainName' presence mismatch in block 'general'`.

The science was bit-identical. Only one run had been given a gain reference, so
only one STAR file names one. **My contract was wrong, not the product.**

**Restated**: a unity gain multiplies every pixel by exactly 1.0, so the
corrected image and the motion trajectory must be bit-identical, and only
`_rlnMicrographGainName` may differ. The allowance is a named field list
carried with its rationale, not a class exemption.

**Now gated by** `run_matrix.numerically_equal`, which requires the comparator
to have reported both numerical checks and tolerates only differences naming an
allowed field, and by `run_matrix.numerically_differs`, which makes the
`gain_nonunity != gain_none` negative demand a **numerical** difference — before
this, a metadata-only difference would have satisfied it, so the negative
control could have passed while the two runs produced identical pixels.
Controls: `provenance_allowance`, `cross_row_consumed`.

## What the historical run does still support

Stated explicitly so the withdrawal is not read as broader than it is.

| Schedule | Invocations | Pixel equality | Native witness in the record |
|---|---:|---|---|
| `base` | 1 | n/a (reference) | complete: 24/24 movies marked, startup marker present |
| `repeat` | 1 | 24/24 exact | complete: 24/24 movies marked, single invocation examined |
| `batch` | 24 | 24/24 exact | **incomplete**: 1 of 24 invocations examined (W2) |
| `resume` | 1 | 24/24 exact | **unproven as recorded** (W1) |

For `resume` the raw record happens to contain the fields the corrected
contract needs, and they are consistent with a pass: `seeded_movies` lists 8
movies, the 8 movies without a stage marker are exactly that set, the 16
executed movies each carry one, and the single invocation recorded
`startup_marker_found: true`. That is a hand re-reading of an old record, not a
harness result, and it is recorded here as an observation only. The corrected
harness has never run on a GPU, so the native integrated screen is **UNRUN**
until a dedicated SCARF execution produces one.

## Status of the replacement evidence

| Claim | Status |
|---|---|
| Gate contracts reject what they are supposed to reject | **PASS** — `negative_controls.py`, CPU, every control asserted against both a good and a bad input |
| Input provenance including truth files (`verify_fixtures` `/4`) | **VERIFIED (content)** on cpu64, 4 cases; see W3 for what "content" excuses |
| `gain_unity == gain_none`, `gain_nonunity != gain_none` | **PASS** on cpu64, real pixels; see W4 |
| Integrated all-24 screen, native CUDA, corrected harness | **UNRUN** — requires a dedicated SCARF allocation |
| Per-row native CUDA matrix, corrected harness | **UNRUN** — same |
| `km_local_realscale` row | **UNRUN** on CPU — the fixture is not generated on that host |
| CPU support matrix | see `support-report.md` |

Historical CPU/RELION Gate 2 failures remain failures. Nothing here converts one
into a pass, and no withdrawal above upgrades any row.
