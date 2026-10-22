# Independent review R1: #265 oracle Linux GCC/libstdc++ follow-up

- Reviewed SHA: `9a61a0e78c1de6ccae2551a3479bf44e9acdacc8` (scripts `990cbd4c`, frozen protocol `65784e25`, results `9a61a0e7`; base reviewed Mac packet `d9d2c4ab`; tested source main `3691374061f782bc84531fd1c79d017ddcb5a7c2`).
- Reviewer worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-9771d90c`, detached at `9a61a0e7`, clean (0 porcelain lines). The author worktree was not touched.
- Method: host-only, on the Mac, Python 3 (`/Users/alex.konstantinov/.local/bin/python3 -I -B`), one thread. I wrote my own checks and did not run any bundled script or binary. There was no SSH, GPU, build, native application or movie run.
- Verdict: **no material finding**. Every frozen criterion LK1, LK2, LK3 and LKF reproduces from the raw committed CSV/JSON/STAR receipts with my own code. Provenance and freeze order hold. There are four low documentation findings. L1 and L4 should be fixed before publication.
- Publication: ready as a **DRAFT prerequisite-only** packet once L1 and L4 are fixed. #265 stays FILED ONLY. The Mac K2 **NOT MET** is unchanged and is correctly kept separate from the Linux LK2.

## Scope and delta

- `git diff --name-only 3691374..9a61a0e7` touches only `docs/post_rc0/issue265_oracle_20261022/`. `d9d2c4ab..9a61a0e7` touches only `linux_followup/`. There is no `src/`, `tests/`, CMake or parent-packet delta.
- Between `d9d2c4ab` and `9a61a0e7` the harness, `fixtures.txt` and `fixtures_followup_subnormal.txt` blobs are unchanged: `cdc58009`, `e7efac92` and `d8a1162a` at `bb08502e`, `f4fc5172`, `d9d2c4ab` and `9a61a0e7`. Their sha256 values `5e69f974…`, `ef11984e…` and `df86b048…` equal `expected_hashes.txt`.
- The new `.md`, `.sh` and `.py` files carry `SPDX-License-Identifier: GPL-2.0-or-later`. The repository is GPL-2.0 (`LICENSE`, `COPYING`). The harness links only the project's own library and system libraries. There is no third-party code and no licence conflict.

## Provenance and freeze order (checked)

- **Source manifest.** I regenerated it locally from `git ls-tree -r 3691374` (`sha  path`, `LC_ALL=C sort -k2`). It gives sha256 `213a6227…c057` and 7216 entries, with no symlinks or submodules. This equals both the frozen `mc265-main-blobs.txt` hash and the remote `src_blobs.txt` hash in `preflight/source_identity.txt`. The six model, formatter and parser blob ids in that file equal `git ls-tree 3691374` for `src/error.h`, `metadata_label.h`, `metadata_table.{cpp,h}` and `micrograph_model.{cpp,h}`.
- **Library.** The receipt shows `CUDA:BOOL=OFF`, Release, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, no `-march`, 0 cuda/cufft/nvcomp symbols, mtime 21:09:22Z and sha256 `0a387aec…`. The harness was built with the library's own `flags.make` defines, includes and flags and the `motioncorr` link line. Build exit 0, empty output, `ldd` and `NEEDED` show no CUDA. The library's build-time source state rests on tree identity and file times, as the README states.
- **Freeze order.**
  - The scripts commit (`990cbd4c`, 21:59:27Z) precedes the build preflight (21:59:44Z).
  - The protocol commit (`65784e25`, 22:01:12Z) precedes the launch (22:01:23Z).
  - The `git show 65784e25:` blobs of `PROTOCOL_FROZEN.md`, `run_linux.sh` and `build_linux.sh` hash to `52e24904…`, `e2e22643…` and `ae888a89…`. These equal `expected_hashes.txt`, and `receipts/launch/hash_check{,_after}.txt` reports all nine entries OK.
  - `receipts/launch/frozen_protocol_commit.txt` is `65784e25…`.
  - `PROTOCOL_FROZEN.md`, `expected_hashes.txt`, both scripts and `preflight/` are unchanged between `65784e25` and `9a61a0e7`.
  - Commit times are self-reported. The SHA in the receipt shows that the protocol content existed at launch, provided the receipt is authentic.
- **Single launch.**
  - `run_linux.sh` writes `launched` before the hash check and refuses a second launch (exit 95).
  - Affinity was `16`, with `OMP_NUM_THREADS=1` and `LC_ALL=C`.
  - Exits were A 0, B 0 and hash-after 0, with empty stderr.
  - Scratch was 18136 KiB (17.7 MiB).
  - Linux `samples_full.csv` has 57201 lines against the Mac's 54601. The 2600 extra rows are exactly the F09 full-precision route that the Mac could not read.

## Results reproduced with my own code (`check.py`, `check.json`)

- **STAR raw bytes.** `cmp` shows all 11 `written_star` files and all 12 `fullprecision_star` files (11 plus the K3 injected file) byte-identical to the Mac's `receipts/iteration2/`, including F09.
- **Coefficient rows.** There are 792 main rows and 216 follow-up rows. Per row:
  - `bit_equal` agrees with my own bit comparison of `pre_write_hex` and `post_read_hex` in every row.
  - The decimal `pre_write` decodes to the same bits as its hex.
  - Python's correctly rounded `float(written_token)` equals the libstdc++ read-back bits for every row on both routes.
- **Full-precision tokens.** Every token in every Linux full-precision STAR decodes exactly to the pre-write double. This includes `4.9406564584124654e-324` (bits `0x0000000000000001`), `9.9999999999999694e-311` and `-0`.
- **Not-bit-equal counts.**
  - Real route: F00 0, F01 0, F02 36, F03 1, F04 1, F05 22, F06 22, F07 36, F08 5, F09 3, F10 4; G00 3, G01 1, G02 1.
  - Full-precision route: 0 for all 14 fixtures. Every full-precision route read OK.
- **Signed zero.** F09 coefficients 3 (X3) and 18 (Y0), and G00 X3, are written `-0.000000` on the real route and `-0` on the full-precision route. All read back as `-0x0p+0`, with the sign bit preserved.
- **Subnormals on the real route.** F09 X2 and G02 X0 (`4.94e-324`) are written `4.940656e-32` and read back as `0x1.0088952d9fea4p-104`. G01 X0 is written `1.000000e-31` and read back as `0x1.039d66589688p-103`. The README description matches.
- **Comparison with the Mac.**
  - Main: 756 common rows. Follow-up: 144 common rows. Only-Linux rows: 36 (F09 full precision) and 72 (G01 and G02 full precision). There are no Mac-only rows.
  - `written_token` text differs in 0 rows. Pre-write bits differ in 0 rows and post-read bits in 0 rows.
  - `pre_write_hex` text differs in 3 rows: F09 X2 real, G01 X0 real and G02 X0 real. In each case it is glibc `0x0.…p-1022` against Apple `0x1…p-10xx`, with identical bits.
- **Criteria.**
  - **LK1:** MET (F00 and F01 real route, 0 not-bit-equal, all errors 0).
  - **LK2:** MET (all 11 read, 0 not-bit-equal, `max_vec` 0). F09 is distinct: `read_ok` true, 0 not-bit-equal.
  - **LKF:** G00, G01 and G02 each `read_ok` true with 0 not-bit-equal.
  - **LK3:** I independently predicted Δ·z³·x·y with Δ = `9.999999999999972e-07`, z = 49 and x = y = −0.5, the basis of coeffY(17). That gives `0.029412249999999918`. Measured is `0.02941225000000003`, a relative difference of 3.77e-15. dx is exactly 0 and the argmax is G1 frame 49, matching the harness.
- **Field error.** I recomputed it at all 224 recorded worst samples (every range of every readable route, both tables) from the stored coefficients. I used `getShiftAt` exactly as in `src/micrograph_model.cpp:35-54`, in source order with plain doubles and no FMA.
  - All 4×224 pre/post shift values are bit-identical to the receipts.
  - 223 of 224 `vec` values are bit-identical. The exception is F10 early, which differs by 1 ulp because Python's `math.hypot` is a different implementation from glibc `hypot`.
  - Every range `max_vec` equals its recorded worst sample.
- **Parser path.** The real parser is `MetaDataTable::setValueFromString`: `std::istringstream >> double`, then a `std::ws`/eof check that reports `Invalid floating-point STAR value` (`src/metadata_table.cpp:436-442`). The platform difference therefore sits in the C++ library's `num_get`. libstdc++'s `num_get` lives in the shared library, so the run-time libstdc++ 14.2 governs. The Mac error texts for F09, G01 and G02 are retained unchanged.

## Linux/Mac numeric differences (diagnostic only)

- Overall `max_vec` is bit-identical for 9 of 11 real-route fixtures. F02 differs by relative 7.86e-13 and F07 by 2.35e-14.
- Per-range differences also occur in F05 (relative up to 7.4e-7, for example late24 `4.793203e-03` against `4.793206e-03`), F06 (up to 2.6e-7), F09, F10 and G00. F09, F10 and G00 differ by 1 ulp of the error value.
- Every differing range has its worst sample at the same frame and pixel on both platforms. The absolute difference is between 0.008 and 4.0 ulp of that sample's shift magnitude.
- Reviewer diagnostic (`mac_eval.py`, `mac_eval.json`): plain source-order non-FMA evaluation reproduces the Linux worst-sample shifts in 176/176 main-table cases, but the Mac's only in 131/168. The 37 mismatches are in F02, F05, F06, F07 and F09.
- This fits floating-point contraction in the AppleClang arm64 build. I did not model contraction, so the cause is **not isolated**. The README correctly does not assert one.

## Findings

**L1 (low; fix before publication). The opening paragraph overstates shift-error identity.**
- `linux_followup/README.md`, opening paragraph, line 7: "The real serializer's coefficient and shift errors are identical to the Mac's."
- Coefficient errors are bit-identical. Shift errors are not: two fixtures differ in overall `max_vec`, and several per-range maxima differ by up to relative 7.4e-7. The "Mac comparison" paragraph of the same README says so.
- The author response repeats the claim ("the real-route errors match").
- Scenario: a reader of only the opening takes it as bit-identical shift errors across platforms.
- Fix request: "coefficient errors are bit-identical; shift-error maxima are identical except last-bit differences (overall ≤7.9e-13 relative; per range ≤7.4e-7 relative, at the same worst samples)".

**L2 (low). The README misdescribes what the frozen text asked for in the Mac comparison.**
- README "Mac comparison" paragraph: "the frozen text asked for the textual count, which is reported as well."
- `PROTOCOL_FROZEN.md` (b) asked for rows where `written_token` or `post_read_hex` differs. It does not mention `pre_write_hex`. Those frozen counts are 0 and 0, both textual and bit-level.
- The `pre_write_hex` comparison, textual (3) and bit-level (0), is entirely post hoc. `compare_platforms.py` labels its bit-level addition and keeps the textual counts, so nothing was relaxed.
- Fix request: state the frozen (b) result (0/0) and label the whole `pre_write_hex` comparison post hoc.

**L3 (low). The cancellation attribution is imprecise.**
- README "Mac comparison" paragraph: "consistent with the earlier review note about cancellation in very large shifts."
- F05 and F06 worst samples do have shifts of 1.3e6 to 7.6e7 px.
- F02 and F07, the only fixtures whose overall `max_vec` differs, have worst-sample shifts of only 0.19 to 190 px. There, a 1 to 4 ulp shift difference is amplified because the error is about 1e-3 of the shift.
- Suggest: "last-bit shift-evaluation differences (≤4 ulp of the shift at the same worst samples), amplified by the post−pre subtraction; cause not isolated". The reviewer non-FMA reproduction may be cited as a diagnostic, not as a cause.

**L4 (low–medium; fix before publication). The parent packet still states that Linux is unmeasured and gives no pointer to the follow-up.**
- These lines still say the Linux libstdc++ reader behaviour is unmeasured or open:
  - `README.md:86`
  - `README.md:123-124` ("Unmeasured boundaries")
  - `README.md:147`
  - `DESIGN_NOTE.md:54`
  - `DESIGN_NOTE.md:81`
- Nothing links to `linux_followup/`.
- Scenario: a maintainer reading the design note for the M-decision sees an open prerequisite that has now been measured for one host and toolchain.
- Fix request:
  - Add a one-line dated pointer at each place, without rewriting the Mac results or the K2 NOT MET. For example: "Measured afterwards on one Linux host and toolchain (GCC 13.3 / libstdc++ 14.2, glibc 2.39): the real reader accepts these tokens bit-exactly; see `linux_followup/`. Other toolchains and RELION remain unmeasured."
  - Advisory for `DESIGN_NOTE.md:53`: the measured platform split means a full-precision writer's subnormal tokens would read on this Linux build and fail on a libc++ build. Cross-platform file portability therefore belongs in the open write-side policy question. It is not a reason to adopt anything.

**Advisories (no change required).**
- **A1. Interference check.** The foreign-process criterion (≥5 % CPU on CPU 16) was recorded with `ps pcpu`, a lifetime average taken from a last-CPU snapshot, and the script does not enforce it. Both receipts show only idle or kernel processes plus the run itself. This does not matter for a correctness-only run with no timing claim.
- **A2. Unreceipted details.**
  - "Lock checked free afterwards" has no receipt file.
  - The scratch `expected_hashes.txt` is not itself hashed in the receipt. Its file list matches the committed list.
  - The per-sample CSVs were hashed after the run, outside the launch script, and are labelled that way.
- **A3. Post-run comparison script.** `compare_platforms.py` is a report script written after the run and was not frozen. Its LK verdicts agree with my independent derivation from raw receipts.

## Checks that were not run

- I did not inspect remote scratch, the 9 MB per-sample CSVs or the library build. I did not rerun the Linux harness, and I did not check that libstdc++'s conversion code accepts underflow. The X4 result is a measurement on one host, as the README states.
- I did not repeat the Mac R1/R2 full-grid arithmetic. The coefficient bits and STAR bytes are identical across platforms, so those conclusions carry over except for the last-bit differences quantified above.

## Unresolved needs (unchanged; none closed by this follow-up)

- Real pre-write coefficients for 10641, including the `bin_factor`-scaled exported copy under early binning. The constructed 0.34–0.56 px late-frame errors do not confirm the real ~0.4 px.
- Behaviour of RELION's reader and writer and of older MotionCorr builds. Other Linux toolchains, libc++ on Linux and other glibc versions.
- A write-side policy for subnormal and non-finite coefficients, now including cross-platform portability.
- `global_shift` table precision, which is out of this oracle.
- The maintainer's CPU/RELION `ad0b230` parity decision for any serializer change on the shared CPU and CUDA write path.
- No tolerance, gate, harm model, PASS promotion, CUDA, performance or science claim follows from this packet.

## Commands

```
git checkout --detach 9a61a0e78c1de6ccae2551a3479bf44e9acdacc8   # status clean
git diff --name-only 3691374..HEAD ; git diff --name-only d9d2c4ab..HEAD
git ls-tree -r 3691374 | awk -F'\t' '{split($1,a," "); print a[3]"  "$2}' | LC_ALL=C sort -k2 | shasum -a 256   # 213a6227…
git show 65784e25:<path> | shasum -a 256   # PROTOCOL_FROZEN.md, run_linux.sh, build_linux.sh
python3 -I -B /tmp/motioncorr-star265-linux-review-r1-20261022/check.py .      > check.json      # rc 0
python3 -I -B /tmp/motioncorr-star265-linux-review-r1-20261022/mac_eval.py .   > mac_eval.json   # rc 0
diff receipts/iteration2/stdout.txt linux_followup/receipts/launch/stdout_main.txt   # F05 late24 digit; F09 read fail vs ok
```

All commands ran from `docs/post_rc0/issue265_oracle_20261022`, with one numeric thread on a busy host (load about 5).
