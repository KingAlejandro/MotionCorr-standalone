#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Repeat the cross-venue witness movie on a second SCARF allocation."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse

home = Path.home() / 'mc-post-rc0-s1'
job = os.environ['SLURM_JOB_ID']
root = Path('/tmp') / ('mc-s1-control-' + job)
root.mkdir(exist_ok=False)
dest = home / ('crosscontrol-' + job)
dest.mkdir(exist_ok=False)
manifest = json.loads((home / 'manifest.json').read_text())
row = next(r for r in manifest['movies'] if r['id'] == 'e10216-00')
path = root / 'data' / row['relative_path']
path.parent.mkdir(parents=True)
cache = Path('/tmp/mc-s1-3645589/data') / row['relative_path']

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

free = shutil.disk_usage('/tmp').free
assert free > 100 << 30
if cache.is_file() and digest(cache) == row['movie_sha256']:
    os.link(cache, path)
    acquisition = dict(cache=str(cache), exit_status=0, free_bytes_before=free)
else:
    accession, tail = row['relative_path'].split('/', 1)
    url = 'https://ftp.ebi.ac.uk/empiar/world_availability/' + accession.removeprefix('EMPIAR-') + '/' + urllib.parse.quote(tail, safe='/')
    cmd = ['curl', '--fail', '--location', '--retry', '4', '--connect-timeout', '30', '--output', str(path), url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    acquisition = dict(argv=cmd, exit_status=r.returncode, free_bytes_before=free)
    (dest / 'fetch.log.gz').write_bytes(gzip.compress((r.stdout + r.stderr).encode(), mtime=0))
    assert r.returncode == 0
acquisition.update(sha256=digest(path), bytes=path.stat().st_size)
(dest / 'acquisition.json').write_text(json.dumps(acquisition, indent=2) + '\n')
assert acquisition['sha256'] == row['movie_sha256']
assert row['gain_source'] is None
row['movie_source'] = str(path)
(root / 'manifest.json').write_text(json.dumps(dict(movies=[row]), indent=2) + '\n')
shutil.copyfile(Path('/tmp') / ('mc-s1-' + job + '-recovery') / 'lane.json', root / 'lane.json')
status = 1
try:
    for backend in ('cpu', 'cuda'):
        label = 'e10216-00-p5-F-cross-' + backend
        cmd = [sys.executable, str(home / 'tools/scarf_sweep_v1.py'), 'arm', '--root', str(root),
               '--movie', row['id'], '--label', label, '--binary', str(home / ('build-F-' + backend) / 'motioncorr'),
               '--sha', '6d68e2d6', '--patches', '5']
        if backend == 'cuda':
            cmd.append('--gpu')
        subprocess.run(cmd, check=True)
        run = root / 'runs' / label
        cmd = [sys.executable, str(home / 'tools/product_fingerprints.py'), str(run), '--venue', 'SCARF']
        (dest / (backend + '-fingerprints.json')).write_text(subprocess.check_output(cmd, text=True))
    status = 0
finally:
    for p in root.rglob('*'):
        if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.star', '.log', '.txt') and 'inputs' not in p.relative_to(root).parts:
            target = dest / p.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == '.json':
                shutil.copyfile(p, target)
            else:
                target.with_name(target.name + '.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0))
    (dest / 'control.exit').write_text(str(status) + '\n')
