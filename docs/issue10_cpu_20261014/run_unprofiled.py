#!/usr/bin/env python3
"""Bounded issue-10 CPU comparison for a PID-namespaced validation host.

Unlike mcprof, this cannot certify per-PID /proc ownership. It records that
limitation, checks taskset's lane from inside a child, and uses wait4 rusage.
No profile flag or diagnostic binary is used. Every measured pair is checked
with the existing strict profiling-kit product comparator.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/profiling'))
from lib import identity, provenance


def digest(path):
    return provenance.sha256_file(str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'candidate', 'data', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=6)
    parser.add_argument('--geometry', choices=('synthetic', 'tutorial'), required=True)
    parser.add_argument('--patch', type=int, choices=(1, 5), required=True)
    parser.add_argument('--threads', type=int, choices=(1, 4), required=True)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three matched repetitions are required')
    args.out.mkdir(parents=True, exist_ok=False)
    binaries = {arm: getattr(args, arm).resolve() for arm in ('base', 'candidate')}
    data = args.data.resolve()
    cpus = '0' if args.threads == 1 else '0-3'
    env = dict(os.environ, OMP_NUM_THREADS=str(args.threads), OMP_DYNAMIC='false',
               OMP_PROC_BIND='close', OMP_PLACES='cores', OPENBLAS_NUM_THREADS='1')
    movie = data / ('tutorial.tiff' if args.geometry == 'tutorial'
                    else 'synthetic_512x512_16frames.mrcs')
    inputs = [movie] + ([data / 'gain.mrc'] if args.geometry == 'tutorial' else [])
    manifest = {
        'instrument': 'unprofiled spawn-to-reap monotonic wall and wait4 rusage',
        'limitation': 'PID namespace disagrees with mounted /proc: per-PID image/ownership '
                      'and physical-host isolation are NOT certified; this is not a clean mcprof verdict',
        'platform': platform.platform(), 'cpu_mask': cpus,
        'cgroup_cpu_max': Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        'cgroup_memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        'environment': {k: env[k] for k in ('OMP_NUM_THREADS', 'OMP_DYNAMIC',
                                         'OMP_PROC_BIND', 'OMP_PLACES', 'OPENBLAS_NUM_THREADS')},
        'binaries': {arm: {'path': str(path), 'sha256': digest(path),
                           'source': provenance.source_for_binary(str(path))}
                     for arm, path in binaries.items()},
        'inputs': {str(path): digest(path) for path in inputs},
        'runs': [], 'comparisons': [],
    }
    probe = subprocess.run(['taskset', '-c', cpus, sys.executable, '-c',
                            'import os,json; print(json.dumps(sorted(os.sched_getaffinity(0))))'],
                           check=True, capture_output=True, text=True)
    expected = [0] if args.threads == 1 else [0, 1, 2, 3]
    manifest['taskset_self_affinity'] = json.loads(probe.stdout)
    if manifest['taskset_self_affinity'] != expected:
        raise RuntimeError('taskset did not establish the requested CPU lane')

    def save():
        (args.out / 'results.json').write_text(json.dumps(manifest, indent=2) + '\n')

    with open('/tmp/motioncorr-bench.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest['lock'] = '/tmp/motioncorr-bench.lock'
        if provenance.compilers_running():
            raise RuntimeError('compiler still running; finish builds before benchmarking')
        for rep in range(-1, args.repeats):
            trees = {}
            order = ('base', 'candidate') if rep % 2 == 0 or rep == -1 else ('candidate', 'base')
            for arm in order:
                out = (args.out / f'r{rep}-{arm}').resolve()
                trees[arm] = str(out)
                cmd = ['taskset', '-c', cpus, str(binaries[arm]), '--i', str(movie),
                       '--o', str(out), '--use_own', '--j', str(args.threads),
                       '--angpix', '0.885' if args.geometry == 'tutorial' else '1',
                       '--voltage', '300', '--bfactor', '150', '--seed', '1',
                       '--patch_x', str(args.patch), '--patch_y', str(args.patch)]
                if args.geometry == 'tutorial':
                    cmd += ['--gainref', str(data / 'gain.mrc')]
                if args.patch == 5:
                    cmd += ['--dose_weighting', '--dose_per_frame', '1.277',
                            '--save_noDW', '--even_odd_split']
                load = os.getloadavg()
                with (args.out / f'r{rep}-{arm}.log').open('w') as log:
                    start = time.monotonic()
                    child = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
                    _, status, usage = os.wait4(child.pid, 0)
                    wall = time.monotonic() - start
                    child.returncode = os.waitstatus_to_exitcode(status)
                manifest['runs'].append({
                    'rep': rep, 'warmup': rep == -1, 'arm': arm, 'command': cmd,
                    'rc': child.returncode, 'wall_s': wall,
                    'user_s': usage.ru_utime, 'sys_s': usage.ru_stime,
                    'peak_rss_kib': usage.ru_maxrss, 'load_before': load,
                    'load_after': os.getloadavg(),
                })
                save()
                if child.returncode:
                    raise RuntimeError(f'{arm} failed: {child.returncode}')
                print(args.geometry, args.patch, args.threads, rep, arm, wall, flush=True)
            comparison = identity.compare_trees(trees['base'], trees['candidate'])
            manifest['comparisons'].append({'rep': rep, **comparison})
            save()
            if not comparison['identical']:
                raise RuntimeError('strict product identity failed')


if __name__ == '__main__':
    main()
