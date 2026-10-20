# #253: CUDA inverse boundary projection

Candidate under POST_FREEZE_TEST_PLAN §9, class CUDA/shared. Base: main
`3691374061f782bc84531fd1c79d017ddcb5a7c2`. Native evidence pending.

The CUDA inverse consumption scratch is projected on kx=0 and (only for even
nx) kx=nx/2: each ky pair becomes `(F(ky) + conj(F(-ky)))/2`.
Self-paired rows become real. Each thread owns both entries, so no in-place
read/write race is possible. Interior bins and resident spectra are unchanged;
projection is performed at consumption, rather than after each cumulative shift.
This chooses the existing FFTW real-inverse result, to rounding, including at
Nyquist corners; it does not introduce a separable Nyquist interpolation policy.
CPU code, peak fitting, convergence, gates and tolerances are unchanged.
Intentional CUDA product differences correct the invalid C2R input contract;
maintainer sign-off is required before merge (§9.2).

All five `cufftExecC2R` sites in `src/` can receive non-Hermitian input:

| Site (base line) | Input provenance | Action |
|---|---|---|
| `cuda_movie_session.cu:2120` | Full globally shifted resident spectrum, copied to inverse scratch | Project scratch, batch-one plan |
| `cuda_fft_prep.cu:254` | Host globally shifted spectrum, copied to device scratch | Project scratch, batch-one plan |
| `cuda_realspace_dw.cu:388` | Globally shifted spectrum with real symmetric dose weights; weights do not restore conjugacy | Project weighted scratch, owned or borrowed batch-one plan |
| `cuda_alignpatch.cu:625` | Weighted cross spectrum of shifted frames/reference; reduced-grid cutoff becomes a new x Nyquist boundary; cropping does not fold its omitted partner | Project CCF scratch for all frames before batched inverse |
| `cuda_alignpatch.cu:988` | Same CCF construction on windowed stacks in the batched patch path, including cumulative fractional shifts | Project each active patch's CCF scratch for all frames |

`rg -n cufftExecC2R src` finds no other site. `projector.cpp` uses forward R2C
and D2Z only. The alignment projection satisfies the real inverse contract and
matches FFTW's treatment of the existing cropped buffer; it does not change the
crop/folding policy or establish scientific correctness of that policy.

The new `CudaHermitianInverse` feeds identical FFTW R2C plus fractional-shift
bytes to the production session inverse, host fallback inverse and dose-weighted
inverse. It checks both frames and resident-spectrum preservation. The primary
4096² case must fail on main and pass on the fix; the compiled session mutant
removes the projection and must produce a numerical mismatch. Small integer,
zero, x-only, y-only, combined and even/odd controls cover boundary geometry.
`--matrix` also characterises unprojected `cufftMakePlanMany` batch 1/2 and the
fixed production paths at all five requested full-frame sizes. Raw plan results
are characterisation, not the production regression's pass condition.
