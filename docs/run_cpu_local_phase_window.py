#!/usr/bin/env python3
"""Bounded CPU phase-window experiments; serialize with issue-10 bench lock.

Whole-movie runs here are single-pair product controls, not timing verdicts.
The default host guard restricts execution to the cpu64 VM. Hostname and child
affinity checks do not certify exclusive ownership of the physical host.
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools/profiling'))
from lib import identity, provenance


def cpu_list(value):
    """Parse Linux taskset list notation and return the exact allowed CPU IDs."""
    cpus = set()
    try:
        for part in value.split(','):
            ends = part.split('-')
            if len(ends) == 1:
                first = last = int(ends[0])
            elif len(ends) == 2:
                first, last = map(int, ends)
            else:
                raise ValueError
            if first < 0 or last < first:
                raise ValueError
            cpus.update(range(first, last + 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected nonnegative CPU IDs/ranges, e.g. 0 or 0,2,4,6') from exc
    if not cpus:
        raise argparse.ArgumentTypeError('CPU list must not be empty')
    return sorted(cpus)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('kernel', 'small-identity', 'tutorial-identity'))
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--bench', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expected-host', default='small-refmac-machine',
                        help='Required execution hostname (default: cpu64 VM small-refmac-machine)')
    parser.add_argument('--cpus-j1', default='0', help='taskset CPU list containing exactly one CPU')
    parser.add_argument('--cpus-j4', default='0-3', help='taskset CPU list containing exactly four CPUs')
    args = parser.parse_args()
    hostname = platform.node()
    if hostname != args.expected_host:
        parser.error(f'wrong execution host: expected {args.expected_host!r}, observed {hostname!r}')
    masks = {1: args.cpus_j1, 4: args.cpus_j4}
    expected_affinity = {}
    for threads, mask in masks.items():
        try:
            expected_affinity[threads] = cpu_list(mask)
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
        if len(expected_affinity[threads]) != threads:
            parser.error(f'j{threads} CPU list must contain exactly {threads} distinct CPU IDs')
    args.out.mkdir(parents=True, exist_ok=False)
    binaries = {arm: getattr(args, arm).resolve() for arm in ('base', 'candidate', 'bench')}
    inputs = [args.data / 'tutorial.tiff', args.data / 'gain.mrc'] if args.mode == 'tutorial-identity' else [args.data / 'synthetic_512x512_16frames.mrcs'] if args.mode == 'small-identity' else []
    manifest = {
        'mode': args.mode,
        'claim_limit': 'helper six paired samples only; whole movies are one-pair identity controls, not speed evidence',
        'host_limitation': 'hostname and child affinity checked; per-PID namespace ownership and physical-host isolation not certified by this driver',
        'expected_host': args.expected_host, 'actual_host': hostname,
        'cpu_masks': masks,
        'platform': platform.platform(),
        'source': provenance.source_for_binary(str(binaries['candidate'])),
        'binaries': {arm: {'path': str(path), 'sha256': provenance.sha256_file(str(path))} for arm, path in binaries.items()},
        'inputs': {str(path.resolve()): provenance.sha256_file(str(path)) for path in inputs},
        'cpu_max': Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        'memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        'runs': [], 'comparisons': [],
    }

    def save():
        (args.out / 'results.json').write_text(json.dumps(manifest, indent=2) + '\n')

    def run(binary, extra, tag, threads):
        mask = masks[threads]
        env = dict(os.environ, OMP_NUM_THREADS=str(threads), OMP_DYNAMIC='FALSE',
                   OMP_PROC_BIND='close', OMP_PLACES='cores', OMP_WAIT_POLICY='PASSIVE',
                   OPENBLAS_NUM_THREADS='1')
        probe = subprocess.check_output(['taskset', '-c', mask, sys.executable, '-c',
                                        'import os,json;print(json.dumps(sorted(os.sched_getaffinity(0))))'], text=True)
        affinity = json.loads(probe)
        if affinity != expected_affinity[threads]:
            raise RuntimeError('child CPU lane differs')
        cmd = ['taskset', '-c', mask, str(binary), *extra]
        with (args.out / f'{tag}.stdout.log').open('w') as stdout, (args.out / f'{tag}.stderr.log').open('w') as stderr:
            start = time.monotonic()
            child = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env)
            _, status, usage = os.wait4(child.pid, 0)
            wall = time.monotonic() - start
            child.returncode = os.waitstatus_to_exitcode(status)
        record = {'tag': tag, 'command': cmd, 'cpu_mask': mask, 'affinity_probe': affinity,
                  'environment': {k: env[k] for k in ('OMP_NUM_THREADS', 'OMP_DYNAMIC', 'OMP_PROC_BIND', 'OMP_PLACES', 'OMP_WAIT_POLICY', 'OPENBLAS_NUM_THREADS')},
                  'rc': child.returncode, 'diagnostic_wall_s': wall, 'peak_rss_kib': usage.ru_maxrss,
                  'user_s': usage.ru_utime, 'sys_s': usage.ru_stime}
        manifest['runs'].append(record)
        save()
        if child.returncode:
            raise RuntimeError(f'{tag} failed with status {child.returncode}')
        return record

    with open('/tmp/motioncorr-bench.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if provenance.compilers_running():
            raise RuntimeError('compiler still active; finish builds first')
        if args.mode == 'kernel':
            for threads in (1, 4):
                tag = f'kernel-j{threads}'
                record = run(binaries['bench'], ['--bench', str(threads)], tag, threads)
                rows = [json.loads(line) for line in (args.out / f'{tag}.stdout.log').read_text().splitlines()]
                if len(rows) != 6 or any(row['retained_complex_exact'] != 446976 for row in rows):
                    raise RuntimeError('kernel did not emit six exact paired comparisons')
                record['pairs'] = rows
                save()
        else:
            tutorial = args.mode == 'tutorial-identity'
            configs = [(5, 4)] if tutorial else [(p, j) for p in (1, 3) for j in (1, 4)]
            movie = args.data / ('tutorial.tiff' if tutorial else 'synthetic_512x512_16frames.mrcs')
            for patch, threads in configs:
                outputs = {}
                for arm in ('base', 'candidate'):
                    tag = f'patch{patch}-j{threads}-{arm}'
                    out = (args.out / tag).resolve()
                    outputs[arm] = out
                    extra = ['--i', str(movie.resolve()), '--o', str(out), '--use_own', '--j', str(threads),
                             '--angpix', '0.885' if tutorial else '1', '--voltage', '300', '--bfactor', '150',
                             '--seed', '1', '--patch_x', str(patch), '--patch_y', str(patch), '--group_frames', '5',
                             '--dose_weighting', '--dose_per_frame', '1.277', '--save_noDW', '--even_odd_split']
                    if tutorial:
                        extra += ['--gainref', str((args.data / 'gain.mrc').resolve())]
                    run(binaries[arm], extra, tag, threads)
                comparison = identity.compare_trees(str(outputs['base']), str(outputs['candidate']), expect_mrc=4)
                manifest['comparisons'].append({'patch': patch, 'threads': threads, **comparison})
                save()
                if not comparison['identical']:
                    raise RuntimeError('strict product identity failed')


if __name__ == '__main__':
    main()
