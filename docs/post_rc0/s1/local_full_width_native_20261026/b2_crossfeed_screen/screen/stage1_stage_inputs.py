"""Stage 1a: copy ONLY runtime.json and the case STAR of the native runs and the retained controls into stage1_root (no truth, no metrics, no NPY, no manifest)."""
import hashlib, json, shutil, sys
from pathlib import Path
sys.dont_write_bytecode = True
W = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1'); ROOT = W / 'stage1_root'
B = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/runs')
RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if ROOT.exists() and any(ROOT.iterdir()):
    sys.exit('stage1_root is not empty')
man = {}
def put(src_dir, star_src, dst, key):
    dst.mkdir(parents=True, exist_ok=True)
    for name, s in (('runtime.json', src_dir / 'runtime.json'), (star_src.name, star_src)):
        shutil.copyfile(s, dst / name)
        man[f'{key}/{name}'] = {'source': str(s), 'sha256': sha(s), 'staged_sha256': sha(dst / name)}
        assert man[f'{key}/{name}']['sha256'] == man[f'{key}/{name}']['staged_sha256']
for c in CASES:
    for a in ('OFF', 'ON'):
        d = B / c / a
        put(d, d / f'{c}.star', ROOT / 'native' / c / a, f'native/{c}/{a}')
for c in ('noisy', 'affine'):
    for a in ('UP_only', 'UP_B2'):
        d = RAW / c / a
        put(d, d / 'output' / f'{c}.star', ROOT / 'controls' / c / a, f'controls/{c}/{a}')
(W / 'out').mkdir(exist_ok=True)
(W / 'out' / 'stage1_staged_manifest.json').write_text(json.dumps(man, indent=1) + '\n')
names = sorted({p.name for p in ROOT.rglob('*') if p.is_file()})
print('staged files', len(man), 'distinct file names', names)
assert all(n == 'runtime.json' or n.endswith('.star') for n in names)
