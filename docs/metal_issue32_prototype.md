# Issue #32: Current-main Metal prototype

**Status: executable prototype; relaxed Gate 2 is FAIL.** This report keeps the
implementation result separate from scientific acceptance and performance.

## Revision and platform

- Main base at port time: `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38` (PR #111 merge).
- Prototype: current-main port of the #30 build/dispatch work and #32 global
  alignment implementation. The published PR head identifies the exact final
  source revision.
- Host: Apple M4 Pro, 20-core GPU; macOS 26.7 (25G229); Xcode 27.0 (27A266a),
  macOS SDK 27.0.
- Build: Release, `-DMETAL=ON`, `-DCUDA=OFF`, using the project's Python
  environment with NumPy available.
- Binary SHA-256 for the retained run: `7ec9ebecbfcef77958081ed2b6677ea93e1236cb3c8812f83c252eb90604d6fc`.
- Requested Metal device: index 0, Apple M4 Pro.

## What ran

The executable reported device 0 and emitted a completion record for both
synthetic movies. Each record reported two iterations and the full ordered
stage list: `weights,reference,ccf,ifft,peak,fourier_shift`. Both CPU and Metal
processes exited 0, wrote non-empty MRC/STAR outputs, and had matching MRC
dimensions. The comparator checked all 8 frame shifts, all 16,384 output
pixels, and the STAR fields for each fixture.

Command (run once per fixture; `--include-subpixel` selects both fixtures):

```sh
/Users/alex.konstantinov/mc-env/bin/python3 tools/run_metal_synthetic_regression.py \
  --cpu-bin build-metal/motioncorr \
  --metal-bin build-metal/motioncorr \
  --device 0 \
  --fixture-dir test-data/fixtures \
  --include-subpixel \
  --output-dir metal-validation \
  --json-out metal-validation/report.json \
  --keep-artifacts
```

The retained execution logs and machine report are in the local validation
directory; the fixture hashes and result metrics below are copied from that
report.

## Acceptance results

The comparator's relaxed Gate 2 includes absolute image RMSE ≤ 0.020,
relative image RMSE ≤ 0.001, maximum pixel error ≤ 5, shift trajectory checks,
and STAR-field checks. Each row is an independent result; **an overall FAIL is
not converted to PASS because other checks succeeded.**

| Fixture | Trajectory RMS / max error (px) | Absolute image RMSE (limit 0.020) | Relative image RMSE (limit 0.001) | Max pixel error (limit 5) | STAR diffs | Result |
|---|---:|---:|---:|---:|---:|---|
| Integer shift | 0.0040607 / 0.0045830 | **0.03865797 — FAIL** | 0.00060139 — pass | 0.245544 — pass | 0 — pass | **FAIL** |
| Subpixel shift | 0.0025705 / 0.0041600 | **0.02206835 — FAIL** | 0.00034331 — pass | 0.126465 — pass | 0 — pass | **FAIL** |

Both CPU and Metal trajectories independently passed the retained known-motion
diagnostic. That does not override the CPU/Metal corrected-image failures. The
MRC comparator also reported four differing core-header bytes in each case;
the pixel and STAR metrics above are not a complete header-equality claim.

No tolerance was changed. Issue #32 remains open. No performance conclusion is
drawn from this two-fixture, one-run screen; the timing fields are execution
diagnostics only.

## Build and test status

- Metal-enabled Release build: passed on the host above.
- `MetalCompletionWitness`: one CTest passed; its controls accept a complete
  six-stage record and reject the old profile-only smoke record, a wrong device,
  an incomplete stage list, and a nonconverged record.
- Full CTest on clean current main `8323c55`: **17/18 passed**;
  `SyntheticRegression` failed its expected-image assertion (max pixel
  difference `23.6498567`, RMSE `0.3119288`; shifts were within `0.004671 px`
  max and `0.003305 px` RMSD). The same failure was seen on the Metal branch.
  This is a current-main baseline issue, not caused by the Metal changes.
- CPU-only build behavior is not established by this report.

## Fixture provenance

| Input | SHA-256 |
|---|---|
| Integer STAR | `61dde751f61f8ba82296b43bfcf831858a8c25cc71a650f3fe08b6ebcf19b28f` |
| Integer ground truth | `1507345754352386e5ef202b28dbe9d693a545480eeab9f0ce3c47da14b50009` |
| Integer movie | `44f32752ebb62fc22428e95a1449e54e3a6952036285b805b96085f296ec5ed0` |
| Subpixel STAR | `f754b4ed4ede6c7e55a8e1e300eba265989c9651908279fd4357a3b3c946e160` |
| Subpixel ground truth | `38e4ac009c3f73062c063b979a40cf103a077ee94326862f9a6b0a791865395b` |
| Subpixel movie | `27590926087551e607acf9fd11d11de294ed63005e4647861a94b5ae2bbf93b7` |

## Scope and remaining work

This is an opt-in global-alignment prototype. Local patch alignment and dose
weighting remain on their existing paths. The next scientific step is to
diagnose the absolute image RMSE difference without changing any gate, then
rerun both cases plus discriminating negative controls on the final source.
Before calling the work accepted, also establish CPU-only build/test behavior,
complete the relevant current-main regression suite, and run the #32-requested
three-run timing and memory measurements on a named host. None of those pending
items is implied by this report.
