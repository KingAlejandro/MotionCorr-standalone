# Exploratory CPU particle-count pilot, 2026-10-22

**Scientific verdict: INCONCLUSIVE. POSTHOC EXPLORATORY, POINT-ONLY.** This collection
was already unblinded. The historical 22-movie selection is reused; this is not a new
held-out qualification. Particle-count retention is neither exact SSNR rho nor accepted
independent harm truth. No SE, CI, power, sensitivity or scientific PASS is inferred.

This record starts directly at `c0ee115c8348df54732f47dbef930b541b2a364a`. The live
issue 61 and PR 65 discussion, frozen protocol/amendments, architecture note,
`CERTIFICATE_VALIDATION.md`, `DESCRIPTIVE_CALIBRATION_PLAN.md`, existing reconstruction
and postprocess drivers, and analyser were read before implementation. The current
PR head was `34dc6bd61a2f55e57a7d65f057b5961d70e2eb12`; its body still contains
superseded PASS claims. This pilot changes no historical record or scientific gate.
Publication belongs to the parent; no push, comment or merge was made.

## Fixed scope and inputs

The parent's fixed plan remains at
`4GPUs:/mnt/clathrin/mc-i61-plan-c0ee115c-dbe9tcqr/plan`. Its 92 planned jobs remain
UNRUN in that immutable planning record. Only the four full-sample reconstructions
were staged into a new execution plan: baseline/thinned × original halves 1/2.
The sole reconstruction argv transformation is the output path into new scratch;
input STAR, working directory, D2 symmetry, padding 2, CTF and half selection remain
exact. No delete-one jobs, re-extraction, accelerated arm, seed scan or outcome-based
selection was authorized or performed. The old AE plan was preserved.

The read-only source is
`/home/alex/mc-issue61/proj/cpu/Extract61/particles.star`, SHA-256
`2a282d0421386c703dc125037a51ed6f35774b78cd421b4584426295f8425ede`.
It contains 4452 particles. Excluding the two historical development movies leaves
4095 baseline particles (2052/2043 by half). Seed **61** and requested fraction
**19/20**, floored independently per movie × half, retain 3870 (1939/1931 by half):
actual total count retention is 3870/4095, approximately **94.5055%**. Unequal, biased
particle contributions prevent interpreting that count ratio as known signal retention.

Preflight checked the planner/source hashes, frozen design/source/jobs manifest,
all 46 subset STAR hashes, raw source-row preservation, original half assignments,
normalized positive stack indices, physical stack aliases and index bounds, all 24
referenced stacks (including excluded development inputs), mask, MTF, wrappers,
container and runtime identities. Stack geometry is 256 × 256; complete identities,
counts, hashes, command arrays and per-half inventories are in the receipts.

## Execution design

Successful scratch: `4GPUs:/mnt/clathrin/mc-i61-pilot-c0ee115c-q21hhr8l`.
The one-shot driver serializes numerical jobs under
`/tmp/motioncorr-i61-cpu-14-15.lock`, with affinity **14–15**, six numerical thread
controls set to **1**, `CUDA_VISIBLE_DEVICES` empty, and no `--nv` container option.
The project, historical data and frozen plan are mounted read-only. Writable home,
tmp, logs and outputs are private to this new scratch. The old global benchmark
lock was probed and immediately released; it was not held over this CPU-only pilot.
No build was needed, so compilation and the shared build lock were unused.

The detached supervisor PID was **3000015**, driver PID **3000016**. Start, child PID,
per-job exit and supervisor-exit receipts support reconciliation without relaunch.
An in-flight `/proc` sample observed the numerical reconstruct process with one
thread, affinity 14–15 and all requested thread/GPU environment values. GPU UUID and
occupancy queries were read-only. No GPU work or controlled timing comparison was
performed; intrinsic progress timings remain in raw logs without a speed claim.

RELION is `5.1.0-commit-cb2683`, BASE double / CUDA-ACC single. The container SHA-256
matches historical provenance:
`b4f659198f78a0a909882d17e254dcaf185c20c68e6f9079e87be303ee225c3c`.
Its internal reconstruction binary hashes to
`ddc192470703eb91a3f022cca8a448da034ce09fc7faf5e49832f67fcec9cf07`, and postprocess to
`2e4fdd6be721a8b6b57e5699c11dbdf713543dcce46401eac306cbf942bcb3ae`.
The historical wrapper, mask and MTF hashes also match exactly.

Both postprocess argv arrays use the historical CPU command's unchanged options:
`--mask MaskCreate/job020/mask.mrc --angpix 1.244531 --mtf mtf_k2_200kV.star
--mtf_angpix 0.885 --auto_bfac --autob_lowres 10` from the CPU project cwd. The
historical command omitted `--randomize_at_fsc`, `--randomize_at_A` and `--random_seed`.
Help from the hash-matched container establishes defaults **0.8**, **-1** and **0**,
respectively; the pilot keeps those defaults. Historical CPU log randomization was
16.7684 Å. The phase-randomization RNG seed 0 is distinct from thinning seed 61.
No threshold, seed, mask or sharpening setting was tuned after seeing results.

## Attempts and limitations

The first preflight, retained at
`4GPUs:/mnt/clathrin/mc-i61-pilot-c0ee115c-e037cwvq`, **FAILed**, exit 1, because the
new driver assumed `/usr/bin/apptainer`; the installation is `/usr/local/bin/apptainer`.
There were **zero numerical launches**. The narrow fix resolves the runtime from
PATH and fails if absent. A regression checks a non-system installation prefix and
missing-runtime refusal. The failed scratch and stderr are retained; a fresh scratch
received the fixed driver. The final driver checks **PASS, 4/4**, covering output-only
staging, exclusion of jackknives, refusal of changed settings/cwd/half rosters,
CPU-only environment and runtime resolution. No existing source or policy changed.

The required remote interpreter `/home/alex/.mc-venv/bin/python3` is Python 3.12.3,
NumPy 2.5.3. It lacks SciPy. The initial metadata probe that imported SciPy
also exited 1 with `ModuleNotFoundError`; the subsequent availability probe recorded
that absence without installing or changing anything. The unchanged existing analyser also requires all 22
baseline jackknife STARs before any point analysis, so a four-map pilot cannot
satisfy its contract. No synthetic/missing jackknife placeholders, altered analyser,
endpoint-math reimplementation or dependency changes are used to bypass this.

## Reconciled results

**Execution PASS:** precisely four reconstructions and two postprocess calls, each exit 0;
no numerical retry. The supervisor exited 0 at 15:12:19 UTC. All four unfiltered maps
and all four processed/masked maps are 256 × 256 × 256, mode 2, with header sampling
1.2445310354232788 Å. Whole-file, core-header and pixel-payload SHA-256 values are
retained separately. These are product/geometry and execution checks, not scientific
qualification.

Literal RELION-reported full-sample values (no analyser-derived delta or interval):

| Arm | Particles | d143, Å | Auto sharpening B, Å² | Randomize from, Å |
| --- | ---: | ---: | ---: | ---: |
| baseline | 4095 | 3.123529 | -28.20819 | 16.768418 |
| thinned | 3870 | 3.154455 | -27.37639 | 16.768418 |

The remote unchanged analyser exited **1**, `ModuleNotFoundError: No module named
'scipy'`. A compatibility run with the explicit local interpreter and byte-identical
postprocess STARs in another fresh scratch also exited **1**: it refused the missing
22 registered jackknife outputs before computing any points. It generated no result
file. This confirms the separate analyser contract limitation without installing
anything remotely or fabricating replicates. **B1 rho and analyser-derived B2/B3
comparisons are UNRUN.** The two raw B2/B3 inputs above are available for description.
No endpoint implementation was copied, changed or bypassed. SE/CI, operating
characteristics, sensitivity and scientific qualification remain **UNRUN**.

Final reconciliation **PASS** at 15:15:01 UTC: all preflight inputs, wrappers,
container, mask, MTF and 24 stacks still match; all 46 fixed-plan STAR hashes are
unchanged and byte-identical to the old AE subsets; the original fixed plan contains
zero numerical products. Six start/exit receipt pairs confirm four reconstructions,
two postprocess calls and zero jackknives. The CPU ownership lock is released. The
main checkout remains `c8844894c7c6366abf297699b5312e4b775eb5b0` with the pre-existing
untracked `pr117-fix-measure-20260929/` directory. Only this new pilot directory is
added on top of C0; existing analyser, protocol, history, production source and shared
FILEONLY 258262–266268 material remain unchanged.

The consumed historical CPU provenance records MotionCorr source
`5407373be31a6fe5f79a8cc5709be00723921b19`. No motion correction or extraction was run
here. This is the historical provenance association; current input identity is bound
by the newly verified complete stack hashes, not inferred from source names alone.

## Receipt map

- `source_inventory.json`: pinned C0 tree and all frozen script/protocol hashes.
- `receipts/execution_plan.json`, `job_[0-5]_{started,pid,exit}.json`: every numerical
  argv, cwd, start/end, PID, exit and log digest. `LAUNCH_INTENT.json`, `STARTED.json`
  and `supervisor_{pid,exit}.json` bind the single detached launch.
- `receipts/preflight_summary.json`: full identity/row/half/stack validation; only
  the long occupancy listing is shortened, with the complete remote receipt hash.
  `launch_resources_summary.json` and `resource_sample_151013.json` retain allocation
  and observed numerical-process affinity, threads and GPU environment.
- `receipts/map_[0-3].json`, `products.json`: all map geometry and whole/core/payload
  hashes. `remote_file_index.json` indexes retained remote raw files. Maps and full
  reconstruction logs remain in the successful remote scratch; no raw maps are
  committed locally. The index is a snapshot taken after reconciliation, excluding
  itself; it does not certify later filesystem immutability.
- `receipts/pp/{cpu,thinned}/held22.star.gz` and `receipts/logs/pp_*.log.gz`:
  lossless copies of the small postprocess outputs, including FSC curves. Decompressed
  bytes match the remote SHA-256 values; `compressed_receipts.json` binds both forms. `reported_postprocess_fields.json`
  transcribes only the literal resolution/B/randomization fields without estimators.
- `receipts/defaults.json`, `version.json`, `container_binaries.json`: executable
  defaults, version and internal binary hashes. Historical copied commands/logs are
  labelled `historical_*` and retain their original meaning; the copied historical
  postprocess log is also losslessly compressed.
- `receipts/analyser_attempt.json`, `host_analyser_compatibility.json`: both failed
  compatibility runs, exact environments, stderr and exits. Neither is a B1 result.
- `preflight_transport.json`, `receipts/failed_preflight/`, `PREDECESSOR.json`:
  retained first preflight failure and zero-numerical-launch reconciliation. The
  `python_environment.json` probe was taken after that failed preflight and copied
  into the successful scratch; its `preflight_exit: 1` refers to its predecessor.
- `driver_tests.json`: final four safety checks, exact command and exit 0.
  `receipts/final_reconciliation.json`: preserved input identities and final counts.

Reproduction must use another new scratch and a separately authorized launch. This
one-shot execution directory cannot be resumed or overwritten: existing start,
output, completion and failure receipts are deliberately exclusive. No new
third-party dependency was added; the driver/tests use Python's standard library.

The first full staged whitespace check flagged RELION-emitted trailing spaces in
the raw STAR/log receipts and one extra blank line in the new README. The README
was corrected; the five affected raw receipts were packaged with deterministic
lossless gzip, never trimmed or numerically changed. Decompression reproduces every
original remote digest. The final full C0-to-pilot whitespace check passes. This is
artifact packaging, with no numerical tolerance, protocol or gate change.
