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

**Replacement evidence: SCARF job 3511139, `gn3000`, device 0, exclusive.**
`raw/scarf-gn3000-3511139/all24-summary.json`, `schedules/resume`, records —
summarised here, not quoted; `seeded_movies` and `executed_movies` are lists
of movie names in the record and the counts below are their lengths:

| Field | Where | Value |
|---|---|---|
| `seeded_movies` | `schedules/resume` | 8 names |
| `executed_movies` | `…/backend_evidence` | 16 names |
| `movies_with_stage_marker` | `…/backend_evidence` | 16 |
| `vacuous` | `…/backend_evidence` | `false` |
| `native_cuda_proven` | `…/backend_evidence` | `true` |

Eight movies were handed to the resume as already finished and were correctly
left alone; the sixteen it actually executed each carry a `[CUDA …]` stage
marker, and the executed set is non-empty, so the quantification is not
vacuous. The claim W1 withdrew is now **supported by a run**, not by a
re-reading. Job 3511210 at `4c2305b` records the same four values, and it is
that record the published report is now generated from.

An earlier revision of this entry set the same five fields in a fenced `json`
block, which read as a verbatim extract of a single object. It was neither:
two of the values were counts standing in for lists, and the five fields do
not share one parent. The record is unchanged; only the presentation was
misleading.

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

**Now gated by** `schedule_witness`, which records the marker for every
invocation, and by `report.banner_coverage`, which reports how many of a
schedule's invocations have one so a cell can never read "native" while
standing on a single stdout. Control: `report_renders_witness`. (An earlier
revision of this paragraph named `report.witness_coverage_gap` as the gate.
That function keys on the per-movie stage markers, not the banner, and using
it for this is precisely the conflation W8a withdraws.)

**Replacement evidence: the same job 3511139, reproduced at 3511210.** `batch`
ran 24 invocations and the record carries 24 booleans in
`startup_marker_per_invocation`, all true, alongside 24 movies with a kernel
stage marker; job 3511210 records the same 24/24 at `4c2305b`. The gap W2
named is closed by measurement, and the record says which invocations were
examined rather than leaving it to be assumed.

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

Run on cpu64, four cases present (`km_local_realscale`, 402 MB, is not
generated on that host). Every `movie_sha256` matched. All four
`ground_truth_sha256` did not. The figures below are read from
`raw/cpu64-4c2305b/verify_fixtures.json`; an earlier revision attributed them
to a run at `8298158`, for which **no record exists under `raw/`** — the
numbers were right and the attribution was not, so it is corrected to the
record that actually holds them.

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
- `km_local_hisnr`'s two noise statistics round differently. The record
  (`raw/cpu64-4c2305b/verify_fixtures.json`,
  `cases/km_local_hisnr/ground_truth/content_comparison`) carries
  `"float_rounding_leaves": ["/noise/absolute_sigma",
  "/noise/noise_free_image_std"]` and
  `"float_rounding_max_relative": 1.840467826221118e-16` against
  `"float_rounding_tolerance_ulps": 4` — a maximum over the two leaves, which
  is all the verifier records. An earlier revision of this file quoted a
  per-leaf pair, "1.8e-16 and 1.5e-16"; the second figure is not in any
  record and is withdrawn. The movie digest for that case matched exactly,
  which is the proof that the noise actually injected is the same; only the
  statistic summarising it rounds differently between NumPy builds. Allowed:
  floats that are the same double to within 4 ULP.

Re-run on `gn3000` at 7ba584e with all **five** cases present, including
`km_local_realscale` (402 MB, not generated on cpu64): every `movie_sha256`
matched and all five `ground_truth_sha256` differed. Four of the five differ on
`/source_commit` alone. `km_local_hisnr` does **not** — in both
`verify_fixtures.json` and `verify_fixtures_inplace.json` it reads

| field | value |
|---|---|
| `differing_leaves` | `/noise/absolute_sigma`, `/noise/noise_free_image_std`, `/source_commit` |
| `float_rounding_leaves` | `/noise/absolute_sigma`, `/noise/noise_free_image_std` |
| `float_rounding_max_relative` | 1.840467826221118e-16 |

so the GPU host needed the *same* float-rounding excuse as cpu64, on the same
case and the same two leaves. `realscale` compared 8032 leaves and added no new
excuse, which is the claim the paragraph was making; the sweeping
`float_rounding_leaves: []` that carried it was false and is **withdrawn**.
Nothing downstream changes — the allowance was already declared, bounded at 4
ULP and controlled — but the sentence asserted a cleaner result than the record
holds.

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

## W5 — One provenance header over sections from different jobs

**Published at 7098a6f** (`support-report.md`): a single `## Provenance` block
naming host `gn0005.scarf.rl.ac.uk`, device 0, one binary digest and one run
window, `2026-09-27T14:14:41Z to 14:20:47Z`, followed by every section of the
report.

**Contradicted by this repository's own `provenance.md`**, which records the
capacity datapoint as coming from a **different Slurm job at a different
commit**: *"Jobs of record: 3510290 (matrix + all-24 + report, at `d48d875`)
and 3510288 (capacity datapoint + `realscale_local`, at `0a6dbff`)"*. The
"Memory capacity" section's 1266 MiB was therefore measured by a different
build in a different allocation from the one the header describes, and nothing
in the rendered report said so. `capacity.json` records a device index and no
host and no binary at all, so "Device: 0" in that section could not be tied to
the header's device 0 even in principle.

**Withdrawn.** The header describes the declared-matrix run only. It was never
evidence for the provenance of the other sections.

**Now gated by** `report.source_attribution`, which prints each section's own
host, device, binary digest and start time, names field by field any
divergence from the header, and — for a record like `capacity.json` that
carries no host or binary — states plainly that the section cannot be
attributed rather than letting the header speak for it. Control:
`report_attributes_each_section`, which asserts the divergence is reported for
a differing host, a differing binary **and** a differing device, that the
differing fields are named, that an identical run is *not* flagged, that the
merged truth tool's top-level `binary`/`gpu` shape is not dropped, and that a
record with no provenance is not given an invented source line.

**And by the declared run window.** Naming host, device and binary is not
enough, which the corrected report demonstrated on its first rendering: jobs
3511139 and 3511154 ran on the same node and reused the same binary by digest,
so every identity field agreed and nothing was flagged — two different
allocations, hours apart, reading as one measurement. The header states a run
window, so a section measured outside it is named as a different run
(`report.outside_reference_window`), and the **aggregate sentence** — the line
most likely to be quoted on its own — carries the caveat too
(`report.is_other_run`). Six reverted variants of the window check are caught
by `report_attributes_each_section`, including having no window check at all,
comparing only against the start, and treating a missing finish time as proof
of divergence.

This was not a hypothetical. The corrected report is assembled from two jobs on
purpose: see `provenance.md`, "Two native allocations, and why".

## W6 — "every `.mrcs` matched the committed manifest"

**Published in `progress.md`, "Fixtures":** *"All five known-motion fixtures
were regenerated and every `.mrcs` sha256 **matched** the committed
`test-data/known_motion/MANIFEST.json`."*

**Contradicted by this repository's own later section**, "Fixture drift between
hosts", and by `provenance.md`: all five cases mismatched the committed
manifest on SCARF `gn0005`, where NumPy 1.22.4 generated them
(`km_global_hisnr.mrcs` `4e8666c1…` against the declared `f9da4668…`). The
original check never read the tracked manifest at all — it read the copy the
generator writes into its own output directory, which agrees with those
outputs by construction. The table it rested on was a comparison of the
fixtures against themselves.

**Withdrawn.** Agreement with a self-written manifest is not agreement with the
declared inputs.

**Now gated by** `verify_fixtures.py`, which reads `MANIFEST.json` out of git
(`git show <ref>:…`) and records which ref and which commit it read
(`manifest_ref`, `manifest_source_commit`), so the verdict names the authority
it was checked against. Controls: `input_hashes`, `truth_provenance`.

**Replacement evidence:** cpu64 `cb587bd` **VERIFIED (content)** over the 4
cases this host generates, against manifest commit `e07fdec2…`; `gn3000` job
**3511210** **VERIFIED (content)** over all 5 under schema `/5` with
`"vacuous": false` (job 3511154 reached the same verdict earlier, but under
schema `/4`, which records no compared count — see W7).
`gn0005`-as-generated remains **NOT VERIFIED** and is preserved as such.

## W7 — A fixture record that compared nothing reported VERIFIED

**Published at 7098a6f**, in the code rather than in prose:
`verified = not (mismatched or undeclared or missing)`. Every disjunct
quantifies over a list that is empty when nothing was examined, so a run that
compared **zero** digests reported `"verified": true`, and the report rendered
"Result: **VERIFIED**" above it.

**Demonstrated, not argued.** cpu64 `4c2305b`, stage (a2), points the verifier
at an empty directory:

```json
"declared_cases": 5, "compared": {"movie": 0, "ground_truth": 0},
"vacuous": true, "verified": false
```

exit 1. Under the published code the same directory produced a pass.

**Withdrawn**: no published "VERIFIED" is evidence unless the record says how
many digests were compared. This is the same defect as W1 and W2 in a third
place — a gate quantifying over an empty set.

**Now gated by** `verify_fixtures.compared`, a per-kind count incremented only
where a digest was actually computed and compared, and `result["vacuous"]`,
which fails the run when either count is zero; by `report.inputs_verified`,
which recomputes the verdict rather than reading the record's own `verified`
flag; and by `report.render_fixture_verification`, which prints
"Digests actually compared: N movie, M ground truth" so the number is visible
next to the verdict. Controls: `report_states_input_coverage`,
`aggregate_needs_every_leg`. Meta-checks `vacuous_fixture_verification` and
`w3_caveat_keyed_on_schema` revert each gate and confirm the control then
fails.

## W8 — The declared matrix certified native CUDA for every schedule

**Published at 7098a6f** (`support-report.md`, implementation coverage): a
`Native witness` column reporting one value per **row**, and a `Verdict` of
`pass` for each row, over four schedules per row.

**Not supported by the record.** The witness was computed for the `base`
schedule and rendered once; `repeat`, `batch` and `resume` contributed nothing
to it and nothing to the row's pass condition. For `batch` — one invocation per
movie — the record holds evidence from a single invocation out of three. The
published column answered "did native CUDA run at all in this row", and was
read as "every schedule in this row ran natively".

**Withdrawn as published.** The rendered column did not answer the question it
was read as answering.

**Now gated by** `run_matrix.schedule_witness`, called with the stdout of
*every* invocation in the schedule; by `entry["passed"]`, which now consumes
it (`and native_schedule and not evidence.get("unexpected_cuda_marker")`); by
`report.schedule_cell`, which renders each schedule's own witness state —
`vacuous`, `NOT established`, `not covered (K of N movies marked)`, or
`native (…)` — instead of pixel equality alone; and by
`report.matrix_witness_gaps`, which finds rows whose per-schedule native claim
the record cannot support and makes the renderer say so. Control:
`matrix_schedule_witness`. Meta-checks `matrix_witness_unrendered`,
`matrix_witness_last_invocation_only` and `matrix_witness_gap_unreported`
revert each of the three gates in turn and confirm the control fails.

### W8a — the withholding was itself wrong, and is withdrawn

**Published in the previous round:** *"the evidence for the repeat, batch and
resume cells above is not in the record and cannot be recovered from it"*, with
all 23 payload rows marked **UNRUN / WITHHELD** and a fresh allocation named as
the only way to close them.

**That is false, and review caught it.** There are two distinct witnesses and
the renderer had conflated them:

| Witness | Where it is written | Coverage in job 3511154 |
|---|---|---|
| Startup **banner**, `Using CUDA acceleration on GPU device N for global alignment.` | stdout, once per invocation | the **last** invocation only — `batch` 1 of 3, `resume` 1 of 2, `repeat` 1 of 1 (complete) |
| Kernel **stage marker**, `[CUDA <stage>] completed; converged=` | each movie's own `.log`, in that schedule's own output directory, by the CUDA code path | **complete** — 23 rows × 4 schedules, every movie `log_present` and `cuda_stage_marker` |

`run_matrix.py` at `7ba584e` called
`backend_witness(run["stdout"], sched_dir, dataset["stems"], opts.gpu)` once per
schedule, with `sched_dir = work / schedule`. The per-movie markers are
therefore that schedule's own measurement, not a copy of `base`'s. For `batch`,
each invocation runs `--do_at_most 1 --only_do_unfinished` and writes exactly
one movie's log, so the three marked logs were written by three different
invocations.

`report.witness_coverage_gap` keyed coverage on the *field name*
`startup_marker_per_invocation`, which only the fixed runner writes, and
discarded `per_movie` entirely. So every row of a fully stage-witnessed record
was called a gap — including `repeat`, which runs once and is missing nothing
at all. The report then withheld 23 rows' worth of measured evidence.

This document's own W2 scores the identical evidence shape — one invocation,
every movie marked — as *"complete: 24/24 movies marked, single invocation
examined"* for the historical all-24 `repeat`. Two passages, the same shape,
opposite verdicts.

**Withholding a measured result is a misstatement in the same way publishing an
unmeasured one is.** Both replace what the record says with what the author
concluded. The correction is not a relaxation: the gate now asks the question
the claim rests on — *was every movie whose pixels are being compared produced
by the CUDA path?* — and a single unmarked movie still fails it.

**Now gated by** the rewritten `report.witness_coverage_gap`, which requires
every movie in `per_movie` to carry `log_present` and `cuda_stage_marker`, or,
where the record names `executed_movies`, every executed movie. A record
showing 16 of 24 marked with no executed set stays a gap: eight movies skipped
and eight run on the CPU are indistinguishable in it. `report.banner_coverage`
reports the banner separately and the cell discloses it as `banner K/N`.
Controls: `matrix_schedule_witness` (cases `no_per_movie_record`,
`half_marked`, `stage_marked_banner_partial`, plus the two positive controls
`stage_only` and `dropped`) and `report_renders_witness`. Meta-checks
`coverage_keyed_on_field_name` and `banner_gap_silently_dropped` revert the
correction and the tightening respectively, and confirm the control fails each
time.

**Replacement evidence: not needed for the stage witness — PASS on the record
already held.** What remained genuinely absent was the startup banner for the
non-final invocations of `batch` and `resume`: the weaker and redundant
witness, disclosed in every affected cell. The **pixel-equality** results in
those cells were never in question.

**And then it was measured anyway.** Job **3511210** (`gn3000`, device 0,
exclusive, `4c2305b`) ran the fixed runner and recorded the banner once per
invocation. `batch` now carries **3 of 3** per matrix row and **24 of 24** on
the integrated screen. One gap is left and is disclosed rather than closed:
the matrix's `resume` schedule runs a seed invocation and a resume invocation
and only the second's stdout is kept, so every payload row reads
`banner 1/2`. Every movie in both invocations carries its stage marker.

## W9 — Option rejection asserted by bare substring

**Published at 7098a6f**: `matrix.py` declared the rejection rows as
`expect_reject="group"` and `expect_reject="j"`, and the runner asserted the
declared token appeared anywhere in the lowercased combined output.

**Not a contract.** `j` occurs in `/home/ubuntu/mc-i83-cpu/build-cpu/...`, in
`--j`, and in any backtrace frame; the assertion was satisfied by a segfault
whose backtrace mentioned a path. A row could have recorded "the binary
rejected `--j 0` and said so" on the strength of a crash that said nothing.

**Withdrawn.** A nonzero exit plus a substring is not a named rejection.

**Now gated by** `run_matrix.rejection_names_option`, which matches
`(?<![0-9A-Za-z_-])--opt(?![0-9A-Za-z_-])` against lines that are not
backtrace frames or separators, and returns the line it matched so the record
carries the diagnostic verbatim; and by `matrix.py`, which now declares the
full options `--group_frames` and `--j`. Control: `rejection_names_option`,
which accepts a real diagnostic and rejects a crash, a backtrace-only output,
`--j_extra`, `--i` and `--group_frames_max`, and additionally requires each
declared token to start with `--`. Meta-check: `substring_rejection`.

**Replacement evidence: cpu64 `4c2305b`, real pixels, reproduced on GPU at
3511210.** Both rejection rows pass and the record names the line:

```json
"expected_option": "--group_frames", "option_named": true,
"option_named_line": "--group_frames must be positive."
"expected_option": "--j",            "option_named": true,
"option_named_line": "--j must be positive."
```

The published report renders those two rows from 3511210 as
``rc=1, named by `--group_frames must be positive.` `` and
``rc=1, named by `--j must be positive.` ``. Through the previous revision these
rows read **not covered** on GPU, because the `7ba584e` records predate the
delimited matcher and kept no matched line.

## W10 — The integrated all-24 screen asserted no STAR metadata

**Published at 7098a6f**: `run_all24_schedules` called
`check_products(base_dir, stems, suffixes, {}, None)`. The fourth argument is
the expected STAR metadata; `{}` asserts nothing. The screen compared the
schedules against each other and checked products existed, so three schedules
writing the same wrong binning, dose or first frame would have agreed with each
other and passed.

**Withdrawn**: schedule-to-schedule equality is not evidence that the values
written match the values requested.

**Now gated by** `run_all24_schedules.expected_star_metadata`, which derives
binning, first frame, dose per frame and pre-exposure from the invocation's own
argument vector and asserts them on the written STAR, and by
`metadata_not_asserted`, which names in the record what is *not* derivable
(`original_pixel_size`, `image_geometry`) rather than leaving the gap silent.
The report prints the asserted values, or a bold *"This record asserted no STAR
metadata"* for a record that has none. Control: `all24_asserts_metadata`.
Meta-check: `all24_asserts_nothing`.

**Replacement evidence: PASS on the integrated candidate.** cpu64 `4c2305b`
executed the assertion for the first time anywhere, on a **synthetic** runroot
(one generated fixture under 24 names,
`tools/validation_issue83/stage_synthetic_runroot.py`), which established that
the assertion names fields the runner actually writes and does not fail a
correct run — and said nothing about the RELION tutorial dataset.

Job **3511210** (`gn3000`, device 0, exclusive, `4c2305b`) then ran it on the
tutorial dataset itself: `all24_equal`, 24 of 24 movies in the STAR, no missing
schedules, no errors, and

```json
"star_metadata_asserted": {"binning": 1.0, "dose_per_frame": 1.277,
                           "first_frame": 1, "pre_exposure": 0.0},
"metadata_not_asserted": ["original_pixel_size", "image_geometry"]
```

The second field is part of the result, not a footnote to it: the tutorial
movies are not MRC, so this harness cannot read the pixel size or the geometry
the products would have to match, and it says so in the record instead of
leaving the gap silent. The published report prints both.

This row was **UNRUN on GPU** through the previous two revisions of this
document. It is now measured.

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
harness result, and it is recorded here as an observation only.

The corrected harness has since run on a GPU twice — job 3511139 and then job
3511210, both `gn3000`, device 0, exclusive — and produced the witness for
itself, which is what W1 and W2 above now rest on. The re-reading was right; it
was never the evidence.

## Status of the replacement evidence

| Claim | Status |
|---|---|
| Gate contracts reject what they are supposed to reject | **PASS** — `negative_controls.py` **19/19** on cpu64 at `cb587bd`, 0 skipped, against real generated fixtures; every control asserted against both a good and a bad input, and every gate additionally reverted at runtime by `meta_controls.py` to confirm its control then fails (**20 meta-checks**: 17 reverted gates + 3 suite exit-status cases, `raw/cpu64-cb587bd/meta_controls.json`). On a GPU host, **3511210 carries 17/17** — the whole suite at `4c2305b`. The two not asserted there, `payload_recorder` and `suite_selects_something`, were added at `cb587bd` and neither needs a GPU. Historically: 3511154 carried 10/10 and **3511139 carried 9 pass / 1 failed**, the whole suite as it then stood at `7ba584e`; an earlier revision said "the `gn3000` records carry 10/10", which was true of one of the two |
| Input provenance including truth files (`verify_fixtures`) | **VERIFIED (content)** — all **5** cases and 5+5 digests on `gn3000` job 3511210 under schema `/5`, `"vacuous": false`; 4 cases and 4+4 digests on cpu64, where the 402 MB fixture is not generated. See W3 for what "content" excuses and W7 for why the compared count is now part of the verdict. The superseded job 3511154's file is schema **`/4`** and carries no `compared`, `vacuous` or `declared_cases` field; an earlier revision headed its row `/5` and so attributed a `/5` verdict to a `/4` record |
| A fixture record that compares nothing is refused | **PASS** — empty directory, `"vacuous": true`, exit 1, on cpu64 and on `gn3000` 3511210; see W7 |
| `gain_unity == gain_none`, `gain_nonunity != gain_none` | **PASS** on cpu64 and on `gn3000` device 0, real pixels; see W4 |
| Invalid options are rejected **by name** | **PASS** — both rejection rows on `gn3000` 3511210 and on cpu64, `option_named_line` recorded verbatim (`--group_frames must be positive.`, `--j must be positive.`); see W9. Previously asserted by bare substring, and the superseded GPU records keep no matched line |
| Integrated all-24 screen, schedule equality and native CUDA | **PASS** — `gn3000` job 3511210, exclusive. `all24_equal`, 24 of 24 movies, no missing schedules, no errors, and a non-vacuous native witness on every schedule: `base`/`repeat` 24 movies marked, `batch` **24/24 invocations bannered** and 24 movies marked, `resume` 16 executed movies each marked |
| Integrated all-24 screen asserts requested STAR metadata | **PASS** — `gn3000` job 3511210 on the tutorial dataset: `binning` 1.0, `dose_per_frame` 1.277, `first_frame` 1, `pre_exposure` 0.0, with `original_pixel_size` and `image_geometry` named in the record as not derivable. **UNRUN on GPU** in the previous two revisions; see W10 |
| Per-row matrix, pixel equality across all four schedules | **PASS** — `gn3000` job 3511210, 25 declared / 25 attempted / 25 pass, no unrun rows |
| Per-row **native execution** on `repeat`, `batch`, `resume` | **PASS for all 23 payload rows, one banner partial** — job 3511210 computes a witness *per schedule* from that schedule's own output directory; every row × schedule carries `log_present` and `cuda_stage_marker` on every movie, and `batch` additionally carries a startup banner for **all 3** invocations. The one remaining gap is `resume`, whose seed invocation's stdout is not kept: every payload row reads `banner 1/2`. An earlier revision marked all of this **UNRUN / WITHHELD** on the strength of the superseded records; that was wrong twice over and is corrected in W8a |
| Requested 128x128 power spectrum | **PASS** — the `power_spectrum` row asserts the requested dimensions on the written product; the wrong-dimension negative is `ps_wrong_dimension`, asserted on both cpu64 and `gn3000` |
| `ground_truth_sha256` detects a mutated truth file | **PASS** — cpu64 and `gn3000` 3511210: `/geometry/pixel_size_angstrom` 0.885 → 0.985 in `km_global_hisnr_ground_truth.json`, detected, after the unmutated tree verified. Recorded **FAILED** in job 3511139, where that precondition was unmet |
| `km_local_realscale` row | **PASS** on `gn3000` (matrix row and motion-truth gate). Still **UNRUN on CPU** — the 402 MB fixture is not generated on that host, which is why the CPU matrix exits nonzero |
| Motion-truth gates | 4 PASS, 1 **FAIL** (`km_local_noisy`, characterization) — `gn3000` job 3511210, on fixtures verified before and after the merged tool regenerated them |
| CPU support matrix | **24/25 pass, 0 fail, 1 unrun** at `cb587bd`; `raw/cpu64-cb587bd/matrix.json`. Diagnostic only |

Four of the report's six sections now come from **one** allocation, job 3511210,
which is the first GPU run at a commit whose runners carry the per-schedule
witness, the delimited rejection matcher and the STAR metadata assertion. The
other two are a different host and a different run and the report says so
section by section: the CPU-backend diagnostic from cpu64, and the capacity
datapoint from `gn0005`, which names no host or binary at all and is rendered
as unattributable. The superseded GPU records 3511139 and 3511154 stay under
`docs/issue83/raw/` unedited, including 3511139's recorded control failure.

**The GPU record is one commit behind the head.** Job 3511210 ran `4c2305b`;
the head is `cb587bd`, which changes `report.py`, `negative_controls.py` and
`record_payload_env.py`, adds `meta_controls.py` and `regenerate_report.sh`,
and touches no runner and no code that executes on a GPU. Two consequences are
stated rather than smoothed over: the two controls added at the head have not
been asserted on a GPU host, and job 3511210's placement recorder matched the
payload by **substring**, its record carrying no `match_mode` field. The
sampled executables are all the job's own `build-cuda/motioncorr`, so nothing
is known to be wrong with it; it is simply the weaker check, and the cpu64 run
at `cb587bd` is the one that used `--match-mode exact`.

Historical CPU/RELION Gate 2 failures remain failures. Nothing here converts one
into a pass, and no withdrawal above upgrades any row.
