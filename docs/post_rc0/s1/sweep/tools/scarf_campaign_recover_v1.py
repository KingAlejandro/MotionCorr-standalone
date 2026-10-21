#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Immutable allocated-node driver: stage locally, run same-node pairs, retain evidence."""
import argparse
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--families', required=True)
p.add_argument('--older', action='store_true')
p.add_argument('--cache-roots', required=True)
p.add_argument('--skip-movies', default='')
a = p.parse_args()
home = Path.home() / 'mc-post-rc0-s1'
job = os.environ['SLURM_JOB_ID']
root = Path('/tmp') / ('mc-s1-' + job + '-recovery')
dest = home / ('venue-' + job + '-recovery')
root.mkdir(exist_ok=False)
dest.mkdir(exist_ok=False)
manifest = json.loads((home / 'manifest.json').read_text())
tool = home / 'tools/scarf_sweep_v1.py'
source = home / 'src-F'
os.environ['TMPDIR'] = '/tmp'
cu = '/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0'
# Resolve device zero through the inherited Slurm visibility in a short-lived
# child, releasing any CUDA runtime state before the occupancy check.
query = "import ctypes,uuid; r=ctypes.CDLL(%r); u=ctypes.create_string_buffer(4096); assert r.cudaGetDeviceProperties_v2(u,0)==0; print('GPU-'+str(uuid.UUID(bytes=u.raw[256:272])))" % (cu + '/lib64/libcudart.so.12')
gpu_uuid = subprocess.check_output([sys.executable, '-c', query], text=True).strip()
mask = sorted(os.sched_getaffinity(0))
assert len(mask) == 8, mask
lane = dict(index=gpu_uuid, uuid=gpu_uuid, cpus=','.join(map(str, mask)),
            ld_library_path=cu + '/lib64:' + str(Path.home() / 'nvcomp-sdk/lib'))
(root / 'lane.json').write_text(json.dumps(lane, indent=2) + '\n')
(root / 'acquisition').mkdir()
(root / 'build-records').mkdir()
host = [subprocess.run(c, shell=True, capture_output=True, text=True).__dict__
        for c in ('hostname', 'lscpu', 'nvidia-smi -L', 'df -h /tmp', 'cat /proc/self/status')]
(root / 'host.json').write_text(json.dumps(host, indent=2, default=str) + '\n')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

def persist():
    # Products remain on node-local storage; only proportional evidence goes to PanFS.
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink() or 'data' in path.relative_to(root).parts or 'inputs' in path.relative_to(root).parts:
            continue
        if path.suffix not in ('.json', '.star', '.log', '.txt', '.exit'):
            continue
        rel = path.relative_to(root)
        target = dest / (str(rel) + ('.gz' if path.suffix in ('.star', '.log', '.txt') else ''))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix == '.gz':
            target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        else:
            shutil.copyfile(path, target)

def fetch(rel, expected):
    path = root / 'data' / rel
    if path.is_file():
        assert digest(path) == expected
        return path
    free = shutil.disk_usage('/tmp').free
    assert free > 100 << 30, free
    for folder in a.cache_roots.split(','):
        cached = Path(folder) / rel
        if cached.is_file() and digest(cached) == expected:
            path.parent.mkdir(parents=True, exist_ok=True)
            os.link(cached, path)
            rec = dict(relative_path=rel, method='verified node-local cache', cache=str(cached),
                       sha256=expected, bytes=path.stat().st_size, free_bytes_before=free, **{'pass': True})
            tag = hashlib.sha256(rel.encode()).hexdigest()[:16]
            (root / 'acquisition' / (tag + '.json')).write_text(json.dumps(rec, indent=2) + '\n')
            persist()
            return path
    accession, tail = rel.split('/', 1)
    url = 'https://ftp.ebi.ac.uk/empiar/world_availability/' + accession.removeprefix('EMPIAR-') + '/' + urllib.parse.quote(tail, safe='/')
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['curl', '--fail', '--location', '--retry', '4', '--connect-timeout', '30', '--speed-time', '60', '--speed-limit', '1024', '--max-time', '1800', '--output', str(path) + '.partial', url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    rec = dict(argv=cmd, exit_status=r.returncode, free_bytes_before=free, expected_sha256=expected)
    if r.returncode == 0:
        Path(str(path) + '.partial').rename(path)
        rec.update(sha256=digest(path), bytes=path.stat().st_size)
    rec['pass'] = r.returncode == 0 and rec.get('sha256') == expected
    tag = hashlib.sha256(rel.encode()).hexdigest()[:16]
    (root / 'acquisition' / (tag + '.json')).write_text(json.dumps(rec, indent=2) + '\n')
    (root / 'acquisition' / (tag + '.log')).write_text(r.stdout + r.stderr)
    persist()
    assert rec['pass'], rec
    return path

def arm(row, patches, sha, backend):
    label = '%s-p%s-%s-%s' % (row['id'], patches, sha, backend)
    cmd = [sys.executable, str(tool), 'arm', '--root', str(root), '--movie', row['id'], '--label', label,
           '--binary', str(home / ('build-%s-%s' % (sha, backend)) / 'motioncorr'), '--sha', sha, '--patches', str(patches)]
    if backend == 'cuda':
        cmd.append('--gpu')
    if sha != 'F':
        cmd.append('--legacy')
    subprocess.run(cmd, check=True)
    persist()
    return label

def compare(ref, test, patches, identity=False):
    cmd = [sys.executable, str(tool), 'analyze', '--root', str(root), '--source', str(source),
           '--ref', ref, '--test', test, '--patches', str(patches)]
    if identity:
        cmd.append('--identity')
    r = subprocess.run(cmd)
    persist()
    return r.returncode

def fingerprints(label):
    cmd = [sys.executable, str(home / 'tools/product_fingerprints.py'), str(root / 'runs' / label), '--venue', 'SCARF']
    record = subprocess.check_output(cmd, text=True)
    (root / (label + '-fingerprints.json')).write_text(record)
    persist()

status = 1
try:
    families = a.families.split(',')
    rows = [r for r in manifest['movies'] if r['family'] in families and r['rank'] < 10 and r['id'] not in a.skip_movies.split(',')]
    rows.sort(key=lambda r: (r['id'] == 'e10474f4-00', families.index(r['family']), r['rank']))
    for row in rows:
        row['movie_source'] = str(fetch(row['relative_path'], row['movie_sha256']))
        if row['gain_source']:
            row['gain_source'] = str(fetch(row['recipe']['gain'], row['gain_sha256']))
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        for patches in (5, 3):
            cpu = arm(row, patches, 'F', 'cpu')
            cuda = arm(row, patches, 'F', 'cuda')
            assert compare(cpu, cuda, patches) == 0
            if row['id'] == 'e10216-00' and patches == 5:
                fingerprints(cpu)
                fingerprints(cuda)
            if a.older and row['id'] == 'e10216-00':
                for sha in ('e875d5fe', '8477dc1b', 'f6c41e24', 'ef7e4c0a', '2368063f', 'c24ae8c2'):
                    # Builds can complete while this correctness allocation progresses.
                    binary = home / ('build-%s-cuda/motioncorr' % sha)
                    if not binary.is_file():
                        raise RuntimeError('older build not ready: ' + sha)
                    oldcpu = arm(row, patches, sha, 'cpu')
                    if compare(cpu, oldcpu, patches, True) != 0:
                        print('INVALID CPU CONTROL', sha, patches, flush=True)
                        continue
                    oldcuda = arm(row, patches, sha, 'cuda')
                    assert compare(oldcpu, oldcuda, patches) == 0
        print('COMPLETE MOVIE', row['id'], flush=True)
    status = 0
finally:
    (root / 'campaign.exit').write_text(str(status) + '\n')
    persist()
