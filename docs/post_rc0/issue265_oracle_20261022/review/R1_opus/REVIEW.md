# Independent review, round 1: #265 native round-trip oracle

- Reviewed SHA: `bb08502ee7b5c2275fdc880c3a80a668356453e5` (branch `docs/265-native-roundtrip-oracle-20261022`)
- Base: `3691374061f782bc84531fd1c79d017ddcb5a7c2` (merge-base verified; one commit on top)
- Reviewer worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f0bb310d`, detached at the reviewed SHA, clean index, 0 untracked files
- Date: 2026-10-22. Host-only review on Mac (Python 3 with NumPy, `-B -I`, one numeric thread, load avg ~3.4-4.3 from system processes). No build, no CTest, no native binary executed, no SSH/GPU/movie data.

## Verdict

The numerical content is correct. My separate Python check reproduces every committed coefficient,
token, per-range maximum, per-frame maximum, worst-sample value and K3 result from the committed
files, with 0 discrepancies. Scope is docs-only. Two wording/classification problems should be fixed
before publication as a prerequisite DRAFT (M1, M2). Four low-severity factual or provenance fixes
are recommended (L1-L4). No tolerance, gate or harm model can be inferred from the packet, and it
does not claim one.

## Findings

### M1 (medium): headline overstates K2; K2 is "not met" under the frozen criterion

`README.md:4-5` says "the same fixtures round-trip with zero error when the coefficient text is written at `%.17g`".
F09's full-precision file is unreadable by the real reader (`READ FAILED`, README row 56, `receipts/iteration2/stderr.txt`).
`PRE_RUN_CRITERIA.txt:13-18` predicted bit-identity "for every fixture", so K2 as frozen is not met.
`README.md:76` calls it "met for 10 of 11", which reads as a partial pass. The failure is retained and not hidden, but the opening sentence contradicts it.

Requested wording: opening — "10 of the 11 fixtures round-trip bit-exactly at `%.17g`; F09's full-precision file
(subnormal token) is rejected by the real reader on this toolchain". K2 line — "K2 not met: 10/11 bit-exact; F09 read failure retained".

### M2 (medium): DESIGN_NOTE misclassifies the future change as CPU-only

`DESIGN_NOTE.md:71-73` says the change needs "the CPU-only re-entry set in item 4" and "is not a CUDA change".
The formatter (`src/metadata_table.cpp`) and `ThirdOrderPolynomialModel::write` (`src/micrograph_model.cpp`) are compiled
into `motioncorr_core` in every configuration. The STAR is written by `MotioncorrRunner::writeModel`
(`src/motioncorr_runner.cpp:1481-1496`), called from the backend-common run loop (`:1043`) and `saveModel` (`:1471`).
A full-precision motion table therefore changes CUDA-route STAR output too. `POST_FREEZE_TEST_PLAN.md` §9 item 4 puts
"CUDA or shared source" in the class that needs full CTest on all three configurations, the touched route rows and native GPU execution.
The note's CPU-only list also omits "the format rows its code touches".
"Do not bundle into C1" can stay as a scheduling recommendation. The re-entry class should be "shared source", or the
classification should be left explicitly to the maintainer.

### L1 (low): width-cap mechanism is misdescribed for the >1e5 cases

- `DESIGN_NOTE.md:15-16`: "`100000.1234567` loses its last digit". Native token is `1.000001e+05` (exactly 12 chars, not truncated),
  read back as 100000.1, abs error 2.3457e-2 (`receipts/iteration2/coefficients.csv`, F08 X3). The loss comes from the
  `|v|>100000` scientific branch keeping 7 significant digits, not from the 12-character cap.
- `README.md:95`: "100000.5 as `1.00000e+05`". It is **-100000.5** that becomes `-1.00000e+05` (abs error 0.5, negative
  scientific branch keeps 6 significant digits). +100000.5 round-trips exactly as `1.000005e+05` (F08 X15 bit-equal).
- The native tokens show the width cap truncating only 3-digit exponents (`1e-300` → `1.000000e-30`, `4.94e-324` → `4.940656e-32`)
  and `-99999.99999995` (`-100000.00000` → `-100000.0000`). 123456.789 → `1.234568e+05` is precision loss.

These are non-physical probes and the conclusions are unchanged. The mechanism text should match the tokens.

### L2 (low): two "measured" tokens in DESIGN_NOTE do not appear in any read file

`DESIGN_NOTE.md:48` cites `-0.0012227128700700001` and `1.0000000000000001e-30`. The full-precision token actually written and
read for -0.00122271287007 is `-0.0012227128700699999` (`fullprecision_star/F03_neg_z3_const.star:11`). No full-precision file
contains `1.0000000000000001e-30`: the F09/G00 files carry `1e-300`, and `1.0000000000000001e-30` is the `%.17g` display of the
real-route post value read from `1.000000e-30`. The claim itself holds: every full-precision coefficient in every readable fixture,
including `2.2250738585072014e-308` and `-0` in G00, is bit-equal. Replace the cited tokens with the ones actually read.

### L3 (low): worst-sample locations are tied

The worst-sample table (`README.md:60-71`) gives one location per fixture. In F03 and F09 the maximum is shared by 52 samples
(a pure-time term, so every position at frame 49 in both geometries ties). In F04, F08, F10 and the K3 control, G1 (0,0) ties with
G2 (0,0), since both normalise to (-0.5, -0.5). The listed G1 location is the first in iteration order. The values are correct.
Add one sentence saying the location is not unique. K3's frame-only check (`roundtrip_oracle.cpp:468`) is unaffected.

### L4 (low, provenance): two receipts depend on uncommitted scratch

- `receipts/followup_subnormal/` has no `hashes.txt`, `source_head.txt` or `build_options.txt`. The binary is identified only by
  path (`argv.txt`: `/tmp/mc265-oracle-20261022/out/roundtrip_oracle`, fixtures given as a relative path). Today that scratch binary
  hashes `d1ccb52a…` (= iteration 2), and the scratch follow-up `summary.json`/`coefficients.csv` equal the committed files
  (`05a7e79b…`, `39777644…`). That shows the current state, not the state at run time.
- `README.md:101-102` says iteration 1's CSV hashes match iteration 2's. The iteration-1 receipt directory does not record them;
  they exist only in scratch `iter1_csv.sha`, whose paths say `out/run` (the directory was later renamed `out_iter1`). I confirmed directly:
  `out_iter1/run/samples_full.csv` `6da068ed…`, `coefficients.csv` `720f1663…`, `per_frame_max_vec.csv` `26f618b8…`,
  and identical `written_star/` and `fullprecision_star/` trees. Iteration-1 binary `9bdf53ca…` matches its committed `hashes.txt`.
  Suggest committing one hash line per receipt so the packet stands alone.

### Advisory (no change required for this DRAFT)

- A1 Pre-write reference with early binning: when `do_own && early_binning`, `writeModel` writes a copy whose coefficients are
  multiplied by `bin_factor` (`src/motioncorr_runner.cpp:1486-1493`). A future capture for the 10641 case must take that exported copy,
  not `mic.model`. `DESIGN_NOTE.md:61` ("at the moment `Micrograph::write` runs") is consistent with this; saying so explicitly would prevent a wrong capture.
- A2 Toolchain: AppleClang arm64 `-O3` may contract FMAs inside `getShiftAt`. Pre and post use the same compiled function, so the
  exact-zero results and K3 are unaffected. Per-sample errors can differ in the last bits from the qualified Linux x86-64 GCC build;
  my independent float64 evaluation agrees with the harness to ≤2.4e-13 relative on the physical fixtures. The README already labels the toolchain.
- A3 libstdc++: whether `istream >> double` accepts subnormals on the project's Linux GCC is unmeasured, and the packet says so.
  I expect libstdc++ sets failbit only on overflow, not underflow, but that is not measured either; it must be measured before any write-side flush/reject decision.
- A4 `run.sh:17` checks dirtiness of `src` and `CMakeLists.txt` only (not `cmake/`). It does not matter at this head (source = clean main checkout per receipt), but a future reuse should check the whole tree.

## Checked with no finding

- **Scope:** `git diff --name-only 3691374..bb08502e` gives 66 files, all under `docs/post_rc0/issue265_oracle_20261022/`. No `src/`, tests or CMake delta. The harness is not part of the CMake build.
- **Native APIs:** the harness calls the library's `ThirdOrderPolynomialModel::getShiftAt/write/read` (`src/micrograph_model.cpp:35-54, 61-87, 89-…`), which go through `MetaDataTable::getValueToString` (`src/metadata_table.cpp:252-278`, `snprintf(buffer,13,"%12.{5,6}{f,e}")`) and `setValueFromString` (`:427-443`, whole-token `istringstream >> double`). Nothing is ported. `RFLOAT` is double (no `RELION_SINGLE_PRECISION` in the recorded DEFS).
- **Convention:** the model `z` is 0-indexed (`micrograph_model.h:47-49`; `Micrograph::getShiftAt` passes `frame - first_frame`, `:412`). Normalisation `px/width - 0.5` matches `:385-386`. The coefficient order in `fixtures.txt:8-15` matches `getShiftAt`.
- **Freezing:** the committed `fixtures.txt` (`ef11984e…`) and `PRE_RUN_CRITERIA.txt` (`b9722d95…`) match `FROZEN_BEFORE_RUN.txt` and scratch `frozen.sha256`. The follow-up table (`df86b048…`) and iteration-2 harness (`5e69f974…`) match `FROZEN_FOLLOWUP.txt`. The follow-up is labelled post-hoc (`fixtures_followup_subnormal.txt:4`, README:78).
- **Iteration 1 → 2 is escape-only:** `diff` of the two summaries shows only the `read_error` newline escape and the added `"any_read_failed":true`. stdout and build options are identical, the library hash `2c237ae5…` is unchanged, and the CSV/STAR outputs are identical (L4). Iteration-1 `summary_INVALID_JSON.json` fails `json.load` ("Invalid control character", line 382). Iteration-2 and follow-up summaries parse.
- **Independent arithmetic** (`scripts/independent_check.py`, output `independent_check.json`, 0 problems):
  - All 36 pre-write bit patterns per fixture/route equal Python `float()` of the frozen tokens.
  - A Python emulation of the formatter rule reproduces every native `written_token` and every coefficient line of `written_star/*.star`.
  - Every real-route post value is bit-equal to `float(token)`. Every full-precision post value is bit-equal to pre. `bit_equal` flags, counts and max coefficient abs error match `summary.json` exactly.
  - Shift error recomputed two ways over the frozen 2600-sample grid: (a) `getShiftAt`-order difference, (b) Σ Δcoeff·basis.
    Harness `max_vec` vs (b): ≤2.4e-13 relative for F02/F03/F04/F07/F09/F10. For F05, F06 and F08 it is 1.3e-7, 1.9e-7 and 2.5e-10, from cancellation in 1e8-3.6e9 px shifts, as labelled.
    Per-range maxima agree to ≤1.9e-12 (physical fixtures), and per-frame maxima to ≤6.5e-12; F05/F06 are ≤5.1e-6 for the same cancellation reason. Argmax locations agree, subject to L3 ties.
  - K3 from the injected file text: only Y17 changed; d = 9.999999999999972e-07; my max |dy| 0.029412249999999918 vs harness measured 0.02941225000000003 (3.8e-15 relative); dx = 0; argmax G1 frame 49 (0,0), tied with G2 (0,0).
- **Signed zero:** F09 X3 and Y0 (`-0.0`) are written `-0.000000` and read back as `-0x0p+0` (bit-equal). G00 full-precision `-0` is read back as `-0x0p+0`. F09's full-precision signed-zero case is covered only by the post-hoc G00, which is acceptable as labelled.
- **Failure retention:** F09 and G01/G02 full-precision `READ FAILED` rows are retained with the reader's message. `any_read_failed:true`. Harness exit 0 is the harness's own status, not a pass, and the README does not present it as one.
- **Real-movie scope:** README:90-93 states that the 0.34-0.56 px values need frames up to 49 on constructed coefficients and do not confirm the 10641 report. The 24-frame bound (≤0.058 px, F10 late24) is reported. `global_shift` is explicitly out of scope (`DESIGN_NOTE.md:40-42`). The F05/F06/F08/F09 non-physical probes are labelled.
- **Design note:** no source fix and no adoption. It covers parser behaviour, backward compatibility (old 5-6-decimal files still parse), other-table byte preservation and the subnormal regression on libc++. Apart from L1, L2 and M2 it is accurate.
- **Licence:** new files carry `SPDX-License-Identifier: GPL-2.0-or-later`, consistent with the repository `COPYING`/`LICENSE`. The harness links only the project library and the system/Homebrew libraries recorded in `build_options.txt`.

## Commands (all exit 0)

```
git checkout --detach bb08502ee7b5c2275fdc880c3a80a668356453e5; git status --short; git merge-base HEAD 3691374…
git diff --name-only 3691374061f782bc84531fd1c79d017ddcb5a7c2 HEAD | grep -v '^docs/post_rc0/issue265_oracle_20261022/'   # empty
shasum -a 256 fixtures.txt PRE_RUN_CRITERIA.txt fixtures_followup_subnormal.txt harness/roundtrip_oracle.cpp
diff receipts/iteration1_json_escape_defect/summary_INVALID_JSON.json receipts/iteration2/summary.json
shasum -a 256 /tmp/mc265-oracle-20261022/{out/roundtrip_oracle,out_iter1/roundtrip_oracle,build/libmotioncorr_core.a,out/run/*.csv,out_iter1/run/*.csv}   # read-only
cmp / diff -rq of committed written_star/fullprecision_star vs scratch out/run and out_iter1/run
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  /Users/alex.konstantinov/.local/bin/python3 -B -I scripts/independent_check.py <packet> > independent_check.json
```

## Limits of this review

Host arithmetic only. I did not rebuild the library or harness and did not execute any binary, so native reproduction rests on the
author's receipts plus hash identity of the scratch artifacts. The 9.7 MB per-sample CSV was hashed (`6da068ed…`, 54,601 lines) but
not re-parsed; samples were reconstructed from the coefficients instead. The libstdc++ and RELION readers were not exercised.

## Publication readiness

Ready to publish as a **prerequisite-only DRAFT** after M1 and M2 are reworded. L1-L4 are recommended in the same pass. It is not
evidence for a production fix, any real-movie accuracy, a tolerance or gate, or CUDA behaviour. #265 stays FILED ONLY.

## Unresolved needs

1. Maintainer decision on the parity-breaking CPU-and-CUDA STAR output change (`ad0b230` parity; §9 item 2).
2. Actual pre-write native coefficients for the 10641 run (the exported, `bin_factor`-scaled copy if early binning applies), to size the real effect.
3. Linux GCC/libstdc++ reader behaviour on subnormal and full-precision tokens (measure; not inferable from this Mac run).
4. A write-side policy for subnormal and non-finite coefficients, and a separate decision on `global_shift` table precision.
5. RELION reader/writer interoperability with full-precision motion tables (not run).
