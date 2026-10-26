#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage hash-bound stored inputs, never execute archive members. Run with python -I."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[4]
W4 = ROOT.parent
EVIDENCE = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261025')
CACHE = ROOT / 'input-cache'
sha = lambda b: hashlib.sha256(b).hexdigest()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == '7b76b848650726c018567312b6526269af72496f'
archives = json.loads((W4 / 'qualification_20261025/RAW-EVIDENCE.json').read_text())['files']
origins = {}

def put(rel, raw, origin):
    p = CACHE / rel
    if p.exists():
        assert p.read_bytes() == raw, rel
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    origins[rel] = origin

for name, prefix in [('W4-phaseD-inputs.tar', 'phaseD'), ('W4-matched-native-inputs.tar', 'matched'),
                     ('w4-repro-inputs.tar', 'repro')]:
    p = EVIDENCE / name
    raw = p.read_bytes()
    assert sha(raw) == archives[name]['sha256'] and len(raw) == archives[name]['bytes']
    with tarfile.open(p) as tf:
        for m in tf.getmembers():
            assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
            # Skip build receipts; keep only stored runtime, index and exact source helpers.
            if prefix == 'repro' and not (m.name == 'r275/file-index.json' or '/state/' in m.name or '/out/' in m.name or m.name.startswith('src805/')):
                continue
            put(prefix + '/' + m.name, tf.extractfile(m).read(), name + ':' + m.name)

manifest = json.loads((CACHE / 'phaseD/fixtures/MANIFEST.json').read_text())
for case, record in manifest['cases'].items():
    for name, pin in record['files'].items():
        raw = (Path('/tmp/mc-v2/fixtures') / name).read_bytes()
        assert sha(raw) == pin, name
        put('fixtures/' + name, raw, 'original fixture MANIFEST:' + pin)
put('fixtures/MANIFEST.json', (CACHE / 'phaseD/fixtures/MANIFEST.json').read_bytes(), 'phaseD pinned manifest')
for rel in ['qualification_20261025/cpu-observation-closure/actual/cpu-observations.json',
            'qualification_20261025/matched-native/actual/out/w4_matched_native.json',
            'qualification_20261025/matched-native/scripts/w4_matched_native.py',
            'qualification_20261025/scripts/w4_objective_oracle.py',
            'review/round1/ndep.py', 'review/round1/ndep.log', 'review/round1/indep.py',
            'ledger/attempt01.json']:
    put('retained/' + rel, (W4 / rel).read_bytes(), '7b76b848:' + str((W4 / rel).relative_to(REPO)))
for rel in ['src/motioncorr_runner.cpp', 'src/micrograph_model.cpp', 'src/metadata_table.cpp',
            'tools/check_motion_diagnostics.py', 'tools/motion_field.py',
            'test-data/generate_motion_diagnostics.py', 'test-data/generate_known_motion_fixture.py']:
    raw = subprocess.check_output(['git', 'show', '805d9de2:' + rel], cwd=REPO)
    put('source/' + rel, raw, '805d9de27898b4a10e6212e65098d5995a40fdb1:' + rel)
files = {rel: dict(sha256=sha((CACHE / rel).read_bytes()), bytes=(CACHE / rel).stat().st_size, origin=origin)
         for rel, origin in sorted(origins.items())}
out = dict(schema='w5-inputs/1', source='805d9de27898b4a10e6212e65098d5995a40fdb1',
           parent='7b76b848650726c018567312b6526269af72496f', archives={n: archives[n] for n in
           ['W4-phaseD-inputs.tar', 'W4-matched-native-inputs.tar', 'w4-repro-inputs.tar']}, files=files)
(ROOT / 'INPUTS.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(dict(files=len(files), bytes=sum(f['bytes'] for f in files.values()), manifest_sha256=sha((ROOT / 'INPUTS.json').read_bytes()))))
