# Frozen Plan: Pairwise Reference Decomposition of Iteration-1 Frame-4 CCF Objective (`PLAN.md`)

**Author:** Research Sub-Agent (`Gemini4Argon`, read-only saved-data mathematical follow-up)  
**Owned Scratch:** `/tmp/mc-local-ccf-pairwise-ref-20261026`  
**Interpreter & Caps:** `/Users/alex.konstantinov/.local/bin/python3 -B` (NumPy `2.4.2`), `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`. No native jobs, no SSH, no source edits, no `.pyc` writes.

---

## 1. Objective & Scope

At bad patch `(62, 79)` (`patch-62-79`), iteration 1 frame 4 already selects the remote integer peak `(10, -8)` and coupled raw peak $\mathbf{x}_{\text{nat}} = (10.062688110916795, -7.802925722413559)$, whose trigonometric-interpolated objective value (`0.6859927335906875`) exceeds that at the explicit observed-frame0-gauge physical point $\mathbf{x}_{\text{phys}} = (-0.7617316542871614, 2.246762288086356)$ (`0.6471161996582063`) by $\Delta_{\text{native}} = +0.0388765339324812$.

This bounded saved-data experiment tests **one factor only** at fixed iteration 1, frame 4 on the two captured patches `(62, 79)` (bad) and `(62, 47)` (central comparison): how the aggregate leave-one-out cross-spectrum
$$S_{\text{agg}}[y, x] = \left(\sum_{j=0}^{3} F_j^{(1)}[y, x]\right) \big(F_4^{(1)}[y, x]\big)^* W[y, x], \qquad S_{\text{agg}}[0, 0] = 0$$
decomposes algebraically into its four individual pairwise reference components $j \in \{0, 1, 2, 3\}$:
$$S_j[y, x] = F_j^{(1)}[y, x]\,\big(F_4^{(1)}[y, x]\big)^*\,W[y, x], \qquad S_j[0, 0] = 0.$$

---

## 2. Inputs & Primary vs Auxiliary Hierarchy

- **Immutable Bundle:** `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1` (`INDEX.json` `sha256: 5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3`).
- **Truth Scoring File:** `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/capture-bundle-r1/truth-scoring-only/noisy_field.npy` (`sha256: 839c484f08ced435120a3f7c60267b95959bc5c06993f7c3015d61ffa3b95799`).
- **Per-Patch Saved Arrays Used (`evidence/runs/ON/capture/patch-62-{79,47}`):**
  - Primary aggregate real CCF map: `iter1-frame4-real-map.bin` ($I_{\text{native}} \in \mathbb{R}^{32\times 42}$).
  - Captured aggregate weighted spectrum: `iter1-frame4-weighted-api-consumed.bin` ($S_{\text{native}} \in \mathbb{C}^{32\times 22}$).
  - Captured entering windowed frame spectra: `iter1-frame{0,1,2,3,4}-window-fft.bin` ($F_j^{(1)} \in \mathbb{C}^{32\times 22}$).
  - Captured native B-factor weight: `weights.bin` ($W \in \mathbb{R}^{32\times 22}$).
  - Peak & shift metadata: `iter1-frame0-peak.json`, `iter1-frame4-peak.json`, `global-shifts.bin`.
- **Auxiliary Status of Regenerated Pairwise Maps:**
  - Because native single-precision `fftwf_execute_dft_c2r` was executed only on the aggregate spectrum $S_{\text{native}}$, the individual pairwise real maps $I_j^{\text{aux}} = \text{irfft2}(S_j) \cdot (32 \times 42)$ (`float64` NumPy reference) and their sum $I_{\text{sum}}^{\text{aux}} = \sum_{j=0}^3 I_j^{\text{aux}}$ are **auxiliary regenerated maps**.
  - We explicitly measure and report the discrepancy $\|S_{\text{native}} - \sum_{j=0}^3 S_j\|_\infty$, $\|I_{\text{native}} - I_{\text{sum}}^{\text{aux}}\|_\infty$, and the point-evaluation remainder between $\mathcal{I}_{\text{trig}}(I_{\text{native}})$ and $\sum_{j=0}^3 \mathcal{I}_{\text{trig}}(I_j^{\text{aux}})$.

---

## 3. Predeclared Fixed Evaluation Points & Algebraic Decomposition

For each patch $(62, c_y)$ with $c_y \in \{79, 47\}$ at Iteration 1, Frame 4 (using v3 symmetric cosine Nyquist splitting $b_{N/2}(x) = \cos(\pi x)$):

1. **Fixed Aggregate Evaluation Points:**
   - $\mathbf{x}_{\text{nat}}$: Aggregate native-selected raw point `pk4['raw_selected_xy_ccf']`.
   - $\mathbf{x}_{\text{int}}$: Aggregate native integer search maximum `pk4['integer_xy']`.
   - $\mathbf{x}_{\text{loc}}$: Aggregate same-basin local stationary candidate refined from $\mathbf{x}_{\text{nat}}$.
   - $\mathbf{x}_{\text{phys}}$: Explicit aggregate observed-frame0-gauge physical point $\big(\text{truth}[4, c_y, 62] - G[4]\big) + \text{pk0}[\text{'raw\_scaled\_xy\_movie'}]$.
2. **Pairwise Component Evaluations & Gap Closure ($j = 0, 1, 2, 3$):**
   - Evaluate $\mathcal{I}_j(\mathbf{x}_{\text{nat}})$ and $\mathcal{I}_j(\mathbf{x}_{\text{phys}})$, and the signed pairwise gap:
     $$\Delta_j = \mathcal{I}_j(\mathbf{x}_{\text{nat}}) - \mathcal{I}_j(\mathbf{x}_{\text{phys}})$$
     (plus the corresponding integer-point gap $\Delta_j^{\text{int}} = \mathcal{I}_j(\mathbf{x}_{\text{int}}) - \mathcal{I}_j(\mathbf{x}_{\text{phys}})$ and local-stationary gap $\Delta_j^{\text{loc}} = \mathcal{I}_j(\mathbf{x}_{\text{loc}}) - \mathcal{I}_j(\mathbf{x}_{\text{phys}})$).
   - Verify exact additive closure $\sum_{j=0}^3 \Delta_j = \Delta_{\text{sum}}^{\text{aux}}$ and report the numerical float32/FFTWf remainder $\Delta_{\text{native}} - \Delta_{\text{sum}}^{\text{aux}}$.
   - Report whether component gaps $\Delta_j$ add or cancel (retaining all signs and magnitudes in raw objective units; no normalization into causal or noise percentages).
3. **Predeclared Auxiliary Per-Component Peak Characterization (Descriptive Only):**
   - For each $j \in \{0, 1, 2, 3\}$, record on $I_j^{\text{aux}}$:
     - Native integer search maximum $(\text{posx}_j, \text{posy}_j, \text{maxval}_j)$ in $[-15, +15]^2$ and $3\times 3$ coupled/separable subpixel offset,
     - Unconstrained local stationary candidate seeded from that component's native peak, and
     - Local stationary candidate seeded from $\mathbf{x}_{\text{phys}}$.
   - *Strict Guardrail:* Truth is never used to select or tune any reference frame, and point-centre truth is not assumed to be the theoretical optimum of a noisy, finite-window, affine-sheared pairwise CCF. No global optimality certificate is claimed (`status = "UNPROVEN_GLOBAL"`).
