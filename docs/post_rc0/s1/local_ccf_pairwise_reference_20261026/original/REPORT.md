# Saved-Data Pairwise Reference Decomposition Report: Iteration-1 Frame-4 CCF Objective

**Author:** Research Sub-Agent (`Gemini4Argon`, read-only mathematical/statistical challenge)  
**Owned Scratch:** `/tmp/mc-local-ccf-pairwise-ref-20261026`  
**Interpreter & Caps:** `/Users/alex.konstantinov/.local/bin/python3 -B` (NumPy `2.4.2`), `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1` (`elapsed_seconds = 0.0459 s`). No native jobs, no SSH, no source edits, no `.pyc` writes.

---

## 1. Provenance, Inputs & Saved-vs-Regenerated Closure

- **Frozen Plan:** `/tmp/mc-local-ccf-pairwise-ref-20261026/PLAN.md` (`sha256: 038ec5a2bc907686b19ec37be1f19ade56715dbcdd260d565dcb8efc93462416`), frozen prior to computation.
- **Immutable Capture Bundle:** `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1` (`INDEX.json` `sha256: 5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3`, capture source `927a6890c8864f81ad58e44eac7281b080714af4`).
- **Truth Fixture:** `capture-bundle-r1/truth-scoring-only/noisy_field.npy` (`sha256: 839c484f08ced435120a3f7c60267b95959bc5c06993f7c3015d61ffa3b95799`).
- **Hermitian & Closure Checks at Iteration 1, Frame 4:**
  - Because Iteration 1 uses the initial unshifted `r2c` patch FFTs $F_j^{(1)}$, all four pairwise cross-spectra $S_j = F_j^{(1)} (F_4^{(1)})^* W$ ($S_j[0,0] = 0$) are strictly R2C Hermitian-valid (`max_kx0_conj_err = 0.0`, `max_kx21_conj_err = 0.0`, `max_corner_imag = 0.0` for $j=0..3$ on both patches).
  - Spectral sum discrepancy $\max |S_{\text{native}} - \sum_{j=0}^3 S_j|$: `1.536e-8` (`float32` sum) / `1.433e-8` (`float64` sum) on `(62, 79)`, and `3.072e-8` / `2.510e-8` on `(62, 47)`.
  - Auxiliary regenerated real-map sum $I_{\text{sum}}^{\text{aux}} = \sum_{j=0}^3 \text{irfft2}(S_j)\cdot 1344$ vs primary saved `iter1-frame4-real-map.bin` ($I_{\text{native}}$): max abs diff `1.499e-7` (`3.654e-8` RMS) on `(62, 79)`, and `1.903e-7` (`4.724e-8` RMS) on `(62, 47)`.

---

## 2. Pairwise Reference Decomposition at Fixed Aggregate Points

Using the v3 symmetric cosine Nyquist trigonometric interpolant (`global_certification_status = "UNPROVEN_GLOBAL"`), we evaluate each pairwise component $j \in \{0, 1, 2, 3\}$ at the fixed aggregate native-selected raw point $\mathbf{x}_{\text{nat}}$, the integer peak $\mathbf{x}_{\text{int}}$, the same-basin local stationary candidate $\mathbf{x}_{\text{loc}}$, and the explicit aggregate observed-frame0-gauge physical point $\mathbf{x}_{\text{phys}} = (\text{truth}[4, c_y, 62] - G[4]) + r^{(1)}[0]$:

### A. Bad Patch `(62, 79)` — Iteration 1, Frame 4
- Fixed points: $\mathbf{x}_{\text{nat}} = (10.062688110916795, -7.802925722413559)$, $\mathbf{x}_{\text{int}} = (10, -8)$, $\mathbf{x}_{\text{loc}} = (10.065022329168, -7.791873097372495)$, $\mathbf{x}_{\text{phys}} = (-0.7617316542871614, 2.246762288086356)$.

| Term / Reference $j$ | $\mathcal{I}(\mathbf{x}_{\text{nat}})$ | $\mathcal{I}(\mathbf{x}_{\text{phys}})$ | Gap $\Delta_j = \mathcal{I}(\mathbf{x}_{\text{nat}}) - \mathcal{I}(\mathbf{x}_{\text{phys}})$ | Integer Gap $\mathcal{I}(\mathbf{x}_{\text{int}}) - \mathcal{I}(\mathbf{x}_{\text{phys}})$ | Component's Own Native-Rule Peak `[ix, iy]` $\to$ `(sel_x, sel_y)` (Descriptive) |
|---|---:|---:|---:|---:|---|
| **$j = 0$ (Frame 0)** | `0.2041299586` | `0.1658738313` | **`+0.0382561273`** | `+0.0399249672` | `[11, -10]` $\to$ `(10.450035, -9.788067)`, `max = 0.210497` |
| **$j = 1$ (Frame 1)** | `0.1661008428` | `0.1507651348` | **`+0.0153357080`** | `+0.0135410854` | `[11, -7]` $\to$ `(10.976841, -6.762658)`, `max = 0.172086` |
| **$j = 2$ (Frame 2)** | `0.1483954487` | `0.1482364370` | **`+0.0001590117`** | `-0.0006393156` | `[0, 0]` $\to$ `(-0.179738, +0.260165)`, `max = 0.154322` |
| **$j = 3$ (Frame 3)** | `0.1673665206` | `0.1822407776` | **`-0.0148742570`** | `-0.0145353414` | `[0, 1]` $\to$ `(-0.218652, +0.660168)`, `max = 0.189439` |
| **Sum $\sum_{j=0}^3$ (Aux)** | `0.6859927707` | `0.6471161807` | **`+0.0388765900`** | `+0.0382913956` | Algebraic closure err: `-2.7756e-17` |
| **Primary Native Map** | `0.6859927336` | `0.6471161997` | **`+0.0388765339`** | `+0.0382913197` | Numeric remainder (native $-$ sum): `-5.6049e-8` |

- **Findings on `(62, 79)` (Strong Cancellation & Early-Frame Dominance, Not Uniform Preference):**
  1. The aggregate gap (`+0.0388765339` primary native; `+0.0388765900` auxiliary sum) does **not** come uniformly from all four reference components.
  2. **Reference $j=0$ (the temporally farthest frame from frame 4, $|\Delta f| = 4$) is the dominant positive contributor** ($\Delta_0 = +0.0382561273$), reinforced by **reference $j=1$** ($|\Delta f| = 3$, $\Delta_1 = +0.0153357080$), while **reference $j=2$** is nearly neutral ($\Delta_2 = +0.0001590117$ at $\mathbf{x}_{\text{nat}}$, and negative $\Delta_2^{\text{int}} = -0.0006393156$ at integer `(10, -8)`).
  3. **Temporally adjacent reference $j=3$ ($|\Delta f| = 1$) strongly opposes the remote peak** with a negative gap $\Delta_3 = -0.0148742570$ that almost completely cancels $\Delta_1 + \Delta_2 = +0.0154947197$ (leaving $\Delta_1 + \Delta_2 + \Delta_3 = +0.0006204627$, so $\Delta_0$ alone equals the net aggregate gap up to $+0.000620$).
  4. In the 3-of-4 leave-one-reference-out sub-aggregates (descriptive algebraic combinations only): dropping $j=0$ reduces the fixed-point gap to $+0.0006204627$ (and $-0.0016335716$ at `(10, -8)`) and moves the sub-aggregate integer peak from `(10, -8)` to `(0, 1)` (`(0.184494, 1.010470)`); dropping $j=1$ moves the sub-aggregate integer peak to `(1, 0)` (`(0.676229, 0.045561)`).

### B. Central Comparison Patch `(62, 47)` — Iteration 1, Frame 4
- Fixed points: $\mathbf{x}_{\text{nat}} = (-1.9689649962290974, 0.8359908488943173)$, $\mathbf{x}_{\text{int}} = (-2, 1)$, $\mathbf{x}_{\text{loc}} = (-1.9628889295318537, 0.8323420300801879)$, $\mathbf{x}_{\text{phys}} = (-1.2864028728259632, 1.4351499952431873)$ (both $\mathbf{x}_{\text{nat}}$ and $\mathbf{x}_{\text{phys}}$ lie in the same near-origin basin, $0.9082\text{ px}$ apart).

| Term / Reference $j$ | $\mathcal{I}(\mathbf{x}_{\text{nat}})$ | $\mathcal{I}(\mathbf{x}_{\text{phys}})$ | Gap $\Delta_j = \mathcal{I}(\mathbf{x}_{\text{nat}}) - \mathcal{I}(\mathbf{x}_{\text{phys}})$ | Integer Gap $\mathcal{I}(\mathbf{x}_{\text{int}}) - \mathcal{I}(\mathbf{x}_{\text{phys}})$ | Component's Own Native-Rule Peak `[ix, iy]` $\to$ `(sel_x, sel_y)` (Descriptive) |
|---|---:|---:|---:|---:|---|
| **$j = 0$ (Frame 0)** | `0.2326440935` | `0.2302191166` | `+0.0024249769` | `+0.0026154556` | `[-2, 1]` $\to$ `(-1.824347, +0.989428)`, `max = 0.232835` |
| **$j = 1$ (Frame 1)** | `0.2117358525` | `0.2078863569` | `+0.0038494956` | `+0.0040276385` | `[-2, 1]` $\to$ `(-2.286275, +1.154470)`, `max = 0.211914` |
| **$j = 2$ (Frame 2)** | `0.2132549854` | `0.2001268815` | `+0.0131281039` | `+0.0114972598` | `[-1, -1]` $\to$ `(-0.864119, -0.806069)`, `max = 0.219458` |
| **$j = 3$ (Frame 3)** | `0.2846954649` | `0.2840385616` | `+0.0006569033` | `+0.0014682840` | `[-2, 1]` $\to$ `(-2.038700, +1.371556)`, `max = 0.285507` |
| **Sum $\sum_{j=0}^3$ (Aux)** | `0.9423303963` | `0.9222709167` | **`+0.0200594796`** | `+0.0196086379` | Algebraic closure err: `-2.7756e-17` |
| **Primary Native Map** | `0.9423304085` | `0.9222709498` | **`+0.0200594586`** | `+0.0196086207` | Numeric remainder (native $-$ sum): `-2.0993e-8` |

---

## 3. Limitations & Next Smallest Discriminating Test

- **Limitations:** This is a fixed-observation algebraic decomposition of the saved Iteration-1 Frame-4 leave-one-out reference sum on two patches of a single noisy movie (`seed = 238262`). Component gaps are conditional algebraic differences in raw objective units, not causal shares or noise variance fractions. Point-centre truth $\mathbf{x}_{\text{phys}}$ is not the theoretical maximizer of a noisy, finite-window ($42\times 32$), affine-sheared pairwise CCF, and individual pairwise peaks are descriptive only (not a proposed estimator or truth-selected reference).
- **Why Distant Pairs ($j=0, 1$) Differ from Adjacent Pairs ($j=2, 3$) on `(62, 79)` Frame 4, and ONE Smallest Discriminating Test:**
  Because global alignment on `noisy` failed to converge and left a large residual inter-frame step between early frames ($f=0, 1$) and late frames ($f=3, 4$) (`G[4] = (-3.185, +1.498)` vs `G[0] = (0,0)` and `G[1] = (-0.905, +0.898)`), frames $0$ and $1$ enter `alignPatch` at iteration 1 with larger uncompensated boundary wrap/window mismatch and relative displacement against frame 4 than frames $2$ and $3$ do.
  - **Smallest next saved-data test (if needed, zero new native jobs):** Using the already-saved `initial-frame{0..4}-samples.bin` in `patch-62-79` and the retainednoiseless twin `affine` patch `(62, 79)` spectra (or synthetic noiseless patch signal under the same `G`), evaluate the same four pairwise gaps $\Delta_0..\Delta_3$ without pixel noise to discriminate whether the large positive $\Delta_0 = +0.038256$ on `F0 * conj(F4)` is driven by the realization of additive pixel noise (`noise = 4`) in frames $0$ and $4$ or by deterministic $42\times 32$ boundary-clipping/shear mismatch across the $4$-frame separation.

---

## 4. Artifact & SHA-256 Index (`/tmp/mc-local-ccf-pairwise-ref-20261026/SHA256SUMS`)
- `PLAN.md`: `038ec5a2bc907686b19ec37be1f19ade56715dbcdd260d565dcb8efc93462416`
- `pairwise_ref_analysis.py`: `50aabc84747b057735ad44a43100e25d9743243488d8fe67ca7a5b92fc49d284`
- `RESULT.json`: `55ceb9d1ee84ede2ea998b13a7bcf2e6d44f0e7873a01e5f353d4f1b30b58e38`
