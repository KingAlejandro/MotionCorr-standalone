# W4 all-patch CPU observation preparation (2026-10-25)

Status: PREPARED; all numeric output and CPU64 execution remain UNRUN.
Scope: one-shot NumPy-only fit consumer for selectors (1,1) through (3,3), with capture-only local observations, retained runtime coefficients/global shifts, and retained STAR print comparison. No MotionCorr launch is performed.

## Inputs and provenance

`input-manifest.json` pins each file in `inputs/` by relative path, byte count, and SHA-256. `inputs.tar` contains exactly those input files. Selector capture inputs are `c2.json` plus the highest captured `c2-iK-after.bin` for that selector. The manifest lists all observed captured iteration indices and asserts the selected index is their maximum. Selector (2,1) uses the original 94-file hash-verified capture collection; selector (1,1) uses the separately reviewed v3 regrade while its historical original FAIL remains immutable; the other seven use their collected v3 capture bytes. Provenance copies include collection-level RESULT/protocol records, original file index and collection receipt, and the selector (1,1) v3 regrade.

Input lineage SHA-256:

- Original `file-index.json`: `31255dab8eef81ee05f68271ac665429db9a48498b240fbe85ebe228ea3c65c3`
- Original collection receipt: `1c00e50547ffa97b0f6a6b3b8b126cfc35929edd2b7d976f8c3d9ba680476e79`
- Original collection tar: `14154ffafcd68493e3e920239b81e07ca7ba6ce42a2198d102037385dfef9dbf`

The per-selector capture folders do not contain their own RESULT/protocol files. The package therefore pins every consumed capture byte directly and retains the available collection-level RESULT/protocol and regrade records as provenance.

## Consumer contract

`consume_w4_cpu_observations.py` verifies all input hashes before use; requires exactly nine unique selectors, CPU metadata, patch geometry, five frames, final captured iteration, exact `<f8` byte length/shape, finite shifts, and exact frame-zero zero gauge. It derives 45 rows using `obs[g] = after[g] + 0.5*after[1]` at `z=g+0.5`, then compares them with retained STAR shifts to `5e-6` px/component. It fits the same 18-term, no-constant cubic-in-z basis with NumPy `lstsq`; reports coefficient deltas, design condition and residuals; and compares the fitted-plus-retained-global field against the retained full-precision runtime model on `[12:84,12:116]`, integer `z=g`. The `1e-10 px` field bound is an arithmetic-control diagnostic only. Truth limits remain global/local/combined `0.20/0.40/0.80 Å` and are not evaluated here. The report explicitly labels science as UNRUN.

## CPU64 admission commands

Stage this directory intact on the parent-approved CPU64 scratch location. Do not run the consumer on macOS. Verify package identity and syntax first:

```sh
cd /path/to/motioncorr-20261025-w4-cpu-observations
shasum -a 256 consume_w4_cpu_observations.py input-manifest.json inputs.tar
python3 - <<'PY'
from pathlib import Path
p = Path('consume_w4_cpu_observations.py')
compile(p.read_bytes(), str(p), 'exec')
print('compile(...) PASS')
PY
mkdir -p inputs
 tar -xf inputs.tar
python3 -I consume_w4_cpu_observations.py
```

Expected consumer output is `cpu-observations.json` plus stdout JSON. This command is a one-shot run: if it stops on an unexplained mismatch, preserve the failure and do not retry blindly. Any structural negative controls or numeric controls are CPU64-only. Parent independently reviews the script, manifest and this protocol before admission. No science PASS is represented by this preparation.
