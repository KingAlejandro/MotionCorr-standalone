"""Writes PINS.json (hashes of every input and script, interpreter identity). Reads files only; computes no payload value."""
import hashlib, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
REPO = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/experiment-local-full-width-weight-20261026')
SCREEN = REPO / 'docs/post_rc0/s1/local_full_width_native_20261026/b2_crossfeed_screen/screen'
B = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1')
ARCH = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-crossfeed-screen-archive-r2/screen')
NB2 = REPO / 'docs/post_rc0/s1/native_b2_20261026'
inputs = {}
def add(label, p): inputs[label] = {'path': str(p), 'sha256': sha(p)}
for c in ('noisy', 'affine', 'pedestal'):
    for a in ('OFF', 'ON'):
        for f in (f'{c}.star', 'runtime.json', f'{c}.log'):
            add(f'run/{c}/{a}/{f}', B / 'runs' / c / a / f)
    add(f'truth/{c}_field.npy', B / 'truth' / f'{c}_field.npy')
add('truth/MANIFEST.json', B / 'truth/MANIFEST.json')
add('bundle/MANIFEST.json', B / 'MANIFEST.json')
for n in ('stage1_fit.json', 'stage1_seal.json', 'stage1_staged_manifest.json', 'stage2_result.json'):
    add(f'screen_out/{n}', ARCH / 'out' / n)
for n in ('w8_fit.py', 'w8_refit.py'):
    add(f'w8/{n}', SCREEN / 'src_w8' / n)
add('tr_proof/tiny_challenge.py', NB2 / 'scripts/tiny_challenge.py')
add('tr_proof/TINY_DIAGNOSTIC_PLAN.md', NB2 / 'TINY_DIAGNOSTIC_PLAN.md')
add('tr_proof/rounding_prediction.json', NB2 / 'rounding_prediction.json')
W = Path(__file__).resolve().parent
scripts = {n: sha(W / n) for n in ('PLAN.md', 'resid_lib.py', 'test_resid_lib.py', 'observe.py', 'make_tables.py', 'build_pins.py')}
json.dump({'schema': 'observation-residual-pins/1', 'python': sys.version.split()[0], 'numpy': np.__version__, 'numpy_file': np.__file__,
           'inputs': inputs, 'scripts': scripts,
           'constants': {'frames': 5, 'pixel_size_A_per_px': 0.885, 'star_rounding_decimals': 5, 'star_axis_rounding_half_unit_px': 5e-6,
                         'sealed_roi_rows_cols': [12, 84, 12, 116], 'tr_formula': 'Tr[H][p,g] = H[p,g] + 0.5*H[p,1]'}},
          open(W / 'PINS.json', 'w'), indent=1, sort_keys=True)
print('pins written', len(inputs))
