# PR #254: independent valid-input output oracle

Source tested: `17c33c2e` (tests and CMake only; production code unchanged from `af2a5900`).

## Change

`tests/cuda_hermitian_inverse.cpp` no longer uses FFTW applied to the malformed
spectrum as the reference. The reference now:

1. takes the same float spectrum the CUDA path receives;
2. projects it on the host in double (x=0 and, for even nx, x=nx/2 columns: conjugate pair -> `(u+conj(v))/2` stored as `h`, `conj(h)`; self-conjugate bins -> real part);
3. inverts that valid spectrum with double-precision FFTW, and, for geometries up to 8192 pixels, with an explicit direct inverse DFT (no FFT library). The two must agree to 1e-12 before the CUDA output is compared.

Unchanged: the 2e-6 relative-max / relative-RMS gates, the five site-specific invariant mutants, odd/even geometry, multiple frames, resident-spectrum preservation, and the 4096² raw-plan leak (characterization only).

New signal-preservation controls (all on the actual consumption buffer captured before `cufftExecC2R`, for the session and wrapper inverses):

- interior bins are bit-identical to the input; boundary-column bins equal the host projection; self-conjugate bins are exactly real. A buffer of zeros fails.
- an already-Hermitian input passes through bit-identically (`hermitian_input` runs, all four odd/even geometries);
- idempotence: the projected buffer fed back through the session is a fixed point and inverts bit-identically;
- known real image: integer shifts of a random image have an analytic answer (the circularly shifted image); session, wrapper and dose outputs are compared to it (64x48, 63x47, 64x47, 63x48);
- wrapper leaves its input spectra unmodified;
- a host self-test shows the checker rejects unprojected, zeroed-boundary, all-zero and altered-interior buffers (and accepts the valid ones) before any GPU work.

New compiled mutants, with the invariant check disabled so only the oracle can reject (`--expect-oracle-failure`, 64x48 shift 0.3,0.2):

| Mutant | Rejected by |
| --- | --- |
| session: projection removed | buffer vs host projection (49 boundary bins wrong, 3 self-conjugate bins not real); the numerical output still matched at this size |
| session: x=0 and x=nx/2 columns zeroed | numerical output (max_rel 0.117) and buffer check (95 bins) |
| wrapper: columns zeroed | same |
| dose: columns zeroed | numerical output (max_rel 0.117) |

So removing the projection is detected by the projection check, not by the numerical output at small sizes; the numerical leak exists only on large geometries (see the previous review directory).

## Results (4GPUs, A100, CUDA 12.8, cuFFT 11303, Release)

Plain run of `cuda_hermitian_inverse` (nvCOMP build, GPU3): exit 0, `INVARIANT PASS inverses=82`, all comparisons PASS at 4096², the small matrix, integer-shift analytic, Hermitian-input and idempotence cases; worst max_relative 6.0e-7 (gate 2e-6). The four oracle mutants each exit 0 with `ORACLE REJECTED MUTANT`; raw logs in `logs/raw-oracle_*.log`.

| CTest suite | Result |
| --- | --- |
| CPU (Release) | 74/74 passed |
| CUDA (Release) | 119/119 passed |
| CUDA + nvCOMP (Release) | 122/122 passed (includes the CI fail-closed fixture; tree is a git checkout) |

Resources: GPU3 UUID `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` under `/tmp/motioncorr-gpu3-correctness.lock` (held only while running, never deleted); `taskset` 8 CPUs (`112-119` for runs, `104-111` for builds); `OMP_NUM_THREADS=8`; occupancy files in `logs/`. Builds exited 0 (`logs/build-*.exit`). The first CPU CTest log was overwritten by a stray driver restart and the suite was rerun; the partial log is kept as `ctest-cpu-killed-partial.log`. No timings are claimed.

Scripts: [build.sh](build.sh), [run-oracle.sh](run-oracle.sh), [run-ctest.sh](run-ctest.sh). Limitation: native CUDA execution on one GPU model and one cuFFT version; the oracle checks the specified projection and a valid-input inverse, not agreement with CPU output.
