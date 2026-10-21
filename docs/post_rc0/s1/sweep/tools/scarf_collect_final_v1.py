#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Collect persisted SCARF evidence; exclude source, binaries, products and environment dump."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path.home() / 'mc-post-rc0-s1'
out = root / 'retained-final'
out.mkdir(exist_ok=True)

def copy(path, target, compress=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    else:
        shutil.copyfile(path, target)

for folder in sorted(list(root.glob('venue-*')) + list(root.glob('crosscontrol-*'))):
    for path in folder.rglob('*'):
        if path.is_file():
            assert path.suffix not in ('.mrc', '.mrcs', '.eer', '.tif', '.tiff')
            copy(path, out / path.relative_to(root))
for folder in sorted(p for p in root.glob('build-records*') if p.is_dir()):
    for path in folder.glob('*'):
        if path.name == 'environment.txt':
            continue
        copy(path, out / (str(path.relative_to(root)) + '.gz'), True)
for folder in root.glob('launch-*'):
    if not folder.is_dir():
        continue
    for path in folder.iterdir():
        if path.is_file() and path.name != 'controller.lock':
            compressed = path.suffix in ('.log', '.out')
            copy(path, out / (str(path.relative_to(root)) + ('.gz' if compressed else '')), compressed)
for pattern in ('*.exit', '*.job', '*.out', '*.log'):
    for path in root.glob(pattern):
        compressed = path.suffix in ('.log', '.out')
        copy(path, out / (path.name + ('.gz' if compressed else '')), compressed)
for name in ('routing-waiters.json', 'followon-recovery.json', 'download-recovery-b4.json'):
    if (root / name).is_file():
        copy(root / name, out / name)
hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted((root / 'tools').glob('*')) if p.is_file()}
(out / 'tools-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
cmd = ['sacct', '-j', ','.join(sorted({p.read_text().strip() for p in list(root.glob('*.job')) + list(root.glob('launch-*/job.id')) if p.read_text().strip()})),
       '--format=JobID,JobName,Partition,State,ExitCode,NodeList,AllocCPUS,ReqMem', '-P']
r = subprocess.run(cmd, capture_output=True, text=True)
(out / 'build-accounting.json').write_text(json.dumps(dict(argv=cmd, exit_status=r.returncode, stdout=r.stdout, stderr=r.stderr), indent=2) + '\n')
print(out)
