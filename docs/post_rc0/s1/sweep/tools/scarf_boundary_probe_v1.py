#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One coarser-history refinement; exact same-venue CPU control precedes CUDA."""
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

home = Path.home() / 'mc-post-rc0-s1'
job = os.environ['SLURM_JOB_ID']
root = Path('/tmp') / ('mc-s1-control-' + job)
dest = home / ('crosscontrol-' + job)
tool = home / 'tools/scarf_sweep_v1.py'
source = home / 'src-F'
sha = '58fd513a'

def persist():
    for p in root.rglob('*'):
        if p.is_file() and not p.is_symlink() and p.suffix in ('.json', '.star', '.log', '.txt') and 'inputs' not in p.relative_to(root).parts:
            target = dest / p.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == '.json':
                shutil.copyfile(p, target)
            else:
                target.with_name(target.name + '.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0))

status = 1
try:
    for backend in ('cpu', 'cuda'):
        label = 'e10216-00-p5-' + sha + '-' + backend
        if backend == 'cuda':
            cpu = json.loads((root / 'analysis/e10216-00-p5-58fd513a-cpu.json').read_text())
            assert cpu['identical'], 'INVALID CPU CONTROL: CUDA unrun'
        cmd = [sys.executable, str(tool), 'arm', '--root', str(root), '--movie', 'e10216-00',
               '--label', label, '--binary', str(home / ('build-' + sha + '-' + backend) / 'motioncorr'),
               '--sha', sha, '--patches', '5', '--legacy']
        if backend == 'cuda':
            cmd.append('--gpu')
        subprocess.run(cmd, check=True)
        ref = 'e10216-00-p5-F-cross-cpu' if backend == 'cpu' else 'e10216-00-p5-58fd513a-cpu'
        cmd = [sys.executable, str(tool), 'analyze', '--root', str(root), '--source', str(source),
               '--ref', ref, '--test', label, '--patches', '5']
        if backend == 'cpu':
            cmd.append('--identity')
        subprocess.run(cmd, check=True)
        persist()
    status = 0
finally:
    (dest / 'boundary-probe.exit').write_text(str(status) + '\n')
    persist()
