# W4 all-patch CPU observation preparation (2026-10-25)

Status: PREPARED; all numeric output and CPU64 execution remain UNRUN.
Scope: one-shot NumPy-only fit consumer for selectors (1,1) through (3,3), with capture-only local observations, retained runtime coefficients/global shifts, and retained STAR print comparison. No MotionCorr launch is performed.

## Inputs and provenance

`input-manifest.json` pins each file in `inputs/` by relative path, byte count, and SHA-256. `inputs.tar` contains exactly those input files. Selector capture inputs are `c2.json` plus the highest captured `c2-iK-after.bin` for that selector. The manifest lists all observed captured iteration indices and asserts the selected index is their maximum. Selector (2,1) uses the original 94-file hash-verified capture collection; selector (1,1) uses the separately reviewed v3 regrade while its historical original FAIL remains immutable; the other seven use their collected v3 capture bytes. Provenance copies distinguish the byte-exact `RESULT-v2-original-FAIL.json` from `RESULT-v3-remaining7.json`; the v3 protocol and selector (1,1) regrade have separate filenames. The consumer hard-pins those exact digests, checks the regrade references the v2 FAIL digest and v3 protocol digest, and verifies every capture byte against the original file index or the corresponding frozen RESULT launch file map. Runtime state/model/STAR/log bytes must agree with both the original #275 file index and the pinned v3 `final_identities`.

Input lineage SHA-256:

- Original `file-index.json`: `31255dab8eef81ee05f68271ac665429db9a48498b240fbe85ebe228ea3c65c3`
- Original collection receipt: `1c00e50547ffa97b0f6a6b3b8b126cfc35929edd2b7d976f8c3d9ba680476e79`
- Original collection tar: `14154ffafcd68493e3e920239b81e07ca7ba6ce42a2198d102037385dfef9dbf`

The per-selector capture folders do not contain per-selector RESULT/protocol files. The original 94-file selector (2,1) receipt must agree with all 94 corresponding source-index entries. For selector (1,1) and the seven remaining selectors, the exact frozen collection RESULT files supply each selected capture hash. These source records are digest-pinned; no ambient or latest RESULT is accepted.

## Consumer contract

`consume_w4_cpu_observations.py` verifies all input hashes before use; requires exactly nine unique selectors, CPU metadata, patch geometry, five frames, final captured iteration, exact `<f8` byte length/shape, finite shifts, and exact frame-zero zero gauge. It derives 45 rows using `obs[g] = after[g] + 0.5*after[1]` at `z=g+0.5`, then compares them with retained STAR shifts to `5e-6` px/component. It fits the same 18-term, no-constant cubic-in-z basis with NumPy `lstsq`; reports coefficient deltas, design condition and residuals; and compares the fitted-plus-retained-global field against the retained full-precision runtime model on `[12:84,12:116]`, integer `z=g`. The `1e-10 px` field bound is an arithmetic-control diagnostic only. The unchanged field-error limits are separately applied to runtime and STAR fields: RMS ≤ `0.20 Å`, p95 ≤ `0.40 Å`, and max ≤ `0.80 Å`. These metric labels replace the incorrect global/local/combined labels; the numeric criteria are unchanged and are not evaluated here. The report explicitly labels science as UNRUN.

## CPU64 admission commands

Stage this directory intact on the parent-approved CPU64 scratch location. Do not run either script on macOS. Run the deliberate structural negatives once before the actual consumer; any failed assertion stops the sequence without retry. The control harness first runs a metadata-only source-path fixture proving that higher CUDA/off-run iteration names cannot affect selector (2,1), then writes temporary copies under `/tmp`, re-pins deliberate byte mutations, and asserts the consumer exits nonzero for the expected reason. It has a CPU64 admission marker and a test-only consumer mode that skips external source pins only inside those isolated mutated fixtures. Then verify package identity and syntax:

```sh
cd /path/to/motioncorr-20261025-w4-cpu-observations
shasum -a 256 consume_w4_cpu_observations.py run_structural_controls.py input-manifest.json inputs.tar
python3 - <<'PY'
from pathlib import Path
for name in ('consume_w4_cpu_observations.py', 'run_structural_controls.py',
             'inputs/affine_patch_oracle.py', 'inputs/w4_allpatch_decomposition_v2.py'):
    p = Path(name)
    compile(p.read_bytes(), str(p), 'exec')
    print('compile(...) PASS', name)
PY
tar -xf inputs.tar
MOTIONCORR_W4_CPU64_ADMISSION=cpu64 python3 -I run_structural_controls.py
python3 -I consume_w4_cpu_observations.py
```

Expected consumer output is `cpu-observations.json` plus stdout JSON. This command is a one-shot run: if it stops on an unexplained mismatch, preserve the failure and do not retry blindly. Any structural negative controls or numeric controls are CPU64-only. Parent independently reviews the script, manifest and this protocol before admission. No science PASS is represented by this preparation.
