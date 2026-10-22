<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# #265 oracle: Linux GCC/libstdc++ platform follow-up

Result: on Linux, the real `ThirdOrderPolynomialModel::read` accepts every full-precision token in the frozen tables, including the subnormals that the Mac
(libc++) reader rejects. All 11 original fixtures and the 3 follow-up fixtures round-trip bit-exactly through the full-precision TEST-ONLY file, so the frozen K2
statement applied to Linux is **MET** (LK2). The original Mac result, K2 **NOT MET** because of the F09 read failure, is a different platform's result and is unchanged.
The real serializer's coefficient errors are bit-identical to the Mac's. Shift-error maxima have small platform differences: overall maxima differ by up to 7.9e-13 relative and per-range maxima by up to 7.4e-7 relative, at the same worst samples. This is platform evidence for a prerequisite question. It is not a source fix, not a
10641 or any real-movie claim, not CUDA/GPU, and has no performance claim. #265 stays FILED ONLY.

## What ran (once; no retry)

- Tested source: main `3691374061f782bc84531fd1c79d017ddcb5a7c2`, read-only tree `/mnt/clathrin/alex-motioncorr-guard264-20261022-0a1f64ab3e19/src-base`.
  All 7216 tracked files are blob-identical to `git ls-tree -r 3691374`, no untracked/ignored files, nothing newer than the library (`preflight/source_identity.txt`).
- Library, not rebuilt: `build-base-cpu/libmotioncorr_core.a` `0a387aec60cae97721eccea46b3afa1a09d00f9c5c7ac63efd9cf2af11f6e72a`, Release, `CUDA=OFF`,
  g++ 13.3.0 `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, no CUDA symbols (`preflight/library_identity.txt`). Run-time glibc 2.39, `libstdc++6` 14.2.0.
- Harness: the original `harness/roundtrip_oracle.cpp` `5e69f974…f0235`, unchanged; binary `fc869fc3…c76fe`; flags and link line copied from the library's own build; no CUDA in `ldd`
  (`preflight/build_options.txt`, `preflight/harness_identity.txt`). Inputs unchanged: `fixtures.txt` `ef11984e…`, `fixtures_followup_subnormal.txt` `df86b048…`.
- Launch: 2026-10-22 22:01:23Z to 22:01:24Z on `4GPUs` (4-gpu-vm), `taskset -c 16` (`Cpus_allowed_list: 16`), `OMP_NUM_THREADS=1`, `LC_ALL=C`, nonblocking `flock` on
  `/tmp/motioncorr-star265-cpu16.lock` (released on exit; the author reported a later free-lock check, but no separate receipt records it), no foreign process above 5 % on CPU 16, no GPU or `nvidia-smi` use.
  Exits: table A 0, table B 0, frozen-hash check before and after 0. Empty stderr for both. Scratch used 17.7 MiB of the 1 GiB cap.
  Receipts: `receipts/launch/` (argv, stdout, stderr, exits, host before/after, hash checks, frozen protocol commit).
- Frozen protocol: `PROTOCOL_FROZEN.md`, committed as `65784e25c3e74c498b56124bbf102305e33a22c8` before the launch, and recorded in `receipts/launch/frozen_protocol_commit.txt`.
  The scripts (`build_linux.sh`, `run_linux.sh`) were committed earlier as `990cbd4c9497763684539e4549c175960966d9e1`. The harness build and identity preflight ran before the freeze and ran no fixture.

## Results against the frozen expectations and criteria

| item | frozen expectation | measured |
|---|---|---|
| LK1: F00/F01 real route exact | X2 | **MET**: 0 coefficients not bit-equal, shift error exactly 0 |
| LK2: all 11 fixtures, full precision, read and bit-exact | X3, X4 | **MET**: all 11 read, 0 coefficients not bit-equal, shift error 0. F09 distinctly: read_ok true, 0 not bit-equal (Mac: read failed) |
| LK3: injected +1e-6 control | X6 | **MET**: relative difference 3.77e-15, dx exactly 0, argmax frame 49 = predicted (same numbers as the Mac) |
| LKF: G00, G01, G02 full precision | X4, X5 | each read_ok true, 0 not bit-equal |
| X1: written STAR bytes equal the Mac's | predicted identical | byte-identical for all 11 `written_star` files and all 12 `fullprecision_star` files (11 fixtures plus the K3 injected file), including the F09 file the Mac reader then rejected |
| X4: libstdc++ accepts subnormals | unverified hypothesis | **observed accepted**: `4.9406564584124654e-324` read back as the same double, `9.9999999999999694e-311` likewise |

Subnormal, tiny and signed-zero reader behaviour (real reader, `platform_comparison.json` `special_coefficients`): full-precision tokens read back bit-exactly for
`4.9406564584124654e-324`, `9.9999999999999694e-311` (the double nearest 1e-310), `2.2250738585072014e-308`, `-2.2250738585072014e-308`, `1e-300`, `-1e-300`, and `-0` for the signed zero (F09 X3/Y0,
G00 X3). The real route's behaviour is the same as the Mac's: signed zero written `-0.000000` and read back as `-0`; `1e-300` written `1.000000e-30`; `2.2250738585072014e-308` written `2.225074e-30`;
subnormals written as the exponent-truncated `4.940656e-32` / `1.000000e-31` and read back as those different tiny values.

Mac comparison (diagnostic, no gate; `platform_comparison.json`): over 756 + 144 shared coefficient rows, `written_token` differs in 0 and the read-back bits differ in 0. `pre_write_hex` differs
textually in 3 rows only because glibc and Apple print `%a` for a subnormal differently (`0x0.0000000000001p-1022` vs `0x1p-1074`); the decimal value and the bit pattern are identical. The entire pre_write_hex comparison (textual and bit-level) is post hoc. The frozen comparison asked about written_token and post_read_hex; both recorded textual difference counts are zero. No frozen criterion was relaxed. The Mac has no full-precision row for F09, G01 and G02
(those reads failed), so 108 Linux rows have no Mac counterpart. Per-fixture overall `max_vec` is bit-identical to the Mac for 9 of 11 real-route fixtures; F02 differs by relative 7.9e-13 and F07 by 2.4e-14.
In the stdout table some per-range values (for example F05 late24, Linux `4.793203e-03`, Mac `4.793206e-03`) also differ in the last printed digits. The Mac build is AppleClang arm64 and this one is GCC x86-64 without FMA;
the differences are last-bit shift-evaluation differences (at most 4 ulp of the shift at the same worst samples), amplified by the post-minus-pre subtraction. The cause was not isolated; F02/F07 involve ordinary shifts as well as the large nonphysical probes.

## Limits

- One host, one GCC/libstdc++ build (run-time libstdc++ 14.2.0 against 13.3 headers), one run. Other Linux toolchains, libc++ on Linux and other glibc versions are not measured.
- This shows the reader accepts and reproduces these tokens, and that the real writer's output text is the same on both platforms. It does not show RELION's own reader or older MotionCorr builds read such files, and it
  does not decide a write-side policy for subnormal or non-finite coefficients, `global_shift` precision, or the parity question.
- The library's build-time source state is established by tree identity and file times, not by a record taken when it was built.
- The follow-up table and the 3 follow-up fixtures were already labelled post hoc in the Mac campaign. Constructed coefficients only; no claim about any real movie.
- The 10641 pre-write coefficients, including the `bin_factor`-scaled exported copy under early binning, are still needed to size the real effect.
- Harness exit 0 means only that the harness completed. The verdicts above come from the harness outputs.

## Files

`PROTOCOL_FROZEN.md`, `expected_hashes.txt`, `build_linux.sh`, `run_linux.sh`, `compare_platforms.py` (report-only; run after the launch), `platform_comparison.json`, `preflight/`, `receipts/launch/`,
`receipts/main/` (original 11 fixtures: `summary.json`, `coefficients.csv`, `per_frame_max_vec.csv`, `written_star/`, `fullprecision_star/`), `receipts/followup/` (same for G00-G02),
`receipts/samples_full.sha256.txt` (the 9 MB per-sample CSVs stay in scratch `/mnt/clathrin/alex-motioncorr-star265-linux-20261022-d9d2c4ab`, not deleted).

## Independent Linux review and parent response

Opus R1 at `9a61a0e78c1de6ccae2551a3479bf44e9acdacc8` found no material finding and independently reproduced LK1/LK2/LKF/LK3, coefficient bits, all23STAR byte comparisons and the recorded worst-sample arithmetic. Full report and checks are retained verbatim in `review/R1_opus/`. Parent corrected L1 shift-error identity, L2 post-hoc comparison labelling, L3 unisolated numerical cause, and L4 links/current platform scope in the parent packet. This is documentation only after review, not another numerical run or independent review round.

The launch script records the CPU last-processor/lifetime-average snapshot but does not enforce the stated >=5% process criterion; that is narrower than a continuous interference measurement. This untimed correctness run makes no performance claim. The free-lock observation has no separate receipt. Original Mac K2 NOT MET and all frozen Linux protocol/scripts/receipts remain unchanged.
