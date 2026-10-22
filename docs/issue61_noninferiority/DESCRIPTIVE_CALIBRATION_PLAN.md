# Prospective thinning plans and descriptive decision summaries

This host-only package starts at PR65 base
`34dc6bd61a2f55e57a7d65f057b5961d70e2eb12`. The live issue61 body/latest discussion,
PR65 body/discussion/reviews, original architecture note, frozen protocol and amendments,
`CERTIFICATE_VALIDATION.md`, Stage-B planner and STAR verification helpers were read.
The current certificate boundary remains closed: **Stage B is INCONCLUSIVE**.
Existing analysers, protocol, historical evidence and production sources are unchanged.

## Planner contract

`scripts/i61_thinning_plan.py` creates a **new** plan directory. Every reconstruction
job is **UNRUN**. The utility never invokes a reconstruction executable, SSH or GPU work.
It uses the existing Stage-B pattern of named columns in one `data_particles` loop,
without importing that script (which executes work at import). It selects exact
`_rlnMicrographName` values, rather than inferring movie identity from filename pieces.

The caller supplies a frozen design JSON containing exactly:

```json
{
  "particles_sha256": "<64 lowercase hex characters: hash of the complete input STAR bytes>",
  "held_movies": ["<exact micrograph name A>", "<exact micrograph name B>"]
}
```

The complete source STAR must match that digest before any output directory is created.
The manifest also hashes the exact design-file bytes and planner source. These hashes bind
local inputs; they do not prove prospective registration, authenticity or scientific truth.
Inputs are read once into snapshots. Later changes cannot alter the generated selection.

For each held-out movie × original `rlnRandomSubset` stratum, retain
`floor(input_count * requested_fraction)` particles. The fraction is parsed as an exact
rational; both decimal strings and fractions are supported. Require at least two unique
held-out movies, both halves in every movie, and at least one retained row in every stratum.
No fraction or seed is supplied by default.

Selection ranks SHA-256 of the compact, ASCII JSON list
`["i61-thinning-v1", seed, exact_movie_name, half_as_string, zero_based_source_row_index,
row_sha256]`. Take the lowest-ranked requested count, then restore original row order.
The row digest includes its original UTF-8 bytes and line ending. This explicitly versioned
algorithm avoids reliance on Python's PRNG implementation. It binds the source row order;
reordering or editing a source requires a new input digest and may change selection.

The complete held-out baseline and retained arm each receive a STAR and paired
delete-one-movie STARs. A jackknife removes **all** rows of the same movie from both arms;
it never redraws the retained selection. Original half assignments are unchanged.
The manifest records per-stratum selected source-row indices/digests and counts, output STAR
hashes, selected-row-list hashes, omitted movie identities, and actual retained fraction per
half for every full/jackknife subset. Subset names are safe numeric labels, with exact movie
mapping in the manifest. Non-held-out source movies are excluded from every subset.

All surviving particle row bytes, column headers, optics and surrounding metadata/comments
are preserved. The bounded single-line STAR lexer uses space/tab separators and LF/CRLF
line endings. A `#` begins a comment only at a token boundary; `movie_A#development` is
one literal name. Single/double quotes delimit a value only at its start and close only
before whitespace/end. Quotes inside unquoted tokens, non-closing quotes inside quoted
tokens, and backslashes are literal. Thus `movie_'A'` cannot alias `movie_A`. Quoted paths
with whitespace, literal `#` and embedded quotes are supported. Unterminated quotes,
unquoted semicolon-prefixed values, control characters and other whitespace separators are refused.
Validation includes non-held source rows and finishes before output creation.

Image references must contain exactly one `@`, a positive ASCII decimal index before it,
and a nonempty stack identifier after it. Leading index zeros are removed **for duplicate
identity comparison only**: `000001@stack.mrcs` and `1@stack.mrcs` are the same identity,
including across movies or halves. Quoted and unquoted spellings decode before comparison.
The stack identifier remains exact; equal indices in different stack identifiers are allowed.
All source rows participate in the duplicate check. Original references and raw row bytes
are never rewritten. Zero, signed, fractional, missing or non-ASCII indices and extra `@`
characters are unsupported and refused. This is a metadata-reference identity check: it
does not resolve filesystem paths, symlinks, hard links or stack aliases, compare stack pixels,
or validate optics associations.

This is a deliberately narrow parser: multiline particle values, missing values, duplicate
columns/image identities, invalid half labels, inconsistent row widths and multiple particle
loops are refused. It is not a general STAR or optics validator. It preserves other blocks
without interpreting them; it does not validate optics references, particle-stack availability,
stack pixels or CTF values. Host parsing/preservation does not establish compatibility of
these syntaxes or line endings with a particular downstream reconstruction executable.

`jobs.json` contains argument arrays, an explicit project working directory (for relative
stack paths), original half selections, input STAR hashes, output/log paths and UNRUN status.
Executable, symmetry, padding and CTF use are all explicit caller inputs. No shell commands
or launch code are generated. The job list covers reconstruction only; post-processing/masks
and execution policy need a separately reviewed plan. Empty `rec`/`logs` directories merely
reserve intended output locations. `manifest.json` hashes `jobs.json`.

Creation refuses **any** existing destination, including an empty directory. Validation
finishes before creation. Publication is not transactional: an I/O failure can leave a partial
new directory, which is retained and cannot be overwritten by another invocation. Choose a
different new directory after investigating such a failure.

**Particle retention fraction is not exact SSNR rho, accepted independent harm truth, or
scientific certification.** Every manifest has `design_truth_status="UNVALIDATED"`,
`gate_policy=null`, `scientific_certification_accepted=false`, and scientific verdict
INCONCLUSIVE. This utility cannot create an accepted sensitivity certificate.

## Descriptive summary contract

`scripts/i61_oc_summary.py` consumes two explicit JSON files. Protocol shape:

```json
{
  "protocol_id": "<caller's frozen protocol identifier>",
  "replication_unit": "<caller's explicit replication unit>",
  "endpoints": [
    {"endpoint": "<name>", "direction": "higher", "margin": 0.95, "critical_value": 2.0}
  ]
}
```

Numbers above are illustrative arithmetic inputs, **not recommended scientific settings**.
The utility supplies no margin, critical value, replication unit, sample size, confidence,
acceptance threshold, power target or gate policy. Direction is `higher` or `lower`.
Records shape:

```json
{
  "protocol_sha256": "<SHA-256 of the exact supplied protocol-file bytes>",
  "replicate_ids": ["<replicate identifier>"],
  "records": [
    {"replicate_id": "<replicate identifier>", "endpoint": "<name>", "estimate": 0.96, "se": 0.01}
  ]
}
```

Each declared replicate must supply exactly one record per declared endpoint. All fields
are required as shown; an optional record `verdict` must agree with the recomputed decision.
Duplicate JSON keys, duplicate/unknown replicates/endpoints, incomplete rosters, missing fields,
unknown fields, nonfinite values, booleans used as numbers, negative SE, nonpositive critical
values and a mismatched protocol digest are rejected. Zero SE is allowed as descriptive input.
The roster can detect missing declared replicates; it cannot detect undeclared omitted work.

Compute `lower = estimate - critical_value * SE` and
`upper = estimate + critical_value * SE`. For `higher`, the raw endpoint decision is PASS
if lower ≥ margin, FAIL if upper < margin, otherwise INCONCLUSIVE; reverse inequalities
for `lower` (PASS at upper ≤ margin, FAIL at lower > margin). These match the existing
analyser's raw endpoint decisions. They do not bypass its scientific validity precondition.

Report those decision counts/fractions per endpoint and **separate one-sided Clopper-Pearson
binomial bounds** at the caller's explicit confidence. The two bounds are not a joint interval
at that confidence, and no multiplicity adjustment is applied. Their binomial interpretation
assumes independent, identically distributed replicates; the software cannot establish this
from labels or detect pseudoreplication. Replication unit and exact input-file hashes travel
with the report. SciPy supplies beta quantiles; this is the existing GPL-compatible dependency.
The thinning planner itself uses only the standard library.

Only decision frequencies are described. No rate is labelled false-pass rate, power, validated
coverage or scientific acceptance. No real thinning truth or synthetic bias metric is inferred;
bias against an independently supported SYNTHETIC construction remains outside this package.
The summary always reports `gate_policy=null`, truth UNVALIDATED, certification false and
scientific verdict INCONCLUSIVE. It is **not** consumed by the existing certificate analyser.
The output file uses exclusive creation and refuses overwrite.

## Commands and host verification

All numeric thread controls are one, with the explicit interpreter:

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1
PY=/Users/alex.konstantinov/.local/bin/python3
$PY docs/issue61_noninferiority/scripts/i61_thinning_plan.py \
  --particles /absolute/input/particles.star --design /absolute/input/design.json \
  --out /absolute/scratch/NEW-plan --seed 61 --retain-fraction 2/5 \
  --project-root /absolute/existing/RELION-project \
  --reconstruct-program /explicit/path/relion_reconstruct --sym D2 --pad 2 --ctf yes
$PY docs/issue61_noninferiority/scripts/i61_oc_summary.py \
  --protocol /absolute/input/oc-protocol.json --records /absolute/input/replicates.json \
  --confidence 0.95 --out /absolute/scratch/NEW-summary.json
$PY -m unittest discover -s docs/issue61_noninferiority/scripts \
  -p test_i61_descriptive_calibration.py -v
$PY docs/issue61_noninferiority/scripts/i61_certificate_host_controls.py \
  --out /tmp/i61-host-package-20261022-6tda8g02/certificate-controls.json
git diff --check
```

CLI examples are syntax examples, not experiment authorization or scientific defaults.
Host controls generate a **synthetic** 64-row STAR with uneven strata, quoted paths/metadata,
unchanged CRLF/optics/suffix blocks and one excluded development movie. No real input is used.
Checks cover repeated/changed seeds, exact stratum counts, row bytes/digests, half assignments,
paired frozen jackknives, job plans/hashes, actual retained fractions, overwrite refusal,
malformed STARs, empty strata, input hash mutation, both actual CLIs, endpoint directions,
boundary decisions, independent binomial-tail identities/extreme counts, closed gates and
malformed/duplicate/missing/nonfinite/inconsistent summary inputs.

Initial host run: **FAIL**, 1/11 tests. A test compared canonical `/private/var/...` with the
macOS `/var/...` alias in the job working-directory assertion. The assertion now canonicalizes
its expected path; planner behavior was correct. Subsequent run: **PASS**, 12/12 tests,
including the added empty-half control. Final run after adding duplicate-design-key and
commented duplicate-block controls: **PASS**, 13/13 tests. This failed attempt remains recorded here.

Existing certificate regression: **PASS**, 20 analyser subprocesses; retained descriptive
endpoint digest `33b5b7d10ffefd46a13592a91ac67931fce3a1b225e78c1d7c59bd58674bd529`
is unchanged. `git diff --check`: **PASS**. Receipts, test log and retained synthetic CLI outputs
are in `/tmp/i61-host-package-20261022-6tda8g02/`: `validation-receipt.json`,
`package-tests.log`, `certificate-controls.json`, `SYNTHETIC-plan/{manifest,jobs}.json`,
the generated STARs, `SYNTHETIC-summary.json` and their synthetic inputs. The retained planner
CLI used the shown `--seed 61 --retain-fraction 2/5 --sym D2 --pad 2 --ctf yes` with that
scratch as project root and `/explicit/UNRUN/relion_reconstruct` as the executable string.
It produced 16 **UNRUN** jobs (two arms × four subsets × two halves). The summary CLI used
explicit confidence .95 and reports 1 PASS/1 FAIL/1 INCONCLUSIVE for each synthetic endpoint,
while its scientific verdict is INCONCLUSIVE. Both CLIs exited zero. Neither launched jobs.

The exact committed package revision is in the implementation handoff. No prior scientific
verdict is changed by these host controls. Reconstruction,
post-processing, historical raw-map/interval reanalysis, remote execution, native GPU,
performance and scientific qualification are **UNRUN**.

Environment checked 2026-10-22: macOS arm64; Python 3.13.7, NumPy 2.4.2, SciPy 1.17.1.
`ps -Ao pid,pcpu,comm`, `uptime`, `df -h .` showed unrelated busy Refmac/security/browser work,
load 11.62/12.58/13.28 and 18 GiB free. Those processes were left alone. These sequential small
host checks provide correctness evidence, not timing measurements. No new dependency was added.

## Independent-review lexical and particle-identity repairs (2026-10-22)

The independent review of `ae5a08a75217f4741858ea4b5237fc4d7168d453`
(`/tmp/i61-independent-review-dSfMBtXs/review-receipt.json`) found two material P2 defects:
shell tokenization truncated an unregistered last-column `movie_A#development` to
`movie_A` (and stripped embedded quotes), and raw-string image comparison missed
`000001@stack.mrcs` versus `1@stack.mrcs` across halves. The bounded STAR lexer and
normalized positive-index identity comparison above repair these defects without rewriting
rows or changing selection ranking, reconstruction settings or scientific policy.

The final 19-test package suite was first run against an exported AE planner/summary with
the new tests: **FAIL**, exit 1 with 25 failing subcases. The retained log reproduces both
review counterexamples through the actual CLI, plus quote aliasing, unsupported indices and
lexical cases. An earlier version of this regression run had 17 failing subcases; its log is
also retained. The first fixed run passed 19/19. The final run, after tightening the lexical
refusal control to use a non-held row with otherwise complete held strata and adding quoted
numeric-alias cases, passed **19/19**. No implementation test failure or tolerance change
was needed. CLI controls verify every generated subset excludes unregistered names, reject
numeric aliases within/across halves before output creation, preserve quoted/special values
and raw CRLF row bytes, and allow equal indices in distinct stack identifiers. Unsupported
lexical syntax in non-held rows and malformed/zero indices fail before output creation.
The original seeded selection, paired jackknife, byte/metadata preservation, plan-only and
summary arithmetic controls remain included.

Existing certificate controls: **PASS**, 20 analyser subprocesses, descriptive endpoint digest
`33b5b7d10ffefd46a13592a91ac67931fce3a1b225e78c1d7c59bd58674bd529` unchanged.
Commands use `/Users/alex.konstantinov/.local/bin/python3` with the same six numeric thread
controls set to one. `ps` occupancy was checked; unrelated work was left running. Logs,
exact commands/exit codes, pinned AE regression scripts/tests and the review receipt are in
`/tmp/i61-pr65-lexical-fixes-EdbcgCi3/`. The package command is the unittest discovery command
above; the certificate command uses that scratch directory for `--out certificate-controls.json`.
`git diff --check` passes. Only this new design note, planner and package tests change from AE;
the OC summary, existing analyser/protocol/history, production source and dependencies are
unchanged. The final commit and scope hashes are recorded in the scratch validation receipt.

These are host-only synthetic checks. The parent's real-input AE plan remains evidence for
AE only; it was not modified or regenerated here. Reconstruction, post-processing, SSH,
remote/native GPU execution, performance and scientific qualification are **UNRUN**. The
scientific verdict remains **INCONCLUSIVE** with no accepted harm truth or OC gate policy.
