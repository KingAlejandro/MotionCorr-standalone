#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Recheck early retained products without changing their original records."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

base = Path('/mnt/clathrin/alex-motioncorr-s1/sweep')
root = base / 'comparator-rechecks-v1'
root.mkdir(exist_ok=False)
(root / 'runs').symlink_to(base / 'runs', target_is_directory=True)
(root / 'manifest.json').symlink_to(base / 'manifest.json')
source = '/mnt/clathrin/alex-motioncorr-rc0/W-QF/src'
digest = hashlib.sha256(Path(source, 'tools/compare_motioncorr.py').read_bytes()).hexdigest()
assert digest == 'cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b'
selection = json.loads((base / 'acquisition/early-comparator-selection.json').read_text())
results = []

def normalized(value):
    if isinstance(value, str):
        return value.replace(str(root), str(base))
    if isinstance(value, list):
        return [normalized(v) for v in value]
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    return value

for name in selection:
    old = json.loads((base / name).read_text())
    assert 'comparator_sha256' not in old
    grid = old['test'].split('-p')[1][0]
    cmd = [sys.executable, str(base / 'tools/sweep.py'), 'analyze', '--root', str(root), '--source', source,
           '--ref', old['reference'], '--test', old['test'], '--patches', grid]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (root / (old['test'] + '.stdout.log')).write_text(r.stdout + r.stderr)
    assert r.returncode == 0
    report = old['test'] + '-backend.json'
    original = json.loads((base / 'analysis' / report).read_text())
    checked = json.loads((root / 'analysis' / report).read_text())
    results.append(dict(original=name, recheck='analysis/' + report, argv=cmd,
                        analyze_exit_status=r.returncode, comparator_sha256=digest,
                        all_gate_fields_equal_after_path_normalization=normalized(checked) == original))
    (root / 'equivalence.json').write_text(json.dumps(results, indent=2) + '\n')
    assert results[-1]['all_gate_fields_equal_after_path_normalization'], name
print('RECHECK COMPLETE', len(results), flush=True)
