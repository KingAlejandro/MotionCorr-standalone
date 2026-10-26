# Frozen DC-pedestal operator control, 26 October 2026

Frozen before copied-spectrum or new replay outcomes. Parent authorized this
follow-up after PR288 boundary packet was sealed at0ba72a7197933f5f0c7149491853c04b0d780013.
No production source edit, movie/capture/forward/window/trajectory run, H7 port,
DC adoption or M3 decision. Historical DC/H7 harm and no-port records remain.

## Inputs, resource and process budget

Exactly four previously used Hermitian-valid sets from inverse-repair-v2:
00021/00046 × CPU-source/CUDA-source, each with frames0/4. The eight spectrum
SHA256s, old peak estimates and original maximum are frozen in FROZEN-PINS.json.
They were already evaluated; no case selection from new outcomes is permitted.
Copy geometry and the two spectra into a new exclusive dc-pedestal-v1-20261026
namespace, retaining originals and unmodified copies. In separate copies replace
ONLY the first8bytes (complex DC ky0,kx0) with complex(+0,+0). Assert all later
bytes exactly equal, original hashes unchanged, finite inputs, exact Hermitian
conjugacy on self-conjugate columns, layout and dimensions unchanged.

Use the EXISTING fixed031f333a replay binary, SHA2564970be307aad38034c0ae1e36537d00d6fb9cca9c28ae81663e4b79edf0018f1.
It explicitly zeroes the22unused spectra in its24-frame CUDA batch. Exactly eight
native replay processes: four sets × CPU `inverse` / CUDA `inverse-valid`.
CPU/CUDA read the SAME copied zero-DC spectra; CUDA must byte-compare its entire
batch before/after projection and emit projection-noop PASS. No build or binary
change. Reference/weight/peak/search/tie logic stays unchanged.

4GPUs only, GPU2 UUID GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598,
CPU80–87, at most8threads; correctness/CPU locks append-open flock-n, benchmark
exclusion probe and compatible overlapping locks. Every native job rechecks
CPU occupancy, GPU2 absence of foreign compute, actual child/thread affinity,
all spectrum/original/binary hashes, free space and aggregate scratch plus1GiB
headroom under20GiB. Retain any refusal/failure; do not blindly retry or signal.
No timing claim. Prior sealed packets and their resource limits stay unchanged.

## Primary prediction and peak rule

H_DC: across the eight common valid maps, maximum CPU-vs-CUDA raw subpixel VECTOR
difference after pre-IFFT DC zeroing is <=0.1 times the original maximum in the
pins, AND no integer peak changes on ANY of the eight inputs on either backend.
A failed ratio OR any changed integer peak falsifies H_DC. No threshold tuning,
case removal or repeat. The10x prediction is diagnostic, not an acceptance gate;
CPU agreement0.001 and truth RMS/p95/max0.20/0.40/0.80Å are unchanged.

"Raw subpixel" here is the same declared double arithmetic peak rule applied
to each saved map, before anchoring: row-major scan y=-12..12,x=-12..12,
strict greater-than updates, native separable five-point parabola with EPS1e-15,
original pnx/ccf_nx,pny/ccf_ny scaling. Explicitly report ties, nonfinite values,
zero and degenerate denominators. These recomputed map estimates are not new
native trajectory observations. Report every input's XY/norm, each backend's
f4-f0, and the CPU/CUDA difference of these anchored two-frame vectors, before
and after; no aggregate-only conclusion.

## Independent arithmetic CCF reference and controls

Existing /home/alex/.mc-venv Python3.12.3 / NumPy2.5.3. Cast exact stored
complex64 values to complex128, call
`np.fft.irfft2(S, s=(ccf_ny,ccf_nx), axes=(-2,-1), norm='forward')`.
Output must be float64. The installed `_raw_fft` swaps inverse normalization
so norm='forward' gives factor1 on each inverse axis: this is unnormalized
C2R, matching NativeFwdOnly's unscaled inverse. Installed source/docstrings
are inspected and hashes/extension/version/code recorded. A tiny analytic DC
normalization control must yield constant1; a non-DC Hermitian cosine checks
axis/sign/amplitude against its analytic value. No native process for controls.
For each actual spectrum, independently evaluate the half-spectrum weighted
C2R sum at the double-reference peak and four neighbors (signed frequencies;
interior kx weight2, self-conjugate columns weight1) to check normalization/input
interpretation. This is an arithmetic CCF reference, NOT physical motion truth.

For each original/zero pair, double maps should differ only by the real stored
DC. Freeze this conservative diagnostic roundoff envelope before outcomes:
eps=np.finfo(float64).eps; k=64*(ceil(log2(nx))+ceil(log2(ny))+1);
gamma_k=k*eps/(1-k*eps). Let L(S) be the full-spectrum L1 norm reconstructed
from the half-spectrum with interior-x weight2 and edge weight1. Inflate each
computed L by1/(1-4*K*eps), K=number of stored complex bins, to cover L1
accumulation. Bound = gamma_k*(L(original)+L(zero)) +
8*eps*(abs(DC)+max(abs(double_original))+max(abs(double_zero))).
Check maxabs(double_original-double_zero-DC) <= bound, retain actual values.
Use the same bound for peak-neighbor direct-sum checks. This is an explicit
conservative epsilon/L1 envelope under ordinary stable FFT error scaling,
not a formal implementation-specific pocketfft error certificate. No fitted
bound or physical-truth claim. Double reference uses the same search/peak rule;
report integer changes and peak XY shifts rather than assuming invariance.

For each float backend, before/after, report peak difference from its matching
double arithmetic reference. At each selected five-point stencil report D=vp+vn-2c,
N=vp-vn, |D|/ULP32(c), and cancellation condition
(|vp|+|vn|+2|c|)/|D|. Also retain map-quantization denominator envelope
0.5*ULP32(vp)+0.5*ULP32(vn)+ULP32(c) divided by |D|. Denominator arithmetic
is double already (#260); conditioning describes information in float maps,
not a claimed FP64 peak-fit defect. Undefined ratios are labelled explicitly.

Separate negative control: cast an ALREADY PRODUCED original float32 map to
float64, subtract exactly its real stored DC constant, and recompute the same
peak. No FFT is run. This cannot restore curvature lost in the float32 inverse.
Report its peak/curvature, original-vs-postmap components and denominator
identity; do not combine it with pre-IFFT DC zeroing or call it recovery.

## Handoff

Publish only this bounded operator result and hashes on existing draft PR288.
Even if H_DC holds, give only the smallest default-off proposal; no new native
full trajectory work until parent assesses historical/scientific harm. All new
results are producer-reported pending any independent audit. No merge or watcher.
