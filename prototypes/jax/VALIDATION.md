# Issue #14 prototype validation

## Scope and provenance

- Base and current `main`: `8323c55faf1c4ddbe35dd36c5cd1266d48f25c38`
- Prototype branch: `prototype/issue-14-jax-global`
- Environment: macOS 26.7 arm64, Python 3.14.7, JAX/JAXlib 0.11.2, NumPy 2.5.3
- Runtime device: JAX CPU `cpu:0`; this is not GPU evidence.
- Input: `test-data/fixtures/synthetic_128x128_8frames_subpixel.mrcs`
- Input SHA-256: `27590926087551e607acf9fd11d11de294ed63005e4647861a94b5ae2bbf93b7`

The prototype is a standalone global-alignment experiment. It does not change the
MotionCorr executable or add a runtime dependency. Local patch alignment, dose weighting,
gain/defect preprocessing, a native JAX GPU run, and an experimental-movie comparison are
outside the evidence below and remain unrun.

## Reproduction

With the pinned requirements in `requirements.txt`:

```sh
python prototypes/jax/test_global_align.py
python prototypes/jax/global_align.py \
  --input test-data/fixtures/synthetic_128x128_8frames_subpixel.mrcs \
  --output /tmp/jax-global-shifts.csv \
  --corrected-sum /tmp/jax-global-sum.mrc --bfactor 150
```

The local run used the equivalent executable from `/tmp/mcjax14-venv`. The CLI report
records hashes, versions, device, synchronized first/warm times, transfer times, and process
peak RSS. On this CPU backend JAX did not expose a device peak-memory counter; process RSS
must not be read as peak device memory.

## Results

`test_global_align.py` passed the CLI-to-reference comparison, existing C++ reference fixture
comparison, and structural controls:

- Reference STAR shifts: maximum absolute error `0.000005 px`; two-coordinate RMS
  `0.000003 px`.
- The documented CLI wrote all eight 1-based frame rows and its provenance JSON for the
  canonical reference fixture; its shifts match the reference at the same errors above.
- Global-only corrected sum versus the C++ reference image: absolute RMSE
  `3.83343e-05`, relative RMSE `5.96351e-07`, maximum pixel error `0.000244141`.
- Asymmetric non-square integer-motion control (64 x 96, eight frames): maximum
  known-motion error `0.0234656 px`; two-coordinate RMS `0.0158379 px`.
- Constant stack: all shifts zero. The first-frame origin is explicitly checked.
- Subpixel known-motion diagnostic: maximum error `0.093689 px`, per-coordinate RMS
  `0.050387 px`. This is a diagnostic only; Issue #14 has no separately approved gate
  for this generated truth fixture, so it is not labeled pass or fail.

The final CLI run converged in two iterations with final iteration RMSD `0.382383 px`.
Forward FFT, alignment, and inverse-sum compile times were `0.042295 s`, `0.181309 s`, and
`0.048003 s`; their synchronized warm medians were `0.000192 s`, `0.001165 s`, and
`0.000198 s`, respectively. Input transfer was
`0.000933 s`, static-array transfer `0.000360 s`, output transfer `0.000013 s`, and process
peak RSS `255721472 bytes`. These are one local CPU run's component observations, not a
controlled performance comparison or a production throughput claim.

## Disposition

This is a working, reproducible CPU prototype for the small reference fixtures, with C++
normalization, R2C layout, signed search, weighting, shift convention, and first-frame origin
checked. It is not complete Issue #14 acceptance: the bounded experimental-movie comparison
and native accelerator measurement still need to be done. Keep Issue #14 open and do not start
the dependent local-patch Issue #15 from these results alone.
