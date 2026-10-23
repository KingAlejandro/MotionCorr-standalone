#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# #262: generate Tier A fixtures, record binaries, build the frozen queue. Usage: prepare.sh ROOT
set -eu
ROOT=$1; PY=/home/alex/.mc-venv/bin/python3
cd "$ROOT"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 13 $PY src/test-data/generate_motion_diagnostics.py --outdir v2fixtures > prepare-v2fixtures.log 2>&1
$PY - <<'P'
import hashlib, json, pathlib
root = pathlib.Path('.').resolve()
def h(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
b = {k: dict(path=str(root / 'b' / k / 'motioncorr'), sha256=h(root / 'b' / k / 'motioncorr'))
     for k in ['cpu-exp', 'cpu-plain', 'cuda-exp', 'cuda-plain']}
(root / 'binaries.json').write_text(json.dumps(b, indent=1) + '\n')
m = json.loads((root / 'v2fixtures/MANIFEST.json').read_text())
ref = json.loads((root / 'tools/pr273-fixture-MANIFEST.json').read_text())
same = {c: m['cases'][c]['files'] == ref['cases'][c]['files'] for c in m['cases']}
for c, files in m['cases'].items():
    for n, s in files['files'].items() if False else m['cases'][c]['files'].items():
        assert h(root / 'v2fixtures' / n) == s, n
(root / 'v2fixtures-vs-pr273.json').write_text(json.dumps(dict(numpy=m.get('numpy'), pr273_numpy=ref.get('numpy'), identical=same), indent=1) + '\n')
print(json.dumps(same))
P
$PY tools/campaign.py queue "$ROOT"
