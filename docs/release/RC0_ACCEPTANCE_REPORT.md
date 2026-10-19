# RC0 acceptance report (DRAFT SKELETON, partly filled; stays DRAFT until the freeze)

> **EVALUATION RC0, not a stable release** (maintainer decision D7, [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198)). No
> unrestricted or stable support is claimed for CUDA local alignment (known limitation **S1**, PROVISIONAL), and no scientific equivalence or
> preference for either backend is established.

Status: **draft skeleton, revision 9** (QF results on F = `6d68e2d6` filled; revision 8 was after R-REL round 2, R-REL-B, the R-QA2 evidence audits of #209 and #208, the 11:54Z review of revision 6 and R-REL round 4). Filled from the qualification PRs #209 (Q1), #204 (raw MRC), #208 (EER), #207 (resident retry) and #212 (S1), all at
main `1db86902`, plus the merges listed in section 1 and the historical pre-freeze native check of main `cb3699ac`, all reported on #198. F = `6d68e2d6`; the QF results on F (W-QF, 2026-10-19) are filled from `docs/rc0/qf/run_6d68e2d6/`. A planned or unrun check is **UNRUN**, never PASS.
Evidence cited here comes from those PRs and #198 and was not re-run by the author of this report; the PRs are open, so their claims are as reported
there. Rows labelled "reference" come from earlier evidence at an older SHA and are not RC0 results.

## 1. Frozen SHA

| Field | Value |
|---|---|
| Frozen source SHA **F** | **`6d68e2d6ec45c37b75fd0f4aaff8272f192b7029`** (#201 merge; same source as the #228 merge `e3871ca2`; D4 = a, #198 comment 6256406171). Full QF on F: `docs/rc0/qf/run_6d68e2d6/` |
| Evidence commits and tag target | later **docs-only** commits under `docs/rc0` and `docs/release` only; the maintainer names the tag target T explicitly. Source-identity check, `git diff F T -- . ':!docs/rc0' ':!docs/release'` must be empty: **pending the tag target T** (`RELEASE_CHECKLIST.md` §10) |
| Base for this draft | main `e3871ca2` (= `1db86902` + #200 F1, #210 TST1, #205 F3/F3b `f67a5866`, #199 D1/D2 record `a1ab83f2`, #217 T3 `483e881d`, #220 C5 `71ab841e`, #223 `ecb7d7f7`, #202 `687ffc17`, #203 `5e12fecf`, #224 `1afa03b5`, #231 D10 `55e30154`, #230 D13 `cb3699ac`, #233 QF runbook `80cef8c0`, #228 D11 `e3871ca2`); per-item qualification evidence is at the SHAs stated below (mostly `1db86902`). Citations in the release documents are at `e3871ca2` |
| Register items merged | C1 #178, C2 #187, C3 #188, C4 #185 (`d7171b81`), E1 #196 (`4b849165`), M1 #195 (`faf5fbdf`), R1 #197 (`0ac2726a`), F1 #200 (`ea86fc90`), TST1 #210 (`2b3c74b3`), C5 #220 (`71ab841e`), #223 (`ecb7d7f7`), #202 (`687ffc17`), #203 (`5e12fecf`), #224 QF runbook (`1afa03b5`), **D10 #231 (`55e30154`)**, **D13 #230 (`cb3699ac`)**, **D11 #228 (`e3871ca2`)**, #233 QF runbook for D10/D11/D13 (`80cef8c0`); merge SHAs of C1-C3 are in the #198 register |
| Pending, not merged | none of the RC0 fixes (C5, D10, D11, D13) remains unmerged. **#201 itself** (these documents) merges before F per D4. #226 D2 and D3 stay deferred until after RC0 (#226 stays open) |
| Parked or closed, not in RC0 | C7 #183 / #219 (parked); C6 #181 and #182 (closed, no-go); device EER renderer #193 / #211 E2 (parked post-RC0, D9) |
| Excluded | T1 #138 (NO-GO for RC0, parked [PR #206](https://github.com/KingAlejandro/MotionCorr-standalone/pull/206)); L1 #141/#152 nvTIFF (NO-GO, not used); C8 #184 and C9 #177/#182 (NO-GO); #149 deferred; TST2 genuine device poisoning (post-RC0, #213); #214 (compressed-MRC exit status), #215 (nvCOMP file identity) post-RC0 |
| CI run on the frozen head | push CI on F, run 39175914447: **success** (Linux CTest and CUDA compile-only; compile-only CUDA is not native evidence). (Pre-freeze, cited only: push CI on `cb3699ac`, run 39122394239, passed.) |
| Decisions recorded | D1: option 1, documented trusted-input precondition (no code change); D2: interim policy A (optional, default-off, not vendored, no project-distributed linked binaries); T3: checked-arithmetic hardening for RC0; D5: F3/F3b fail-closed approved, F4 a documented limitation; D6: preserve the EER skip-and-warn recovery; D7: evaluation RC0 with S1 provisional; **D10: fix host EER memory safety before freeze (done, #231)**; **D11: fix the stale CUDA error before freeze (done, #228)**; **D12: licence and notices review (#18) deferred**; **D13: fix the report-plot `label2offset[-1]` read before freeze (done, #230)**; **D14: performance rule, upper bound of the median paired difference at most +0.5 %, plus the 2026-10-18 addenda**. D3 (each merge) is per PR; **D4 = option (a)**: freeze a `main` commit F, push CI and full QF on F; F = `6d68e2d6` |

### 1a. Qualification state: completed versus pending

**Completed** (per item, pre-freeze, on the stated SHAs; as reported on #198 and the cited PRs, not re-run on the frozen SHA):

| Item | SHA / PR | Result as reported |
|---|---|---|
| Q1 baseline qualification | `1db86902`, PR #209 | CTest 58/59 CPU (ProfilingKit rerun passed), 89/89 CUDA, 92/92 CUDA+nvCOMP; 14/14 same-backend products identical; #178 checks; 1/2/4-worker endpoint 6/6 (section 2a) |
| M1 raw-integer MRC staging | `1db86902`, PR #204 | valid input identical across routes; refusals 15/15 |
| E1 EER compact route | `1db86902`, PR #208 | 31 CUDA + 3 CPU complete non-PDF tree comparisons; overflow guard discriminates |
| R1 resident patch retry | `1db86902`, PR #207 | success and injected-failure cases identical to pre-#197 |
| S1 diagnosis | `1db86902`, PR #212 | CPU versus CUDA local-alignment divergence localised; bounded statement in `SUPPORT.md` §0 |
| F3/F3b fail-closed reads | #205 merged `f67a5866` | truncated raw MRC movie, gain and defect map fail with "is truncated or unreadable"; valid input byte-identical; required tests `TruncatedMrcMovie`, `TruncatedGainDefect` |
| T3 checked arithmetic | #217 merged `483e881d` | overflow or unreadable strip offset gives a named decline; reported native GPU run: tutorial x 24 `nvcomp` identical, crafted files decline; independent review confirmed (#198 register T3) |
| QM smaller-GPU memory admission | `483e881d`, PR #225 (audited by R-QM) | 162 runs on one A100 80 GB with a VRAM balloon: 0 crashes, 0 hangs, 0 wrong outputs; every completed constrained run identical to its unconstrained run; every failure clean (no products); free-VRAM floors per geometry, a non-monotone band below the full-speed floor, and three defects (#226): **D1 (stale CUDA error after a handled OOM) was fixed before freeze by D11, [PR #228](https://github.com/KingAlejandro/MotionCorr-standalone/pull/228), merged `e3871ca2` (see the D11 row below)**; D2 and D3 are deferred until after RC0; documented limits (balloon on one card, one movie per family, hosts below about 36 GiB RAM untested) in `SUPPORT.md` §8 |
| C5 measurement | PR #218 | whole-job reduction on x86-64 cpu64: tutorial -3.28 %, EMPIAR-10474 Falcon 4 -3.97 % resolved beyond the null; EMPIAR-10216 unresolved; products identical |
| C5 CPU dose symmetry, merged | #220 merged `71ab841e` | lean port of #179 under the qualified-toolchain contract (`SUPPORT.md` §9); `CpuDoseSymmetry` and `CpuDoseSymmetryBase` are in the required collection; the contract text was re-checked against the merged source |
| D10 host EER memory safety | #231 merged `55e30154` (tested source `97fb9fda`) | **bounded** result: 37 damaged-input fixtures all controlled with 0 sanitizer reports under ASan+UBSan on the fix (35 of 37 produced reports on main); borrowed-neighbour cases for three codecs; MRC header cases; 28/28 valid groupings clean under ASan; valid-input products byte-identical, main `71ab841e` versus fix, 24/24 (CPU and CUDA); D14 timing passed (CPU whole job upper bounds -0.07 % and +0.19 %, accepted sequential-null deviation; CUDA compact +0.30 %). Container damage fails the movie; the D6 skip-and-warn and E-1 behaviours are unchanged. Not a claim about arbitrary damaged input (`SUPPORT.md` §2). Record: `docs/rc0/eer_memory_safety/` |
| D13 report-plot undefined axis | #230 merged `cb3699ac` (code `b82d25f4`) | `addToCPlot2D` no longer indexes `label2offset[-1]`; `ReportPlotUndefinedAxis` added; native CTest 73/73, 106/106, 109/109 on the fix over main `1afa03b5`; ASan negative and positive controls; CPU and nvCOMP identity; D14 CPU timing passed (definitive upper bound +0.297 %, nulls sequential and accepted; supplementary interleaved run +0.261 %). Record: `docs/rc0/report_plot_undefined_axis/` |
| QF runbook and rehearsal | #224 merged `1afa03b5`; update #233 merged `80cef8c0` | rehearsal on `483e881d`, audited; the update for D10/D11/D13 is final: items 15, 16 and 17, `grade_ctest.py` (no automatic rerun discharge: the operator dispositions a load-sensitive failure by hand in the D4 record) and `asan_eer.sh`. The runbook has not been executed on F |
| D11 stale CUDA error after a handled OOM (#226 D1) | #228 merged `e3871ca2` (pinned to reviewed head `6650120c`), 4GPUs GPU3 | correctness accepted; a movie that fails with a handled device OOM no longer degrades or refuses the next movie (strict-product test `CudaStaleErrorAfterOom`; three-movie balloon jobs; fatal handling unchanged; no genuine sticky-error control, TST2). **D14 final PASS on all three workloads**: tutL (upper bound +0.07 %) from the earlier definitive 4GPUs run, whose PASS stands; tutG (+0.110 %) and e10216L (+0.114 %) from the single attended confirmatory campaign, which supersedes their earlier UNRESOLVED results (+0.63 %, +0.70 %). The timing measured #228's own code (`0b11f6a8`/`78aae2d3`), **not the composition with main**. Evidence `docs/rc0/stale_cuda_oom/` (`raw/perf/confirmatory-4gpus/`); independent R-D11 evidence review: [#228 comment](https://github.com/KingAlejandro/MotionCorr-standalone/pull/228#issuecomment-6256272293) |
| **Historical pre-freeze native check of main `cb3699ac` (before D11)** (cited from [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198#issuecomment-6249369756), not re-run here) | `cb3699ac`, 4GPUs, GPU0 and GPU1 pinned by UUID | CTest CPU 74/74, CUDA 107/107, CUDA+nvCOMP 110/110; collection checks rc 0; push CI run 39122394239 passed. **Not the frozen-SHA result.** Expected counts at F, with `CudaStaleErrorAfterOom`: CPU 74, CUDA 108, CUDA+nvCOMP 111; **observed on F at QF: 74/108/111** |

**QF on the frozen SHA F = `6d68e2d6`** (W-QF, 4GPUs, 2026-10-19; report and D4 record `docs/rc0/qf/run_6d68e2d6/`):

| Item | Result on F |
|---|---|
| CTest on CPU, CUDA, CUDA+nvCOMP (QF items 1-3) | **PASS**: 74/74, 108/108, 111/111, 0 failed, skipped or not run; collection validator and `test_ci_fail_closed` PASS; no load-sensitive rerun needed |
| Route and product campaign (item 5) and CPU identity vs Q1 (item 6) | **PASS**: 14/14 (7 families x G/L), auto/compact/float identical, compact refused only on 10028 with nothing published; CPU products identical to Q1 `1db86902` 14/14. CPU-vs-CUDA backend gate recorded, not graded |
| #178 CPU unweighted path (item 7) | **PASS**: 6/6 identical to `d7171b81`; the injected recoverable `cudaMalloc` failure (ordinal 16) reaches the CPU line and is identical |
| Multi-GPU 1/2/4 workers (item 8) | **PASS**: G/L x w1/w2/w4 and mixed w1/w2, every dataset contract PASS, distinct sampled UUIDs, products identical across worker counts and to one process |
| #123 adapted compact-ingest matrix (item 9) | **PASS** on both CUDA executables: 16/16 rows, 28/28 arms witnessed, gain control differs |
| `CpuDoseSymmetry` and `CpuDoseSymmetryBase` (item 10) | **PASS** in CPU, CUDA and CUDA+nvCOMP; AUTO selects the symmetric path (x86-64 GCC 13.3.0, no FMA flags) |
| EER #208 replay (item 11); resident retry #207 (item 12) | **PASS**: 41/41 cases, 4/4 negative controls, guard-removed control o1n/o5n; retry single-GPU 4/4 (41/30/9/25) and dataset |
| Raw integer MRC #204 harness (item 13) | **FAIL under its frozen criterion, dispositioned**: one case, big-endian mode 0 with nx = 128, is now processed on every route because #231 fixed the byte-swap test (F5); every other record matched #204, 6 KNOWN-F4 as expected. Supplementary run: products identical across CUDA routes and to the little-endian input |
| `EerMemorySafety` (item 15), `ReportPlotUndefinedAxis` (item 16), `InputFormats`, `CutDownMovie` on the frozen SHA | **PASS** in all three builds; `EerMemorySafety` also passes under ASan+UBSan on F, and F's decoder sources equal #231's tested `97fb9fda` |
| `CudaStaleErrorAfterOom` (D11, item 17) and expected counts CPU 74 / CUDA 108 / CUDA+nvCOMP 111 | **PASS**: `with_d11`; the test passes in both CUDA builds and the validator enforces `CUDA_REQUIRED_TESTS`; counts observed 74/108/111 |
| macOS statement | made: "builds and runs; not qualified; known CPU CTest differences" (see section 2); **rerun on F (QF item 14, not graded): 74 collected, 72 passed, `SyntheticRegression` failed (#222), `NativeMovieStaging` skipped; `MultiGpuScheduling` passes** |
| D12 licence and notices review (#18) | **deferred** (maintainer 2026-10-17); not an RC0 freeze blocker |

## 2. Supported and unsupported configurations

Classes follow `SUPPORT.md` §1; evidence is at `1db86902` unless stated. "QF" = re-verification on the frozen SHA F = `6d68e2d6` (`docs/rc0/qf/run_6d68e2d6/`).

| Configuration | Class | Evidence at `1db86902` | QF |
|---|---|---|---|
| CPU `--use_own`, Release, Linux x86_64 | supported (intended) | CPU CTest 58/59 (`ProfilingKit` 30 s load timeout, passed on rerun); CPU build route-invariance runs 14/14 exit 0 (#209) | CTest 74/74; CPU products identical to Q1 `1db86902` 14/14 |
| CPU `--use_own`, Release, macOS arm64 | **builds and runs; not qualified; known CPU CTest differences** | local author runs at `1db86902`, the merge with `2b3c74b3` (60 collected, 57 passed) and the merge with `483e881d` (68 collected, 65 passed): 2 failed, 1 skipped (`NativeMovieStaging`); **revision-7 run at the merge head `49efcd43` (main `cb3699ac` + docs): 74 collected, 72 passed, 1 failed (`SyntheticRegression`), 1 skipped (`NativeMovieStaging`)**, binary `666a3d51...9518d`, `pbzip2` absent so those `InputFormats` cases are waived as UNRUN. `SyntheticRegression` fails because libc `rand()` differs from glibc, so the same `--seed` gives different hot-pixel replacement and output bytes on macOS and glibc Linux (#222); `MultiGpuScheduling` failed from a test-harness `/var` symlink issue and **passes since PR #223 merged** | not qualified; item 14 rerun on F: 74 collected, 72 passed, 1 failed (`SyntheticRegression`), 1 skipped |
| CUDA, one device, **no nvCOMP** | supported for evaluation; **local alignment: S1, no unrestricted claim** | **CTest 89/89 only** (0 skipped, #209). **No real-data campaign was run on a no-nvCOMP CUDA binary**: the route-invariance and #178 checks below used the CUDA+nvCOMP binary | CTest 108/108; #123 matrix 16/16; still no real-data campaign on the no-nvCOMP binary |
| CUDA, one device, **with nvCOMP** (`USE_NVCOMP=ON`) | experimental; trusted-input precondition (D1) | CTest 92/92, 0 skipped (#209). **Same-backend route comparisons: 14/14** `--ingest auto` vs `--ingest float` on 7 families x G/L, run with this binary (tutorial auto route `nvcomp`; 10361, 10474 Falcon 3, 12963, 10216, 10164 `compact`; 10028 `float`): identical normalised MRC (label, extended header, payload) and STAR products. This is a products-only identity: complete-tree comparison needs the disclosed route-log allowances (without them only 10028 G/L pass; the four declared prefixes pass 10/14; the four signed-MRC cases, 10216 and 10164 G/L, are manually inspected exceptions needing `Released native int`). **#178 checks (this binary): six CPU-backend checks (CUDA-linked binaries run WITHOUT `--gpu`) and one injected recoverable CUDA-to-CPU fallback under `--gpu` (injected `cudaMalloc` failure #16), all matching the pre-#178 build `d7171b81`; this is not real out-of-memory or device-poisoning evidence; frozen-SHA rerun pending** | CTest 111/111; campaign 14/14 route-identical; #178 6/6 plus the injected fallback; #123 matrix 16/16 |
| Multi-GPU via `run_dataset.py` | supported for evaluation | 1/2/4 workers x 24 tutorial movies, G and L, 6/6 endpoint PASS; every launcher worker physically witnessed on its intended, distinct GPU UUID; normalised products identical across worker counts and to a single process (labels and extended headers included, only the writer timestamp masked); real-Ghostscript 30-page `logfile.pdf` (PDF content is inventoried, not compared); the mixed tutorial + 10641 + EER 1- vs 2-worker case also matched (#209). Not run: launcher failure/resume injection | item 8 PASS (G/L x 1/2/4 workers, mixed 1/2); launcher failure/resume injection still not run |
| Raw integer MRC modes 0/1/6 (compact route, #195) | supported on valid input | real 10164/10216/10028 G and L, auto vs float 6/6 identical; synthetic modes 0/1/6/2/12/101 28/28; compressed xz/zstd 16/16 on the float route; pinned-compact refusals 15/15; modes 3/4 refuse (#204, evidence audit corrected @ `5944617b`) | item 13 FAIL under its frozen criterion on one case (big-endian mode 0, nx = 128, now processed after #231), dispositioned; all other records as #204 |
| Truncated raw MRC, gain, defect map | **fails closed** (F3/F3b, #205 merged `f67a5866`): movie-level rejection, message "is truncated or unreadable"; compressed MRC unchanged (F4) | #205 tests `TruncatedMrcMovie`, `TruncatedGainDefect` (+ `Cuda` variants); valid input byte-identical | PASS: the four F3/F3b tests in their builds |
| Compressed MRC (`.bz2`/`.xz`/`.zst`) | supported on valid, **independently validated** input (F4: decoder exit status unchecked) | #204 (native `pbzip2` UNRUN; `.bz2` tested through a `bzip2 -cd` shim) | item 13 compressed and KNOWN-F4 records as #204 |
| EER compact route (#196) | supported on valid input; `--expected_frames` recommended (D6); **damaged EER input: bounded D10 behaviour, not a general safety claim** (a damaged container fails the movie; an overrunning fraction takes the D6 skip-and-warn path; whole-IFD truncation is a shorter movie, E-1; `SUPPORT.md` §2) | 31 CUDA auto/float cases and 3 CPU `0ac2726a`/`1db86902` cases passed the complete **non-PDF** output-tree comparator with the declared timestamp, output-root, timing-line and route-log normalisations (MRC labels, extended headers and payloads included); **three of the 31 CUDA cases selected `float` in both arms** (overflow controls), so they are not compact executions; all seven inventoried corpus EER files are tag 65001 at 4096 x 4096; real 65000, 65002 and 2K files were not run (#208, R-QA2) | item 11 PASS 41/41 plus guard-removed control; item 15 PASS (`EerMemorySafety`, also under ASan+UBSan) |
| Resident patch retry (#197) | supported | success path 10641 41/50 and 10216 30/50 patches retried, identical to pre-#197 and to `1db86902` with #197 reverted (28 comparisons); injected recoverable failure identical, injected fatal failure refuses with no publication; 1- vs 2-worker identical (#207) | item 12 PASS (single GPU 4/4, dataset) |
| **CUDA local alignment vs CPU** | **S1, PROVISIONAL**: relative RMSE 0.43-0.60 on 10216, 10474 Falcon 3, 12963 (5 x 5 patches) | #209 backend diagnostic, #212 diagnosis | heavy testing is the priority after freeze |
| Input rows R1-R12 | per `RELEASE_CHECKLIST.md` §7 | partly covered by #204, #208, #209 | items 5, 9, 11 and 13 on F (`RELEASE_CHECKLIST.md` §9) |
| Unsupported (named in `SUPPORT.md` §1) | unsupported | n/a | n/a |

### 2a. Qualification summary at `1db86902` (wording permitted by the R-QA2 audits)

The audits are [#209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209#pullrequestreview-5554715457) and
[#208](https://github.com/KingAlejandro/MotionCorr-standalone/pull/208#pullrequestreview-5554719869) (read-only, bounded to retained records).

> **#209 (baseline).** At baseline 1db86902 on 4GPUs, CPU CTest passed 58/59 with ProfilingKit passing on selective rerun; CUDA and CUDA+nvCOMP passed 89/89 and 92/92. Fourteen same-backend auto/float comparisons had identical normalized MRC/STAR products; complete-tree results require the disclosed route-log allowances, including four manually inspected signed-MRC exceptions. Six CPU-backend checks of CUDA-linked binaries and one injected recoverable CUDA-to-CPU fallback matched d7171b81 under the stated identity comparator. Tutorial 1/2/4-worker endpoints passed 6/6 and normalized products matched; the mixed 1/2-worker case also matched. MRC labels and extended headers were checked, with only the writer timestamp masked. Original campaign GPU UUIDs were pinned but not physically witnessed; three later runs and all launcher workers were witnessed. CPU–CUDA agreement limitations remain diagnostic. Qualification of the final frozen composition is pending.

> **#208 (EER).** At baseline 1db86902, 31 CUDA auto/float cases and three CPU 0ac2726a/1db86902 cases passed the complete non-PDF output-tree comparator with the declared timestamp, output-root, timing-line and route-log normalizations. MRC labels, extended headers and payloads were included. Three of the CUDA cases were float-fallback controls. Synthetic overflow boundaries and a guard-removed mutant discriminated the uint16 guard; pinned compact refused overflow-ineligible input. The seven inventoried corpus EERs were all tag 65001. Single-sample real-file measurements showed approximately 34–47% lower host RSS at upsampling 1/2/3, no saving in the tested −1 cases, and Falcon4 upsampling 2 completed at 79522 MiB sampled process VRAM with 21547 versus 40171 MiB host RSS. Damaged-input outcomes remain inherited limitations, including silent acceptance or skip-and-warn publication. Malformed-input memory safety and OOM behavior are not established. Final frozen-composition qualification is pending.

Details the audits require next to those figures:

- **GPU witnessing.** The 28 original CUDA campaign runs and the injected fallback pair were UUID-pinned (`CUDA_VISIBLE_DEVICES`) but **not physically witnessed** (no process-id hit in the sampler; the campaign has 28 CUDA and 14 CPU runs). Three later runs (12963 L, 10361 G, tutorial L) and all launcher workers were witnessed. The later runs do not retroactively witness the originals.
- **The 79,522 MiB** is **sampled NVML process VRAM, one run per arm**, on an 81,920 MiB card (about 2.3 GiB remained). It is not an allocation upper bound or a guaranteed fit, and the out-of-memory path was not exercised.
- **"34/34"** is defined above: complete non-PDF trees under the declared normalisation. Damaged-input batches were **not** strict-tree comparisons (16 hex characters of MRC payload hash and STAR sizes only).
- **#209's 14/14** is a products-only identity; the PASS* signed-MRC cases are inspected exceptions, not a recorded green rerun with the extra prefix.
- **ProfilingKit** passed on a selective rerun; there is no 59/59 single full-suite CPU pass.

**Must NOT be claimed (R-QA2):** 59/59 in one CPU suite; 14/14 unmodified all-files or PDF identity; six actual CUDA-fallback injections; every original GPU run physically witnessed; real OOM recovery or device poisoning; general CPU-CUDA local or scientific equivalence; speed or scaling; literal 34/34 byte-identical all-file or PDF trees; 31 compact-route executions; complete identity of damaged-input MRC/STAR trees; malformed-EER fail-closed handling or memory safety (an R-QA2 limit at `1db86902`; after #231 only the bounded D10 statement in section 3 may be made, and never a claim for arbitrary damaged input); real 65000/65002/2K/legacy EER validation; statistically established savings or speedups, or a guaranteed fit on smaller GPUs; qualification of `2b3c74b3` or of the final RC0.

## 3. Known limitations

Carry over from `SUPPORT.md` §0, §5, §6 and §8, updated at freeze:

- **S1 (PROVISIONAL, first post-freeze priority):** the statement in `SUPPORT.md` §0, verbatim; evidence PRs #212 and #209;
- the `0.001` relative-RMSE diagnostic fails for CUDA versus CPU in all 14 tested family and config cases at `1db86902` (config G 0.0015-0.023); the absolute RMSE
  limit failed in 9 and the max-pixel limit in 5 of 14, tracking intensity scale (#209); the historical 24 tutorial movies gave 0.002899-0.010082;
- no Tier D scientific gate (#61, #73);
- resume does not detect changed settings (#149 deferred);
- no rollback: a failed movie can leave a truncated or earlier per-movie file and an auxiliary `_PS.mrc`; a failed batch withholds the joint
  output and keeps healthy per-movie products (`SUPPORT.md` §6);
- a failed `logfile.pdf` render leaves no `logfile.pdf` (F1, merged); strict in `--aggregate_only`;
- F3/F3b fail closed (#205 merged); F4 compressed MRC must be validated independently (#214); F5 big-endian mode-0 MRC with nx = 128: observed failing identically on every tested route of the GCC build up to `483e881d`; #231 replaced the `abs(INT_MIN)` swap test with ordered comparisons (`src/rwMRC.h:149-151`), so the undefined-behaviour rationale is gone. **Observed on F (QF):** the F5 input is now processed on every route (CPU and CUDA float, auto and compact all exit 0 with complete products), so QF item 13 is FAIL under #204's recorded expectation and is dispositioned in the D4 record (`docs/rc0/qf/run_6d68e2d6/README.md`). A supplementary run found the CUDA routes product-identical and every arm's products equal to the same pixels written little-endian. No CTest pins this outcome;
- **EER damaged input (D10, #221; fix merged in #231): three separate behaviours, bounded tests.** (1) A damaged container (invalid strip size or range, failed directory or strip read, missing mandatory tag, malformed legacy footer) or an invalid MRC header fails that **movie**: exit 1, no completion STAR for it, no joint output. (2) The retained D6 skip-and-warn: a fraction that would over-read or overshoot its own bytes is skipped with a warning and the movie publishes (`src/renderEER.cpp:489-496, 504-507, 554-557, 611-616, 659-663`). (3) Whole-IFD truncation without `--expected_frames` is still a shorter movie (E-1). The evidence is a bounded set of generated and fixture cases; **no claim is made for arbitrary damaged input**, no fuzzing campaign exists, and real 65000, 65002 and 2K files were not run. Known pre-existing post-RC0 item, not a user-facing limitation: the `RelionError` backtrace-buffer LeakSanitizer finding (`src/error.cpp:58`).
- EER (D6): damaged fractions are skipped with a warning and the movie publishes; undetected corruption that preserves the pixel count; a truncated EER is a
  shorter movie unless `--expected_frames` or a STAR count is supplied, and even then only a mismatch in the **grouped** frame count (`floor(fractions / eer_grouping)`) is detected;
- nvCOMP (D1): assumes complete, unmodified input files; a file changing between scan and read is not detected (#215); T3 checked arithmetic merged (#217; the Deflate-body precondition is unchanged); use `--ingest compact` otherwise;
- optional proprietary dependencies (D2): no project-distributed nvCOMP/nvTIFF-linked binaries; nvTIFF not used;
- host RAM with `--grouping_for_ps` (about +3.8 GiB float, +1.9 GiB compact on 10216), per-geometry free-VRAM floors with a streaming fallback, a non-monotone band below the full-speed floor, and the QM findings (PR #225; #226 D1, the stale CUDA error after a handled OOM, was fixed by D11, #228, merged `e3871ca2`; #226 D2 and D3 are deferred until after RC0; `SUPPORT.md` §8),
  EER upsampling 2 memory (Falcon 4, 144 groups: one run per arm sampled 79,522 MiB NVML process VRAM on an 81,920 MiB card, about 2.3 GiB remained; little observed headroom, not a guaranteed fit);
- macOS arm64: builds and runs; not qualified; known CPU CTest differences. `SyntheticRegression` fails because libc `rand()` differs from glibc (the same `--seed` gives different output bytes on macOS and glibc Linux, #222); `MultiGpuScheduling` failed from a test-harness `/var` symlink issue and passes since PR #223 merged; `NativeMovieStaging` is skipped;
- C5 CPU dose symmetry (#220 merged): enabled by default only on x86-64 GCC without FMA code generation; other toolchains run the original code unless a site sets `MOTIONCORR_CPU_DOSE_SYMMETRY=ON` after `CpuDoseSymmetry` passes; native-FMA flags unqualified and not recommended; performance claim x86-64 cpu64 only (`SUPPORT.md` §9);
- `ProfilingKit` has a load-sensitive 30 s subprocess timeout (#209);
- data-dependent patch non-convergence retry (EMPIAR-10641, 10216): host RSS 2.07 GiB with the resident retry versus 7.0 GiB before #197, one retry +504 MiB VRAM on 10641 (#207);
- differences from RELION 5.1: `SUPPORT.md` §0a (#216);
- anything newly found during QF.

## 4. Failed and UNRUN checks

Every check that failed or was not run, with the reason. Original failures are not dropped.

| Check | Status | Reason / evidence |
|---|---|---|
| Frozen-SHA qualification (QF) on F | **executed**: 16 items PASS, item 13 FAIL (dispositioned), item 14 not graded | `docs/rc0/qf/run_6d68e2d6/` |
| CUDA-to-CPU unweighted fallback (#198 C1) | six CPU-backend checks and one injected recoverable fallback executed at `1db86902` | #209: six current-vs-`d7171b81` pairs ran CUDA-linked binaries **without `--gpu`** (CPU backend) and all matched; one pair (injected `cudaMalloc` failure #16) executed the actual fallback branch under `--gpu` (CUDA-then-CPU log witness, both exits 0, four MRCs plus STAR/EPS identical). Not real OOM, not device poisoning. **Rerun on F: PASS** (QF item 7) |
| `ProfilingKit` (CPU, Linux) | FAILED once, then passed | 30 s subprocess timeout at load about 27; passed on rerun (#209) |
| `SyntheticRegression` on macOS | FAILED (documented, platform difference) | max pixel diff 23.649856567382812 from libc `rand()` differing from glibc (#222); unchanged from main; reproduced at `67b5315b` and the merge with `483e881d`; reproduced in the revision-7 run at `49efcd43` (max pixel difference 2.364986e+01, RMSE 3.119288e-01) |
| `MultiGpuScheduling` on macOS | **PASSED** in the revision-7 run (59.3 s); it FAILED at revisions up to 6 (test-harness `/var` symlink; 73 of 74 checks) | fixed by PR #223 (merged `ecb7d7f7`); passed on Linux (#209) |
| `NativeMovieStaging` on macOS | SKIPPED | Linux-only |
| Forced out-of-memory on session initialisation (QM) | executed with a VRAM balloon at `483e881d` (PR #225) | completed with documented limits; EER OOM path in #208 not exercised (the movie fit) |
| Genuine device poisoning | UNRUN | all fatal cases inject error codes; post-RC0 (#213) |
| Native `pbzip2` | UNRUN | absent; `.bz2` tested via a `bzip2 -cd` shim (#204) |
| 10441 and 10641 config G/L product campaign; launcher failure/resume injection; PDF content; second venue; timing | UNRUN | #209 |
| Real 65000, 65002 and 2K EER files; 8K gain at upsampling 1; measured 144-group retry VRAM; converging real-data retry | UNRUN | #208, #207 |
| F3/F3b required tests on the frozen SHA | **PASS** | QF item 4 |
| T3 `DeflateLayout*` tests and native nvCOMP controls on the frozen SHA | **PASS** | required tests in QF items 1-3; `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`, `CudaAdler32` in item 3 |
| Cross-backend `compare_motioncorr.py --gate backend`, all families | executed as a diagnostic at `1db86902` | relative RMSE fails 14/14 as expected; see §3 and S1 (#209). Not a gate result |
| EER frame-count metadata; RELION pipeliner/GUI without `logfile.pdf`; RELION 5.1 vs standalone on the #186 families | UNRUN | `POST_FREEZE_TEST_PLAN.md` §3a (#216) |
| Example run inventory with Ghostscript on macOS; `run_dataset.py` success path on macOS | UNRUN | local attempt failed only because `gs` is not installed there (`RELEASE_CHECKLIST.md` §8); Linux real-Ghostscript run passed (#209) |
| #123 adapted compact-ingest matrix | **PASS** on F | QF item 9, both CUDA executables |
| `CpuDoseSymmetry` and `CpuDoseSymmetryBase` on the frozen SHA and each released toolchain | **PASS** on F (QF item 10; CPU, CUDA, CUDA+nvCOMP, GCC 13.3.0; macOS arm64 also passes, original loop) | #220 is merged; both are required at QF (they pass on macOS arm64 in the revision-7 run, which uses the original loop there, and in the pre-freeze Linux check of `cb3699ac`, which is not frozen-SHA evidence) |
| #226 D1: stale CUDA error after a handled OOM (D11, #228) on the frozen SHA | **PASS** | QF item 17: `with_d11`, `CudaStaleErrorAfterOom` passes in both CUDA builds; D14 timing was on #228's own code, not the composition |
| #226 D2 (config-L admission gap) and D3 (late OOM failure) | deferred until after RC0 | admission redesign stays out of RC0; none changes output |
| EER damaged-input handling (D10, #221) on the frozen SHA | **PASS** | QF item 15: `EerMemorySafety` in all three builds and under ASan+UBSan on F; bounded cases only, no arbitrary-damaged-input claim |
| macOS platform statement | made (not qualified; known CPU CTest differences) | W-MAC, #222; #223 is merged; the revision-7 macOS run is recorded in section 2 and `RELEASE_CHECKLIST.md` §3 |
| `InputFormats` compressed-MRC cases that need `pbzip2` on macOS | UNRUN (waived by the CMake configure step) | `pbzip2` is not installed on the author's machine; `zstd` and `xz` cases ran |
| F5 big-endian mode-0 MRC with nx = 128 after #231 | **observed on F** | QF item 13 FAILs on this case under #204's recorded expectation (it now completes on every route); dispositioned in the D4 record. A supplementary run found products identical across the CUDA routes and equal to the little-endian input. No CTest pins it |
| D12 licence and notices review (#18) | deferred | maintainer 2026-10-17; not an RC0 freeze blocker |
| nvTIFF/LZW, device EER renderer (parked post-RC0), nvCOMP widening, #183 | not in RC0 | #198 register |

## 5. Resource requirements

Peak host RSS and device memory per corpus family. The reference columns are the #186 measurements at main `116eb04a`
(before #178, #187, #195, #196, #197 and #185 merged); the RC0 columns were not measured: QF on F is a correctness run with no resource protocol. The table after the reference tables gives the qualification measurements at `1db86902`.

Reference provenance. CPU: cpu64, AMD EPYC 7763, 64 cores, SMT off, 226 GB RAM, THP `madvise`, GCC 13.3.0, FFTW 3.3.10, libtiff 4.5.1,
binary SHA-256 `86a43e9f0fa0787ba7eef5270c65eee466857e493d7f6df6daa98de0b28bed53`; config L (`--patch_x 5 --patch_y 5`), dose weighting,
`taskset` to 1 or 8 CPUs, median of the unprofiled runs (`docs/workload_corpus/cpu/README.md`, `cpu/provenance.json`). GPU: 4GPUs GPU0
(A100 80 GB PCIe, driver 570.86.10), `taskset -c 96-103`, `--j 8 --gpu 0`, CUDA 12.8, nvCOMP 5.3.0.16, THP `madvise`, binary SHA-256
`79c88e4ce1f1cb5a445f4da34f195b31edd257d58f4706624678f61fe6d6166c`, inputs in tmpfs; VRAM is the NVML per-process peak (sampled, so a
lower bound) and includes the CUDA context (`docs/workload_corpus/gpu/README.md`, `gpu/provenance.json`).

| Family | Reference CPU RSS GiB, L, `--j 1` / `--j 8` | Reference GPU host RSS GiB, L | Reference VRAM GiB, G / L | RC0 RSS | RC0 VRAM |
|---|---|---|---|---|---|
| tutorial (3710 x 3838 x 24) | 2.75 / 3.19 | 0.4 | 3.2 / 3.3 | not measured at QF | not measured at QF |
| EMPIAR-10028 (4096 x 4096 x 16) | 2.17 / 2.67 | 1.6 | 2.6 / 2.7 | not measured at QF | not measured at QF |
| EMPIAR-10361 (5760 x 4092 x 62) | 11.24 / 11.99 | 1.7 | 11.6 / 12.3 | not measured at QF | not measured at QF |
| EMPIAR-10641 (5760 x 4092 x 70) | 12.75 / 13.50 | 7.0 (includes the retry path) | 13.1 / 14.7 | not measured at QF | not measured at QF |
| EMPIAR-10441 (11520 x 8184 x 50) | 36.31 / 39.09 | 5.0 | 37.0 / 39.3 | not measured at QF | not measured at QF |
| EMPIAR-10474 Falcon 3 (4096 x 4096 x 58) | 8.62 / 9.16 | 5.3 | 7.9 / 8.8 | not measured at QF | not measured at QF |
| EMPIAR-10474 Falcon 4 (4096 x 4096 x 144) | 21.19 / 21.35 | 12.0 | 18.6 / 20.0 | not measured at QF | not measured at QF |
| EMPIAR-12963 (4096 x 4096 x 39) | 5.91 / 6.47 | 3.7 | 5.5 / 6.2 | not measured at QF | not measured at QF |
| EMPIAR-10164 (7420 x 7676 x 8) | 3.89 / 5.57 | 2.2 | 4.5 / 4.5 | not measured at QF | not measured at QF |
| EMPIAR-10216 (4096 x 4096 x 59) | 7.62 / 8.15 | 4.2 | 8.0 / 9.0 | not measured at QF | not measured at QF |

**Qualification measurements at `1db86902` (PR #209).** Peak host RSS (GiB) of the single-movie worker process from `/usr/bin/time -v`, one movie per
family, `--j 8`, `docs/workload_corpus/families.json` options. Source `1db869025507ac801845b4001b84e6bc0e77a645` (clean clone), host 4GPUs
(4-gpu-vm, 4 x A100 80 GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, nvCOMP 5.3.0.16, THP `madvise`), lane GPU1 and CPUs 104-111, Release builds
(CPU binary `dd86cd41...6b26439`, CUDA+nvCOMP `77db3f92...12a99`; full hashes in `docs/rc0/qual_main_1db86902/raw/summaries/build-info.txt`).
One sample per cell for the seven family rows; no variability is available. Routes are the `--ingest_witness` values. Not a performance claim. **Exception:** the EMPIAR-10641 row below is from PR #207 and is a **two-movie** process peak with **two passes per arm** (CPU-only: one pass per arm); the Falcon 4 row is one run per arm from PR #208. They are not single-movie samples.

| Family | cfg | auto route | RSS auto | RSS `--ingest float` | RSS CPU build |
|---|---|---|---:|---:|---:|
| tutorial | G / L | nvcomp | 0.34 / 0.34 | 1.52 / 1.52 | 2.71 / 2.84 |
| EMPIAR-10361 | G / L | compact | 1.54 / 1.53 | 5.67 / 5.68 | 11.06 / 11.28 |
| EMPIAR-10474 Falcon 3 | G / L | compact | 3.16 / 3.16 | 5.02 / 5.14 | 8.53 / 8.65 |
| EMPIAR-12963 | G / L | compact | 2.30 / 2.30 | 3.57 / 3.63 | 5.89 / 5.97 |
| EMPIAR-10216 | G / L | compact | 2.10 / 2.10 | 3.89 / 4.01 | 7.50 / 7.66 |
| EMPIAR-10028 | G / L | float | 1.59 / 1.54 | 1.55 / 1.58 | 2.11 / 2.43 |
| EMPIAR-10164 | G / L | compact | 0.80 / 0.85 | 2.14 / 2.08 | 3.78 / 4.60 |
| EMPIAR-10641 (two movies) | L, `--j 8` | compact, resident retry (db) | **2.07, 2.07** (two passes; two-movie process peak; PR #207, lane GPU2, CPUs 80-87) | injected fallback 6.63, 6.67; pre-#197 6.99, 7.03 (two passes each); `--ingest float` not run | CPU-only build, two movies, CPUs 80-87, one pair, no null control: **12.92 GiB** (13,550,512 KiB, raw GNU `time -v`, exit 0) for `1db86902`, 13.50 GiB (14,158,836 KiB) for the pre-#197 CPU build (PR #207 `evidence/runs/b5_cpu_db.side` and `b5_cpu_pre.side`); not run in #209's single-movie campaign. Reference CPU `--j 8`: 13.50 (#186 at `116eb04a`, different host) |
| EMPIAR-10474 Falcon 4, 144 groups, upsampling 2 | as #208 `m1` | compact | 21.04 (21,547 MiB, PR #208, lane GPU2, CPUs 112-119) | 39.23 (40,171 MiB, same run set) | **UNRUN** at upsampling 2 (reference upsampling 1, `--j 8`: 21.35, #186) |
| EMPIAR-10441 | G / L | compact | **UNRUN** at `1db86902` | **UNRUN** | **UNRUN** (references: GPU host RSS 5.0, CPU `--j 8` 39.09, VRAM peak 39.3 GiB, #186 at `116eb04a`) |

Other qualification figures (single runs, same host): EER upsampling at the compact route lowered host RSS 34-39 % at upsampling 1 and 43-47 % at 2 and 3
(no saving at -1); a 144-group Falcon 4 movie at upsampling 2 completed with 79,522 MiB sampled NVML process VRAM on the 81,920 MiB card (calculated 80,520 MiB; one run per arm; about 2.3 GiB remained; not an upper bound) with host RSS 21,547 MiB compact versus 40,171
MiB float (PR #208, lane GPU2, CPUs 112-119). EMPIAR-10641 resident retry (two movies, two passes per GPU arm): peak host RSS 2.07, 2.07 GiB versus 6.63, 6.67 GiB (injected fallback) and 6.99, 7.03 GiB (pre-#197); NVML VRAM 14,582 / 15,034 / 15,034 MiB
= 14.24 / 14.68 / 14.68 GiB (sampled); CPU-only two-movie run 12.92 GiB (raw 13,550,512 KiB; the "13.6 GiB" in #207's README does not match its raw GNU-time record: 13,550,512 KiB is 13.55 decimal GB, and the pre-#197 CPU value is 13.50 GiB, README "14.2"); one resident retry allocates 504 MiB (10641) / 301 MiB (10216) (PR #207, lane GPU2, CPUs 80-87; VRAM corrected after R-QA1).
`--grouping_for_ps 4` on EMPIAR-10216: about +3.8 GiB host RAM (float) and +1.9 GiB (compact), single samples (PR #204, lane GPU3, CPUs 88-95).

Source tables: `docs/workload_corpus/cpu/README.md` ("Peak RSS" table) and `docs/workload_corpus/gpu/README.md` ("Per-family result"
table). Rule of thumb from the GPU report: VRAM peak is two resident float32 movies (`2 x frames x nx x ny x 4 B`) plus 0.7-4.2 GiB;
estimates for 24, 40 and 48 GiB cards are arithmetic, not runs. Also record: scratch space per run, pinned host memory
(`MOTIONCORR_NVCOMP_PINNED_MAX_MB`, default 256 MiB per worker, `cuda_movie_session.cu:1580-1581`), per-worker RSS and VRAM at 1/2/4 devices,
and the 8-CPU or other CPU cap actually used. Add the two inherited host/VRAM behaviours: `--grouping_for_ps` on the resident CUDA
path downloads one extra Fourier movie to the host (`src/motioncorr_runner.cpp:3251-3258`), and the resident path needs two float-size
stacks on the device (EMPIAR-10441 peaked at 39.3 GiB). EER upsampling 2 quadruples movie storage (one sampled run above; not a guaranteed fit).

## 6. Measured performance

One row per measurement. A timing without all fields is not reported. Compare only rows with matching venue, allocation, THP setting,
binary, inputs and storage.

| Field | Meaning |
|---|---|
| source | exact SHA, clean tree |
| binary | path and SHA-256, build type, compiler, CUDA/nvCOMP versions |
| hardware | CPU model, GPU model/UUID, RAM, THP mode, persistence mode, venue |
| resources | CPUs and devices actually allocated, `--j`, `--max_io_threads`, locks held |
| inputs | files and SHA-256, replayed versus distinct movies |
| options | full command line |
| samples | repetitions, interleaving, excluded runs and why |
| variability | min-max or IQR, paired difference with interval |
| output verdict | product comparison performed (tool, profile, result), not only exit status |
| limitations | what the number does not show |

RC0 rows: none recorded (QF on F ran no timing).

Reference rows (earlier SHAs; context only, not RC0 results):

| Row | source | binary | hardware, resources | inputs, options | samples, variability | output verdict | limitations |
|---|---|---|---|---|---|---|---|
| GPU, tutorial, config L, `--ingest auto` (witness `nvcomp`): 1.43 s whole process, 2 movies | `116eb04a`, clean | SHA `79c88e4c...6166c`, Release | 4GPUs GPU0 A100 80 GB, CPUs 96-103, `--j 8`, THP `madvise`, persistence off | 2 tutorial movies (hashes in `corpus.md`), corpus options, `--gpu 0` | 5 unprofiled repeats, 1.43 [1.41-1.51] s | exit 0 and product count only; no product comparison | tmpfs inputs, one GPU model, process start dominates a 2-movie run (about 1.2 s of 1.4 s) (`docs/workload_corpus/gpu/README.md`) |
| CPU, tutorial, config L, `--j 8`: 10.0 s whole process, 2 movies | `116eb04a`, clean | SHA `86a43e9f...8bed53`, Release `-O3 -DNDEBUG -fopenmp`, GCC 13.3.0 | cpu64, `taskset -c 0-7`, THP `madvise`, `OMP_PROC_BIND` unset | same 2 movies, corpus options, no `--gpu` | 2 of 3 planned clean repeats, 10.0 [9.9-10.0] s | exit 0 and product count; retained tree hashes only | warm page cache, host shared with other users' jobs on other CPUs (`docs/workload_corpus/cpu/README.md`) |
| Dataset endpoint, 24 tutorial movies, 4 x 8 CPUs versus 1 x 32 | `d7339fd` | SHA `ae13ab74...5307d`, Release, CUDA | 4GPUs, 4 A100 (one worker each), fixed 32-CPU budget | 24 tutorial movies, `run_dataset.py`, `--ingest auto` | 6 interleaved reps, publication 10.37 s (IQR 0.82) versus 13.87 s (IQR 0.55), paired difference -4.02 s (CI -4.70, -2.90) | all three arms identical to a single-process single-GPU run on 24 movies (MRC bytes outside the timestamp, normalised STARs, product presence) | host shared throughout; predates #176, #178, #187, #195-#197; not a fixed-budget claim for RC0 (`docs/multi_gpu/scaling/README.md`) |

Per-family GPU and CPU timing tables are in `docs/workload_corpus/{cpu,gpu}/`; do not copy them here without their provenance.

## 7. Sign-off

Maintainer review of this report, the scope decision and the tag are separate steps (`RELEASE_CHECKLIST.md` §10). Frozen source SHA F: `6d68e2d6`. Tag target T (named by the maintainer; F or a later docs-only evidence commit): pending. `git diff F T -- . ':!docs/rc0' ':!docs/release'` empty: pending. Maintainer sign-off: pending (QF on F is recorded in `docs/rc0/qf/run_6d68e2d6/`).


## Post-RC0 re-entry: #226 D3

Validated PR implementation head: `4cd851677bfda80e60ef189cb1ff668cef721043` (CUDA source; subsequent evidence commits are documentation only).
Release builds and full CTest pass: CPU **74/74** on cpu64, CUDA **109/109** and CUDA+nvCOMP **112/112** on an A100.
`CudaEarlyStreamingOom` passes. The original QM balloon harness on the original GPU1 UUID reproduces the late
16/21 GiB failures on `c8844894`; G/L × auto/float now refuse early with required/available memory, no failed-movie
products and 743 MiB RSS. All four 22 GiB controls complete identically; unconstrained products also match
`c8844894`. [Commands, hashes, raw receipts and powered before/after control](../rc0/issue226/d3/README.md).
No numerical gate, tolerance or completed-product difference is introduced. Not rerun: complete frozen QF,
scientific S1, performance qualification, macOS, native multi-GPU publication, real smaller GPUs, host-RAM
exhaustion, genuine device poisoning or optional upsampling/binning/PS matrices. Those rows retain their earlier
SHA and verdict; a new tag remains a maintainer decision.
