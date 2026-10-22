# Independent review, round 2: #265 native round-trip oracle

- Reviewed SHA: `f4fc51723ac3f32dc956dcf9e755aaa71b220d0b` (branch `docs/265-native-roundtrip-oracle-20261022`), one docs commit on `bb08502e`
- Base: `3691374061f782bc84531fd1c79d017ddcb5a7c2`
- Reviewer worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-46a27020`, detached at the reviewed SHA, clean index, 0 untracked files
- Prior round: R1 of `bb08502e`, `REVIEW.md` sha256 `ee42f060036a852382cc95570a5f51b6ab1b23cc5c030fcdb13a22947e968617`
- Date: 2026-10-22. Host-only on Mac (Python 3, `-B -I`, one numeric thread; load avg 3.5-5.1 from system processes). No build, CTest, native binary, SSH, GPU or movie data. Author scratch `/tmp/mc265-oracle-20261022/` and author worktree read only.

## Verdict

No material findings. M1, M2, L1, L2, L3, L4 and advisories A1-A3 are resolved. The new provenance file is accurate and labelled
as after-the-fact. The frozen inputs, harness, `run.sh` and all receipts are byte-unchanged, so the R1 arithmetic still applies.
Three low items remain (R2-L1 to R2-L3); none changes a result or a conclusion. The packet is ready to publish as a
prerequisite-only DRAFT, with or without those fixes. #265 stays FILED ONLY.

## Findings

### R2-L1 (low): wrong range for F02 scientific-branch losses

`README.md:100`: "In F02 those scientific-branch losses are 4.5e-12 to 2.9e-11 absolute (X2, X5, X8, X11)".
From `receipts/iteration2/coefficients.csv` the four cited errors are X2 1.234e-11, X5 3.479e-11, X8 2.910e-11, X11 4.51e-12,
so the range is 4.5e-12 to 3.5e-11. F02 has 13 scientific-branch coefficients in total (X2, X5, X8, X11, X14, X17, Y2, Y5, Y8, Y11,
Y13, Y14, Y17); the largest error among them is 4.756e-10 (Y5). Suggested text: "In F02 the 13 scientific-branch coefficients lose
3.5e-12 to 4.8e-10 absolute". The conclusion that the fixed branch dominates (4.8e-6) is unchanged.

### R2-L2 (low): §9 item 4 is slightly misquoted

`DESIGN_NOTE.md:78-79` lists "the format rows its code touches" as part of the §9 item 4 "CUDA or shared source" class. In
`docs/release/POST_FREEZE_TEST_PLAN.md` that phrase belongs to the CPU-only bullet; the shared bullet is "full CTest on all three
configurations, the checklist rows whose route the change touches, and native execution on a GPU". Including format rows is the
stricter union, and it was what R1 asked for, so no evidence requirement is weakened. Suggested wording: "...the 'CUDA or shared source'
class (full CTest on all three configurations, the touched route rows, native GPU execution), plus the format rows its code touches
from the CPU-only list."

### R2-L3 (low): R1 advisory A4 neither resolved nor left open

The correction list (`README.md:131-136`) and the author response do not mention A4. `README.md:13` still says the source was
"clean (`receipts/iteration2/source_dirty.txt` empty)", but `run.sh:17` checks only `src` and `CMakeLists.txt`. That does not matter
at this head, but the word "clean" is broader than what was checked. Either add "(checked for `src` and `CMakeLists.txt` only)" or list
A4 as left open.

## Prior findings: status

| R1 item | status at f4fc5172 | evidence |
|---|---|---|
| M1 headline/K2 | resolved | `README.md:4-7` and `:81-82` say 10 of 11 bit-exact, K2 **NOT MET**, F09 failure retained. `DESIGN_NOTE.md:56` agrees. No remaining "zero error"/"met for 10 of 11" text (grep). |
| M2 CPU-only classification | resolved (wording nit R2-L2) | `DESIGN_NOTE.md:76-80`: shared source, CPU and CUDA STAR output change, §9 item 4 shared class, compilation does not qualify, C1 separation is a recommendation, sign-off required. Writer path confirmed at base: `writeModel` `src/motioncorr_runner.cpp:1481`, called at `:1043` and `:1471`; early-binning copy at `:1486`. |
| L1 mechanism text | resolved | Tokens checked against `coefficients.csv`: F08 X17 123456.789 -> `1.234568e+05` (err 0.011); X12 -100000.5 -> `-1.00000e+05` (err 0.5); X15 100000.5 -> `1.000005e+05` bit-equal; X9 -99999.99999995 -> `-100000.0000`; F02 X1 -> `-0.02144`; X4 -> `-0.00875`; X2 -> `4.187390e-04`; X8 -> `-5.84736e-05`. The 7/6 significant-digit description matches `%12.6e`/`%12.5e`. |
| L2 cited tokens | resolved | `-0.0012227128700699999` is line 11 (X idx 2) of `receipts/iteration2/fullprecision_star/F03_neg_z3_const.star`. G00 full-precision tokens `2.2250738585072014e-308` and `-0` are in `receipts/followup_subnormal/coefficients.csv`, bit-equal (`0x1p-1022`, `-0x0p+0`). |
| L3 ties | resolved | Recomputed from scratch `samples_full.csv` (`6da068ed…`): F03 and F09 each have 52 tied maxima at frame 49; F04, F08, F10 tie G1/G2 (0,0); F02, F05, F06, F07 have a single maximum at the listed location; F00/F01 all zero. K3 tie was confirmed in R1. |
| L4 provenance | resolved | Every hash in `RETROSPECTIVE_PROVENANCE.md` matches the scratch files today: binary `d1ccb52a…` (mtime 21:27:50Z), iteration-1 binary `9bdf53ca…`, library `2c237ae5…`, `src.sha` `3691374…`, follow-up `summary.json` `05a7e79b…` and `coefficients.csv` `39777644…` equal committed, follow-up stdout/stderr/exit byte-equal, follow-up output mtimes 21:27:55Z, `iter1_csv.sha` (mtime 21:27:39Z) holds the two stated lines under `out/run`, iteration-1 CSVs equal iteration-2's, iteration-1 `summary.json` `64233df5…dfd3a` equals committed `summary_INVALID_JSON.json`. The file says these are later observations, not run-time records; commit time 21:42:55Z is consistent with the stated 21:41Z. |
| A1 early binning | resolved | `README.md:127-128`, `DESIGN_NOTE.md:65-67`. |
| A2 FMA/toolchain | resolved | `README.md:125-126`; `build_options.txt` contains `-O3`. |
| A3 libstdc++ | resolved | `README.md:121-122`, `DESIGN_NOTE.md:55`; stated as unmeasured, no assumption either way. |
| A4 `run.sh` dirtiness scope | open, not stated | R2-L3. |

## Checked with no finding

- **Scope:** `git diff --name-only 3691374..f4fc5172` gives 71 files, all under `docs/post_rc0/issue265_oracle_20261022/`; no `src/`, tests or CMake delta.
  `bb08502e..f4fc5172` changes `README.md`, `DESIGN_NOTE.md` and adds `RETROSPECTIVE_PROVENANCE.md` and `review/R1_opus/` only.
- **Frozen material unchanged:** `git diff --quiet bb08502e f4fc5172 -- fixtures.txt PRE_RUN_CRITERIA.txt FROZEN_BEFORE_RUN.txt fixtures_followup_subnormal.txt harness run.sh receipts` exits 0. No run was repeated, so the R1 independent arithmetic (0 discrepancies) still covers the numbers.
- **Review retention:** `review/R1_opus/SHA256SUMS.txt` verifies; `REVIEW.md`, `independent_check.json` and `scripts/independent_check.py` are `cmp`-identical to `/tmp/motioncorr-star265-review-r1-20261022/`. No header was added.
- **Failure semantics kept:** iteration-1 invalid JSON, the F09 `READ FAILED` row, and the post-hoc follow-up label are all unchanged. Exit code 0 is still not presented as a pass.
- **Claims did not grow:** the new text adds no tolerance, gate, harm model, real-movie, CUDA-runtime, performance or science claim. The 10641 case still needs real pre-write coefficients; `global_shift` stays out of scope and is listed as open.
- **Design note:** still no source fix and no adoption. Parser range, backward compatibility, other-table byte preservation and the libc++ subnormal regression are covered, and Linux, RELION interoperability and the subnormal/non-finite write policy are now listed as unmeasured.
- **Licence:** new author file `RETROSPECTIVE_PROVENANCE.md` carries `SPDX-License-Identifier: GPL-2.0-or-later`.

## Commands (all exit 0)

```
git checkout -q --detach f4fc51723ac3f32dc956dcf9e755aaa71b220d0b; git status --short; git diff --quiet HEAD
git diff --name-only 3691374061f782bc84531fd1c79d017ddcb5a7c2..HEAD | grep -v '^docs/post_rc0/issue265_oracle_20261022/'   # empty (grep rc 1)
git diff bb08502e..f4fc5172 -- README.md DESIGN_NOTE.md RETROSPECTIVE_PROVENANCE.md review/R1_opus/SHA256SUMS.txt
git diff --quiet bb08502e f4fc5172 -- fixtures.txt PRE_RUN_CRITERIA.txt FROZEN_BEFORE_RUN.txt fixtures_followup_subnormal.txt harness run.sh receipts
(cd review/R1_opus && shasum -a 256 -c SHA256SUMS.txt); cmp review/R1_opus/<f> /tmp/motioncorr-star265-review-r1-20261022/<f>
shasum -a 256 / stat / cmp on /tmp/mc265-oracle-20261022/{out,out_iter1,out_followup,build}/... (read-only)
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  /Users/alex.konstantinov/.local/bin/python3 -B -I r2_check.py <packet> /tmp/mc265-oracle-20261022 > r2_check.json
```

`r2_check.py` and `r2_check.json` are in this directory. The script reads the committed `coefficients.csv` for the cited tokens and the
read-only scratch `samples_full.csv` for worst-sample ties.

## Limits

Host-only. No binary was rebuilt or executed; native reproduction rests on the author's receipts and on hash identity of scratch
artifacts, as in R1. Scratch state is observed now, not at run time. The libstdc++ and RELION readers were not exercised.

## Publication readiness

Ready as a **prerequisite-only DRAFT** at `f4fc5172`. R2-L1 to R2-L3 are low and can be fixed in a docs-only commit without a further
numerical check. Not evidence for a production fix, a real-movie accuracy figure, a tolerance or gate, or CUDA behaviour.

## Unresolved needs (unchanged from R1)

1. Maintainer decision on the parity-breaking STAR output change on the shared CPU/CUDA write path (`ad0b230` parity; §9 item 2).
2. Actual pre-write native coefficients for the 10641 run (the `bin_factor`-scaled exported copy if early binning applies).
3. Linux GCC/libstdc++ reader behaviour on subnormal and full-precision tokens.
4. A write-side policy for subnormal and non-finite coefficients, and a separate decision on `global_shift` precision.
5. RELION reader/writer interoperability with full-precision motion tables.
