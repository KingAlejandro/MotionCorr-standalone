#!/usr/bin/env python3
"""Bounded, unwrapped, within-process kernel measurements; not a job speed claim."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/profiling'))
from lib import provenance, stats

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--stress', action='store_true')
args = parser.parse_args()
args.out.mkdir(exist_ok=False, parents=True)
env = dict(os.environ, OMP_DYNAMIC='false', OMP_PROC_BIND='close', OMP_PLACES='cores',
           OMP_WAIT_POLICY='PASSIVE', OPENBLAS_NUM_THREADS='1')
manifest = {'spectrum_fixture': 'deliberate subnormal stress' if args.stress else 'finite normal values and signed zero; no deliberate subnormals',
            'scope': 'unwrapped source-bound dose kernel, one process per configuration; '
                     'within-process paired statistics are descriptive, not certified job speed',
            'limitation': '/proc PID namespace differs from child PIDs; no certified ownership, '
                          'foreign activity or physical host isolation',
            'platform': platform.platform(), 'binary': str(args.binary.resolve()),
            'binary_sha256': provenance.sha256_file(str(args.binary)),
            'source': provenance.source_for_binary(str(args.binary)),
            'cpu_max': Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
            'memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip(),
            'environment': {k: env[k] for k in ('OMP_DYNAMIC','OMP_PROC_BIND','OMP_PLACES',
                                               'OMP_WAIT_POLICY','OPENBLAS_NUM_THREADS')},
            'configurations': []}
with open('/tmp/motioncorr-bench.lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    if provenance.compilers_running():
        raise RuntimeError('compiler active: finish all builds before measuring')
    for nx, ny, count in ((512, 512, 64), (3710, 3838, 24)):
        for threads in (1, 4):
            mask = '0' if threads == 1 else '0-3'
            env['OMP_NUM_THREADS'] = str(threads)
            probe = subprocess.check_output(['taskset', '-c', mask, sys.executable, '-c',
                      'import os,json;print(json.dumps(sorted(os.sched_getaffinity(0))))'], text=True)
            affinity = json.loads(probe)
            if affinity != ([0] if threads == 1 else [0, 1, 2, 3]):
                raise RuntimeError('wrong self-reported taskset affinity')
            name = f'{nx}x{ny}x{count}-j{threads}'
            command = ['taskset', '-c', mask, str(args.binary.resolve()), '--bench',
                       str(nx), str(ny), str(count), str(threads), '6']
            if args.stress:
                command.append('--stress')
            with (args.out / (name + '.jsonl')).open('w') as output, \
                 (args.out / (name + '.stderr')).open('w') as error:
                rc = subprocess.run(command, env=env, stdout=output, stderr=error).returncode
            rows = [json.loads(line) for line in (args.out / (name + '.jsonl')).read_text().splitlines()]
            pairs = []
            for rep in range(6):
                runs = [r for r in rows if r['rep'] == rep]
                by_arm = {r['arm']: r for r in runs}
                if len(runs) != 2 or set(by_arm) != {'base', 'candidate'}:
                    raise RuntimeError('incomplete kernel pair')
                pairs.append({'a': by_arm['base']['wall_s'], 'b': by_arm['candidate']['wall_s'],
                              'order': 'AB' if runs[0]['arm'] == 'base' else 'BA'})
            record = {'configuration': name, 'command': command, 'rc': rc, 'self_affinity': affinity,
                      'spectra_bitwise_equal_every_pair': rc == 0,
                      'within_process_wall_statistics': stats.paired(pairs)}
            manifest['configurations'].append(record)
            (args.out / 'results.json').write_text(json.dumps(manifest, indent=2) + '\n')
            print(name, record['within_process_wall_statistics'], flush=True)
            if rc:
                raise RuntimeError('kernel returned failure: inspect stderr; no performance claim')
