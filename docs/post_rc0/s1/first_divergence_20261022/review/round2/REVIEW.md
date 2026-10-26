# W4 first-divergence packet: independent review round 2 (2026-10-22)

Reviewed: `25e8261a0b6485c89b78d7c886845bfa232cfc64` (resolved from the local ref),
branch `diag/known-motion-first-divergence-20261022`, detached in the reviewer worktree
`t3-7fd1de91`. Round-1 head was `7d85898d`. No native process, GPU, remote access, push,
PR, comment or Notion write. No edits to the author's packet. The only local computation
was reading stored JSON, regenerating `ledger.json` into a temp file, and hashing.

## Verdict

**Ready as a DRAFT diagnostic packet.** No blocking defect. One non-blocking residual
(R2-1) is a mislabelled machine-ledger key on exactly the quantity F7 disputes; it is a
rename plus regeneration, with no native rerun. No merge or adoption recommendation.

## F7 (the contested finding): the author is right, my round-1 F7 was wrong

Code: `offline_stages.py:186-194` (identical to `offline/attempt03-offline_stages.py`, which is
the script that produced the retained JSON) does, per frame:
`p, wpos = parabola(m)` on the double-precision map `m = ccf_map(F1d, f, False)`;
`exact_objective_continuous = continuous_argmax(S, wpos)` as a separate field; and
`native_minus_exact_parabola_px = ||native - p||`. So the compared quantity is native minus
the parabola rule on the double map, not the continuous maximum.

Retained output (`offline/attempt03.json`, `S2_iteration1_same_state`, recomputed from the stored vectors):

| case/backend, frame | native | parabola(double map) | continuous max | native-parabola | native-continuous |
|---|---|---|---|---|---|
| integer CPU 1 | (1.667,-3.25) | (0.898,-2.301) | (1.444,-2.719) | **1.221** (stored 1.2211272) | **0.576** |
| integer CUDA 1 | same | same | same | 1.2211273 | 0.576 |

The stored value equals the recomputed native-parabola distance for all 20 records (stored vs
recomputed agree to 3 decimals everywhere). The max over frames per case is 1.221 integer
(both backends), 0.632 fractional CPU, 0.160 fractional CUDA. The author's numbers and the
clarified README label (`README.md:109`) are correct. **F7 closed in the author's favour.**
My round-1 reading of the label was wrong; the code and outputs do not support the
continuous-maximum interpretation.

Residuals from this check (see R2-1, R2-4): the machine ledger still names the field `..._vs_exact_max_px`, and the row's meaning is not stated.

## Findings decided

| ID | Decision | Evidence checked now |
|---|---|---|
| F1 | **Closed** | README `173-185` limits the #264/#265 exclusion to integer/fractional/flat/repeated and calls pedestal an inference. `ledger/attempt01.json` pedestal CPU (index 4) has 36 local coefficients, sum of absolute values 0.0 exactly. 9 patches / model 1 confirmed from round 1. Claim "decision not logged, coefficients not captured" stays honest. |
| F2 | **Closed** | README `20-39`: "relative to the inherited objective", weight "fidelity only" (`:107`, `:266`), co-causes, "no single exclusive cause". `ledger.json` iso 5-iteration rms 0.0428 / 0.0485 matches my round-1 0.043 / 0.049. |
| F3 | **Closed**, one wording nit (R2-2) | N=9/13/20 numbers match `ndep.log`: integer prod/50it 0.044 / 0.002 / 0.000; fractional 0.067 / 0.001 / 0.000; prod/5it 0.268-0.480; eigenvalues -0.976 / -0.903 / -0.849 and -1.196 at N=5. README `37-39`, `133-138`, `262-264`, ledger `scope` all bound nonconvergence to N=5. |
| F4 | **Closed** | `git log`: `daaa2217` committed 20:11:07+01:00 (manifest, "roughly 0.26-0.34 px" at its line 62); `98855b28` committed 20:16:41+01:00 = 19:16:41 UTC, introduces `analyze_native.py` with the 0.2-0.45 test (line 97). Launch 19:20:31 UTC is self-reported in the receipts. Both bands and sources are in README `65-69` and ledger. CUDA 0.495 NOT MET under both; CPU 0.308 inside both. |
| F5 | **Closed** | "inferred" in README `44-47`, ledger category/first_divergence/uncertainty. |
| F6 | **Closed** | README `24-26` and `110-111`: bias needs a nonzero cross term, axis-aligned anisotropy gives none. |
| F7 | **Closed (author correct)** | See above. |
| F8 | **Closed** | README `35-37`, `152-154`, `196-197`; numbers 11.833 vs 0.279 (N=20, fractional, 5 it) match `ndep.log`. Presented as diagnostic counter-evidence, no adoption. See R2-3 on scope wording. |

## Coherence, provenance, scope

- **Scope:** `git diff --name-only 805d9de2 25e8261a` lists nothing outside `docs/post_rc0/s1/first_divergence_20261022/`; no `src/` or CMake change. Between `7d85898d` and `25e8261a` only README, `final_ledger.py`, `ledger.json` changed; the rest are additions. Manifest, native evaluation, receipts, offline and estimator attempts, and the retained failure records are not in the diff, so they are unchanged.
- **Ledger:** `python3 -B -I final_ledger.py <tmp>` reproduces the committed `ledger.json` byte-for-byte (`cmp` clean). Historical totals assert 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE, 16 rows. `ledger.json` input hashes for the six listed inputs match the files (`ledger/attempt01.json` da05b557…, `offline/attempt03.json` 766cbcfb…, `estimator/attempt02.json` bc06251a…, `native/evaluation-attempt01.json` 19706cc6…, `review/round1/indep.json` c5a206d7…, `ndep.log` 71b1840b…). README ledger table and `ledger.json` text agree (guard exclusion, N=5 bound, pedestal inference, both bands). `final_ledger-round1.{log,exit}` added; the original generator log is kept.
- **Review evidence copy:** all six files in `review/round1/` are byte-identical to the source directory (`cmp`) and match `round1-artifacts.json`. `hashes.txt` lists only the four named files, so `REVIEW.md` and `hashes.txt` being "not in reviewer hashes" is true. `s273.json` and `receipts/` are recorded as received-not-copied and I did not verify them (nothing cites them).
- **GPL:** new scripts from the original packet carry SPDX. The two reviewer scripts `review/round1/indep.py` and `ndep.py` have no SPDX header. They are preserved artifacts whose bytes are hash-bound, so adding one would break the binding. Other `docs/**/*.py` in the repo lack SPDX too and no repo check enforces it. I regard this as acceptable; a one-line note in `round1-artifacts.json` would make it explicit (optional).

## Residual items (none blocks DRAFT publication)

- **R2-1 (should fix; wording/ledger only, no rerun).** `final_ledger.py:26` names the field `iteration1_native_vs_exact_max_px`, and `ledger.json` carries it at lines 160, 207, 513, 560 (1.2211, 0.6319, 1.2211, 0.1605). The value is `max(native_minus_exact_parabola_px)`, i.e. native minus the parabola on the double map, not versus an exact maximum. That is the very mislabel F7 was about, and the response says the label was clarified when only the README was. Rename (e.g. `iteration1_native_vs_double_map_parabola_px_max`) and regenerate. The legacy JSON field `exact_objective_parabola` and the comment at `offline_stages.py:186` ("exact objective vs native candidate") cannot be edited without breaking `script_sha256`; a README sentence saying "exact_objective_* fields in `offline/attempt03.json` mean the parabola rule on the double map" would suffice.
- **R2-4 (wording).** `README.md:109` gives "1.22 px (frame 1) ... vs the continuous maximum: 0.58 px" without saying what the row measures or that the continuous-maximum comparison is for the same frame only. Over all frames the native-vs-continuous maximum is larger: integer CPU frame 0 is 1.041 px. The row measures the effect of the native float32 map (quantization and ties) on the same parabola rule, not parabola bias and not distance to truth. One sentence would prevent misreading.
- **R2-2 (wording).** "reach truth by 50 iterations" (`README.md:38`, `:137`) overstates N=9: 0.044 / 0.067 px, and `ndep.log` shows `conv=False` at tolerance 1e-9 for all production 50-iteration rows. Say "within 0.07 px at N=9 and about 0 at N=13/20". The probes also use two motions on one target, which README does say are synthetic.
- **R2-3 (wording).** `README.md:35-37` says "a reviewer probe with 20 synthetic frames diverges to 11.8 px" without "fractional"; the integer N=20 isotropic probe is 0.041 px. Line 152 has it right. Only 1 of 8 isotropic probe rows diverges.

## Still unresolved (unchanged from round 1, all stated in the packet)

- No native CCF map for `fixedref-cuda-fractional` (tie flip inferred) or for pedestal.
- Affine and noisy local stages, and pedestal patch maps, are not localized.
- Neutrality is shown against the #275 capture-off build; the link to #273 production rests on the #275 review.
- Causal explanation, not an accuracy PASS; no effect on the 2/10/4 totals.

## Commands (local, Mac, no numeric libraries beyond json)

- `git switch --detach 25e8261a`; `git diff --name-only/--stat 805d9de2 25e8261a`; `git diff --name-status 7d85898d 25e8261a`
- `python3 -B -I final_ledger.py /tmp/w4r2-70858/ledger.json` exit 0, then `cmp` clean
- `python3 -B -I` read-only scripts over `offline/attempt03.json`, `ledger/attempt01.json`, `ledger.json`
- `cmp` of the six `review/round1/*` files against `/tmp/motioncorr-w4-independent-review-20261022-lXjp/`; `shasum -a 256` of listed inputs
