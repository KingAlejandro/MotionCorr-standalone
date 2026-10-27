# Independent Mathematical & Statistical Challenge Report: Native B2 (`PR #287`) on Retained Data

**Author:** Research Sub-Agent (`Gemini4Argon`, read-only mathematical/statistical challenge)  
**Scratch Directory:** `/tmp/mc-b2-challenge-gemini4argon-20261026`  
**Scope:** Strictly read-only analysis of retained data only. No source edits, no new native/movie/GPU jobs, no parameter/threshold/gate changes, and no exclusion of frozen $N=5$ cases.

---

## 0. Frozen Pre-Calculation Plan Receipt

Frozen prior to local calculations in `/tmp/mc-b2-challenge-gemini4argon-20261026/FROZEN_PLAN.md` (`sha256: f8ff63f47d88df865faf76a5233833358c031936c1584f8be471e1561f92de6a`):
- **H0:** Test whether the K267 `noisy` ($N=5$) regression (OFF runtime ROI RMS `2.342955 Å`, max `9.903899 Å` $\to$ ON-v3 runtime ROI RMS `3.587250 Å`, max `19.563705 Å`) is caused by a solver mismatch in `LocalB2::fit`, numerical ill-conditioning, STAR serialization, or acceptance-gate divergence (`largest_delta > 3 px` or `fit_rmsd >= 10 px`).
- **H1:** Derive the exact temporal operators under the singular observation mapping $T_r: \mathbb{R}^{N-1} \to \mathbb{R}^N$ ($y_{p,0} = \tfrac{1}{2}L_{p,1}$, $y_{p,g} = L_{p,g} + \tfrac{1}{2}L_{p,1}$ for $g \ge 1$, so $y_{p,1} \equiv 3 y_{p,0}$), challenge raw-observation row-$L_2$ gain metrics that ignore $T_r$, and characterize finite-horizon ($N=5$) endpoint behavior versus $N=40$.
- **H2:** Decompose the fixed-observation error on `noisy` and `affine` into the unabsorbed global-trajectory term and the propagated patch-discrepancy term, keeping all standalone norms, counterfactual removals, and inner-product cross terms explicit as conditional algebraic diagnostics rather than causal shares.

---

## 1. Pins, Hashes, Upstream Identity, Solver & Acceptance-Gate Audit (H0 Falsified)

- **Code & Binary Receipts:**
  - PR #287 (`native-b2-cpu-prototype`), production commit `326f03a073aec0d26c9cd585ce4f701d1c808245` on base `4fa272f6`; challenge docs commit `d1ddd7fb` (preregistered plan `7c929f65`).
  - Native binary `sha256: 531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb` (identical in `noisy/OFF` and `noisy/ON-v3`, exit `0`).
  - Retained local challenge bundle `/tmp/motioncorr-b2-retained-challenge-20261026/INDEX.json` (`sha256: 2b18f46961829cbc16a339d7ec855a6d7cce2a8cbcc4a538cadf75d565a7cfbc`).
  - Fixtures: `noisy_field.npy` == `affine_field.npy` (`sha256: 839c484f08ced435120a3f7c60267b95959bc5c06993f7c3015d61ffa3b95799`); `noisy.mrcs` (`sha256: 5000fbfc...`); `noisy/OFF/output/noisy.star` (`sha256: 9dc77e8a...`); `noisy/ON-v3/output/noisy.star` (`sha256: dd929a36...`).
  - Retained harmful `vel1_N20` (`iso`) native trajectory RMS is `11.858575180641232 px` (runtime field RMS `10.494839 Å`, max `14.859852 Å`, `FAIL`; distinct from the offline `11.833 px` label).
- **Upstream & Solver Identity:**
  - In K267 `noisy`, OFF and ON-v3 share the **exact same** non-converged 5-iteration global trajectory, the **same** 9 converged patches, and **byte-identical** 45-row `data_local_shift` tables satisfying $|y_{p,1} - 3 y_{p,0}| \le 1.0\times 10^{-5}\text{ px}$.
  - Because all 9 patches use the same time grid $g \in \{0,1,2,3,4\}$, the demeaned B2 design matrix is a Kronecker product $A_{\text{proj}} = S \otimes (M Z_{\text{B2}}) \in \mathbb{R}^{45\times 18}$. Our independent Kronecker solver $C_{\text{B2}} = S^+ Y ((M Z_{\text{B2}})^+)^\top$ matches the 27-column augmented SVD $[S \otimes Z_{\text{B2}}, I_9 \otimes 1_5]$ to **$5.52\times 10^{-13}\text{ px}$** in coefficient space, and both agree with native `ON-v3/runtime.json` to **$3.56\times 10^{-5}\text{ px}$** in coefficients and **$1.1367\times 10^{-5}\text{ px}$** max vector field difference on the full border (within the $4.724\times 10^{-5}\text{ px}$ `%12.6f` STAR rounding bound).
- **Conditioning vs Statistical Sensitivity:**
  - Full rank **27/27**; column-scaled condition numbers are well-behaved ($\kappa_{\text{scaled}}(S) = 4.410$, $\kappa_{\text{scaled}}(M Z_{\text{B2}}) = 45.109$ vs $\kappa_{\text{scaled}}(Z_{\text{OFF}}) = 55.282$; 27-column $\kappa_{\text{scaled}}(A_{\text{aug}}) = 294.29$, raw $4290.50$). Numerical conditioning is not the cause of the regression.
- **Acceptance-Gate Audit (`local_enabled = true` in both arms):**
  - Corner neighbour gradient check (`MAXIMUM_TOLERANCE = 3.0 px`): `noisy` OFF `largest_delta = 0.740015 px` $\to$ ON-v3 `1.776145 px` (both $< 3.0\text{ px}$). On `affine`: OFF `0.040345 px` $\to$ ON-v3 `0.035643 px`.
  - Fit residual check (`fit_rmsd_threshold = 10.0 px`): `noisy` OFF logs `(2.219433, 2.120719) px`; ON-v3 logs nuisance-adjusted `(2.157742, 1.633121) px` (unadjusted `(2.237709, 2.162682) px`). Both are well below $10\text{ px}$, so the changed residual definition did not alter model acceptance on these cases, although subtracting 9 per-patch intercepts per axis reduces residual degrees of freedom from $27$ to $18$ against an unchanged $10\text{ px}$ threshold.

---

## 2. Challenge to Raw-Observation Row-$L_2$ Gain & Exact $N=5$ Endpoint Theorem (H1)

### A. Challenge to Raw-Observation Row-$L_2$ Operator Gain (`3.1559` vs `1.7696`)
Evaluating the row-$L_2$ norm of $H_{\text{obs}}$ directly on the 45 post-recentering STAR observations $y \in \mathbb{R}^{45}$ yields `3.155887` (B2) vs `1.769586` (OFF) on the full border.
- While row-$L_1$ on $H_{\text{obs}}$ (`11.3196` ON vs `6.9296` OFF) is the appropriate worst-case sensitivity bound for independent `%12.6f` STAR rounding errors, **row-$L_2$ on $H_{\text{obs}}$ is not a valid physical alignment-noise gain** because it assumes $\text{Cov}(y) = \sigma^2 I_{45}$, violating the deterministic constraint $y_{p,1} \equiv 3 y_{p,0}$ ($y_p = T_r L_p$).
- If pre-pin frame errors are written as $\varepsilon = (\varepsilon_0, \dots, \varepsilon_{N-1})^\top$ with pre-pin increments $L_g = \varepsilon_g - \varepsilon_0$ ($L = E_{\text{pin}}\varepsilon$), then $y = T_r L = T_r E_{\text{pin}}\varepsilon = \varepsilon + (\tfrac{1}{2}\varepsilon_1 - \tfrac{3}{2}\varepsilon_0)1_N$.
- Because B2 projects off $1_N$ ($H_{\text{B2,obs}}1_N = 0$), it satisfies the exact operator identity:
  $$G_{\text{B2},\varepsilon} \equiv H_{\text{B2,obs}} T_r E_{\text{pin}} \equiv H_{\text{B2,obs}} \quad (\forall N \ge 4).$$
  Inherited OFF does **not** annihilate $1_N$ ($H_{\text{OFF,obs}}1_N \ne 0$). Omitting $T_r$ or $T_r E_{\text{pin}}$ therefore leaves B2's row-$L_2$ norm unchanged while artificially hiding OFF's constructive amplification of $\varepsilon_0$ and $L_1$. Under the two idealized equal-variance i.i.d. reference models (assuming spatial independence across patches), B2 actually has **lower** operator row-$L_2$ norms than OFF even at $N=5$:

| Idealized Noise Covariance Model ($3\times 3$ K267 geometry, $N=5$) | OFF (Inherited) | ON (B2) | Ratio ON / OFF |
|---|---:|---:|---:|
| **Raw obs $y \sim \text{i.i.d.}(0, \sigma^2 I_{45})$ [Ignores $T_r$, violates $y_1=3y_0$]** — Border max / ROI RMS | `1.769586` / `0.487912` | `3.155887` / `0.864815` | `1.783x` / `1.772x` |
| **Pre-pin increments $L \sim \text{i.i.d.}(0, \sigma^2 I_{36})$ via $K = H_{\text{obs}} T_r$** — Border max / ROI max / ROI RMS | `2.533021` / `1.479620` / `0.658133` | `2.231549` / `1.303520` / `0.574363` | **`0.881x` / `0.881x` / `0.873x`** |
| **Pre-pin frame errors $\varepsilon \sim \text{i.i.d.}(0, \sigma^2 I_{45})$ via $G_\varepsilon = H_{\text{obs}} T_r E_{\text{pin}}$** — Border max / ROI max / ROI RMS | `4.201486` / `2.454225` / `1.140138` | `3.155887` / `1.843456` / `0.864815` | **`0.751x` / `0.751x` / `0.759x`** |

*(Caveat: Lower expected variance holds under these specific i.i.d. equal-variance models for $L$ or $\varepsilon$ with spatial independence; actual patch CCF errors can be heteroscedastic, non-Gaussian, and correlated across frames or patches.)*

### B. Exact $N=5$ Endpoint Unsmoothing Theorem
The $5\times 4$ temporal operators $K_{\text{B2}} = H_{\text{B2,obs}} T_r$ and $K_{\text{OFF}} = H_{\text{OFF,obs}} T_r$ mapping pre-pin shifts $(L_1, L_2, L_3, L_4)^\top$ to published trajectories $\hat{h}(f)$ at $f \in \{0,1,2,3,4\}$ are:
$$K_{\text{B2}} = \begin{pmatrix} 0 & 0 & 0 & 0 \\ \frac{5}{7} & \frac{3}{7} & -\frac{2}{7} & \frac{1}{14} \\ \frac{2}{7} & \frac{4}{7} & \frac{2}{7} & -\frac{1}{14} \\ -\frac{2}{7} & \frac{3}{7} & \frac{5}{7} & \frac{1}{14} \\ \mathbf{0} & \mathbf{0} & \mathbf{0} & \mathbf{1} \end{pmatrix}, \qquad K_{\text{OFF}} \approx \begin{pmatrix} 0 & 0 & 0 & 0 \\ 1.1002 & 0.1497 & -0.2254 & 0.0692 \\ 1.0430 & 0.3789 & 0.1582 & -0.0688 \\ 0.5435 & 0.4733 & 0.5897 & -0.0648 \\ 0.3170 & 0.2187 & 0.5081 & \mathbf{0.4303} \end{pmatrix}.$$

- **Proof of Row 4 of $K_{\text{B2}}$ (`[0, 0, 0, 1]`):**
  At $N=5$, $\text{span}\{1_5, g, g^2, g^3\} \subset \mathbb{R}^5$ has a 1D orthogonal complement spanned by the 4th-difference vector $d_4 = (1, -4, 6, -4, 1)^\top$. By even symmetry about $g=2$, $d_4$ has **equal endpoint entries** ($d_{4,0} = d_{4,4} = 1$). Therefore, for any observation vector $y \in \mathbb{R}^5$, the OLS residuals at $g=0$ and $g=4$ are equal ($r_0 = r_4 = \frac{d_4^\top y}{70}$). Since $\hat{y}_g = a + \hat{h}_{\text{B2}}(g)$ and $\hat{h}_{\text{B2}}(0) = 0$, subtracting $g=0$ from $g=4$ cancels both the nuisance intercept $a$ and the equal endpoint residuals $r_4 - r_0 = 0$:
  $$\boxed{\hat{h}_{\text{B2}}(4) = (y_4 - r_4) - (y_0 - r_0) \equiv y_4 - y_0 \equiv L_4.}$$
- **Mechanistic Tradeoff ($N=5$ vs $N=40$):**
  - At $N=5$, B2 performs **zero temporal smoothing at the final frame $f=4$**: any gross error in $L_4$ (frame 5) is passed with **unit gain ($1.0000$)** into $f=4$, whereas OFF damps $L_4$ by **$0.430297$** (so B2 has **$2.324\times$** higher gain on $L_4$ at $f=4$ and **$2.260\times$** higher column RMS on $L_4$, plus **$1.508\times$** higher gain on $L_2$ at $f=2$: $\frac{4}{7} = 0.5714$ vs $0.3789$).
  - By $N=40$ (same basis and geometry), this finite-horizon endpoint identity disappears: B2's final-frame impulse gain $|K[39, 38]|$ drops to **`0.4019`** vs OFF's **`0.5995`** (`0.670x` lower), while its i.i.d. $\varepsilon$ RMS factor drops to `0.6193` vs OFF's `1.5388` (`0.4024x`).

---

## 3. Conditional Fixed-Observation Decomposition on `noisy` and `affine` (H2)

In both `affine` and `noisy`, the ground-truth field is exact bilinear-in-space, linear-in-time motion ($T^{\text{true}}(u,v,f) = S(u,v) c_1 f$ to within $1.64\times 10^{-14}\text{ px}$). For fixed observed global shifts $G = g^{\text{true}} + \Delta G$ and fixed observed pre-pin patch shifts $L^{\text{obs}} = L^{\text{ideal}} + \eta$ (where $L^{\text{ideal}}_{p,g} = T^{\text{true}}(x_p,y_p,g) - G_g$), linearity and $S^+ 1_9 = e_0$ give the exact fixed-observation sum:
$$\Delta F_E = \underbrace{(I_5 - K_E)\Delta G}_{a_E \text{ (unabsorbed global term, spatially constant)}} + \underbrace{\text{Eval}(S^+ \eta K_E^\top)}_{b_E \text{ (propagated patch-discrepancy term)}}.$$

*(Qualification: All decompositions below hold conditionally on the **fixed** observed $G$ and $\eta$ from the retained runs. Holding $\eta$ fixed does not simulate re-running patch alignment under a different global trajectory, and cannot rule out that upstream global non-convergence in `noisy` indirectly induced worse patch tracking errors $\eta$.)*

| Fixed-Observation Diagnostic Quantity (ROI, $\text{\AA}$ / $\text{\AA}^2$) | `noisy` OFF | `noisy` ON-v3 (B2) | `affine` OFF | `affine` ON-v3 (B2) |
|---|---:|---:|---:|---:|
| **Total Native Runtime Error** (`a_E + b_E`) RMS / p95 / max ($\text{\AA}$) | `2.342955` / `4.376571` / `9.903899` | `3.587250` / `7.098330` / `19.563705` | `0.402437` / `0.742489` / `0.911068` | `0.317174` / `0.656753` / `0.696313` |
| **Total Mean-Square Error** $\|a_E + b_E\|_{\text{MS}}^2$ ($\text{\AA}^2$) | `5.489440` | `12.868362` | `0.161955` | `0.100599` |
| **1. Unabsorbed Global Term** $a_E = (I_5 - K_E)\Delta G$ RMS / max ($\text{\AA}$) | `0.509010` / `0.963336` | `0.464770` / `0.600016` | `0.214314` / `0.303035` | `0.087828` / `0.113385` |
| **1. Standalone MS** $\|a_E\|_{\text{MS}}^2$ ($\text{\AA}^2$) | `0.259091` | `0.216011` | `0.045930` | `0.007714` |
| **2. Patch-Discrepancy Term** $b_E = \text{Eval}(S^+\eta K_E^\top)$ RMS / max ($\text{\AA}$) | `2.296835` / `10.153156` | `3.568837` / `19.563705` | `0.338284` / `0.701794` | `0.296557` / `0.615954` |
| **2. Standalone MS** $\|b_E\|_{\text{MS}}^2$ ($\text{\AA}^2$) | `5.275450` | `12.736597` | `0.114436` | `0.087946` |
| **Cross Term** $2\langle a_E, b_E\rangle_{\text{MS}}$ ($\text{\AA}^2$) | `-0.045101` | `-0.084246` | `+0.001589` | `+0.004939` |

- **Fixed-Observation Role of the Global Term $a_E$:** On fixed observations, $I_5 - K_{\text{B2}}$ annihilates the cubic subspace of $\Delta G$ and leaves only the 4th-difference mode proportional to $(0, -2, 3, -2, 0)^\top$, which vanishes identically at $f=4$ and has lower standalone RMS (`0.464770 Å` ON vs `0.509010 Å` OFF) and max (`0.600016 Å` ON vs `0.963336 Å` OFF). For fixed $\eta$, `local_error_px` (which subtracts the spatial mean at each frame) is algebraically independent of $a_E$ and increases from `2.336360 px` (`11.136685 px` max) in OFF to `3.538221 px` (`19.243104 px` max) in ON-v3.
- **Conditional Algebraic Split of $\eta$ into the 3 Gross Patch-Tracking Errors ($u_3$) vs Remaining Terms ($u_{\text{rest}}$):**
  In `noisy`, three of the 36 pre-pin patch-frame entries have gross tracking discrepancies (`> 14 px` vector error; we call these gross patch-tracking errors as no internal CCF maps were saved to classify objective aliasing vs boundary/iteration effects):
  1. Patch $(2,3)$ `(104, 47)`, **frame 5 ($g=4, L_4$)**: $\eta = (-17.680, +14.721)\text{ px}$ ($\|\eta\| = 23.006\text{ px}$),
  2. Patch $(3,2)$ `(62, 79)`, **frame 5 ($g=4, L_4$)**: $\eta = (+10.567, -10.115)\text{ px}$ ($\|\eta\| = 14.628\text{ px}$),
  3. Patch $(2,2)$ `(62, 47)`, **frame 3 ($g=2, L_2$)**: $\eta = (+12.877, -8.768)\text{ px}$ ($\|\eta\| = 15.578\text{ px}$).
  Writing the total ROI field error as $u_{\text{tot}} = u_3 + u_{\text{rest}}$ (where $u_3$ is the field from those 3 entries alone and $u_{\text{rest}}$ is the counterfactual field with those 3 entries zeroed, retaining $\Delta G$ and the other 33 entries of $\eta$):
  - **ON-v3 (B2):**
    - $\|u_3\|_{\text{RMS}} = 3.204051\,\text{\AA}$ (standalone RMS ratio $\|u_3\|_{\text{RMS}} / \|u_{\text{tot}}\|_{\text{RMS}} = 0.893178$; standalone MS $\|u_3\|_{\text{MS}}^2 = 10.265944\,\text{\AA}^2$, or **$0.797766$ ($79.8\%$) of total MS**, not $89\%$; standalone max `18.327374 Å` vs total max `19.563705 Å`, ratio $0.9368$, which is a norm ratio and not an additive share).
    - $\|u_{\text{rest}}\|_{\text{RMS}} = 1.069131\,\text{\AA}$, standalone MS $\|u_{\text{rest}}\|_{\text{MS}}^2 = 1.143041\,\text{\AA}^2$ ($8.88\%$ of total MS; counterfactual zeroing of the 3 entries reduces total MS by $91.12\%$, with max `4.450749 Å`).
    - Exact cross term: $2\langle u_3, u_{\text{rest}}\rangle_{\text{MS}} = +1.459378\,\text{\AA}^2$ ($+11.34\%$ of total MS).
  - **OFF (Inherited):**
    - $\|u_3\|_{\text{RMS}} = 1.751936\,\text{\AA}$ (standalone RMS ratio $0.747746$; standalone MS $\|u_3\|_{\text{MS}}^2 = 3.069279\,\text{\AA}^2$, or $55.91\%$ of total MS; standalone max `7.831586 Å`).
    - $\|u_{\text{rest}}\|_{\text{RMS}} = 1.189940\,\text{\AA}$, standalone MS $\|u_{\text{rest}}\|_{\text{MS}}^2 = 1.415957\,\text{\AA}^2$ ($25.79\%$ of total MS; counterfactual zeroing reduces total MS by $74.21\%$, with max `5.507935 Å`).
    - Exact cross term: $2\langle u_3, u_{\text{rest}}\rangle_{\text{MS}} = +1.004203\,\text{\AA}^2$ ($+18.29\%$ of total MS).
  - Because two of the three gross patch-tracking errors lie at $g=4$ ($L_4$) where $K_{\text{B2}}[4,3] \equiv 1.0000$ (vs $0.430297$ in OFF), B2 passes them without temporal damping into frame $f=4$, producing the ROI max (`19.563705 Å` at $f=4, y=41, x=115$) and full-border max (`30.106952 px` at $f=4, y=40, x=127$).

---

## 4. What Remains Unidentified & Next Discriminating Step

1. **What remains unidentified in retained data:**
   - Whether upstream global non-convergence in `noisy` (`5` iterations, final step `1.40998 px`) indirectly degraded the patch CCF landscape and helped trigger the three gross patch-tracking errors $\eta_{p,g}$.
   - Whether late-frame ($g=4$) gross patch errors at $N=5, \text{noise}=4$ are systematic across noise draws or specific to seed `238262` (testing new seeds would require new native baseline runs and is not available offline from retained data).
2. **Recommended smallest falsifiable next step (using existing upstream arms on the retained 8 K267 cases):**
   - If the parent characterizes the existing `coupled+DC` upstream alignment arm with and without `--experimental_local_b2` on the retained 8 K267 cases under a frozen $2\times 2$ factorial (`{upstream: base vs coupled+DC} x {local fit: OFF vs B2}`), pre-declare two falsifiable checks before execution:
     1. **Upstream-mediation check on `noisy`:** Does changing the upstream alignment arm (`coupled+DC`) alter global convergence and eliminate or shift the gross $g=4$ patch-tracking discrepancies $\eta_{p,4}$, and does B2 still regress relative to OFF on `coupled+DC` when any gross $g=4$ discrepancy is present (as predicted by $K_{\text{B2}}[4,3] \equiv 1$)?
     2. **Fixed-observation cross-feed control (zero new native jobs once `coupled+DC` OFF is run):** Because B2 only touches the downstream polynomial fit after patch alignment, feeding the `coupled+DC` OFF patch observations into the exact offline operators $K_{\text{OFF}}$ and $K_{\text{B2}}$ deterministically predicts the `coupled+DC + B2` field to `%12.6f` precision and separates upstream global/patch tracking changes from downstream B2 endpoint sensitivity.
   - Do **not** exclude or down-weight the frozen $N=5$ `noisy` case to pass; `noisy` ON-v3 remains a retained regression and candidate promotion blocker.

---

## 5. Retained Scratch Artifacts & SHA-256 Index (`/tmp/mc-b2-challenge-gemini4argon-20261026`)

- `FROZEN_PLAN.md`: `f8ff63f47d88df865faf76a5233833358c031936c1584f8be471e1561f92de6a`
- `run_challenge_analysis.py`: `723224b70f4ee58c64621ba50b439b2229298f7314271e33df28db7b58d02d42`
- `challenge_gains.py`: `050d944a4c5ac5fd0bea28a8f8c9c8d5c657bb9fb9f6b8ba0c23a6f6fc576a68`
- `affine_check.py`: `fc26f2a36258d748ec0e97b56104417ab6e09d464e09a5b426553fb73f114fcc`
- `challenge_results.json`: `0d37170831897cd2eb81d7574cd3ab9d0e9d6bd0dd288f8113dc6405dacd69cf`
- `operator_gain_challenge.json`: `c16efcb89059c5ad5942b727229d05657cb0eee5180138442d0d964d3b726a09`
- `affine_and_spatial_check.json`: `af71e467964e6a79346b85b58da94c81af514e45d400e4b337ae431f5418d632`
