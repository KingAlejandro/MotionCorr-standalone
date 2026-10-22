<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# #265 oracle: Linux GCC/libstdc++ follow-up, frozen protocol

Frozen by the commit that contains this file, before any fixture is run on Linux. The run receipt records that commit SHA.
Written 2026-10-22 about 22:01Z. The harness build and the source/library identity preflight (below) were done before this freeze; they ran no fixture.

Scope: one bounded, host-only, CPU-only platform measurement of the real `ThirdOrderPolynomialModel::write`/`read` and `MetaDataTable`
formatter and parser on Linux GCC/libstdc++, to resolve the platform prerequisite left open by the Mac (libc++) oracle. It is not an
approved source fix, not a 10641 or any real-movie claim, not a performance claim, not CUDA/GPU. #265 stays FILED ONLY. The original
Mac result (frozen K2 **NOT MET**, F09 read failure) is immutable and is not re-evaluated here.

## Identity (all verified before the freeze; receipts in `preflight/`)

- Tested source: `3691374061f782bc84531fd1c79d017ddcb5a7c2` (main). Tree: `/mnt/clathrin/alex-motioncorr-guard264-20261022-0a1f64ab3e19/src-base`,
  read only. All 7216 tracked files hash blob-for-blob to `git ls-tree -r 3691374`; no untracked or ignored files; no file newer than the library
  (`preflight/source_identity.txt`; manifest sha256 `213a6227…c057`). Actual model, formatter and parser blobs: `micrograph_model.cpp 437600458505…`,
  `metadata_table.cpp a98d204ddb90…`, `metadata_label.h 9168c4ff7996…`, `micrograph_model.h 78c5b844802f…`, `metadata_table.h c528756e6bd8…`, `error.h 72bac222446e…`.
- Library, not rebuilt: `.../build-base-cpu/libmotioncorr_core.a`, sha256 `0a387aec60cae97721eccea46b3afa1a09d00f9c5c7ac63efd9cf2af11f6e72a`,
  Release, `CUDA=OFF`, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, no `-march`, `MOTIONCORR_CPU_DOSE_SYMMETRY_MODE=2`, compiler `/usr/bin/c++` g++ 13.3.0,
  0 cuda/cufft/nvcomp symbols (`preflight/library_identity.txt`). Its build-time source state is not independently recorded beyond the above.
- Runtime libraries on this host: glibc 2.39, `libstdc++6` 14.2.0 package (the executable resolves `libstdc++.so.6` at run time; it was compiled with g++ 13.3 headers).
- Harness: original, unmodified `harness/roundtrip_oracle.cpp` `5e69f974b4f44aaddfa2894bde55107a1e7327cbd8bc2b7559421c6b6b2f0235`, built against that library with the
  library build's own defines/includes/flags/link line (`preflight/build_options.txt`), build exit 0, empty stdout/stderr. Binary
  `.../bin/roundtrip_oracle_linux` sha256 `fc869fc361533596ea889b76907c00df287265857ec92c957eec3d98537c76fe`; `ldd`/`NEEDED` list no CUDA library (`preflight/harness_identity.txt`).
- Inputs, unchanged from the Mac campaign: `fixtures.txt` `ef11984e8a812f3e5274298f30a575728b5e85d34024fc6e1535398e76f2bb2d` (11 fixtures) and
  `fixtures_followup_subnormal.txt` `df86b048c81b7502a319db2248952b156e3fb6a6736d89a2880bd790fa3100b9` (already labelled post hoc; G00, G01, G02).
- Frozen hash list for the launch: `expected_hashes.txt` (this directory). `run_linux.sh` refuses to run on any mismatch (UNRUN).
- Mac references for diagnostic comparison, committed and immutable: `receipts/iteration2/coefficients.csv` `720f1663…`, `receipts/iteration2/summary.json` `55cd1645…`,
  `receipts/followup_subnormal/coefficients.csv` `39777644…`, `receipts/followup_subnormal/summary.json` `05a7e79b…`, `receipts/iteration2/written_star/*`.

## Launch (exactly once, no retry)

Host `4GPUs` (4-gpu-vm). Scratch `/mnt/clathrin/alex-motioncorr-star265-linux-20261022-d9d2c4ab` (cap 1 GiB; 5 MiB used before launch). Resources: CPU 16 only,
`taskset -c 16`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `LC_ALL=C`; nonblocking `flock -n` on `/tmp/motioncorr-star265-cpu16.lock`. No GPU, no `nvidia-smi`, no
build after this point. Fresh read-only host/process/affinity/space preflight is captured by the script at launch.

```
taskset -c 16 bash $W/inputs/run_linux.sh $W <this-protocol-commit-sha>
  A: $W/bin/roundtrip_oracle_linux $W/inputs/fixtures.txt $W/out_main
  B: $W/bin/roundtrip_oracle_linux $W/inputs/fixtures_followup_subnormal.txt $W/out_followup     (run after A, same launch)
```

Stop and report, without retry or repair in place: lock contention; any hash mismatch; a foreign non-kernel process using at least 5 % CPU whose last CPU is 16 at
launch; scratch above the cap. A failed or invalid outcome is retained as measured.

## Expected outcomes, written before the run

These are predictions, not criteria to pass. Where the measurement differs, the measurement is reported.

- X1. Written STAR text is byte-identical to the Mac `written_star/*` for every original fixture (same `snprintf` rules; both platforms use correctly rounded decimal conversion).
- X2. Real route, F00 and F01: all coefficients bit-equal, every shift error exactly 0.
- X3. Full-precision (TEST-ONLY) route: F00-F08 and F10 read and are bit-exact, as on the Mac.
- X4. F09 and G01/G02 full-precision (subnormal tokens): **unverified hypothesis**, not a measured fact: libstdc++'s `istream >> double` accepts underflow to a subnormal
  and returns the `strtod` value, so these read and are bit-exact (`0x1p-1074` for `4.94e-324`). This rests on the author's recollection of libstdc++'s conversion code
  (failbit only on overflow) and was not checked against source or run before this freeze. Either outcome is recorded.
- X5. G00 (smallest normal, `1e-300`, `-0`): full-precision bit-exact, as on the Mac.
- X6. K3 injected control (same criteria as `PRE_RUN_CRITERIA.txt`): measured max |dy| equals the predicted value to relative 1e-9, dx exactly 0, argmax at frame 49.

## Platform criteria and what is reported (frozen)

Each is reported separately as MET, NOT MET or UNRUN, from the harness outputs, never from a harness exit code. Harness exit 0 means only that it completed; `any_read_failed:true`
is reported as such.

- LK1: F00 and F01, real route: 0 coefficients not bit-equal and max shift error exactly 0.
- LK2: the frozen original K2 statement applied to Linux: all 11 original fixtures, full-precision route, read succeeds and 0 coefficients not bit-equal and shift error exactly 0.
  The result is NOT MET if any fixture fails, and F09's own outcome (read_ok, message, bit equality of its coefficients) is stated distinctly beside it. This does not change the Mac K2 status.
- LK3: K3 control as in `PRE_RUN_CRITERIA.txt` (relative difference below 1e-9, dx exactly 0, argmax frame equals the predicted frame).
- LKF: follow-up table G00, G01, G02: per fixture, full-precision read_ok and 0 coefficients not bit-equal (reported per fixture, no combined verdict).
- Subnormal reader behaviour: reported per fixture from the full-precision route: read_ok, the real reader's error text if any, and the read-back coefficient bits.
- Signed zero: F09 X3/Y0 and G00 X3 (`-0.0`): written token and read-back bits, real and full-precision routes.
- Smallest normal / tiny: G00 X0 (`2.2250738585072014e-308`), X1, and `1e-300`: tokens and read-back bits, both routes.
- Diagnostic Mac comparison, no gate, no tolerance: (a) `cmp` of each Linux written STAR with the Mac one; (b) count of rows of `coefficients.csv` where `written_token` or `post_read_hex`
  differs from the Mac file for the same (fixture, route, coefficient); (c) per fixture and route, the Linux/Mac values of `max_vec` and their relative difference. Shift differences
  in the last bits are possible (the Mac build is AppleClang arm64 `-O3`; this one is GCC x86-64 without FMA); they are reported as measured.

No timing is recorded or claimed. Outputs kept in the repository are compact (summaries, coefficient tables, STAR files, per-frame table, receipts); the full per-sample CSV stays in scratch with its hash.
