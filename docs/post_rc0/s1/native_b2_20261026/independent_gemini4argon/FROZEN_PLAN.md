# Frozen Diagnostic Hypothesis & Control Plan (Research Sub-Agent, Gemini4Argon)

Frozen prior to running any local numerical calculations on retained evidence.

## Scope & Constraints
- Read-only mathematical/statistical challenge on retained data only (`/tmp/motioncorr-b2-native-20261026` and `/tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures`).
- No source edits, no new native/movie/GPU jobs, no parameter/threshold/degree tuning, no movie pixel reads.
- Local tiny numerical scripts restricted to `<= 2` BLAS/OMP threads in `/tmp/mc-b2-challenge-gemini4argon-20261026`.

## Hypotheses & Falsification Rules

1. **H0 (Solver / Numerical Conditioning / Serialization / Acceptance-Gate Mismatch):**
   - *Hypothesis:* The K267 `noisy` ($N=5$) regression (OFF runtime RMS $2.342955\,\text{\AA}$, max $9.903899\,\text{\AA}$ $\to$ ON-v3 runtime RMS $3.587250\,\text{\AA}$, max $19.563705\,\text{\AA}$) arises from a solver defect in `LocalB2::fit`, numerical rank deficiency/conditioning, STAR serialization loss, or a difference in acceptance gating (`largest_delta > 3` px or `fit_rmsd >= 10` px).
   - *Test/Falsification:* Recompute the B2 fit independently via (i) full 27-column augmented SVD `[S \otimes Z_B2, I_9 \otimes 1_5]` and (ii) exact separable Kronecker projection `S^+ Y ((M Z_B2)^+)^T` on the retained `noisy` and `affine` observations. Compare against `runtime.json` and `noisy.star`, and evaluate both `largest_delta` and `fit_rmsd` (with and without nuisance subtraction). H0 is falsified as the regression driver if native ON-v3 matches independent SVD to STAR observation precision ($\sim 10^{-5}$ px) and both gates pass in OFF and ON-v3.

2. **H1 (Temporal Operator Leverage & Variance Amplification at $N=5$ vs $N=40$ under Singular $T_r$):**
   - *Hypothesis:* Because `group_frames=1, interpolate_shifts=0` maps $N-1$ pre-pin patch shifts $L_p \in \mathbb{R}^{N-1}$ to $N$ observations $y_p = T_r L_p \in \mathbb{R}^N$ with $(T_r L)_0 = 0.5 L_1$ and $(T_r L)_g = L_g + 0.5 L_1$ ($g \ge 1$), the observation space has dimension $N-1$. Adding a free per-patch intercept removes the $z=0.5$ origin tether and projects $(N-1)$ pre-pin shifts onto 3 cubic temporal basis vectors after demeaning over $N$ points. At $N=5$ ($N-1=4$ free times for 3 cubic + 1 intercept parameters), freeing the intercept dramatically increases temporal operator norm and endpoint ($f=4$) leverage on late-frame/mid-frame errors compared to OFF, whereas at $N=40$ ($39$ free times for $4$ parameters) demeaning removes the persistent $+0.5 L_1$ anchor offset with minimal variance inflation.
   - *Test/Falsification:* Derive and compute the exact $(N \times (N-1))$ temporal operators $K_{\text{OFF}} = Z_{\text{eval}} Z_{\text{OFF}}^+ T_r$ and $K_{\text{B2}} = Z_{\text{eval}} (M Z_{\text{B2}})^+ T_r$, together with the spatial projection $P_S = S S^+$ on the $3\times 3$ ($128\times 96$) and $5\times 5$ ($4096^2$, $5760\times 4092$) patch grids. Compare singular values, frame-by-frame noise covariance $\text{Cov}(\hat{h}) = K \Sigma_L K^\top$, and impulse responses at $N=5$ vs $N=40$.

3. **H2 (Causal Attribution: Unabsorbed Non-Cubic Global Error $-\Delta G$ vs Stochastic Patch CCF Outliers in `noisy`):**
   - *Hypothesis:* Because `affine` (noise=0) and `noisy` (noise=4) share the exact same ground-truth displacement field (`839c484f...`), linearity of the Kronecker estimator allows exact additive decomposition of the published local field into:
     - (a) True local motion $T_r[h_{\text{true}}]$,
     - (b) Global alignment error coupling $T_r[-\Delta G]$ (which lies strictly in the spatially constant mode $S_0 = 1$ and tests global/local cancellation of non-cubic $G$ error), and
     - (c) Pure stochastic patch CCF errors $T_r[\eta_p]$ (including catastrophic false-peak outliers in `noisy` such as patch (2,2) $f=3$, patch (2,3) $f=5$, patch (3,2) $f=5$).
   - *Test/Falsification:* Quantify the exact RMS and max field errors contributed by (a), (b), and (c) in both OFF and ON-v3, and test counterfactual removal/isolation of the global error vs the patch CCF outliers. This directly decides whether unabsorbed non-cubic $G$ error or free-intercept amplification of stochastic patch errors causes the `noisy` regression.
