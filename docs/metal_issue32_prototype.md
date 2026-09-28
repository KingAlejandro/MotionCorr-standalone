# Issue #32: Current-main Metal prototype

**Status: executable prototype; relaxed Gate 2 is FAIL.** This report keeps the
implementation result separate from scientific acceptance and performance.

## Revision and platform

- Main ref at port time: `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38` (PR #111 merge).
  Issue #96 currently records `48d1c9f` as main, so its SHA and the live GitHub
  `refs/heads/main` did not agree during this port; this branch follows the live
  ref and does not resolve that roadmap discrepancy.
- Prototype: current-main port of the #30 build/dispatch work and #32 global
  alignment implementation. The published PR head identifies the exact final
  source revision.
- Source revision used by the retained Metal run: `7e7ba3731526dcfd42cb27ec5ddc918f5591ca50`.
- Host: Apple M4 Pro, 20-core GPU; macOS 26.7 (25G229); Xcode 27.0 (27A266a),
  macOS SDK 27.0.
- Build: Release, `-DMETAL=ON`, `-DCUDA=OFF`, using the project's Python
  environment with NumPy available.
- Binary SHA-256 for the retained run: `fcecb5fa353e266323810b62f6673d00e2ad0da42b1207b80404d81b3f92fca8`.
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

The retained execution logs and machine report are at
`/private/tmp/mc-metal-prototype-evidence/final/` on the executing host; the
fixture hashes and result metrics below are copied from that report.

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

The one-run Metal global-alignment wall intervals were `168.15 ms` (integer)
and `82.44 ms` (subpixel); full process wall intervals were `0.258 s` and
`0.171 s`, respectively. These are single characterizations, not the issue's
required three-run timing result or a speedup claim.

## Build and test status

- Metal-enabled Release build: passed on the host above.
- `MetalCompletionWitness`: one CTest passed; it accepts a complete ordered
  six-stage record and rejects the old profile-only smoke record, a wrong
  device, incomplete or reordered stages, and nonconvergence.
- Metal profile timing fields are host wall intervals around synchronous
  command encoding/setup and completion waits. The reported buffer figure is
  only the calculated total of explicit buffer lengths; it excludes MPSGraph
  scratch and is not a process/device peak-memory measurement.
- Full CTest on clean current main `8323c55`: **17/18 passed**;
  `SyntheticRegression` failed its expected-image assertion (max pixel
  difference `23.6498567`, RMSE `0.3119288`; shifts were within `0.004671 px`
  max and `0.003305 px` RMSD). The same failure was seen on the Metal branch.
- The Metal-enabled and CPU-only prototype builds each passed **18/19**; the
  only failure was the same `SyntheticRegression` assertion reproduced on
  clean current main. The CPU-only binary linked no Metal/Foundation/MPS
  frameworks, and a `--metal` request exited 1 with the expected unsupported
  build error.

## Fixture provenance

| Input | SHA-256 |
|---|---|
| Integer STAR | `61dde751f61f8ba82296b43bfcf831858a8c25cc71a650f3fe08b6ebcf19b28f` |
| Integer ground truth | `1507345754352386e5ef202b28dbe9d693a545480eeab9f0ce3c47da14b50009` |
| Integer movie | `44f32752ebb62fc22428e95a1449e54e3a6952036285b805b96085f296ec5ed0` |
| Subpixel STAR | `f754b4ed4ede6c7e55a8e1e300eba265989c9651908279fd4357a3b3c946e160` |
| Subpixel ground truth | `38e4ac009c3f73062c063b979a40cf103a077ee94326862f9a6b0a791865395b` |
| Subpixel movie | `27590926087551e607acf9fd11d11de294ed63005e4647861a94b5ae2bbf93b7` |

| Corrected output | CPU SHA-256 | Metal SHA-256 |
|---|---|---|
| Integer MRC | `7798cc595e58cc617a28cd1e72b3c58dc4724aa3dc60f4a56574e52fec98688f` | `22916f6eb59d9a5758fb822c789f1555cf0672075d2a2c9ada41d928553c5f9e` |
| Integer per-movie STAR | `d9154c0f20c4c45a62043eefe0b095823894912c1fb6e6810fc14ac17eaffa37` | `ff56154f61f7cdedd4b93ddaab59ff6f2bb789da288dc033a12135a2dcae8895` |
| Subpixel MRC | `d23b044aa0267c8587985751b6671615f718fedf21c74452998775dd26f0f096` | `2ac790a7abbe5edc5a95c2d7f95a4ffc8de1f1372c042b27d42a4773a5f65e54` |
| Subpixel per-movie STAR | `4b69a274da04f32c8a6a0193d79bbe4e033e492bb2aadf6555b5f4a4256466a0` | `c88d8f1149b66eec931020171aef7d301ddcfc9404633abbcd686117af96a9a5` |

## Scope and remaining work

This is an opt-in global-alignment prototype. Local patch alignment and dose
weighting remain on their existing paths. The next scientific step is to
diagnose the absolute image RMSE difference without changing any gate, then
rerun both cases plus discriminating negative controls on the final source.
CPU-only build isolation was checked; the known current-main
`SyntheticRegression` failure remains. The #32-requested three-run timing and
memory measurements have not been completed. None of those pending items is
implied by this report.
