# Independent Mathematical & Source Review: W4 Offline Affine Attribution (`REPORT.md` §§3–6 & `DRAFT_HELD_ISSUE_time_convention.md`)

- **Review workspace**: `/tmp/motioncorr-20261025-w4-review/REVIEW.md`
- **Reviewed packet**: `/tmp/motioncorr-20261025-w4attr/{REPORT.md, DRAFT_HELD_ISSUE_time_convention.md, scripts/w4_allpatch_decomposition.py, scripts/w4_shrinkage.py, out/allpatch-attempt01.json, out/shrinkage-attempt01.json, src805/}`
- **Source revision verified**: `805d9de27898b4a10e6212e65098d5995a40fdb1` (`/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-01f535cb`) and `#275` receipts (`7cda1e89…e5db`)
- **Mode**: Read-only source inspection and independent analytic/algebraic verification. No native, GPU, build, or SSH jobs run; author's artifacts and worktrees untouched.
- **Historical baseline & gates**: Unchanged `#273` totals (**2 PASS / 10 FAIL / 4 UNIDENTIFIABLE**), unchanged `0.20 / 0.40 / 0.80 Å` (`0.225989 / 0.451977 / 0.903955 px` at `0.885 Å/px`) field thresholds over fixed ROI `[12:84, 12:116]`, retained 5-frame failures (`affine` CPU `0.454743 px` FAIL, CUDA `0.323146 px` FAIL), and retained `N=20` isotropic-weight `11.833 px` counterexample.

---

## 1. Overall Verdict

**NO NUMERICAL BLOCKER for bounded offline evidence; MATERIAL MATHEMATICAL QUALIFICATIONS & WORDING CORRECTIONS REQUIRED before relying on `REPORT.md` §§1, 4–6 or filing `DRAFT_HELD_ISSUE_time_convention.md`.**

All numeric outputs in `out/allpatch-attempt01.json` and `out/shrinkage-attempt01.json` are algebraically and source-consistently reproduced from the pinned `#275` receipts and `805d9de2` source. However, four mathematical/causal subtleties require explicit correction in how the result is stated:

1. **The `0.242 px` (CPU) / `0.333 px` (CUDA) exact-observation failure does NOT come from the true spatially varying affine deformation (`local_error_px = 0.000 px`); it is 100% the spatially uniform (`global_mean_error_px`) residual of upstream nonlinear global-stage trajectory error $\delta G[f]$ (`0.5436 px` CPU / `0.3753 px` CUDA RMS) after imperfect cancellation by the local polynomial's spatially constant terms $\{1\cdot z, 1\cdot z^2, 1\cdot z^3\}$.** Because the fixture's true affine warp $-(q-c)A_{\text{true}}(f)^T$ is linear in frame index $f$, the production convention reproduces its spatially varying component with **zero error**.
2. **The mechanism is a coupled `(z_fit = g + 0.5, zero-anchor -interp[0] = +0.5*local[1], z_eval = g)` convention on a constant-free cubic basis $\{z, z^2, z^3\}$, NOT `z_fit = g + 0.5` vs `z_eval = g` alone.** In production (`src/motioncorr_runner.cpp:3827–3832`), subtracting `interpolated_shifts[0] = 1.5*local[0] - 0.5*local[1] = -0.5*local[1]` linearly extrapolates frame 0 from $z_0 = 0.5$ back to $z = 0$ (where $P(x,y,0) = 0$), and evaluating at $z_{\text{eval}} = g$ shifts time back by $-0.5$ frames. On linear trajectories $L[g] = \alpha g$, those two half-frame operations cancel identically ($\alpha g + 0.5\alpha = \alpha(g+0.5) \mapsto \alpha g$). Changing `z_fit` to $g$ without removing `-interp[0]` (or removing `-interp[0]` while keeping $z_{\text{fit}} = g + 0.5, z_{\text{eval}} = g$) breaks exactness even on linear motion (`0.446 px` / `0.452 px` RMS error on $L[f] = f$).
3. **`0.242 / 0.333 px` is an exact-observation counterfactual error, NOT an unconditional lower bound ("floor") across arbitrary patch observations, and is distinct from the cubic model-capacity floor (`0.096568 px` CPU / `0.017456 px` CUDA).** Under the production operator $T_{\text{prod}}$, the exact-observation error $(I - T_{\text{prod}})\,\delta G$ splits **orthogonally** in time into:
   - an irreducible **cubic model-capacity floor** $(I - P_{\text{int}})\,\delta G \in \mathcal{C}^\perp = \text{span}\{[0, 4, -6, 4, -1]^T\}$ of **`0.096568 px` (CPU) / `0.017456 px` (CUDA) RMS** (`PASS` on both backends), which is orthogonal to every cubic field, and
   - a **pure time/zero-anchor convention distortion** $(P_{\text{int}} - T_{\text{prod}})\,\delta G \in \mathcal{C} = \text{span}\{z, z^2, z^3\}$ of **`0.222075 px` (CPU) / `0.332464 px` (CUDA) RMS**.
   Because $(P_{\text{int}} - T_{\text{prod}})\,\delta G$ lies *inside* the cubic space $\mathcal{C}$, it is not orthogonal to the propagated patch observation error $E_{\text{obs}} \in \mathcal{C}$. On CUDA, the spatial-mean components of $E_{\text{floor}}$ and $E_{\text{obs}}$ have inner-product cosine **$-0.7256$** (because y-shrunken native patch observations do not inject the full $-0.5\,\delta G_y[1]$ extrapolation overshoot), so the actual CUDA runtime field error (**`0.323140 px` RMS**; global-mean **`0.241458 px` RMS**) is *smaller* than the `0.332922 px` "floor".
4. **Neither the time/anchor convention nor the global divergence is the sole cause of the `affine` failure.** Even if the production convention is replaced by the integer-time convention (`obs[g] = local[g] = star_obs[g] - star_obs[0]` fitted and evaluated at integer $z = g$) on the **retained native patch observations**, both backends **still fail** the `0.226 px` gate (**`0.358338 px` RMS on CPU**, **`0.287613 px` RMS on CUDA**) because the native patch observation errors `local[g] - L*_p[g]` contribute **`0.345081 px` (CPU)** and **`0.287083 px` (CUDA) RMS** in $\mathcal{C}$. Thus `(global error × production time/anchor convention)` and `(patch observation error/shrinkage)` are each independently gate-failing co-causes on this case.

---

## 2. Source Verification at `805d9de2`

| Component | Source location (`805d9de2`) | Verified production behavior (`affine`: $128\times 96\times 5$, `group=1`, `interpolate_shifts=false`, `first_frame_sum=1`, `prescaling=1`) | Match in `w4_allpatch_decomposition.py` / `w4_shrinkage.py` |
|---|---|---|---|
| Frame grouping | `src/motioncorr_runner.cpp:2181–2205` | `n_groups = 5`, `group_start = {0,1,2,3,4}`, `group_size = {1,1,1,1,1}`. | Exact. |
| Patch bounds & centers | `src/motioncorr_runner.cpp:3454–3524` | `patch_nx = 42`, `patch_ny = 32` (both even; X ranges `[0,42), [42,84), [84,126)`, omitting columns `126..127`). Integer division `x_center = (x_start + x_end - 1) / 2` gives `{20, 62, 104}`; `y_center` gives `{15, 47, 79}` (0.5 px below the geometric window centroids `{20.5, 62.5, 104.5}` and `{15.5, 47.5, 79.5}`). | Exact (`CENTRES` uses `{20,62,104}×{15,47,79}`; `(0.5,0.5)` centroid shift separately tested and changes floor RMS by $+0.0001\text{ px}$ CPU / $-0.0011\text{ px}$ CUDA). |
| Frame-0 gauge in `alignPatch` | `src/motioncorr_runner.cpp:4825–4838` | Every iteration subtracts `cur_shifts[0]` from all frames and accumulates into `xshifts/yshifts`, enforcing `g[0] = (0,0)` and `local[0] = (0,0)`. | Exact. |
| `interpolateShifts` & default `else` branch | `src/motioncorr_runner.cpp:3814–3836`, `4250–4277` | `centers[g] = g + 0.5`. For `iframe = 0` (`cur_group = 0`), `interpolated_shifts[0] = 1.5*local[0] - 0.5*local[1] = -0.5*local[1]`. Default `else` (`!interpolate_shifts`) pushes `obs[g] = local[g] - interpolated_shifts[0] = local[g] + 0.5*local[1]` at `patch_frames[g] = g + 0.5`. Since `local[0] = 0`, `obs[0] = 0.5*local[1]` and `obs[g] - obs[0] = local[g]`. | Exact in both scripts (`w4_shrinkage.py:23` recovers `local[g] = obs[g] - obs[0]`). |
| Polynomial basis & solver | `src/motioncorr_runner.cpp:3861–3899`, `src/matrix2d.h:1291–1325` | 18-term basis $\{1, x, x^2, y, y^2, xy\} \otimes \{z, z^2, z^3\}$ with $x = X/N_x - 0.5$, $y = Y/N_y - 0.5$, no constant term in $z$. Solved via SVD (`svdcmp`/`svbksb`) with threshold `EPS = 1e-10`. Since $\kappa(A) = 4069.25$ (CPU) / $4768.47$ (CUDA), $\sigma_{\min}(A) \approx 0.03 \gg 10^{-10}$, so no singular values are zeroed. | Exact basis ordering and coordinates (`w4_allpatch_decomposition.py:48–59`). |
| STAR `local_shift` frame truncation | `src/motioncorr_runner.cpp:3949`, `src/micrograph_model.cpp:289` | Runner pushes `patchZ = z + first_frame_sum = g + 1.5`; `Micrograph::write` casts `(int)patchZ[i]`, truncating `g + 1.5` to `g + 1` (`1..5`). | Exact (`rlnMicrographFrameNumber - 1 + 0.5` recovers `g + 0.5` when `group = 1, first_frame_sum = 1`). |
| Model evaluation time `z` | `src/motioncorr_runner.cpp:4338, 4406, 4577`, `src/acc/cuda/cuda_realspace_dw.cu:49`, `src/micrograph_model.cpp:365` | Both CPU and CUDA reconstruction paths and `Micrograph::getShiftAt` evaluate `ThirdOrderPolynomialModel` at integer `z = iframe = 0, 1, 2, 3, 4` (where $z = 0$ gives zero local shift). | Exact (`field_of` evaluates at `float(f)` for $f \in \{0..4\}$). |
| Independent truth & gauge | `test-data/generate_motion_diagnostics.py:45–81`, `tools/check_motion_diagnostics.py:47–84` | Forward map $p = q + g(f) + (q - c)A(f)^T$ with $g(0) = 0, A(0) = 0$; `truth[f] = q - forward(r, f, q) = -(g(f) + (q - c)A(f)^T)`. Fixed frame-0 material coordinates, no registration, evaluated on `ROI = [12, 84, 12, 116]`. | Exact. |

---

## 3. Analytic Derivation, Orthogonal Decomposition & Temporal Counterexamples

### 3.1 Kronecker structure and why the spatially varying affine warp has zero floor
For $N_p$ accepted patches and $N_f = 5$ frames, the $5N_p \times 18$ design matrix factors as a Kronecker product:
$$A = \Phi \otimes Z_{\text{fit}}, \qquad A^+ = \Phi^+ \otimes Z_{\text{fit}}^+,$$
where $\Phi \in \mathbb{R}^{N_p \times 6}$ spans $\{1, x, x^2, y, y^2, xy\}$ (with $\text{rank}(\Phi) = 6$ for both the 9-patch CPU set and 8-patch CUDA set) and $Z_{\text{fit}} \in \mathbb{R}^{5 \times 3}$ has rows $[z_g, z_g^2, z_g^3]$ at $z_g = g + 0.5$.
Let $Z_{\text{eval}} \in \mathbb{R}^{5 \times 3}$ have rows $[f, f^2, f^3]$ at $f \in \{0, 1, 2, 3, 4\}$, and let $M \in \mathbb{R}^{5 \times 5}$ be the `interpolateShifts` zero-anchor matrix mapping $L \mapsto \text{obs}$:
$$(\text{obs})_g = L[g] - (1.5\,L[0] - 0.5\,L[1]) \implies M = I_5 - 1.5\,\mathbf{1} e_0^T + 0.5\,\mathbf{1} e_1^T.$$
Then the production temporal operator mapping any 5-frame trajectory $L$ (with $L[0] = 0$) to its evaluated polynomial trajectory at $f \in \{0, 1, 2, 3, 4\}$ is the $5\times 5$ matrix:
$$T_{\text{prod}} = Z_{\text{eval}}\, Z_{\text{fit}}^+\, M.$$

Now consider the ideal point-residual trajectory at patch center $(X_p, Y_p)$ relative to the backend's global trajectory $G[f] = T(c_x, c_y, f) + \delta G[f]$:
$$L^*_p[f] = T(X_p, Y_p, f) - G[f] = \underbrace{L_{\text{aff}}(X_p, Y_p, f)}_{\text{linear in }(x,y)\text{ and linear in }f} - \underbrace{\delta G[f]}_{\text{spatially constant }(\phi_0 = 1)}.$$

- **Analytic Control 1 (Exactness on linear-in-time trajectories $L[g] = \alpha g$)**:
  For $L[g] = \alpha g$, $M L$ has components $\alpha g + 0.5\alpha = \alpha(g + 0.5) = \alpha z_g$, which is the first column of $Z_{\text{fit}}$ scaled by $\alpha$. Hence $Z_{\text{fit}}^+(M L) = [\alpha, 0, 0]^T$, and $T_{\text{prod}} L = Z_{\text{eval}}[\alpha, 0, 0]^T = \alpha f = L$.
  Because $L_{\text{aff}}(X, Y, f) = -(f/4)(q - c)A_1^T$ is linear in $f$ and linear in $(x, y) \in \text{col}(\Phi)$, the production pipeline reproduces $L_{\text{aff}}(X, Y, f)$ with **identically zero error** (`local_error_px = 0.000000 px`, and `production_convention_truth_global_accepted = 0.000000 px`).
  Notice that if one drops `-interp[0]` ($M \to I_5$) while keeping $z_{\text{fit}} = g + 0.5, z_{\text{eval}} = g$, or changes $z_{\text{fit}} \to g$ while keeping $M$, exactness on $L[f] = f$ is **destroyed** ($\|T L - L\|_{\text{RMS}} = 0.452341\text{ px}$ and $0.446403\text{ px}$, respectively).

- **Analytic Counterexample 2 (Pure convention failure on in-model quadratic/cubic time without model-capacity confound)**:
  Take $L[g] = g^2 = [0, 1, 4, 9, 16]^T$ (or $L[g] = g^3 = [0, 1, 8, 27, 64]^T$). Since $L \in \mathcal{C} = \text{col}(Z_{\text{eval}})$, the 3-parameter cubic model at integer time has **zero capacity error** ($P_{\text{int}} L = Z_{\text{eval}} Z_{\text{eval}}^+ L = L$, $\text{RMS} = 0$). Under $T_{\text{prod}}$, however, $\text{obs}[g] = g^2 + 0.5 = (z_g - 0.5)^2 + 0.5 = z_g^2 - z_g + 0.75$ has a non-zero constant term $+0.75 \notin \text{span}\{z_g, z_g^2, z_g^3\}$ and is then evaluated at $z = g$ instead of $z_g = g + 0.5$, yielding:
  $$T_{\text{prod}}\begin{bmatrix}0\\1\\4\\9\\16\end{bmatrix} - \begin{bmatrix}0\\1\\4\\9\\16\end{bmatrix} = \begin{bmatrix}0 \\ -0.223058 \\ -1.118956 \\ -2.292954 \\ -3.350310\end{bmatrix} \quad (\text{RMS} = 1.885950), \qquad
    T_{\text{prod}}\begin{bmatrix}0\\1\\8\\27\\64\end{bmatrix} - \begin{bmatrix}0\\1\\8\\27\\64\end{bmatrix} = \begin{bmatrix}0 \\ -0.361529 \\ -4.059478 \\ -10.896477 \\ -20.675155\end{bmatrix} \quad (\text{RMS} = 10.609480).$$
  This proves analytically that the `(z_fit = g + 0.5, -interp[0], z_eval = g)` convention fails on any nonlinear temporal trajectory even when the trajectory lies 100% inside the 3-parameter cubic polynomial space.

### 3.2 Exact orthogonal separation of model capacity vs convention distortion on $\delta G[f]$
In the subspace $\{u \in \mathbb{R}^5 : u_0 = 0\} \cong \mathbb{R}^4$, the integer-time operator $P_{\text{int}} = Z_{\text{eval}}(Z_{\text{eval}}^T Z_{\text{eval}})^{-1}Z_{\text{eval}}^T$ is the **symmetric orthogonal projector** onto the 3D cubic subspace $\mathcal{C} = \text{span}\{z, z^2, z^3\}$, and $I - P_{\text{int}} = \hat{v}_\perp \hat{v}_\perp^T$ projects onto the 1D orthogonal complement spanned by the 4th-order finite-difference vector:
$$v_\perp = [0, 4, -6, 4, -1]^T, \qquad \sum_{f=1}^4 v_\perp[f]\, f^k = 0 \quad (k = 1, 2, 3), \qquad \|v_\perp\| = \sqrt{69}.$$
Because $\text{im}(T_{\text{prod}}) = \text{col}(Z_{\text{eval}}) = \mathcal{C}$, the exact-observation error $(I - T_{\text{prod}})\,\delta G$ splits **orthogonally** into:
$$(I - T_{\text{prod}})\,\delta G = \underbrace{(I - P_{\text{int}})\,\delta G}_{\in\,\mathcal{C}^\perp\text{ (cubic model-capacity floor)}} \;\oplus\; \underbrace{(P_{\text{int}} - T_{\text{prod}})\,\delta G}_{\in\,\mathcal{C}\text{ (pure convention distortion)}},$$
with exact Pythagorean identity $\|(I - T_{\text{prod}})\,\delta G\|_{\text{RMS}}^2 = \|(I - P_{\text{int}})\,\delta G\|_{\text{RMS}}^2 + \|(P_{\text{int}} - T_{\text{prod}})\,\delta G\|_{\text{RMS}}^2$:

| Backend | Raw global error $\|\delta G\|_{\text{RMS}}$ (px) | Cubic model-capacity floor $\|(I - P_{\text{int}})\,\delta G\|_{\text{RMS}}$ in $\mathcal{C}^\perp$ (px) | Pure convention distortion $\|(P_{\text{int}} - T_{\text{prod}})\,\delta G\|_{\text{RMS}}$ in $\mathcal{C}$ (px) | Combined exact-observation counterfactual $\|(I - T_{\text{prod}})\,\delta G\|_{\text{RMS}}$ (px) | Native `local[g]` refit under counterfactual integer time (px RMS) |
|---|---:|---:|---:|---:|---:|
| **CPU** | `0.543588` | **`0.096568`** PASS (`0:4:6:4:1` profile `[0, .1040, .1560, .1040, .0260]`) | **`0.222075`** | **`0.242162`** FAIL | **`0.358338`** FAIL (obs-error component `0.345081`) |
| **CUDA** | `0.375262` | **`0.017456`** PASS (`0:4:6:4:1` profile `[0, .0188, .0282, .0188, .0047]`) | **`0.332464`** FAIL | **`0.332922`** FAIL | **`0.287613`** FAIL (obs-error component `0.287083`) |

Note also that enabling production `--interpolate_shifts` (`src/motioncorr_runner.cpp:3816–3825`, which linearly interpolates `centers[g] = g + 0.5` to integer `z = g` and recenters to frame 0) still yields **`0.242959 px` RMS on CPU** and **`0.341263 px` RMS on CUDA** on exact observations, because `interpolateShifts` itself anchors unit groups at `g + 0.5`.

---

## 4. Challenge of the Four Specific Numeric Claims in `REPORT.md`

1. **"Exact patch observations fail at 0.242 px (CPU) and 0.333 px (CUDA) RMS vs 0.226 px"**:
   - **Verified numerically**, with three mandatory qualifications: (a) it is zero (`0.000 px`) on the true global trajectory and arises entirely from imperfect cancellation of the upstream nonlinear global error $\delta G[f]$ (`local_error_px = 0`); (b) model capacity accounts for only `0.096568 px` (CPU) and `0.017456 px` (CUDA) in $\mathcal{C}^\perp$, while the coupled `(z_fit = g + 0.5, -interp[0], z_eval = g)` convention distortion in $\mathcal{C}$ accounts for `0.222075 px` (CPU) and `0.332464 px` (CUDA); (c) because the $\mathcal{C}$-component is not orthogonal to observation error $E_{\text{obs}} \in \mathcal{C}$, `0.242 / 0.333 px` is an **exact-observation counterfactual**, not a mathematical lower bound over noisy/shrunken observations (on CUDA, destructive interference $\cos\theta = -0.7256$ between $E_{\text{floor}}$ and the spatial mean of $E_{\text{obs}}$ yields total runtime RMS `0.323140 px < 0.332922 px`).
2. **"Refitting STAR observations at `z = g + 0.5` reproduces runtime field to $\le 4.4\times 10^{-6}$ px"**:
   - **Verified numerically** (`4.4437e-6 px` max on CPU, `4.0767e-6 px` max on CUDA; max coefficient difference `1.94e-5` CPU, `3.47e-5` CUDA, vs `0.3825 / 0.4915 px` when refitted at naive integer $z = g$).
   - **Scope limit**: The `4.4e-6 px` residual is bounded by the 6-significant-digit rounding (`≤ 5e-6 px`) of the STAR `local_shift` table amplified by $\kappa(A) \approx 4.1\text{–}4.8\times 10^3$. It proves that production fitted `obs[g]` at $z_g = g + 0.5$ and that `np.linalg.lstsq` matches `svdcmp`/`svbksb` (`src/matrix2d.h:1291`) to print precision; it does not test solver discrepancies below `4.4e-6 px` (irrelevant to the `0.226 px` gate).
3. **"The native field error is exactly (linear, residual $2\times 10^{-14}$) this floor plus the propagated observation error (0.382 / 0.384 px RMS alone)"**:
   - **Verified numerically, but requires rewording**: In `w4_allpatch_decomposition.py:139–160`, `tot - floor_field - prop` is $B A^+ \text{obs} - B A^+ \text{ideal} - B A^+(\text{obs} - \text{ideal})$, which is `1.38e-14 px` (CPU) / `2.23e-14 px` (CUDA) purely by **distributivity of floating-point matrix multiplication** on the refitted STAR coefficients `(fcx, fcy)` (against runtime `model.txt` `(rcx, rcy)`, the difference is `4.44e-6 / 4.08e-6 px`). Moreover, vector additivity $E_{\text{tot}} = E_{\text{floor}} + E_{\text{obs}}$ must not be read as orthogonal variance additivity: in spatial modes, $\|E_{\text{tot}}\|_{\text{RMS}}^2 = \|\bar{E}_{\text{tot}}\|_{\text{RMS}}^2 + \|\widetilde{E}_{\text{tot}}\|_{\text{RMS}}^2$ (`0.424483^2 + 0.163080^2 = 0.454731^2` on CPU; `0.241458^2 + 0.214750^2 = 0.323140^2` on CUDA), where 100% of $\widetilde{E}_{\text{tot}}$ comes from $E_{\text{obs}}$ while $\bar{E}_{\text{floor}}$ and $\bar{E}_{\text{obs}}$ interfere non-orthogonally ($\cos\theta = +0.0121$ CPU, $-0.7256$ CUDA).
4. **"Runtime vs STAR differs by $\le 1.8\times 10^{-4}$ px, so `#265` serialization does not affect this verdict"**:
   - **Verified numerically**: `runtime_minus_star_field_px` is `1.76e-4 px` max / `5.06e-5 px` RMS on CPU (`0.454731` vs `0.454743 px` RMS) and `1.63e-4 px` max / `3.80e-5 px` RMS on CUDA (`0.323140` vs `0.323146 px` RMS). `#265` STAR rounding is completely ruled out as a cause of the `affine` failure.

---

## 5. Evidence Classification: Source + Offline vs UNRUN / Native

| Assertion | Status | Evidence basis & boundary |
|---|---|---|
| `group=1` default path fits `obs[g] = local[g] + 0.5*local[1]` at $z_g = g + 0.5$ and evaluates polynomial at integer $z = g$ | **SUPPORTED (Source + Offline)** | `src/motioncorr_runner.cpp:3827–3832, 4250–4277, 4406, 4577`, `src/acc/cuda/cuda_realspace_dw.cu:49`; STAR refit at $z = g + 0.5$ matches `model.txt` to `4.4e-6 / 4.1e-6 px` vs `0.383 / 0.492 px` at integer $z$. |
| STAR serialization rounding (`#265`) adds $\le 1.76\times 10^{-4}$ px max / $5.1\times 10^{-5}$ px RMS | **SUPPORTED (Offline from `#275` native receipts)** | Direct comparison of `state/{global,model}.txt` (`%.17g`) against `out/affine.star`. |
| Exact point observations + retained backend `global.txt` fail at `0.242 px` (CPU) / `0.333 px` (CUDA) RMS (`0.097 / 0.017 px` at integer $z$; `0.000 px` on true global) | **SUPPORTED (Offline counterfactual)** | Exact-observation counterfactual on retained `global.txt`; parent will reproduce scripts on `cpu64` after admission. |
| Native patch observations `local[g]` exhibit y-shrinkage (`slope_y = 0.468` CPU, `0.3245` CUDA) and fail even under integer-time fitting (`0.358 / 0.288 px` RMS) | **SUPPORTED (Offline at STAR print precision)** | Derived from `out/affine.star` `local_shift` (`≤ 5e-6 px` precision). |
| Why native patch observations shrink across all 9 patches (window/weight objective `R_fm` vs tie/parabola/anchor arithmetic) | **UNRUN (Offline §6 test & Native W4 captures)** | Only patch `(2,1)` has full-precision trajectories/maps in `#275`; all-patch `R_fm` (§6) is unrun offline, and the 8 remaining CPU / 8 CUDA native patch captures are unrun. |
| Causal mechanism of the upstream `affine` global-stage trajectory error $\delta G[f]$ (`0.544 px` CPU / `0.375 px` CUDA RMS) | **UNRUN / DESCRIPTIVE ONLY** | "Earliest divergence" identifies stage order, not why global alignment erred under affine strain + B-factor weight + 5-frame iteration. |
| Native model-1 applied-image pixel witness isolating polynomial interpolation | **UNRUN / NOT TESTED** | `checker.json` has `application_consistency_status: "NOT_TESTED"`; evaluation at integer $z = g$ is source-verified, not isolated by a native applied-image witness. |
| M4 production identifiability / abstention on `flat` and `repeated` | **`not_assessed` (UNIMPLEMENTED in production)** | Existing `UNIDENTIFIABLE` status in `tools/check_motion_diagnostics.py:72` is a static fixture-recipe label check (`r["signal"] in ("flat", "repeated")`), **not** production abstention. |

---

## 6. Review of Controls, §6 Diagnostic Routing Criteria, and Governance Update

1. **`N=20` isotropic-weight `11.833 px` counterexample**: Properly retained in `REPORT.md` §§1, 5, 7 as a mandatory visible regression control. It proves that an estimator modification (`#279` isotropic weight) that passes 5-frame replays can fail catastrophically (`11.833 px`) at `N=20` via alias/peak-selection instability.
2. **Section 6 smallest next test (`R_fm`) criteria**:
   - The thresholds in `REPORT.md` §6 (`native - R_fm <= 0.15 px` RMS and `R_fm slope <= 0.6` vs `R_fm slope >= 0.9` and `native - R_fm >= 0.3 px` RMS) are **prospective diagnostic routing thresholds** used solely to decide whether to run the 8 native CPU patch captures. They are **not** acceptance gates and must never substitute for the unchanged `0.20 / 0.40 / 0.80 Å` (`0.226 / 0.452 / 0.904 px`) field accuracy contract.
   - **Technical precision required before running §6**: `REPORT.md` §6 describes `R_fm` as the continuous maximum of the production-weighted CCF "between an independently rendered window and the target window". In production (`src/motioncorr_runner.cpp:4753, 4828`), `alignPatch` correlates frame $g$'s cropped patch against the **leave-one-out multi-frame sum** $\sum_{j \ne g} F_{\text{patch}}[j]$ and subtracts frame 0's shift, not against the static `target` (`frame 0`) window alone. The §6 script should explicitly distinguish (or compute both) the static frame-0 reference oracle and the leave-one-out sum at `global.txt`.
3. **25 Oct Accuracy-Contract Approval (Scope & Governance)**:
   - Per Alex's explicit 25 Oct approval at top of Notion:
     - Current identifiable high-signal in-model 5-frame fixtures remain **required**;
     - `N=5/9/13/20` probes and the `11.833 px` counterexample remain **visible regression controls**;
     - Field accuracy limits remain **unchanged at `0.20 / 0.40 / 0.80 Å` (`0.226 / 0.452 / 0.904 px`) evaluated separately on runtime and STAR**;
     - Signal metrics remain **report-only with controls**; new noisy acceptance cohorts remain **held** until prospective criteria are fixed;
     - **Future branch research authority**: Separate-branch experiments on weight normalization (`#279`), peak/iteration/stopping (`#280`), the coupled fit time/zero-anchor convention, and patch window treatment are now permitted as isolated branch research, while `main`, adoption, C1 gates, and defaults remain **unchanged**, C2 / M6 / held-out evaluation remain **held**, and M4 production identifiability remains **`not_assessed`**.

---

## 7. Concrete Wording Corrections for `REPORT.md` and `DRAFT_HELD_ISSUE_time_convention.md`

1. **`DRAFT_HELD_ISSUE_time_convention.md` title & summary**:
   - *Replace*: `Title: HELD: local-motion fit places frame g at z = g + 0.5 but reconstruction applies the model at z = g`
   - *With*: `Title: HELD: default group-1 local-motion fit couples half-frame anchor z = g + 0.5 and linear frame-0 extrapolation (-interp[0] = +0.5*local[1]) in a constant-free cubic evaluated at integer z = g`
   - *Add explicit clarification*: State that (a) on linear-in-time trajectories (including the true spatially varying affine warp of the `affine` fixture), the $+0.5\,\text{local}[1]$ extrapolation offset and the $-0.5$ evaluation shift cancel identically (`local_error_px = 0.000 px`); (b) on the `affine` fixture, the `0.242 / 0.333 px` exact-observation error is 100% the spatially uniform (`global_mean_error_px`) residual of the upstream nonlinear global trajectory error $\delta G[f]$ (`0.544 / 0.375 px` RMS), which splits orthogonally into a `0.097 / 0.017 px` cubic model-capacity floor in $\mathcal{C}^\perp$ and a `0.222 / 0.332 px` convention distortion in $\mathcal{C}$; and (c) modifying `z_fit` without removing `-interp[0]` (or vice versa) breaks exactness even on linear motion.
2. **`REPORT.md` §1 item 4 & §4 ("floor" and "linear, residual 2e-14")**:
   - Refer to `0.242 px` (CPU) / `0.333 px` (CUDA) as the **exact-observation counterfactual error** (rather than an unconditional "floor"), noting that its $\mathcal{C}$-component (`0.222 / 0.332 px`) interferes non-orthogonally with observation error $E_{\text{obs}} \in \mathcal{C}$ ($\cos\theta = -0.7256$ on CUDA, where runtime RMS `0.323 px < 0.333 px`), whereas the true observation-independent floor in $\mathcal{C}^\perp$ is the cubic capacity residual (`0.097 / 0.017 px`).
   - State that `2e-14 px` is the exact algebraic distributivity of the linear least-squares operator $B A^+ \text{obs} = B A^+ \text{ideal} + B A^+(\text{obs} - \text{ideal})$ on the refitted STAR table, and report that refitting the native `local[g] = obs[g] - obs[0]` trajectories at counterfactual integer time $z = g$ still fails (`0.358 px` CPU / `0.288 px` CUDA RMS), confirming that the time/anchor convention and patch observation shrinkage are both independently gate-failing co-causes.
3. **`REPORT.md` §1 item 5 & §5 ("earliest divergence" and M4)**:
   - Clarify that "earliest divergence" refers to pipeline stage order (`global -> local observation -> fit -> STAR`), not sole causal attribution of the `affine` failure or a completed causal decomposition of why the global stage erred on `affine`.
   - Explicitly label M4 production identifiability as `not_assessed` (existing checker `UNIDENTIFIABLE` is a fixture-recipe label in `check_motion_diagnostics.py`, not production abstention).
