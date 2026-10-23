#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Data-only comparator/selector controls, not native or cleanup qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('capture', here / 'capture_cpu_v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
raw = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
root.mkdir(exist_ok=False)
results = []
remote = b'/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2/runs/cpu-affine-on/out'
for case in ('positive', 'timestamp_only', 'payload', 'label', 'STAR', 'state', 'log'):
    old, run = root / case / 'old', root / case / 'run'
    base = old / 'runs/cpu-affine-on'
    for d in (base, run):
        (d / 'out').mkdir(parents=True)
        (d / 'state').mkdir()
        for name in ('affine.star', 'corrected_micrographs.star', 'affine.mrc', 'affine.log'):
            b = (raw / 'out' / name).read_bytes()
            if name.endswith('.star'):
                b = b.replace(remote, str(d / 'out').encode())
            (d / 'out' / name).write_bytes(b)
        for name in ('global.txt', 'model.txt'):
            shutil.copyfile(raw / 'state' / name, d / 'state' / name)
    if case in ('timestamp_only', 'payload', 'label'):
        p = run / 'out/affine.mrc'
        b = bytearray(p.read_bytes())
        if case == 'timestamp_only':
            b[224:1024] = m.re.sub(rb'Relion    [0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}',
                                  b'Relion    01-Jan-00  00:00:00', bytes(b[224:1024]))
        else:
            b[1024 if case == 'payload' else 300] ^= 1
        p.write_bytes(b)
    if case in ('STAR', 'state', 'log'):
        p = run / {'STAR': 'out/affine.star', 'state': 'state/global.txt', 'log': 'out/affine.log'}[case]
        p.write_bytes(p.read_bytes() + b'X')
    checks = m.neutrality(old, run)
    expected = case in ('positive', 'timestamp_only')
    results.append({'case': case, 'expected': expected, 'accepted': all(checks.values()), 'checks': checks})
for case in ('capture_positive', 'wrong_selector', 'wrong_frames', 'extra_call', 'empty_array'):
    run = root / case
    d = run / 'capture'
    d.mkdir(parents=True)
    for i, tag, sel in ((1, 'cpu-global', [0, 0]), (2, 'cpu', [1, 1])):
        meta = {'tag': tag, 'call': i, 'patch_yx': sel, 'frames': 5}
        if i == 2 and case == 'wrong_selector':
            meta['patch_yx'] = [1, 2]
        if i == 2 and case == 'wrong_frames':
            meta['frames'] = 4
        (d / ('c%d.json' % i)).write_text(json.dumps(meta))
        (d / ('c%d-i1-input.bin' % i)).write_bytes(b'' if case == 'empty_array' else b'1234')
    if case == 'extra_call':
        (d / 'c3.json').write_text('{}')
    try:
        m.captures(run, [1, 1])
        accepted = True
    except RuntimeError:
        accepted = False
    results.append({'case': case, 'expected': case == 'capture_positive', 'accepted': accepted})
# New archive checks use fresh tiny tar fixtures; no native process runs.
import io
import tarfile
expected = {'src/a': b'A', 'src/b': b'B', 'src/c': b'C', 'src/d': b'D'}
pins = {n: hashlib.sha256(b).hexdigest() for n, b in expected.items()}
for case in ('archive_positive', 'archive_missing', 'archive_extra', 'archive_duplicate', 'archive_wrong_content', 'archive_symlink'):
    archive = root / (case + '.tar.gz')
    rows = list(expected.items())
    if case == 'archive_missing': rows = rows[:-1]
    if case == 'archive_extra': rows.append(('src/e', b'E'))
    if case == 'archive_duplicate': rows[-1] = rows[0]
    if case == 'archive_wrong_content': rows[-1] = (rows[-1][0], b'X')
    with tarfile.open(archive, 'w:gz') as t:
        for i, (n, b) in enumerate(rows):
            info = tarfile.TarInfo(n)
            if case == 'archive_symlink' and i == 3:
                info.type = tarfile.SYMTYPE
                info.linkname = 'a'
                t.addfile(info)
            else:
                info.size = len(b)
                t.addfile(info, io.BytesIO(b))
    try:
        m.check_overlay_archive(archive, pins)
        accepted = True
    except RuntimeError:
        accepted = False
    results.append({'case': case, 'expected': case == 'archive_positive', 'accepted': accepted})
report = {'driver_sha256': m.sha(here / 'capture_cpu_v2.py'), 'suite_sha256': m.sha(Path(__file__)),
          'argv': sys.argv, 'results': results, 'all_as_expected': all(r['accepted'] == r['expected'] for r in results),
          'scope': 'Data only. No native child, timeout, signal or cleanup path executed.'}
(root / 'CONTROLS.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'controls': len(results), 'all_as_expected': report['all_as_expected']}))
sys.exit(0 if report['all_as_expected'] else 1)
