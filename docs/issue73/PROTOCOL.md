# Prospective protocol — independent-collection scientific validation of native CUDA (#73)

Issue: [#73](https://github.com/KingAlejandro/MotionCorr-standalone/issues/73).
Related: #61 / PR #65 (single-collection study), #60 / PR #64 (diagnostic calibration), ADR #66.

**Status: PREREGISTRATION.** Every endpoint, margin, analysis set and decision rule below is fixed
by the commit that introduces this file. No corrected micrograph, FSC, resolution or endpoint value
from *any* arm on the target collection had been computed when it was committed. Only deposited
third-party metadata (particle counts, pixel size, voltage, file sizes) was inspected, and only to
establish that the study is physically possible at all — see §3.

Any later change to a margin, an endpoint definition or the analysis set must appear as a separate
commit labelled `PROTOCOL AMENDMENT` stating its reason. The original stays in history.

Pinned source commit for all runs under this protocol:
`1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (`origin/main`, verified identical to live origin at
2026-09-27). No production kernel, comparator threshold, FFT engine, precision default, RNG or
scientific formula is modified by this work.

---

## 1. Question

On a collection that shares **no specimen, no session, no detector and no microscope** with the
RELION tutorial data, does the native CUDA backend preserve the cryo-EM signal recoverable from a
movie, relative to the same-source CPU implementation on identical inputs and options?

PR #65 answered this for one collection (EMPIAR-10204 beta-galactosidase, K2, 200 kV) and stated
plainly that its 22 held-out movies are *within* that collection, not an independent one. This
protocol does not reuse those movies and does not reinterpret that result.

Corrected-image relative RMSE is carried as a **descriptive diagnostic only**, preserved in full
per ADR #66 §4. No numerical gate is evaluated, proposed or changed here, and no historical Gate 2
failure is reclassified.

## 2. Why the tutorial collection cannot answer it

Recorded in [`HOST_DATA_SURVEY.md`](HOST_DATA_SURVEY.md): every raw movie set reachable on
Alex-owned storage across `cpu64`, `4GPUs` and `scarf` is the same 24 beta-galactosidase tutorial
movies. Two other collections exist on `4GPUs` but neither is usable:

| Collection | Why not usable |
| --- | --- |
| `/mnt/clathrin` (clathrin-auxilin, K3/300 kV) | **No raw movies and no gain reference.** Extracted subparticles and downstream refinements only. Motion correction cannot be run on it at all. |
| `/mnt/milan_xval/empiar_data/11233` (TRPM8) | Permission-restricted to another user, and is a **final particle stack** with no raw movies. Recorded as unavailable; no escalation attempted. |

Neither is substituted for a raw-movie comparison.

## 3. Target collection

**EMPIAR-12963** — *Melbournevirus Mini variant Nucleosome*, Villalta/Luger et al.
Cross-reference **EMD-45966**. Released 2025-12-07.

Licence: **CC0**. EMPIAR states all archived data "can be re-used freely without any conditions or
restrictions". Attribution is by courtesy: accession code plus the original publication, and the
EMPIAR paper (Iudin et al., 2023, *Nucleic Acids Res.* 51, D1503–D1511). No account, credential or
access grant is required; anonymous HTTPS from the EBI FTP mirror.

### Independence from the tutorial collection

| Property | Tutorial (EMPIAR-10204) | Target (EMPIAR-12963) |
| --- | --- | --- |
| Specimen | beta-galactosidase | Melbournevirus Mini variant nucleosome |
| Microscope / voltage | 200 kV | FEI Titan Krios, **300 kV** |
| Detector | K2 Summit | **Falcon IV** |
| Raw format | MRC / TIFF | **EER** |
| Pixel size | 0.885 Å | **0.485 Å** (super-resolution grid 8192², physical 0.97 Å) |
| Cs | 1.4 mm | **2.7 mm** |
| Total dose | ~30.6 e/Å² over 24 frames | **50 e/Å²** |
| Symmetry / target | D2, 2.x Å class | nucleosome, deposited at **4.41 Å** |

Different specimen, session, facility, detector, voltage and file format. This is an independent
collection in the sense #73 requires.

### Verified availability of every required resource

Checked against the deposited files themselves, not the deposition form — which is wrong in at
least one place (it lists the corrected micrographs as 4096² at 0.49 Å; the particle metadata shows
the micrographs are **8192²** at 0.485 Å).

| Requirement | Verified artifact | Evidence |
| --- | --- | --- |
| Raw movies | `RawMicrographs/Images-Disc1/GridSquare_*/Data/*.eer`, 2894 movies | FTP listing; sampled sizes 756–806 MiB |
| Gain reference | `GainReference/20230326_221855_EER_GainReference.gain`, 32.3 MiB | staged; `file` reports **TIFF little-endian** |
| Particle orientations | `Refinement/J189_003_particles.cs`, `alignments3D/pose`, `/shift` | staged, read with numpy |
| Half-set assignment | `alignments3D/split` — **18026 / 18025** | staged |
| CTF per particle | `ctf/df1_A`, `df2_A`, `df_angle_rad`, `accel_kv`=300, `cs_mm`=2.7, `amp_contrast`=0.1 | staged |
| Micrograph linkage | `J189_passthrough_particles.cs`: `location/micrograph_path`, `center_x_frac`, `center_y_frac` | staged; `uid` matches particles file elementwise |
| Reference map / half maps / masks | `J189_003_volume_map{,_half_A,_half_B}.mrc`, `_volume_mask_fsc.mrc`, `_mask_refine.mrc` | FTP listing, 343 MiB each |

Particle→movie mapping is exact: `location/micrograph_path` embeds the EER basename, so particles
can be re-extracted from *our own* corrected micrographs at identical fractional coordinates, with
the deposited orientations, CTF and half-set carried through unchanged.

### Native format support

`--gainref` accepts the TIFF gain via `src/rwTIFF.h`; EER is decoded natively by
`src/renderEER.cpp` and selected automatically (`EERRenderer::isEER`). `--eer_upsampling 2` gives
the 8192² grid the deposited particles were picked on, and `--eer_grouping` sets the fraction
count. `--gain_rot` / `--gain_flip` / `--defect_file` are available if the gain orientation needs
correcting. No code change is required to read this collection; confirming the gain orientation and
the correct `--eer_grouping` is an explicit objective of the feasibility pilot (§7).

## 4. Frozen analysis sets

Sampling is frozen here, before any outcome is seen.

- **Feasibility subset (staged, ≤ 2 GiB):** the two movies with the most deposited particles,
  `FoilHole_4677724_..._041554_EER` (54 particles) and `FoilHole_4681533_..._062633_EER` (50), plus
  gain and particle metadata. **Total 1575.5 MiB** against a 2048 MiB cap. Exact bytes and hashes
  in [`results/acquisition_manifest.json`](results/acquisition_manifest.json). This subset is for
  plumbing and diagnostics only and is **declared incapable of the primary endpoint** (§7).
- **Confirmatory set (NOT yet acquired):** a 350-movie simple random sample, drawn with
  `seed = 73` from the 2809 micrographs carrying particles, sorted by micrograph basename. The
  draw is reproducible from the staged metadata alone by
  `tools/science_issue73/i73_select_movies.py`. Expected yield ≈ 4492 particles, matching PR #65's
  4452 so the two collections' results are comparable at similar statistical weight.
- **Development allowance:** the two feasibility movies are development data. They are excluded
  from the confirmatory draw and no primary endpoint is reported from them.

## 5. Arms and options

| Arm | Backend | Host |
| --- | --- | --- |
| `cpu` | reference/oracle, `CUDA=OFF` | `cpu64`, bounded mask, `--j 1`, one movie per process |
| `cuda` | native CUDA global + local | dedicated SCARF Slurm allocation (preferred) or `4GPUs` under `taskset -c 96-103` + `flock`, one benchmark at a time |

Identical options across arms, fixed now:

```
--use_own --j 1 --seed 1 --dose_weighting --dose_per_frame <50/Ngroups>
--patch_x 5 --patch_y 5 --bfactor 150
--eer_upsampling 2 --eer_grouping <fixed at §7 step 2>
--gainref <gain> [--gain_rot/--gain_flip as fixed at §7 step 2]
--angpix 0.485 --voltage 300
```

`cuda` adds `--gpu 0`. `--eer_grouping` and the gain orientation are the only two values not fixed
in this document; they are determined by the §7 step-2 feasibility checks **on the two development
movies**, recorded as a `PROTOCOL AMENDMENT`, and then frozen for the confirmatory set. They are
properties of the collection, not of either backend, and are chosen identically for both arms.

Each movie is driven by its own one-row STAR file: batch invocation changes the per-process
`rand()` stream used by hot-pixel replacement, which would make only the first movie comparable.

## 6. Endpoints and margins

Derived by [`tools/science_issue73/i73_margins.py`](../../tools/science_issue73/i73_margins.py);
outputs committed at [`results/margins_derivation.json`](results/margins_derivation.json).
λ = 0.0196870 Å at 300 kV. All margins are evaluated at the deposited map resolution, 4.41 Å.

### Primary endpoint — B1

**ρ = effective-data fraction of `cuda` vs `cpu`** = median over qualifying shells of
`SSNR_cuda(s) / SSNR_cpu(s)`, with `SSNR(s) = 2·FSC(s)/(1−FSC(s))` from the matched-orientation
half-map FSC. Qualifying shells: `8.0 Å ≥ d(s) ≥ 4.41 Å` **and** `FSC_cpu(s) ≥ 0.143`.

- **Margin: lower one-sided 95% bound on ρ must be ≥ 0.95.** Non-inferiority.
- Shell budget at box 448, 0.485 Å/px: shells k = 28…49, **22 qualifying shells**, against a
  prespecified minimum of 20. If fewer than 20 qualify, B1 is reported **INCONCLUSIVE** — this is a
  real risk on this collection and is declared now, not after the fact.
- Interpretation on this collection: a 5% effective-particle loss costs 0.022–0.056 Å of resolution
  (B = 200…80 Å²) and a 20% loss costs 0.099–0.261 Å. The margin is therefore strict, not
  permissive.

### Secondary endpoints

| ID | Endpoint | Test | Margin |
| --- | --- | --- | --- |
| A1 | `rlnCtfMaxResolution`, paired per micrograph | non-inferiority | ≤ +0.10 Å in the paired mean |
| A2 | mean defocus `(U+V)/2`, paired | equivalence, two-sided | **± 125 Å** (π/8 phase error at 4.41 Å; π/4 would be 247 Å) |
| A3 | `rlnCtfFigureOfMerit`, paired | non-inferiority | ≥ −5% relative in the paired mean |
| B2 | `d143` after matched-orientation reconstruction | non-inferiority | ≤ +0.05 Å |
| B3 | auto-B delta | non-inferiority | ≥ −10 Å² |

Stage A is a **screen, not a decision**. PR #65 measured that `CtfMaxResolution` failed to detect
even a 20% degradation on its collection. Per #73's pass criteria, a CTF-only result can never
establish equivalence here; if B1 is inconclusive, the study reports inconclusive regardless of
Stage A.

### Uncertainty

Unit of replication is the **movie**, never the pixel. Delete-one-movie jackknife over the
confirmatory set (n = number of movies contributing ≥ 1 particle). The one-sided 95% bound on ρ
uses the jackknife standard error with a normal quantile; the jackknife pseudo-value distribution
is committed alongside the point estimate so the assumption is checkable.

## 7. Harmful controls — prespecified, and the study fails without them

Built by transforming the **`cpu`** arm's corrected micrographs, so they are instrument controls,
not backends. Expectations are fixed now.

| Control | Construction | Purpose | Prespecified expectation |
| --- | --- | --- | --- |
| `ctrl_noise_f005` | + Gaussian noise, variance `0.05·var(micrograph)` | sensitivity at the margin | ρ ≈ 1/(1+f) = **0.952**, resolved below 0.95 |
| `ctrl_noise_f020` | as above, `f = 0.20` | sensitivity at clear harm | ρ ≈ **0.833**, resolved unambiguously |
| `ctrl_envelope_b20` | Fourier multiply by `exp(−B s²/4)`, `B = 20 Å²`, identical in both half-sets | specificity | large image RMSE, ρ ≈ **1.00** |

**Decision rule.** If `ctrl_noise_f005` is not resolved below the 0.95 margin with the confirmatory
set's own n, the instrument is underpowered on this collection and the primary result is reported
**INCONCLUSIVE** — a `cuda` PASS is not reportable. An absent or unmeasured harmful-control
response cannot be read as equivalence. This rule exists specifically so that a null result cannot
be laundered into a pass.

## 8. Execution order

Strict, so that no outcome can influence a margin:

1. **Freeze.** Commit this protocol. *(preregistration timestamp)*
2. **Feasibility pilot**, two development movies, `cpu` arm on `cpu64`:
   determine `--eer_grouping` from the EER frame count and 50 e/Å² total dose; confirm gain
   orientation; confirm the corrected micrograph is 8192² at 0.485 Å and that deposited fractional
   coordinates land on real particles. Record as `PROTOCOL AMENDMENT`.
3. **Paired pilot**, same two movies, `cuda` arm; compare corrected outputs *before* any
   re-estimation: relative and absolute image RMSE, max pixel error, global trajectory RMS,
   per-axis shift difference, and the full `--gate backend` report. Preserve all of it.
4. **Resource decision point.** The confirmatory set needs ~270 GiB of raw EER and a GPU window;
   neither is authorized by this issue's budget. Publish the requirement (§9) and stop if unmet.
5. **Confirmatory run**, only if resourced: 350 movies, both arms, matched extraction, B1 + controls.

Steps 1–3 are in scope now. Steps 4–5 depend on a resource decision that is Alex's, not this
session's.

## 9. Storage and compute requirement for the confirmatory set

From `results/margins_derivation.json`:

| Movies | Raw EER | Corrected sums, both arms | Expected particles |
| ---: | ---: | ---: | ---: |
| 2 (staged) | 1.5 GiB | 1.0 GiB | 26 |
| 100 | 77 GiB | 50 GiB | 1283 |
| **350 (confirmatory)** | **270 GiB** | **175 GiB** | **4492** |
| 2809 (whole collection) | 2167 GiB | 1405 GiB | 36051 |

- **Storage:** ~445 GiB working set for the confirmatory run. `cpu64` has 204 GiB free — **not
  sufficient**. `4GPUs` has 781 GiB free on `/` and SCARF `/home/vol05` has 2.4 TiB free; SCARF is
  the only host that comfortably holds raw + corrected + extracted for both arms.
- **Download:** 270 GiB from EBI. This exceeds this issue's ≤ 2 GiB cap by two orders of magnitude
  and **requires explicit authorization**; it is not taken.
- **Compute:** CPU arm is the binding cost — 8192² EER, 350 movies, one movie per process on a
  bounded mask. GPU arm needs a coordinated exclusive SCARF window. Both are estimated from the
  pilot's measured per-movie wall time rather than guessed here; the pilot reports it.

## 10. What this protocol cannot establish

Stated before results exist, not retrofitted.

- One additional collection is two collections, not a general claim. A PASS supports native CUDA on
  *these two* specimen/detector/voltage combinations and nothing wider.
- The feasibility pilot (§7 steps 2–3) has ~104 particles and **cannot** evaluate B1, any FSC
  endpoint, or any harmful control. It establishes that the pipeline runs on independent data and
  reports image-level diagnostics. It is not evidence of signal equivalence and will not be
  described as such.
- Stage B's FSC is comparative across arms, biased identically by the fixed external orientations;
  it is not a gold-standard resolution estimate.
- The deposited orientations come from a CryoSPARC pipeline whose motion correction is neither of
  our arms. That is a feature for matching — both arms get the same externally-derived selection —
  but it means the particle set is not optimal for either arm.
- Exit status, run counts and summary tables never establish correct pixels or that CUDA kernels
  actually executed. Native execution is evidenced separately per ADR #66 §4, by a parseable
  process log plus an explicit backend-selection check.
- Modes not exercised (frame grouping variants, binning, `--float16`, multi-GPU, tomography,
  polishing, per-arm CTF) are UNRUN and will be tabled as such.

## 11. Compute discipline

- CPU work on `cpu64` (`small-refmac-machine`) after a load check, pinned with `taskset` to a
  bounded mask, at most 8 build jobs. Load and affinity recorded per run.
- GPU work prefers a dedicated SCARF Slurm allocation. `4GPUs` is a fallback only: all MotionCorr
  descendants together within `taskset -c 96-103`, at most 8 logical CPUs, one benchmark at a time,
  under `flock /tmp/motioncorr-bench.lock`, deferring to other users' jobs and leaving `llama`
  untouched.
- SCARF login connections are currently resetting intermittently; use one multiplexed connection
  and back off rather than retrying in a loop.
- Coordinate with the active #85 I/O work: no concurrent benchmark on a shared allocation.
- No credential changes, no new accounts, no paid services.

## 12. Protocol amendments

Amendments are appended, never applied by editing the frozen text above. Each records what was
still open, what fixed it, and whether any arm output existed at the time.

### Amendment 1 — `--eer_grouping` and `--dose_per_frame` fixed (2026-09-27)

§5 left exactly two values open, to be fixed by §8 step 2. This amendment fixes the first.
**No corrected micrograph existed on this collection when it was written, from either arm**, so
no outcome could have influenced it.

Measured with `tools/science_issue73/i73_eer_probe.py`, which walks the TIFF IFD chain and
decodes nothing:

| Quantity | Value | Source |
| --- | --- | --- |
| Raw detector frames per movie | **1911** (both movies) | IFD count |
| Physical frame size | 4096 × 4096 | TIFF tags 256/257 |
| EER compression tag | 65001 | TIFF tag 259 |
| Gain | 4096 × 4096, 32-bit float, LZW | TIFF tags 256/257/258/259 |
| Depositors' rendered fractions | **40** | EMPIAR API `frames_per_image` |
| Total dose | 50 e⁻/Å² | EMPIAR API imageset details |
| Raw physical pixel | 0.97 Å | EMPIAR API `pixel_width` |

`src/motioncorr_runner.cpp:1259` computes `nn = getNFrames() / eer_grouping` with the remainder
truncated, and renders fraction *i* from raw frames `i·G+1 … (i+1)·G`. So:

```
--eer_grouping   47        floor(1911 / 47) = 40 fractions, matching the depositors
--dose_per_frame 1.2297    50 e/Å² x 47/1911, the dose actually in one rendered fraction
```

Frames 1881–1911 (31 of 1911, 1.6 % of dose) are truncated by the integer division. This is the
code's own behaviour, is identical in both arms, and is recorded rather than worked around.

Two independent confirmations of `--eer_upsampling 2`, already fixed in §5: the EMPIAR physical
pixel 0.97 Å halves to exactly the 0.485 Å in the deposited particle metadata, and the measured
4096² gain against an 8192² render grid is the supported `(gain=det=4K, grid=8K)` case at
`src/renderEER.h:149`.

Still open, per §5: **gain orientation** (`--gain_rot` / `--gain_flip`), which needs a rendered
micrograph to confirm and is therefore settled in §8 step 2 proper.

### Amendment 3 — gain orientation fixed, no correction needed (2026-09-27)

§5 left gain orientation open because it needs a rendered micrograph to settle. It is now
settled, from the `cpu` arm on the two **development** movies only. No confirmatory movie has
been processed and no endpoint has been computed, so this cannot have been tuned to an outcome.

Scored by `tools/science_issue73/i73_check_pilot.py`: inner-disc-minus-annulus contrast at each
deposited particle against 20× as many matched random positions, as an AUC.

| Movie | Particles | AUC, y as-is | AUC, y flipped | Particle \|contrast\| | Random \|contrast\| |
| --- | ---: | ---: | ---: | ---: | ---: |
| `FoilHole_4677724_…_041554_EER` | 54 | **0.912** | 0.452 | 0.0199 | 0.0063 |
| `FoilHole_4681533_…_062633_EER` | 50 | **0.946** | 0.489 | 0.0202 | 0.0061 |

Both movies agree, so:

```
(no --gain_rot, no --gain_flip, no --defect_file)
```

A misapplied gain imposes a fixed pattern that destroys particle contrast, so an AUC of 0.91–0.95
at the depositors' own coordinates is positive evidence the gain is applied in the right
orientation, not merely an absence of error. The flipped convention sits at chance (0.45–0.49),
which is what a wrong frame looks like and confirms the test can tell the two apart.

The deposited CryoSPARC fractional y maps directly to MRC row order (**y as-is**). That is a
property of the deposited metadata, identical for both arms, and is frozen here for the
confirmatory set.

This fixes the last value §5 left open. All options in §5 are now fully determined.

### Amendment 2 — cross-reference correction (2026-09-27)

§5 and §10 cite "§7 step 2" for the values deferred to the feasibility pilot. The execution order
is **§8**; §7 is the harmful controls. Editorial only — no endpoint, margin, set or option
changes. Recorded here rather than silently corrected in place.

### Amendment 4 — the `ctrl_noise_f005` decision rule was self-contradictory (2026-09-27)

Raised in PR #87 review. The objection is correct and the rule is replaced.

**The defect.** For additive noise of variance `f·var`, the prespecified expectation is
ρ = 1/(1+f). At `f = 0.05` that is **0.95238**, which lies *above* the 0.95 non-inferiority
margin. §7 nonetheless required this control to be "resolved below 0.95". A control whose true
value sits above the margin can only be resolved below it by an error, and increasing *n* makes
the bound converge on 0.952 — that is, tighter data makes the requirement *less* satisfiable, not
more. Power cannot repair it. The rule conflated two different questions.

**The two questions, now kept apart.**

| | Question | Test |
| --- | --- | --- |
| **D** | Can the instrument detect degradation at all? Is ρ < 1? | upper one-sided 95 % bound on ρ < 1.000 |
| **N** | Can the instrument reject non-inferiority? Is ρ < 0.95? | upper one-sided 95 % bound on ρ < 0.950 |

**Buffer rule, prespecified.** A control may be *required* to answer **N** only if its expected ρ
is ≤ **0.90** — at least 0.05 beyond the margin, the same distance the margin itself sits from
1.0. Controls above the margin are reported against **D** only.

**Revised controls.**

| Control | `f` | Expected ρ | Asked | Blocking |
| --- | ---: | ---: | --- | --- |
| `ctrl_noise_f005` | 0.05 | 0.952 | **D** — near-margin characterization. Above the margin, so **N** is not asked of it. | no |
| `ctrl_noise_f011` | 0.1111 | **0.900** | **N** — the closest-to-margin control that satisfies the buffer rule | **yes** |
| `ctrl_noise_f020` | 0.20 | 0.833 | **N** — clear harm | **yes** |
| `ctrl_envelope_b20` | — | ≈ 1.00 | specificity: large image RMSE must *not* move ρ | **yes** |

**Revised decision rule.**

- If `ctrl_noise_f011` is not resolved below 0.95 at the confirmatory set's own *n*, the instrument
  is underpowered on this collection: **INCONCLUSIVE**, and a `cuda` PASS is not reportable.
- If `ctrl_noise_f020` is not resolved below 0.95, likewise INCONCLUSIVE — a fortiori.
- If `ctrl_envelope_b20` **is** resolved below 0.95, the instrument manufactures harm from a change
  that removes no information: INCONCLUSIVE. (New; the old §7 stated an expectation for this
  control but attached no consequence to its failure.)
- `ctrl_noise_f005` is reported but does not gate. If its upper bound is not below 1.0, that is
  recorded in the report as a measured power limitation of this collection, not as a pass.
- Unchanged: an absent or unmeasured harmful-control response is never equivalence.

**This is not a loosening.** The replaced rule gated on a control that could not satisfy it, which
is a gate that fails open or fails arbitrarily rather than one that fails safe. The new blocking
control at ρ = 0.900 is *stricter* than the `f = 0.20` control already prespecified, and a
consequence is newly attached to the specificity control. The 0.95 margin, the primary endpoint,
every secondary margin, the analysis sets and the comparator thresholds are untouched.

No outcome was inspected in making this change: no confirmatory movie has been processed and ρ has
not been computed on either arm. `tools/science_issue73/i73_margins.py` is unchanged — the margin
it derives is not edited here.

### Amendment 5 — the gain-orientation conclusion of Amendment 3 is withdrawn (2026-09-27)

Raised in PR #87 review. The objection is correct.

**What Amendment 3 claimed.** That particle-vs-random AUC of 0.91–0.95 at the deposited
coordinates, with a y-flipped comparison at chance, is "positive evidence the gain is applied in
the right orientation".

**Why that does not follow.** The y-flip comparison flips the *coordinate lookup*, not the gain.
It therefore controls the coordinate convention and nothing else. The AUC result supports two
narrower claims, which stand:

1. the deposited CryoSPARC fractional y maps to MRC row order **as-is**, and
2. there is real particle signal at the deposited positions, so the pipeline is not producing noise.

It does not separate those from the orientation of the detector gain, because no variant with a
differently-oriented gain was ever rendered and scored. An argument of the form "a misapplied gain
would destroy contrast, contrast survives, therefore the gain is right" needs the counterfactual
actually measured; asserting it is circular.

**Status.** The frozen option set is unchanged —

```
(no --gain_rot, no --gain_flip, no --defect_file)
```

— because that is what the deposited gain and the RELION defaults imply, but it is now carried as
**assumed and unverified**, not established. §5's open item on gain orientation is reopened, and
Amendment 3's final sentence ("All options in §5 are now fully determined") is retracted.

**The control that would settle it**, recorded here before it runs: re-render one development
movie under each distinct orientation of the gain (the eight dihedral transforms reachable through
`--gain_rot` 0–3 × `--gain_flip` 0–2) and score each with the same particle-contrast AUC. If the
identity is uniquely best, the assumption is verified; if several are indistinguishable, the test
is not sensitive enough on this specimen and the assumption stays unverified and is declared so.
Prespecified now so the outcome cannot be reinterpreted afterwards. Cost is CPU-only on `cpu64`,
one movie, no new download.
