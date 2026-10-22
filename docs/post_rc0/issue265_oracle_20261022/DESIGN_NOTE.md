<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# #265 possible motion-table `max_digits10` interface: preparation note

Status: preparation only. Source behaviour is unchanged, and no fix is authorised. #265 stays filed pending the
maintainer's parity decision (the formatter is inherited from RELION `ad0b230`).

## Where the loss happens

`ThirdOrderPolynomialModel::write` (`src/micrograph_model.cpp`) calls `MD.setValue(EMDL_MICROGRAPH_MOTION_COEFF, …)`.
`MetaDataTable::write` formats every double label through `getValueToString` (`src/metadata_table.cpp:252-278`): `%12.6f`
for positive values, `%12.5f` for negative values, `%12.6e` / `%12.5e` when `0 < |v| < 0.001` or `|v| > 100000`, into
`char buffer[14]` with `snprintf(buffer, 13, …)`. The oracle measured two effects:

- Fixed notation keeps 6 (positive) or 5 (negative) decimals, so significant digits depend on magnitude. -0.00122271287007 is written as `-0.00122` (3 digits).
- Scientific notation (|v| < 0.001 or |v| > 100000) keeps 7 significant digits for positive and 6 for negative values. Measured: 123456.789 is written `1.234568e+05`,
  100000.1234567 as `1.000001e+05` (reads back 100000.1), -100000.5 as `-1.00000e+05` (abs error 0.5), while 100000.5 round-trips as `1.000005e+05`.
- The 12-character cap (`snprintf(buffer, 13, …)`) truncates only text of 13 or more characters: three-digit exponents (`1e-300` is written `1.000000e-30` and reads back as `1e-30`;
  `4.94e-324` as `4.940656e-32`) and `-99999.99999995` (`-100000.0000`). These matter only for magnitudes outside any plausible motion coefficient.

## Interface options

1. **Per-label or per-table precision flag on `MetaDataTable`** (smallest change). Default off, so every other table is
   byte-identical. `ThirdOrderPolynomialModel::write` turns it on for its own table before `MD.write`.
   `getValueToString` then formats doubles of that table with `%.17g` into a buffer of at least 32 bytes
   (`-1.2345678901234567e-308` is 24 characters).
2. **Model-local formatting.** `ThirdOrderPolynomialModel::write` writes the block text itself and does not use the generic
   formatter. Duplicates the STAR framing (header, `loop_`, labels) and so can drift from the generic writer; not recommended over option 1.

17 significant digits is `std::numeric_limits<double>::max_digits10`. The shortest round-trip form (`std::to_chars`)
would give shorter files but depends on the standard library's floating-point `to_chars`; this note does not choose.

## Byte compatibility

- Every STAR table other than the motion-model table must be byte-identical before and after. A guard for that is part of
  any future change.
- The motion-model table bytes change for every coefficient, including ones that already round-trip (`0` stays `0`
  numerically but its text changes from `0.000000` to `0`, and column width changes). Anything that compares the
  motion-model block textually must be updated. Files that mention the label or block in the repository today:
  `tests/test_input_formats.py`, `tests/test_runner_contract.py`, `tests/test_micrograph_model_bounds.py`,
  `tools/compare_motioncorr.py`, `tools/test_compare_motioncorr.py`, `tools/motion_field.py`. This list is by name
  search only; whether each depends on the text of the block was not checked.
- The `global_shift` table uses the same formatter (5 to 6 decimals), so a reloaded `Micrograph::getShiftAt` still carries a
  global-shift rounding of up to about 5e-6 px per component. That is outside #265's coefficient scope and the oracle does
  not measure it; it is a separate decision if round-trip exactness of the whole model is wanted.
- Output MRC images use the in-memory model and are not affected.

## Parser and backward compatibility

- `MetaDataTable::setValueFromString` parses doubles with `std::istringstream >> double` and requires the whole token.
  Measured: the full-precision tokens actually read, such as `-0.0012227128700699999` (F03 X idx 2) and `2.2250738585072014e-308` and `-0` (G00), are read back bit-exactly.
- Measured, macOS arm64 / AppleClang / libc++: a **subnormal** token (`4.94e-324`, `1e-310`) makes the real reader throw
  `Invalid floating-point STAR value`, because libc++ sets failbit on underflow. Today the same coefficient is silently written
  as an exponent-truncated number that reads back as a different tiny value. A full-precision writer would turn that
  case from a wrong value into an unreadable file on libc++. Whether the project's Linux GCC / libstdc++ reader accepts
  subnormals was not measured here (Mac only), and it is not assumed to match; it must be measured before any write-side decision.
  The frozen K2 criterion (full-precision bit-identity for every fixture) is therefore NOT MET in the oracle's results (F09 read failure), and that failure is retained. Real motion coefficients are never subnormal; a future change should still
  decide whether to flush or reject them at write time.
- Files written at full precision are still ordinary whitespace-separated doubles, so the current reader parses them (measured). RELION's reader
  shares this parsing code by inheritance; it was not run here. Existing 5-6 decimal files keep reading unchanged. Non-finite values are already rejected by
  `ThirdOrderPolynomialModel::read`; the writer should refuse them rather than emit `nan`/`inf` text.

## What a future approved change must test, with pre-write native coefficients

- The reference must be the native `ThirdOrderPolynomialModel` doubles held in memory at the moment `Micrograph::write`
  runs: captured as hex floats or a cloned model, or constructed directly as in this oracle. With early binning
  (`do_own && early_binning`) `MotioncorrRunner::writeModel` writes a copy whose coefficients are multiplied by `bin_factor`; the capture must be that exported copy,
  not `mic.model`, otherwise the reference is in binned pixels and the comparison is wrong. It must not be a model re-fitted
  to, or read back from, a rounded STAR file. Reading the 10641 STAR and comparing against a refit would measure the refit.
- Compare the same compiled `getShiftAt` before write and after the real `read`, per component, in absolute unbinned px, over
  the movie's actual frame range and image geometry, and report the worst sample.
- Include the controls from this oracle: exact-representable and zero fixtures (no change expected), the
  -0.00122271287007 probes in a pure-time and a cross term, and an injected-error control showing the harness detects a
  1e-6 coefficient change at the predicted sample.
- The discriminating test must fail on the current formatter (`real-write-read` rows of `receipts/iteration2/summary.json`)
  and pass with the change, with bitwise coefficient equality as the criterion.
- The write path is shared source, not CPU-only. `MetaDataTable::getValueToString` and `ThirdOrderPolynomialModel::write` are compiled into `motioncorr_core` in every
  configuration, and the STAR is written by `MotioncorrRunner::writeModel` from the backend-common run loop and `saveModel`. A full-precision motion table therefore changes
  CUDA-route STAR output as well as CPU. Under `docs/release/POST_FREEZE_TEST_PLAN.md` §9 item 4 that is the "CUDA or shared source" class: full CTest on all three
  configurations, the checklist rows the changed route touches, the format rows its code touches, and native execution on a GPU. Compilation does not qualify it.
- Because the change alters STAR output and breaks parity with RELION `ad0b230`, it needs maintainer sign-off first (`AGENTS.md`; §9 item 2). Scheduling it separately from C1 is a recommendation, not a rule.
- Unmeasured and open: Linux libstdc++ reading of subnormal and full-precision tokens; RELION reader/writer interoperability with full-precision motion tables; a write-side policy for subnormal and
  non-finite coefficients; and `global_shift` precision (above).
