# CONTROL_PLAN v1 (synthetic controls only; written and hashed BEFORE the first control run)

Scope: synthetic spectra only. No captured payload, no truth, no native/GPU/SSH. Interpreter
`/Users/alex.konstantinov/.local/bin/python3 -I -B` (CPython 3.13.7, NumPy 2.4.2, SciPy 1.17.1),
`OMP/OPENBLAS/VECLIB/MKL = 1`. Control wall-clock cap 120 s. Tolerances below are fixed now and are
not tuned after seeing results. A failed control is retained (ATTEMPTS.log + its output) and fixed
only by a NEW script revision (`*_v2.py`), never by editing a tolerance in place.

## Objective under test (raw half-plane phase-coherence J)

Grid 32 rows (y) x 42 columns (x); half-plane array [32,22]. kx = x, ky = (y>16 ? y-32 : y) (y=16 -> +16).
m_x = 1 for x in {0,21}, else 2. DC (y=0,x=0) weight zeroed. s is (5,2) = (frame, [x,y]), s[0]=0.

    J(s) = sum_{j<f} Re sum_{y,x} m_x W[y,x] F_j conj(F_f) exp(+i phi_jf),
    phi_jf = 2pi ( kx (s_fx - s_jx)/42 + ky (s_fy - s_jy)/32 )

Native convention (source 927a689, shiftNonSquareImageInFourierTransform called with -cur/pn):
F_f(s) = F_f^0 exp(-i 2pi (kx s_fx/42 + ky s_fy/32)); then F_j(s) conj(F_f(s)) = F_j^0 conj(F_f^0) exp(+i phi_jf).

Derivatives (Q_jf = m_x W F_j conj(F_f), Omega_x = 2pi kx/42, Omega_y = 2pi ky/32, d = s_f - s_j):

    T_jf(d)        = Re sum Q e^{i phi}
    dT/dd_a        = - sum Omega_a Im(Q e^{i phi})                 (a in {x,y})
    d2T/dd_a dd_b  = - sum Omega_a Omega_b Re(Q e^{i phi})
    dJ/ds_f        = sum_{j<f} dT_jf/dd - sum_{l>f} dT_fl/dd
    H_J            = sum_{j<f} (e_f - e_j)(e_f - e_j)^T (x) d2T_jf          (then drop frame 0)

Sign check: where the pair is perfectly coherent (Q e^{i phi} real >0), d2T = -sum Omega Omega |Q| <= 0,
so J is concave at a coherent peak. The optimizer minimises -J.

## Controls and predeclared tolerances

Common: N=5 frames, rich independent bandlimited spectra = rfft2 of independent Gaussian 32x42 white
noise images (seeded PCG64), multiplied by an independent per-frame envelope, with Nyquist column (x=21)
and Nyquist row (y=16) zeroed ("valid", unless stated). Two weight sets: `Wnative` = exp(-2*B*(ly^2/32^2 +
x^2/22^2)) with B=150 (the native formula, evaluated here from the formula only, not from saved weights),
and `Wwide` with B=2 (so that Nyquist rows/columns carry weight). Jscale = sum_{j<f} sum m_x W |F_j||F_f|
(L1 magnitude of the objective). All "rel" errors are |a-b|/Jscale.

| id | control | pass condition |
|----|---------|----------------|
| C0 | s = 0: J vs independent native-grid reference (shift spectra, leave-one-out aggregate, numpy irfft2 x 1344, lag 0, J = 0.5 sum_f map_f[0,0]) | rel <= 1e-12 |
| C1 | 20 random integer s (frames 1..4 in [-7,7] px, seed 11): J vs reference | rel <= 1e-12 for every draw |
| C2 | 20 random fractional s (N(0,1.7) px, seed 12), both W sets: J vs reference | rel <= 1e-12 for every draw |
| C3 | gauge invariance: J(s + c) = J(s) for a common translation c of ALL five frames (c fractional, 20 draws), s[0] unconstrained here | rel <= 1e-12 |
| C3b | gauge fixing in the optimizer path: objective wrapper never changes s[0]; vector length 8 | exact (assert) |
| C4 | pairwise vs aggregate: sum_{j<f} pair terms equal the aggregate leave-one-out form at the SAME s (C0-C2 reference) AND at integer d each pair term equals the unshifted pair real map irfft2(Q_jf-without-m) x 1344 at lag (d_y mod 32, d_x mod 42) | rel <= 1e-12 |
| C5 | analytic gradient vs central finite differences (h = 1e-5 on each of the 8 coordinates), 10 random fractional states, both W | max abs err <= 1e-7 * Jscale |
| C6 | analytic Hessian vs central difference of the analytic gradient (h = 1e-5), 10 random fractional states, both W; Hessian symmetric | max abs err <= 1e-7 * Jscale; asymmetry <= 1e-12 * Jscale |
| C7 | Hessian sign: for a coherent state F_f = G exp(+i k s*_f), at s* the Hessian is negative semidefinite (max eig <= 1e-9 * Jscale) and J(s*) = Jmax = sum m W |G|^2 x 10 pairs | rel <= 1e-12, eig bound |
| C8 | noise-free coherent recovery, shifts s* = zeros / integers / fractional (3 cases; 9 starts = zero start + the 8 frozen PCG64(238267) N(0,2) draws; the two native starts have no synthetic analogue): each of the optimizer runs from the 8 random starts reaches J >= Jmax(1 - 1e-8) OR is reported as non-recovery; PASS for the control requires the highest-J outcome to satisfy J >= Jmax(1-1e-10) AND torus distance of that outcome to s* <= 1e-5 px. Truth is used ONLY to build the synthetic spectrum and to score; never to select a start. Per-start outcomes are listed, not summarised away | as stated |
| C9 | mutants fail: (a) wrong-sign phase (e^{-i phi}), (b) swapped axes (kx paired with s_y/32, ky with s_x/42 style swap), each as objective mutant vs the reference at 10 random fractional states with s != 0, and as gradient mutant vs FD of the CORRECT objective. The control passes only if each mutant FAILS the corresponding C2/C5 check, i.e. min over draws of rel diff >= 1e-3 (objective) and max grad err >= 1e-3 * Jscale (gradient) | as stated |
| C10 | NYQUIST exposure (Wwide, real-image spectra WITH Nyquist content kept, Hermitian-consistent): (a) at integer lags raw J equals the symmetric-Nyquist real-map trig interpolant (map = irfft2 of each pair product; Nyquist split cos convention), rel <= 1e-12; (b) at fractional lags raw J minus interpolant D(s) is reported and must be exposed: max over 10 draws |D|/Jscale >= 1e-6; (c) for Nyquist-free spectra D == 0 at fractional lags, rel <= 1e-12; (d) linearity: D computed from the full product spectrum equals D computed from the product masked to (x==21 or y==16), rel <= 1e-12 (the discrepancy lives only on the Nyquist row/column). Raw J is NOT zeroed or altered; the difference is a reported property of the two objectives | as stated |
| C11 | Optimizer sanity on a noisy synthetic (coherent + noise, 1 draw, Wnative): final J >= start J for every one of the 9 runs (zero + 8 random); reported nit/nfev/status retained | as stated |
| C12 | Time: control suite wall-clock | <= 120 s |

Independent reference (`reference_J`) shares no code path with the analytic objective except numpy
primitives: it builds explicit shifted complex spectra, forms leave-one-out aggregates, uses irfft2.
The Nyquist interpolant uses an explicit full-plane slow sum (no FFT) as a third implementation, and is
itself cross-checked against irfft2 at integer lags (part of C10a).

Precision: float64 throughout; spectra come from float64 rfft2 (controls) so float32 roundoff does not
enter the controls; the stage-1 payload spectra are float32 cast to float64.
