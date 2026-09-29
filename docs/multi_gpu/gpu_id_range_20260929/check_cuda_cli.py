#!/usr/bin/env python3
"""Observe the production CUDA CLI boundary without initializing a device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--binary', required=True, type=Path)
p.add_argument('--shim', required=True, type=Path)
p.add_argument('--out', required=True, type=Path)
p.add_argument('--old', action='store_true')
a = p.parse_args()
a.out.mkdir()
missing = a.out / 'no_such_input.star'
assert not missing.exists()
rows = []
specs = [('4294967296', 'old_alias')] if a.old else [
    ('2147483648', 'range'), ('4294967296', 'range'),
    ('18446744073709551616', 'range'), ('9' * 128, 'range'),
    ('0', 'zero'), ('0' * 30, 'zero'),
    ('2147483647', 'maximum'), ('0' * 20 + '2147483647', 'maximum'),
    ('0:1', 'external'), ('4294967296', 'external')]
for i, (spec, kind) in enumerate(specs):
    marker = a.out / f'{i}.enum'
    env = dict(os.environ, LD_PRELOAD=str(a.shim.resolve()), MC_ENUM_WITNESS=str(marker.resolve()))
    command = [str(a.binary.resolve()), '--i', str(missing.resolve()),
               '--o', str((a.out / f'products-{i}').resolve()), '--gpu', spec]
    command += ['--use_motioncor2', '--motioncor2_exe', '/bin/false'] if kind == 'external' else ['--use_own']
    cp = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    text = cp.stdout + cp.stderr
    (a.out / f'{i}.log').write_text(text)
    calls = marker.read_text().splitlines() if marker.exists() else []
    passed = cp.returncode != 0
    if kind == 'range':
        passed &= ('outside the supported device id range' in text and not calls
                   and 'Using CUDA acceleration' not in text)
    else:
        passed &= calls == ['cudaGetDeviceCount']
        passed &= 'outside the supported device id range' not in text
        if kind in ('zero', 'old_alias'):
            passed &= 'Using CUDA acceleration on GPU device 0' in text and 'no_such_input.star' in text
        elif kind == 'maximum':
            passed &= 'Invalid GPU device ID 2147483647' in text
        elif kind == 'external':
            passed &= 'no_such_input.star' in text and 'device entries' not in text
    rows.append({'spec': spec, 'kind': kind, 'command': command, 'returncode': cp.returncode,
                 'enum_calls': calls, 'pass': bool(passed), 'log': f'{i}.log'})
result = {'binary': str(a.binary.resolve()), 'binary_sha256': hashlib.sha256(a.binary.read_bytes()).hexdigest(),
          'shim_sha256': hashlib.sha256(a.shim.read_bytes()).hexdigest(), 'old_alias_control': a.old,
          'gpu_computation': False, 'cases': rows, 'pass': all(r['pass'] for r in rows)}
(a.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['pass'] else 1)
