#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read ahead into the allocation's node-local scratch, with verified atomic publication."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import urllib.parse

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--root', required=True, type=Path)
p.add_argument('--families', required=True)
a = p.parse_args()
manifest = json.loads((Path.home() / 'mc-post-rc0-s1/manifest.json').read_text())
tasks = {}
for row in manifest['movies']:
    if row['family'] not in a.families.split(',') or row['rank'] >= 10:
        continue
    tasks[row['relative_path']] = row['movie_sha256']
    if row['gain_source']:
        tasks[row['recipe']['gain']] = row['gain_sha256']

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

def fetch(item):
    rel, expected = item
    path = a.root / 'data' / rel
    # Leave the driver's active transfer alone.
    if path.is_file() or Path(str(path) + '.partial').exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(str(path) + '.prefetch.partial')
    assert not partial.exists()
    free = shutil.disk_usage(a.root).free
    assert free > 100 << 30
    accession, tail = rel.split('/', 1)
    url = 'https://ftp.ebi.ac.uk/empiar/world_availability/' + accession.removeprefix('EMPIAR-') + '/' + urllib.parse.quote(tail, safe='/')
    cmd = ['curl', '--fail', '--location', '--retry', '4', '--connect-timeout', '30', '--output', str(partial), url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    rec = dict(relative_path=rel, expected_sha256=expected, argv=cmd, exit_status=r.returncode, free_bytes_before=free)
    if r.returncode == 0:
        rec.update(sha256=digest(partial), bytes=partial.stat().st_size)
    rec['pass'] = r.returncode == 0 and rec.get('sha256') == expected
    if rec['pass']:
        try:
            os.link(partial, path)  # exclusive publication; never replace a driver's file
            rec['published'] = True
        except FileExistsError:
            rec['published'] = False
            assert digest(path) == expected
        partial.unlink()
    folder = a.root / 'acquisition'
    folder.mkdir(exist_ok=True)
    tag = hashlib.sha256(rel.encode()).hexdigest()[:16] + '-prefetch'
    # Atomic JSON publication avoids a collector reading a partial record.
    record = folder / (tag + '.json')
    tmp = record.with_suffix('.tmp')
    tmp.write_text(json.dumps(rec, indent=2) + '\n')
    tmp.rename(record)
    (folder / (tag + '.log')).write_text(r.stdout + r.stderr)
    assert rec['pass'], rec
    print('VERIFIED', rel, flush=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(fetch, tasks.items()))
print('PREFETCH COMPLETE', flush=True)
