# Independent Mathematical & Statistical Review: W5 Round 2 (E1 Global Half-Gain Damping)

- **Target under review**: `docs/post_rc0/s1/first_divergence_20261022/w5_intervention_20261025/round2/` (Parent `cd4c996b`, numerical source `805d9de2`, `MotioncorrRunner::alignPatch` in `src/motioncorr_runner.cpp:4664-4864`).
- **Verification script & machine-readable calculations**: `verify_e1_challenge.py` and `verification_results.json` (in this directory, run with `python3 -I`).

---

## Executive Verdict Table

| # | Claim / Sub-claim under Review | Rating | Calculation & Basis |
|---|---|---|---|
| **C1a** | At $N=5$, the double-precision anchored simultaneous update map at true motion has eigenvalues $\approx 0.698524$ and $-1.192520$ (scaled by $g=0.5$ to $0.849262$ and $-0.096260$), computed at the right point and in the right gauge. | **SUPPORTED** *(in `double`)* | Reproduced exactly (`max_abs_diff = 0.0` vs saved $8\times 8$ Jacobian). Exact discrete-stencil closed form gives $J_{\text{block}} = I_2 + \frac{5}{4}A_{\text{sep}}$ with fourfold eigenvalues $+0.69852426$ and $-1.19251971$ (differing from central-difference $+0.69852393, -1.19251988$ by $\le 3.3\times 10^{-7}$ due to $\epsilon=10^{-3}\text{ px}$ step). Frame-0 anchoring is an exact quotient gauge on $\mathcal{V}_0=\{s_0=0\}$. |
| **C1b** | The smooth `double` linearisation at truth also governs `map32` / native CPU (`float32` CCF map `Iccs`). | **WRONG** | Because `W(0,0)=1`, the `100.0` pedestal puts $m(0,0)=40004.746$ in `float32`, where $1\text{ ULP}=2^{-8}=0.00390625$ and peak curvature is $d_{xx}=d_{yy}=-0.0234375=-6\text{ ULPs}$. Thus $M_{\text{map32}}(s)$ is a staircase with $\sim 0.083\text{ px}$ quantization steps and **zero derivative ($J_{\text{map32}}=I_8$, all eigenvalues $=1.0$)** inside a deadzone around truth. |
| **C1c** | The five-frame fixture errors come from linear instability rather than a wrong attractive fixed point or other estimator defects. | **UNSUPPORTED / WRONG** *(as a general 5-frame claim)* | True only for `double` 50-step pure translations (`integer`, `fractional`). False on 5-frame `affine` (where W5 Round 1 proved a $0.343210\text{ px}$ finite-window CCF objective bias at truth, and $g=0.5$ at 50 steps still **FAILS** at $0.2628\text{ \AA}$ `double` / $0.2885\text{ \AA}$ `map32`). Under production $5\text{ it}/0.5\text{ px}$ stop, $g=0.5$ still **FAILS** `double` `integer` ($0.3307\text{ \AA}$) and `map32` `fractional` ($0.2600\text{ \AA}$) due to premature $0.5\text{ px}$ tolerance termination. |
| **C2** | Scalar damping ($g=0.5$) is the right repair for the extra update gain ($-2.1925$ vs ideal $-1.25$ at $N=5$). | **WRONG** | Exact derivation proves $100\%$ of the extra gain beyond $-\frac{N}{N-1}=-1.25$ comes from a **peak-definition defect**: the separable 1D parabola ignores the off-diagonal CCF Hessian $D_{xy}$ ($\rho_{xy}=0.756418$), splitting single-frame peak response eigenvalues into $\mu_{\pm}(A)=-(\bar{d}\pm\rho_{xy})\in\{-1.754016,-0.241181\}$. Scalar damping $g=0.5$ masks the over-gained mode ($\mu_-$) by crippling the already under-gained diagonal mode ($\mu_+=-0.241\implies \lambda_+=0.8493$). Inverting the $2\times 2$ Hessian on the $3\times 3$ peak stencil restores $A_{\text{2D}}\approx -0.991 I_2$ and $\lambda(J_{\text{2D}})\in\{-0.2288,-0.2496\}$. |
| **C3** | Fixed gain $g=0.5$ is principled and safe across frame counts $N$ and weightings. | **WRONG** | $g=0.5$ was chosen heuristically after seeing $\lambda_-\approx -1.196$ at $N=5$ (it sits near $g_{\text{zero}-}(5)=1/2.1925=0.4561$). Principled leave-one-out relaxation is $g_{\text{LOO}}(N)=\frac{N-1}{N}$ ($0.8$ at $N=5$). Under `prod` weight, $g=1$ is **already linearly stable for $N\ge 9$** ($g_{\max}=1.0135, 1.0525, 1.0832$ at $N=9,13,20$), and at $N=20$ $g=0.5$ has a **worse spectral radius** ($\rho=0.8731$) than $g=1$ ($\rho=0.8463$). Under `iso` weight, $g=1$ is stable for all $N\ge 3$ ($g_{\max}\in[1.100,1.568]$), and $g=0.5$ degrades 5-step contraction $\rho^5$ by $21\times$ ($N=13$) and $45\times$ ($N=20$). |
| **C4** | Production-stop ($5\text{ it}/0.5\text{ px}$) regressions under $g=0.5$ are merely 5-iteration budget effects rather than estimator harm. | **WRONG** *(for `prod` weight)* / **SUPPORTED** *(only for `vel0-N13/20-iso`)* | `vel0-N13/20-iso` hit the 5-step cap and pass at step 6 (though $N=20$ suffers a $19.61\text{ px}$ nonlinear transient at step 2). In contrast, under production weight (`prod`), `vel0-N5-prod` ($0.4042\to 0.4676\text{ \AA}$, iter 4), `vel1-N13-prod` ($0.2373\to 0.4023\text{ \AA}$, iter 4), `vel0-N13-prod` (iter 5), and `vel1-N20-prod` ($0.2470\to 0.3037\text{ \AA}$, iter 5) **all terminate early via `raw_update < 0.5 px` (`converged=True`)** because on the slow mode $|\eta_+|\approx 0.25\text{--}0.30$, so `raw < 0.5 px` triggers when truth error is still up to $1.9\text{ px}$. |
| **C5** | E1 supports a default-off CPU prototype using fixed $g=0.5$ global gain. | **UNSUPPORTED / NO-GO** | Fails under production stopping on `noisy` (`double` RMS $1.6685\to 3.0492\text{ \AA}$, max $7.1367\to 21.4926\text{ \AA}$ via premature global stall at iter 3 and lost right-edge patch; `map32` RMS $1.6356\to 1.7445\text{ \AA}$ via false convergence of a $22.6\text{ px}$ outlier patch), fails `map32-5it` `fractional` ($0.2600\text{ \AA}$) and `affine` ($0.2004\text{ \AA}$), and regresses `prod` $N=13,20$ controls even at unlimited `max_iter` with production `tolerance = 0.5 px`. |

**Recommendation**: **NO-GO** for a default-off native CPU prototype with fixed $0.5$ global gain. A principled repair must fix the root cause (replacing the separable 1D parabola with a $3\times 3$ 2D quadratic Hessian solve, paired with the leave-one-out step $g_{\text{LOO}}(N)=\frac{N-1}{N}$ and DC-bin removal before `float32` IFFT), which is a **new hypothesis requiring fresh pre-registered controls**.

---

## 1. Challenge 1: Linearisation Accuracy, Evaluation Point, and Gauge

### 1.1 Independent Reproduction and Exact Analytical Formula
In `e1_characterize.py`, the state $s = (s_0, s_1, \dots, s_{N-1}) \in \mathbb{R}^{N \times 2}$ is updated by the simultaneous anchored map
$$M(s)_f = s_f + u_f^{\text{raw}}(s) - u_0^{\text{raw}}(s), \qquad u_f^{\text{raw}}(s) = P\Bigl(\mathcal{F}^{-1}\Bigl\{\sum_{j \ne f} \mathcal{S}(F_j, s_j)\,\overline{\mathcal{S}(F_f, s_f)}\,W\Bigr\}\Bigr),$$
where $\mathcal{S}(F, c)(k) = F(k)e^{-2\pi i (k_x c_x/n_x + k_y c_y/n_y)}$ and $P(\cdot)$ is the integer argmax plus separable 1D parabolic interpolation.

1. **Gauge**: Because $\mathcal{S}(F_j, s_j + c)\overline{\mathcal{S}(F_f, s_f + c)}$ is invariant to any common translation $c \in \mathbb{R}^2$ and the output is anchored to frame $0$ ($M(s)_0 = s_0$), the frame-0 anchored subspace $\mathcal{V}_0 = \{s : s_0 = (0,0)\} \cong \mathbb{R}^{2(N-1)}$ is strictly invariant under $M$. Differentiating with respect to $(s_1, \dots, s_{N-1})$ at $\delta s_0 = 0$ gives the exact $2(N-1)\times 2(N-1)$ quotient Jacobian.
2. **Exact discrete-stencil Jacobian**: At true motion $s = t$, all shifted frames equal the target spectrum $F_t(k)$ with weighted power spectrum $S(k) = |F_t(k)|^2 W(k)$. Perturbing $s = t + \delta s$ ($\delta s_0 = 0$) shifts the $f$-th CCF by
   $$\Delta_f = \delta s_f - \frac{1}{N-1}\sum_{j \ne f} \delta s_j + O(\|\delta s\|^2) = \frac{N}{N-1}\delta s_f - \frac{1}{N-1}\sum_{j=1}^{N-1}\delta s_j + O(\|\delta s\|^2).$$
   For small $\Delta = (\Delta_x, \Delta_y)$ around integer peak $(0,0)$, the CCF on the 5-point stencil $(0,0), (\pm 1, 0), (0, \pm 1)$ is
   $$C_{\Delta}(d_x, d_y) = \frac{1}{n_x n_y}\sum_{k_x, k_y} S(k_x, k_y)\cos\!\left(2\pi\left[\frac{k_x}{n_x}(d_x + \Delta_x) + \frac{k_y}{n_y}(d_y + \Delta_y)\right]\right).$$
   Differentiating the separable parabola $P_x(C_\Delta) = -\frac{C_\Delta(1,0)-C_\Delta(-1,0)}{2[C_\Delta(1,0)+C_\Delta(-1,0)-2C_\Delta(0,0)]}$ (and similarly $P_y$) at $\Delta=(0,0)$ yields $u_f^{\text{raw}} = A_{\text{sep}}\Delta_f + O(\|\Delta_f\|^2)$, where
   $$A_{\text{sep}} = -\begin{pmatrix} D_{xx} & 0 \\ 0 & D_{yy} \end{pmatrix}^{-1}\begin{pmatrix} G_{xx} & G_{xy} \\ G_{yx} & G_{yy} \end{pmatrix},$$
   with exact discrete spectral moments:
   $$D_{xx} = \Bigl\langle S(k)\bigl(2\cos\tfrac{2\pi k_x}{n_x}-2\bigr)\Bigr\rangle = -4.849664\times 10^{-7}, \quad D_{yy} = \Bigl\langle S(k)\bigl(2\cos\tfrac{2\pi k_y}{n_y}-2\bigr)\Bigr\rangle = -3.883144\times 10^{-7},$$
   $$G_{xx} = \Bigl\langle S(k)\bigl(-\tfrac{2\pi k_x}{n_x}\bigr)\sin\tfrac{2\pi k_x}{n_x}\Bigr\rangle = -4.836263\times 10^{-7}, \quad G_{xy} = \Bigl\langle S(k)\bigl(-\tfrac{2\pi k_y}{n_y}\bigr)\sin\tfrac{2\pi k_x}{n_x}\Bigr\rangle = -3.283209\times 10^{-7},$$
   $$G_{yx} = \Bigl\langle S(k)\bigl(-\tfrac{2\pi k_x}{n_x}\bigr)\sin\tfrac{2\pi k_y}{n_y}\Bigr\rangle = -3.281858\times 10^{-7}, \quad G_{yy} = \Bigl\langle S(k)\bigl(-\tfrac{2\pi k_y}{n_y}\bigr)\sin\tfrac{2\pi k_y}{n_y}\Bigr\rangle = -3.875221\times 10^{-7}.$$
   Evaluating $A_{\text{sep}}$ gives:
   $$A_{\text{sep}} = \begin{pmatrix} -0.99723681 & -0.67699714 \\ -0.84515488 & -0.99795954 \end{pmatrix}, \qquad \text{spec}(A_{\text{sep}}) = \{-1.75401577, \, -0.24118059\}.$$
   When frame 0 is subtracted ($u_f = u_f^{\text{raw}} - u_0^{\text{raw}}$), the common sum $-\frac{1}{N-1}\sum_{j=1}^{N-1} A_{\text{sep}}\delta s_j$ cancels identically between frame $f$ and frame $0$, decoupling all $N-1$ frames into identical $2\times 2$ blocks:
   $$J = \frac{\partial M}{\partial s}\bigg|_{s=t,\, s_0=0} = I_{N-1} \otimes \left(I_2 + \frac{N}{N-1}A_{\text{sep}}\right).$$
   At $N=5$ ($\frac{N}{N-1} = 1.25$):
   $$J_{\text{block}}^{\text{exact}} = \begin{pmatrix} -0.24654602 & -0.84624643 \\ -1.05644360 & -0.24744943 \end{pmatrix}, \qquad \lambda_{\pm} = +0.69852426, \, -1.19251971.$$
   This matches `e1-characterization.json`'s central-difference Jacobian ($\epsilon=10^{-3}\text{ px}$, $\lambda_+ = +0.69852393$, $\lambda_- = -1.19251988$) to $3.3\times 10^{-7}$, and explains why Round 1's continuous-Hessian approximation ($G_{ii}/D_{ii}\to 1$, $\lambda = +0.69545280, -1.19545280$, cited as $-1.196$ in `E1-PREDICTION.md`) differed by $0.00293$.

### 1.2 Why the Linearisation Fails for `map32` / Native CPU and Non-Translation Fixtures
1. **Complete breakdown of linearisation in `float32` (`map32` / native CPU)**:
   In `MotioncorrRunner::alignPatch`, `Iccs` is `Image<float>` (`float32`), and `weight(0,0) = 1.0`. Because the fixture pedestal is $100.0$, the unnormalized CCF at $(0,0)$ has DC value $m(0,0) \approx 4 \times 100^2 = 40004.74609375$. At this magnitude in IEEE-754 `float32`, $1\text{ ULP} = 2^{-8} = 0.00390625$, while the signal curvature is only:
   $$d_{xx}^{\text{f32}} = m(0,1) + m(0,-1) - 2m(0,0) = -0.0234375 = -6\text{ ULPs}, \quad d_{yy}^{\text{f32}} = -0.0234375 = -6\text{ ULPs}.$$
   Consequently, $P(m)$ in `float32` is quantized to rational multiples of $\frac{1}{2\times 6} = \frac{1}{12} \approx 0.0833\text{ px}$! Within a deadzone of radius $\sim 0.08\text{--}0.12\text{ px}$ around truth, $m(0,1)$ and $m(0,-1)$ round to the exact same `float32` value (`40004.734375`), yielding $u = 0$ and **$J_{\text{map32}} = I_8$ (all 8 eigenvalues equal $1.000000$)** at $\epsilon = 10^{-3}\text{ px}$ (`verification_results.json`). This is why `map32-gain0.5-50it` stops dead at iteration 10 (`fractional`, $0.104588\text{ \AA}$) and iteration 11 (`integer`, $0.073975\text{ \AA}$) with `endpoint_update_rms_px = 0.0`, and why `map32-gain1-50it` on `fractional` ($0.081461\text{ \AA}$) outperforms `map32-gain0.5-50it` ($0.104588\text{ \AA}$).
2. **Invalidity of the "not a wrong fixed point" claim on 5-frame deformed fixtures (`affine`)**:
   On `affine`, W5 Round 1 demonstrated that the weighted finite-window CCF has a non-zero update of $0.343210\text{ px}$ at truth (a genuine objective bias, not an instability artifact). Stabilizing the global loop with $g=0.5$ at 50 iterations still fails `affine` ($0.262779\text{ \AA}$ in `double`, $0.288536\text{ \AA}$ in `map32`). Note also a script defect in `e1_intervention.py` line 42: in the `50it` arm (`it=50, tol=1e-9`), `patch_fit` was called with `gain=1.0, tol=1e-9`, causing $0/9$ patches to converge (`NULL_TOO_FEW_OBSERVATIONS`) and dropping the local model entirely; however, even when `patch_fit` is held at production `5it/0.5px` while global uses `50it/1e-9` with $g=0.5$, `map32` `affine` still fails at $0.203526\text{ \AA}$ RMS.

---

## 2. Challenge 2: Ideal Linear Model & Root Cause of the $-2.1925$ Update Eigenvalue

### 2.1 Ideal Linear Model
If the peak finder returned the exact shift of frame $f$ relative to the mean of the other frames, $A = -I_2$, then:
$$u_f^{\text{raw}} = -\Delta_f = -\left(\delta s_f - \frac{1}{N-1}\sum_{j \ne f}\delta s_j\right) = -\frac{N}{N-1}\delta s_f + \frac{1}{N-1}\sum_{j=0}^{N-1}\delta s_j.$$
On the zero-sum differential subspace $\sum_j \delta s_j = 0$ (or equivalently on $\mathcal{V}_0 = \{\delta s_0 = 0\}$ after frame-0 anchoring $u_f = u_f^{\text{raw}} - u_0^{\text{raw}}$), the update Jacobian is $-\frac{N}{N-1}I_{2(N-1)}$ ($-1.25 I_8$ at $N=5$), and the state-transition Jacobian is:
$$J_{\text{ideal}} = \left(1 - \frac{N}{N-1}\right)I_{2(N-1)} = -\frac{1}{N-1}I_{2(N-1)} = -0.25 I_8 \quad (N=5),$$
which is contractive for all $N \ge 3$.

### 2.2 Quantitative Attribution Across the Four Candidates
Why is the measured update Jacobian eigenvalue on the unstable mode $\eta_- = -2.192520$ instead of $-1.25$?
$$\eta_- = \underbrace{\frac{N}{N-1}}_{1.250000} \times \underbrace{\mu_-(A_{\text{sep}})}_{-1.754016} = -2.192520.$$
Testing each candidate from the derivation in Section 1.1:
1. **Weighted CCF response to a reference built from misaligned frames**: **$0\%$ contribution to the linear eigenvalue at truth**. Because $\sum_{j \ne f} e^{-2\pi i k\cdot\delta s_j} = (N-1)\bigl[1 - 2\pi i k\cdot\bigl(\frac{1}{N-1}\sum_{j\ne f}\delta s_j\bigr) + O(\|\delta s\|^2)\bigr]$, to first order in $\delta s$ the sum of misaligned frames is identical to a single unblurred frame at the mean shift. Reference smearing is purely $O(\|\delta s\|^2)$.
2. **Double-counting between accumulated shifts and Fourier re-shift**: **$0\%$ contribution**. In `alignPatch` (`src/motioncorr_runner.cpp:4836-4847`), `xshifts` accumulates the total trajectory while `shiftNonSquareImageInFourierTransform` shifts `Fframes` incrementally by `-cur_xshifts`.
3. **Anchoring**: **$0\%$ excess over the leave-one-out factor $\frac{N}{N-1}=1.25$**. Before anchoring, the leave-one-out matrix $L = \frac{N}{N-1}(I_N - \frac{1}{N}\mathbf{1}\mathbf{1}^T)$ already has eigenvalue $\frac{N}{N-1} = 1.25$ with multiplicity $N-1$. Anchoring ($P_0 = I_N - \mathbf{1}e_0^T$) satisfies $P_0 L P_0 = \frac{N}{N-1}P_0$, preserving all $2(N-1)$ nonzero eigenvalues identically.
4. **Separable 1D parabola on an anisotropic (diagonally oriented) 2D CCF peak**: **$100\%$ of the excess factor ($1.754016\times$)**.
   Fitting two independent 1D parabolas along $y=0$ and $x=0$ evaluates the $x$-derivative at $y=0$ instead of at the subpixel peak $y_* = -\Delta_y$, introducing the cross-Hessian contamination $G_{xy}\Delta_y \approx H_{xy}\Delta_y$. Mathematically, the separable parabola is **one step of Jacobi iteration on the $2\times 2$ CCF Hessian $H$**:
   $$A_{\text{sep}} = -\text{diag}(D_{xx}, D_{yy})^{-1} G \implies \mu_{\pm}(A_{\text{sep}}) = -\bar{d} \pm \rho_{xy} = -0.997598 \pm 0.756418 \in \{-1.754016, \, -0.241181\},$$
   where $\bar{d} = \frac{1}{2}(G_{xx}/D_{xx} + G_{yy}/D_{yy}) = 0.997598$ and $\rho_{xy} = \sqrt{\frac{G_{xy}G_{yx}}{D_{xx}D_{yy}}} = 0.756418$.
   Why is $\rho_{xy}$ so large ($0.7564$) under `prod` weight compared to `iso` weight ($0.2170$)? Because `alignPatch` line 4739 normalizes $k_x$ by `nfx = nx/2 + 1 = 65` instead of `nx = 128`, damping $k_x$ nearly $4\times$ harder in `exp(-2*dist2*scaled_B)`. In the synthetic target (`generate_motion_diagnostics.py`), this suppresses the second frequency band $(k_x, k_y) = (7, -3)$ ($k_x k_y = -21 < 0$) relative to the lowest band $(3, 2)$ ($k_x k_y = +6 > 0$), creating a strongly tilted elliptical peak.

### 2.3 Why Damping Masks a Peak-Estimator Defect Instead of Fixing It
Because $A_{\text{sep}}$ splits the eigenvalues symmetrically around $-\bar{d}\approx -1$ into an over-gained anti-diagonal mode ($\mu_- = -1.7540$) and an under-gained diagonal mode ($\mu_+ = -0.2412$), multiplying by a scalar $g = 0.5$ cannot fix the conditioning ($\kappa(A_{\text{sep}}) = |\mu_-/\mu_+| = 7.27$ is invariant to scalar scaling!):
- Under $g=0.5$, the slow mode eigenvalue becomes $\lambda_+ = 1 - 0.5 \times 1.25 \times 0.241181 = +0.849262$ (after 5 iterations, $0.849262^5 = 0.4418$, leaving $44\%$ of the error), and its raw update is only $|\eta_+| = 0.3015$ of the remaining error, triggering false convergence at the $0.5\text{ px}$ stop.
- By contrast, inverting the $2\times 2$ Hessian using the 4 corner pixels $(x_0 \pm 1, y_0 \pm 1)$ already present in `Iccs` ($D_{xy} = \frac{1}{4}[m(1,1)-m(1,-1)-m(-1,1)+m(-1,-1)]$) gives:
  $$A_{\text{2D}} = -\begin{pmatrix} D_{xx} & D_{xy} \\ D_{xy} & D_{yy} \end{pmatrix}^{-1} G = \begin{pmatrix} -0.990760 & -0.007193 \\ -0.009591 & -0.991893 \end{pmatrix}, \quad \text{spec}(A_{\text{2D}}) = \{-0.999652, \, -0.983001\},$$
  which restores $\lambda(J_{\text{2D}}) \in \{-0.249565, \, -0.228752\}$ at $N=5$ with $g=1$ (and $\lambda \in \{+0.000278, \, +0.013599\}$ with the principled leave-one-out factor $g_{\text{LOO}} = \frac{N-1}{N} = 0.8$).

---

## 3. Challenge 3: Principled vs. Tuned Gain & Stability Range Across $N$ and Weighting

### 3.1 Is $g = 0.5$ Principled or Tuned?
$g = 0.5$ is **not derived from a principle**; it is an empirical round number selected after observing the Round 1 linearized eigenvalue $\lambda_- \approx -1.196$ at $N=5$ (`E1-PREDICTION.md`). Specifically:
- The principled simultaneous leave-one-out relaxation factor is $g_{\text{LOO}}(N) = \frac{N-1}{N}$ ($0.6667, 0.8000, 0.8889, 0.9231, 0.9500$ for $N = 3, 5, 9, 13, 20$).
- Even for the unfixed separable parabola, the scalar gain that minimizes the spectral radius $\rho(I_2 + g\frac{N}{N-1}A_{\text{sep}})$ is $g_{\text{opt}}(N) = \frac{N-1}{N\bar{d}} = 0.8019$ at $N=5$, which achieves $\rho = \frac{\rho_{xy}}{\bar{d}} = 0.7582 < 0.8493 = \rho(J_{g=0.5})$.
- The choice $g = 0.5$ sits near the fast-mode zeroing gain $g_{\text{zero}-}(5) = \frac{1}{|\eta_-|} = \frac{4}{5 \times 1.754016} = 0.4561$ specific to $N=5$ and `prod` weighting on this target image.

### 3.2 Exact Linear Stability Range $0 < g < g_{\max}(N, W) = \frac{2(N-1)}{N|\mu_-(A_W)|}$

| Weight | $N$ | $\frac{N}{N-1}$ | $\eta_-$ (fast update) | $\eta_+$ (slow update) | Stable Range $(0, g_{\max})$ | $\lambda_{\pm}(g=1.0)$ | $\rho(g=1.0)$ | $\lambda_{\pm}(g=0.5)$ | $\rho(g=0.5)$ |
|---|---|---|---|---|---|---|---|---|---|
| `prod` | 3 | $1.5000$ | $-2.631024$ | $-0.361771$ | $(0, \, 0.760160)$ | $-1.6310, \, +0.6382$ | $1.6310$ (UNSTABLE) | $-0.3155, \, +0.8191$ | $0.8191$ |
| `prod` | 5 | $1.2500$ | $-2.192520$ | $-0.301476$ | $(0, \, 0.912192)$ | $-1.1925, \, +0.6985$ | $1.1925$ (UNSTABLE) | $-0.0963, \, +0.8493$ | $0.8493$ |
| `prod` | 9 | $1.1250$ | $-1.973268$ | $-0.271328$ | $(0, \, 1.013547)$ | $-0.9733, \, +0.7287$ | $0.9733$ (STABLE) | $+0.0134, \, +0.8643$ | $0.8643$ |
| `prod` | 13 | $1.0833$ | $-1.900184$ | $-0.261279$ | $(0, \, 1.052530)$ | $-0.9002, \, +0.7387$ | $0.9002$ (STABLE) | $+0.0499, \, +0.8694$ | $0.8694$ |
| `prod` | 20 | $1.0526$ | $-1.846332$ | $-0.253874$ | $(0, \, 1.083229)$ | $-0.8463, \, +0.7461$ | **$0.8463$** (STABLE) | $+0.0768, \, +0.8731$ | **$0.8731$ (WORSE)** |
| `iso` | 3 | $1.5000$ | $-1.817709$ | $-1.166781$ | $(0, \, 1.100286)$ | $-0.8177, \, -0.1668$ | $0.8177$ (STABLE) | $+0.0911, \, +0.4166$ | $0.4166$ |
| `iso` | 5 | $1.2500$ | $-1.514758$ | $-0.972317$ | $(0, \, 1.320343)$ | $-0.5148, \, +0.0277$ | $0.5148$ (STABLE) | $+0.2426, \, +0.5138$ | $0.5138$ |
| `iso` | 9 | $1.1250$ | $-1.363282$ | $-0.875085$ | $(0, \, 1.467048)$ | $-0.3633, \, +0.1249$ | **$0.3633$** (STABLE) | $+0.3184, \, +0.5625$ | **$0.5625$ (WORSE)** |
| `iso` | 13 | $1.0833$ | $-1.312790$ | $-0.842675$ | $(0, \, 1.523473)$ | $-0.3128, \, +0.1573$ | **$0.3128$** (STABLE) | $+0.3436, \, +0.5787$ | **$0.5787$ (WORSE)** |
| `iso` | 20 | $1.0526$ | $-1.275586$ | $-0.818793$ | $(0, \, 1.567907)$ | $-0.2756, \, +0.1812$ | **$0.2756$** (STABLE) | $+0.3622, \, +0.5906$ | **$0.5906$ (WORSE)** |

*(Worst-case over all possible image spectra where $\rho_{xy}\to 1 \implies |\mu_-|\to 2$: $g_{\max}^{\text{worst}}(N) = \frac{N-1}{N}$.)*

- **Safety across the range**: While $g=0.5$ is asymptotically linearly stable ($\rho < 1$) for all $N \ge 3$, it is **only beneficial near $N=3, 5$ under `prod` weight**. For `prod` at $N \ge 9$ and `iso` at all $N \ge 3$, $g=1$ is already linearly stable; for `prod` at $N=20$ and `iso` at $N \ge 9$, $g=0.5$ **strictly worsens the spectral radius $\rho(J)$** and slows convergence.

---

## 4. Challenge 4: Do the 5-Stop Regressions Indicate Slower Convergence or Harm?

We must separate the `iso` regressions from the `prod` regressions using the saved iteration histories in `e1-intervention.json`:

1. **`vel0-N13-iso` ($0.0264\to 0.2149\text{ \AA}$, PASS $\to$ FAIL) and `vel0-N20-iso` ($0.0363\to 0.3030\text{ \AA}$, PASS $\to$ FAIL)**:
   - At $g=1$, both converge in **3 iterations** (`raw_update = 0.1451 px` and `0.2402 px < 0.5 px`).
   - At $g=0.5$, because $\rho(J)$ is degraded from $0.3128, 0.2756$ to $0.5787, 0.5906$, neither reaches `raw < 0.5 px` by iteration 5 (`last_raw = 0.5484 px` and `0.7760 px`; `converged = False`). In the 50-iteration trace, both cross `raw < 0.5 px` and pass the $0.20\text{ \AA}$ gate at **iteration 6** ($0.1199\text{ \AA}$ and $0.1583\text{ \AA}$).
   - Note, however, that on `vel0-N20-iso`, halving step 1 leaves an $11.93\text{ px}$ residual (vs $1.36\text{ px}$ at $g=1$), inducing a large nonlinear overshoot at iteration 2 (`raw_update = 19.6129 px` vs `1.5670 px` at $g=1$).
2. **Production-weight (`prod`) regressions at 5-stop (`vel0-N5-prod`, `vel0-N13-prod`, `vel0-N20-prod`, `vel1-N13-prod`, `vel1-N20-prod`) — GENUINE HARM (Premature Tolerance Stall)**:
   - Unlike `vel0-N13/20-iso`, the production-weight regressions are **not** caused by hitting the 5-iteration budget:
     - `vel0-N5-prod-gain0.5-5it`: **stops early at iteration 4** (`converged = True`, `raw = 0.1871 px < 0.5 px`) at **$0.467552\text{ \AA}$** (worse than `gain1`'s $0.404234\text{ \AA}$).
     - `vel1-N13-prod-gain0.5-5it`: **stops early at iteration 4** (`converged = True`, `raw = 0.1633 px < 0.5 px`) at **$0.402256\text{ \AA}$** (**+69.5% worse** than `gain1`'s $0.237302\text{ \AA}$).
     - `vel0-N13-prod-gain0.5-5it` (`raw = 0.2087 px < 0.5 px`, p95 $0.4084\to 0.6201\text{ \AA}$) and `vel1-N20-prod-gain0.5-5it` (`raw = 0.1447 px < 0.5 px`, RMS $0.2470\to 0.3037\text{ \AA}$) both terminate at iteration 5 with **`converged = True`**.
     - Even `vel0-N20-prod-gain0.5` ($0.439490\text{ \AA}$ at iter 5 vs `gain1`'s $0.303939\text{ \AA}$) crosses `raw = 0.2056 px < 0.5 px` at **iteration 6** at **$0.376950\text{ \AA}$** (`FAIL`), still **+24.0% worse** than `gain1`.
   - **Mechanism**: Because $g=0.5$ annihilates the fast mode ($\lambda_-(0.5)\in[-0.096,+0.077]$) in 3–4 steps while leaving a large error in the slow mode ($\lambda_+(0.5)\in[0.849,0.873]$) where the unscaled update sensitivity is only $|\eta_+|\in[0.254,0.301]$, `raw_update < 0.5 px` triggers while the true position error is still $0.32\text{--}0.53\text{ px}$ ($0.28\text{--}0.47\text{ \AA}$). Increasing `--max_iter` to 50 under the production `0.5 px` tolerance does not fix a single one of these cases.

---

## 5. Challenge 5: Concrete Harmful Counterexamples to a Default-Off $g=0.5$ Option

1. **Noisy 5-frame movie (`noisy` fixture in `e1-intervention.json`) — Premature global stall + catastrophic local fit degradation**:
   - **In `double-gain0.5-5it`**: Global alignment takes two half-steps (`0.7816 px`, `0.7779 px`) and **stalls at iteration 3** (`raw_update = 0.0497 px < 0.5 px`) at a degraded global trajectory (even at 50 steps, global error is **$0.870770\text{ \AA}$** vs **$0.698054\text{ \AA}$** for `gain=1`, +24.7% worse). When the frames are globally aligned with this stalled trajectory, patch `[1, 3]` at `(104, 15)` fails the 5-step convergence check (`last_raw = 0.5793 px > 0.5 px`), reducing accepted patches from `8/9` (`gain=1`) to `7/9` (`gain=0.5`) and leaving only one patch on the right column $x=104$. The 18-term polynomial fit condition number jumps from $4784.8$ to $7242.4$, and full-field error explodes:
     - Runtime RMS: **$1.668452\text{ \AA} \to 3.049155\text{ \AA}$ (+82.8% worse)**
     - Runtime p95: **$3.319727\text{ \AA} \to 6.398229\text{ \AA}$ (+92.7% worse)**
     - Runtime max: **$7.136670\text{ \AA} \to 21.492574\text{ \AA}$ (3.01$\times$ worse)**
   - **In `map32-gain0.5-5it`**: Global alignment stalls at iteration 4 (`raw = 0.1221 px < 0.5 px`), and the altered global alignment causes a corrupted outlier patch (`patch [2, 3]`, `state_norm = 22.60 px`, rejected under `gain=1` with `last_raw = 3.2404 px`) to **falsely pass `raw < 0.5 px` at iteration 3** (`last_raw = 0.3587 px`), worsening full-field RMS from **$1.635645\text{ \AA}$ to $1.744475\text{ \AA}$**.
2. **Longer movies ($N=13, 20$) under production weighting and tolerance**:
   - As shown in Section 4, `vel1-N13-prod` worsens from **$0.237302\text{ \AA}$ to $0.402256\text{ \AA}$** (stalling at iter 4 with `raw = 0.1633 px < 0.5 px`), and `vel0-N20-prod` worsens from **$0.303939\text{ \AA}$ to $0.439490\text{ \AA}$** (max $0.838566\text{ \AA} > 0.80\text{ \AA}$) at iter 5 and stalls at iter 6 at **$0.376950\text{ \AA}$**.
3. **Every retained identifiable fixture under $g=0.5$ terminates at iteration $\le 4$ under the production $0.5\text{ px}$ tolerance**:
   - Across `zero` (iter 1), `integer` (iter 4), `fractional` (iter 3), `affine` (iter 3 in `double`, iter 4 in `map32`), `pedestal` (iter 3 in `double`, iter 1 in `map32`), and `noisy` (iter 3 in `double`, iter 4 in `map32`), **none reaches iteration 5** because `raw_update` drops below `0.5 px` by iteration 4. Thus, under production tolerance, `map32` still fails `fractional` ($0.260018\text{ \AA}$) and `affine` ($0.200436\text{ \AA}$), and `double` still fails `integer` ($0.330736\text{ \AA}$).

---

## 6. Challenge 6: Smallest Native Experiment to Falsify the Claim

Because native `MotioncorrRunner::alignPatch` uses hard-coded `tolerance = 0.5 px` and `float32` `Fframes`/`Iccs` (where DC pedestal quantization makes $d_{xx}=d_{yy}=-6\text{ ULPs}$), the claim can be falsified by a minimal **2-fixture native CPU run** (no new fixtures, no GPU required):

1. **Minimal Falsification Experiment (Production Stop & `--max_iter 50` Equivalence)**:
   - Run the proposed native CPU prototype (`--use_own --skip_defect` with the global $0.5$-gain flag) on the two pinned 5-frame translation fixtures `integer.mrcs` and `fractional.mrcs` at `--max_iter 5` and `--max_iter 50`.
   - **Falsification criteria**:
     1. *Early-stop equivalence*: Both movies terminate at iteration $\le 4$ with `RMSD < 0.5 px`, so `--max_iter 50` produces **bit-identical** STAR/runtime trajectories to `--max_iter 5`, falsifying any claim that `--max_iter 50` can access the long-budget recovery without also overriding the internal `0.5 px` tolerance.
     2. *Gate failure on `fractional.mrcs` (and sensitivity on `integer.mrcs`)*: `fractional.mrcs` fails the $0.20/.40/.80\text{ \AA}$ gate (in `map32-gain0.5-5it` it scores $0.260018 / 0.435231 / 0.435231\text{ \AA}$ FAIL after stopping at iter 3 with `raw = 0.1648 px`). Moreover, on `integer.mrcs`, where exact `double-gain0.5-5it` fails ($0.330736\text{ \AA}$) and `map32-gain0.5-5it` ($0.181790\text{ \AA}$) only barely passes due to `float64`-FFT/`float32`-map quantization, native `float32` `fftwf` + `shiftNonSquareImageInFourierTransform` shifts the 6-ULP parabola denominator across the $\sim 0.083\text{ px}$ ($0.074\text{ \AA}$) quantization lattice.
2. **Secondary Falsification (Even with a diagnostic tolerance override `tol = 1e-9, max_iter = 50`)**:
   - On `fractional.mrcs` with `tol = 1e-9, max_iter = 50`, compare native CPU `gain = 1.0` vs `gain = 0.5`: because the `float32` CCF peak has a $\pm 0.083\text{ px}$ ULP deadzone where $v_p - v_n = 0$, `gain = 0.5` stalls dead (`RMSD = 0`) inside the deadzone at a **worse** error than `gain = 1.0` (as already seen in `map32-50it`: $0.104588\text{ \AA}$ for `gain=0.5` vs $0.081461\text{ \AA}$ for `gain=1.0`).

---

## 7. Final Recommendation

1. **Prototype Decision**: **NO-GO** for a default-off native CPU prototype using a fixed $0.5$ global gain.
   - A fixed $0.5$ scalar gain does not fix the underlying mathematical defect; it halves the step along the already under-gained diagonal mode ($\lambda_+: 0.6985 \to 0.8493$), causing systematic premature termination at the `0.5 px` tolerance check across `prod` $N \in \{5, 9, 13, 20\}$ trajectories, failing `fractional` and `affine` in `map32-5it`, and causing severe harm on `noisy` (RMS $+82.8\%$, max $+201.2\%$ in `double`; false outlier-patch acceptance in `map32`).
2. **Principled Derivation (New Hypothesis Requiring Fresh Controls)**:
   - Any estimator repair in this family should be derived from first principles rather than tuned scalar damping:
     1. **Peak-estimator repair**: Replace the separable 1D parabola in `alignPatch` with a $2\times 2$ Hessian solve on the existing $3\times 3$ peak neighborhood (using the 4 corner samples $m(y_0\pm 1, x_0\pm 1)$ to compute $D_{xy}$), which removes the cross-axis Jacobi contamination $\rho_{xy}$ and restores $A_{\text{2D}} \approx -I_2$ across all orientations and weightings without slowing the diagonal mode.
     2. **Frame-coupling step size**: If simultaneous updates are retained, the principled leave-one-out step factor is $g_{\text{LOO}}(N) = \frac{N-1}{N}$ (which depends on $N$ and approaches $1$ for long movies, avoiding the $N=13, 20$ regressions of fixed $g=0.5$).
     3. **DC pedestal removal before `float32` IFFT**: Zeroing the $(0,0)$ DC bin of `Fccs` (or subtracting frame means) removes the $40000$ DC offset in `Iccs`, recovering $\sim 13$ bits ($\sim 8000\times$) of `float32` precision in $v_p + v_n - 2v_0$ and eliminating the 6-ULP quantization deadzone.
   - Because this constitutes a **new estimator hypothesis** (modifying the peak rule / $N$-dependent step / DC handling rather than fixed $0.5$ global damping), it **must not** be retrofitted into E1; it requires a fresh pre-registered prediction and control set.
