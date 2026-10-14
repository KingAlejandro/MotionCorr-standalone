#!/usr/bin/env python3
"""Bounded reconstruction-stage experiment. Run only in an exclusive benchmark lane."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/profiling'))
from lib import provenance, stats


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def expand_mask(mask):
    cpus = set()
    for field in mask.split(','):
        bounds = field.split('-')
        if len(bounds) == 1:
            cpus.add(int(bounds[0]))
        elif len(bounds) == 2:
            first, last = map(int, bounds)
            if first > last:
                raise ValueError('reversed CPU range')
            cpus.update(range(first, last + 1))
        else:
            raise ValueError('invalid CPU mask')
    if not cpus or min(cpus) < 0:
        raise ValueError('invalid CPU mask')
    return sorted(cpus)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cpus-j1', default='0', help='one CPU on the measured host')
    parser.add_argument('--cpus-j4', default='0-3', help='four CPUs on the measured host')
    parser.add_argument('--expected-host', default='small-refmac-machine',
                        help='refuse to benchmark on any other hostname')
    args = parser.parse_args()
    hostname = platform.node()
    if hostname.split('.')[0] != args.expected_host.split('.')[0]:
        parser.error(f'refusing timing on {hostname!r}; expected {args.expected_host!r}')
    masks = {1: args.cpus_j1, 4: args.cpus_j4}
    for count, mask in masks.items():
        if len(expand_mask(mask)) != count:
            parser.error(f'j{count} mask must contain exactly {count} CPUs')
    args.binary = args.binary.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, OMP_DYNAMIC='false', OMP_PROC_BIND='close',
               OMP_PLACES='cores', OMP_WAIT_POLICY='PASSIVE', OPENBLAS_NUM_THREADS='1')
    manifest = {
        'scope': 'actual production streaming reconstruction vs frozen #178 separate-scan caller',
        'limitation': 'Stage-only paired experiment, not a complete movie or clean mcprof verdict. Caller must provide an exclusive measurement lane. Container and VM results must remain separate.',
        'hostname': hostname, 'expected_hostname': args.expected_host,
        'platform': platform.platform(),
        'parent_affinity': sorted(os.sched_getaffinity(0)),
        'pid_matches_proc_self': (read_optional('/proc/self/stat') or '').split()[:1] == [str(os.getpid())],
        'source': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        'binary': str(args.binary), 'binary_sha256': provenance.sha256_file(str(args.binary)),
        'cpu_max': read_optional('/sys/fs/cgroup/cpu.max'),
        'memory_max': read_optional('/sys/fs/cgroup/memory.max'),
        'lscpu': subprocess.check_output(['lscpu'], text=True),
        'environment': {k: env[k] for k in ('OMP_DYNAMIC', 'OMP_PROC_BIND', 'OMP_PLACES', 'OMP_WAIT_POLICY', 'OPENBLAS_NUM_THREADS')},
        'configurations': [],
    }
    with open('/tmp/motioncorr-bench.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if provenance.compilers_running():
            raise RuntimeError('finish builds before benchmarking')
        for nx, ny, count, threads, model in (
            (3710, 3838, 24, 1, 'polynomial'),
            (3710, 3838, 24, 4, 'polynomial'),
            (3710, 3838, 24, 4, 'null'),
            (3710, 3838, 7, 4, 'polynomial'),
        ):
            mask = masks[threads]
            probe = subprocess.check_output(['taskset', '-c', mask, sys.executable, '-c',
                'import os,json;print(json.dumps(sorted(os.sched_getaffinity(0))))'], text=True)
            affinity = json.loads(probe)
            if affinity != expand_mask(mask):
                raise RuntimeError('requested CPU affinity not established')
            name = f'{nx}x{ny}x{count}-j{threads}-{model}'
            command = ['taskset', '-c', mask, str(args.binary), str(nx), str(ny),
                       str(count), str(threads), '6', model]
            env['OMP_NUM_THREADS'] = str(threads)
            load = os.getloadavg()
            with (args.out / (name + '.jsonl')).open('w') as raw, (args.out / (name + '.stderr')).open('w') as errors:
                subprocess.run(command, stdout=raw, stderr=errors, env=env, check=True)
            rows = [json.loads(line) for line in (args.out / (name + '.jsonl')).read_text().splitlines()]
            if len(rows) != 7 or not all(r['bitwise_equal'] for r in rows):
                raise RuntimeError('paired output validation missing')
            measured = [r for r in rows if not r['warmup']]
            pairs = [{'a': r['baseline_seconds'], 'b': r['candidate_seconds'],
                      'order': 'AB' if r['pair'] % 2 == 0 else 'BA'} for r in measured]
            result = {'name': name, 'command': command, 'self_affinity': affinity,
                      'load_before': load, 'load_after': os.getloadavg(),
                      'baseline_median_s': stats.median([p['a'] for p in pairs]),
                      'candidate_median_s': stats.median([p['b'] for p in pairs]),
                      'paired_statistics': stats.paired(pairs)}
            manifest['configurations'].append(result)
            (args.out / 'results.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
            print(name, result['baseline_median_s'], result['candidate_median_s'],
                  result['paired_statistics']['verdict'], flush=True)
    if provenance.sha256_file(str(args.binary)) != manifest['binary_sha256']:
        raise RuntimeError('benchmark binary changed during experiment')


if __name__ == '__main__':
    main()
