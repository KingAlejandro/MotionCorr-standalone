# S1.1/S1.2: frozen RC0 breadth and longevity sweep

Measured on 2026-10-19 at frozen source F, `6d68e2d6ec45c37b75fd0f4aaff8272f192b7029`. This supersedes the 16-movie first pass in this PR. Tracking: [#238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238). Product source, defaults and acceptance gates are unchanged.

## Current result

The primary sample contains **114 byte-distinct movies: 24 tutorial movies and 10 in each of the other nine #186 families**, each at 5×5 (config L) and 3×3. There are 228 primary pairs and 251 completed F pairs including venue repetitions. Each CPU/CUDA pair uses the same input, options and host. [per_movie.csv](per_movie.csv) identifies the primary sample, venue, host, allocation, CPU mask, GPU UUID, input hash, patch rows/counts/differing sets, relative RMSE and backend metrics; complete comparator reports remain directly readable under [evidence](evidence).

**One retained native failure:** the SCARF 40 GB A100 ran out of memory on the first 10441 movie at 3×3 (CUDA exit 1, `cuda_alignpatch.cu:1121`, error 2). Its CPU arm exited 0 with 9 converged patches and 450 local-shift rows. CUDA convergence and relative RMSE are **UNRUN**, not zero. The same movie and nine additional 10441 movies completed both grids on the 80 GB 4GPUs venue. See [failed_attempts.csv](failed_attempts.csv). The evidence validator deliberately exits 1 for the retained native failure; completed-pair, coverage and control checks are reported separately in [validation.json](validation.json).

For incidence, **large S1 disagreement** means relative RMSE ≥0.1. This descriptive screen continues the first-pass convention for SUPPORT §0's large disagreement; it is not an acceptance gate. The frozen `compare_motioncorr.py --gate backend` result is retained separately. A screen-negative row can still fail that gate.

| family | movies | large S1 5×5 | large S1 3×3 | backend FAIL 5×5 / 3×3 | primary venue |
|---|---:|---:|---:|---:|---|
| e10028 | 10 | 0/10 | 0/10 | 10 / 10 | 4GPUs |
| e10164 | 10 | 0/10 | 0/10 | 6 / 8 | 4GPUs, SCARF |
| e10216 | 10 | 7/10 | 5/10 | 10 / 10 | SCARF |
| e10361 | 10 | 0/10 | 0/10 | 10 / 10 | 4GPUs |
| e10441 | 10 | 0/10 | 0/10 | 4 / 4 | 4GPUs |
| e10474f3 | 10 | 4/10 | 1/10 | 6 / 9 | SCARF |
| e10474f4 | 10 | 0/10 | 0/10 | 5 / 6 | 4GPUs, SCARF |
| e10641 | 10 | 5/10 | 0/10 | 8 / 6 | 4GPUs |
| e12963 | 10 | 7/10 | 3/10 | 10 / 10 | 4GPUs |
| tutorial | 24 | 0/24 | 0/24 | 0 / 0 | 4GPUs |

At 5×5, 20/23 screen-positive pairs have a non-converging patch on at least one backend and 14/23 have different accepted sets. The screen is positive in 20/31 pairs with non-convergence and 3/83 without it. At 3×3, 5/9 screen-positive pairs have a non-converging patch on at least one backend and 2/9 have different accepted sets. The screen is positive in 5/14 pairs with non-convergence and 4/100 without it. Non-convergence is associated with incidence, but it is neither necessary nor sufficient in this sample.

The first 10216 3×3 movie has all nine patches accepted on both backends yet relative RMSE 0.196182. The second original corpus movie, `e10216-01` (input SHA beginning `c3b841e9`), has **zero accepted patches on both backends at both grids**, relative RMSE 1.248469 and global-coordinate RMS difference 44.6509 px (maximum 168.4257 px); it reproduces on both venues. Large disagreements with matching accepted sets, including global-trajectory failures, must not all be attributed to a patch acceptance flip. These are associations in this sample, not a universal classifier or a causal mechanism. Mechanism work is tracked separately in [PR #250](https://github.com/KingAlejandro/MotionCorr-standalone/pull/250); this sweep did not independently repeat it.

## Longevity and controls

**28/28 older CPU-versus-F controls are identical**, each against F on the same venue before interpreting the corresponding old CUDA probe. Ten older SHAs were run, all older than `116eb04a`. Full revisions and source archive hashes are in [preparation/revisions.json](preparation/revisions.json) and [preparation/local-archives.sha256](preparation/local-archives.sha256); [longevity.csv](longevity.csv) contains every probe, backend verdict, relative RMSE, patch count/set and required CPU control.

Rounded values are shown below; individual venue probes retain full precision in the CSV.

| older SHA | 10216 5×5 relative RMSE | 10216 3×3 | Falcon 3 5×5 | identical CPU controls |
|---|---:|---:|---:|---:|
| `e875d5fe` | 0.021936 | 0.555101 | 0.592989 | 5/5 |
| `8477dc1b` | 0.021936 | 0.555101 | UNRUN | 2/2 |
| `f6c41e24` | 0.018004 | 0.185328 | 0.593955 | 5/5 |
| `ef7e4c0a` | 0.018128 | 0.185341 | UNRUN | 2/2 |
| `58fd513a` | 0.434362 | UNRUN | UNRUN | 1/1 |
| `2368063f` | 0.434362 | 0.196182 | UNRUN | 2/2 |
| `c24ae8c2` | 0.430011 | 0.196361 | UNRUN | 2/2 |
| `2ff18e93` | 0.434362 | 0.196182 | 0.599858 | 3/3 |
| `c499b1d3` | 0.434362 | 0.196182 | 0.599858 | 3/3 |
| `6b6adf44` | 0.434362 | 0.196182 | 0.599858 | 3/3 |

For 10216 5×5, the native sampled interval from screen-negative `ef7e4c0a` (0.018128) to screen-positive `58fd513a` (0.434362) narrows the earlier interval. **Both endpoints still fail the unchanged backend gate.** The parent of `58fd513a` differs from `ef7e4c0a` only in a default CMake CUDA-architecture setting; both measured CUDA builds explicitly set architecture 80. That parent comparison is source evidence, not a native parent run or a causal attribution; see [preparation/FFT-boundary-source.txt](preparation/FFT-boundary-source.txt).

10216 3×3 and Falcon 3 5×5 are already screen-positive at the earliest native revision tested, `e875d5fe` (2026-09-24). That build dispatches CUDA global alignment and CPU local alignment; native CUDA patch alignment starts in later probes (dispatch evidence: [preparation/dispatch-history.txt](preparation/dispatch-history.txt)). There is no single sampled introduction shared by these cases, and no continuous per-commit proof. `d01f512d` compiled successfully for CPU/CUDA but was not run, so this is not an earliest-buildable-runtime claim.

Older CPU identity covers exact MRC core bytes 0–223, payload, extended header and per-movie STAR, plus the frozen `--gate exact --require-complete-coverage` comparator with timestamp-normalized MRC labels. Unmasked label timestamps differ. Logs, plots, PDFs and joint-output inventory are outside the control; this is same-backend product identity, not scientific equivalence.

**8/8 cross-venue identity checks pass** on the common 10216 first movie at 5×5: SCARF CPU versus cpu64 CPU, and SCARF CUDA versus 4GPUs CUDA, for each of four SCARF allocations. Complete product-region hashes and the precise scope are in [preparation/cross-venue/controls.json](preparation/cross-venue/controls.json). These controls do not generalize identity to other inputs. Every numerical backend pair in this sweep still remains on one host.

## Selection, venue and provenance

- All 52 initially staged movies completed both grids after resumption. **Original PID 1831303 did not finish:** its queued arm received SIGTERM during lock/affinity migration and the controller raised `CalledProcessError`; the original controller numeric exit was not retained. Its log and queued-restart record are retained. The resumed pass has `staged-resume.exit=0`. No native payload was signalled. The routed expansion and final 10441 pass also exited 0.
- All 24 available tutorial movies were used. Other families retain the original staged corpus movies and add spaced directory selections to reach 10 each. Every family had at least ten distinct inputs available; none requires a smaller-denominator exception. This selection is not a whole-accession census. Sixty-two added movies were fetched with free-space checks under `/mnt/clathrin/alex-motioncorr-s1/sweep/data`; URLs, argv, exits, headers, hashes and selection are in [evidence/acquisition](evidence/acquisition). SCARF staging independently verifies those hashes in node-local `/tmp`, including reuse of verified cached files. [evidence/manifest.json](evidence/manifest.json) records all 114 inputs and gain identities; original corpus hashes match.
- Primary 10216/Falcon 3 pairs use SCARF; 10441, 10641, 12963, 10028, 10361 and tutorial use 4GPUs. Falcon 4 uses two 4GPUs movies plus eight SCARF movies; 10164 uses one plus nine. Whole pairs are selected once per movie, never cross-venue arms. Venue repetitions and per-venue incidence remain in [family_summary.json](family_summary.json); [preparation/venue_assignment.json](preparation/venue_assignment.json) records the routing.
- 4GPUs uses the rehashed QF F binaries: CPU `43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42`, CUDA+nvCOMP `2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3`. Both arms use `taskset -c 96-103` and `--j 8`. Every GPU arm takes its physical-GPU correctness lock and checks the benchmark lock; available GPUs are selected by UUID, with process-descendant UUID witnesses. Actual selections are recorded per row. Early records omit hostname and runner hash; the table explicitly identifies host evidence from scratch paths plus the collection-host inventory instead of inventing per-arm observations.
- SCARF F and older CPU/CUDA builds are separate Release builds from `git archive`; F CUDA enables nvCOMP. Builds ran on the CPU `scarf` partition with configure/build exit statuses checked. GPU runs use non-exclusive `gpu-devel` allocations, one GPU, 8 CPUs and 48 GB RAM, excluding the four known-bad nodes; observed successful node is `gn0005`, with its 40 GB A100, distinct from the 4GPUs 80 GB model. `TMPDIR` and movies/products use node-local `/tmp`. Scripts were uploaded separately and checksum-verified before launch; retained script hashes identify immutable versions. cpu64's F CPU control uses its own Release binary, 8-CPU affinity and `motioncorr-cpu64-bench.lock`. Hardware and runtime versions are retained in run/host/build records and [preparation/runtime_versions.json](preparation/runtime_versions.json).
- Recipe options remain `--use_own --dose_weighting --bfactor 150 --seed 1 --j 8`, the family gain/dose/EER parameters, and the explicit patch grid. Relative `Movies/...` input paths keep products under each run's `out/Movies/...`. Legacy builds omit unsupported ingest/expected-frame flags; decoded STAR row counts remain checked. Corpus dose/voltage placeholders are not scientifically validated recipes.
- The frozen comparator hash is `cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b`. The first 32 comparison records selected its QF path but lacked a captured hash. Rechecking retained products with the frozen hashed comparator reproduced all 32 gate reports and metrics after path normalization; original reports and [evidence/comparator-rechecks/equivalence.json](evidence/comparator-rechecks/equivalence.json) are retained.
- Setup/transport/controller failures are retained separately from native failures: the initial fetch bookkeeping exception, obsolete UUID-probe setup, rejected second GPU submissions, and a later Falcon 4 download/curl-56 failure. The recovered SCARF campaign step `3645685.0` completed with Slurm exit `0:0`; its login-side launcher disappeared without writing exit/release sentinels. After checking all 34 pairs and successful non-extern steps, the idle allocation was released explicitly (exit 0). The missing original launcher status and recovery command are retained in `evidence/scarf/launch-b5/completion-recovery.json`. A recovery step against an expired allocation failed before executing its script. These attempts are not counted as completed pairs. Their logs/exits and the historical controller sources remain in evidence and [preparation/controller_sources](preparation/controller_sources).

## Reproduction and evidence layout

The authoritative commands and exit statuses are the per-arm `run.json`, comparator argv/reports, build commands/status/cache/flags/hash files, acquisition records and Slurm accounting. Helpers live only under this evidence directory. `sweep.py` and `scarf_sweep_v1.py` implement checked single arms; campaign helpers select the recorded manifest and explicit venues. Archived operational scripts include fixed historical job IDs and are evidence, not launch instructions. Use a fresh writable scratch tree and the recorded source/input hashes for a new campaign; runners refuse to overwrite native run directories.

Generate the review tables from the retained evidence, from this directory:

```sh
python3 tools/summarize.py evidence
python3 tools/summarize_longevity.py evidence
python3 tools/validate_evidence.py evidence --require-complete
```

The last command is expected to exit 1 for the retained SCARF native failure. Check the individual validity, breadth and control fields in `validation.json`. Per-run STAR/log/witness/time files are compressed into `evidence/raw-*.tar.gz`, indexed by member SHA-256 in `evidence/raw_files.json`; `pack_raw.py` verifies contents before moving individual raw files into those archives. Tables generated before and after packaging are byte-identical. JSON comparison/run records remain directly readable. No MRC or executable is committed. Time-log fields are retained as required comparator evidence; no timing claim is made.

Not run here: the complete EMPIAR populations; exhaustive per-commit history or native `d01f512d`; older-SHA probes beyond the selected 10216/Falcon 3 movies; independent S1.3 mechanism experiments or S1.4 downstream CTF/FSC/B-factor validation. No support, gate or default change is proposed.
