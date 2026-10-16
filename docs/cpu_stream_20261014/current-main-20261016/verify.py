#!/usr/bin/env python3
"""Current-main exact-product/RSS qualification. Run from archived candidate root."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools/profiling'))
# The archived runner can also be placed in the qualification workspace.
if not (Path(__file__).resolve().parents[3] / 'tools/profiling/lib').exists():
    sys.path.insert(0, '/home/ubuntu/fix178-20261016/candidate/tools/profiling')
from lib import identity


def digest(path, offset=0):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        f.seek(offset)
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def hashes(root):
    result = {}
    for rel in identity.inventory(str(root)):
        path = root / rel
        if path.suffix in ('.mrc', '.mrcs'):
            with path.open('rb') as f:
                header = f.read(1024)
            result[rel] = {'size': path.stat().st_size,
                           'payload_sha256': digest(path, 1024 + struct.unpack_from('<i', header, 92)[0]),
                           'normalized_header_sha256': hashlib.sha256(identity.normalise_mrc_header(header)).hexdigest()}
        elif path.suffix == '.star':
            result[rel] = {'root_normalized_sha256': hashlib.sha256(identity.normalise(path.read_bytes(), str(root))).hexdigest()}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('/home/ubuntu/fix178-20261016'))
    p.add_argument('--base-revision', required=True)
    p.add_argument('--candidate-revision', required=True)
    args = p.parse_args()
    root = args.root.resolve()
    evidence = root / 'evidence'
    evidence.mkdir(exist_ok=True)
    out = root / 'outputs'
    out.mkdir(exist_ok=True)
    inputs = {'tutorial': root / 'data/tutorial.tiff', 'gain': root / 'data/gain.mrc',
              'synthetic': root / 'candidate/test-data/fixtures/synthetic_128x128_8frames.mrcs'}
    results = {'base_revision': args.base_revision, 'candidate_revision': args.candidate_revision,
               'platform': platform.platform(), 'inputs': {str(k): digest(v) for k, v in inputs.items()},
               'binaries': {a: digest(root / a / 'build/motioncorr') for a in ('base', 'candidate')},
               'environment': {'GLIBC_TUNABLES': 'glibc.malloc.hugetlb=1', 'OMP_DYNAMIC': 'false',
                               'OMP_PROC_BIND': 'close', 'OMP_PLACES': 'cores', 'OPENBLAS_NUM_THREADS': '1'},
               'cpu_mask': '32-37', 'runs': [], 'comparisons': []}
    if (evidence / 'results.json').exists():
        previous = json.loads((evidence / 'results.json').read_text())
        assert previous['base_revision'] == args.base_revision
        assert previous['candidate_revision'] == args.candidate_revision
        results = previous
        results['inputs'].update({str(k): digest(v) for k, v in inputs.items()})
    env = dict(os.environ, **results['environment'])

    def save():
        (evidence / 'results.json').write_text(json.dumps(results, indent=2) + '\n')

    def run(fixture, patches, threads, config, rep=0, reverse=False):
        name = f'{fixture}-p{patches}-j{threads}-{config}-r{rep}'
        roots = {}
        if any(c['name'] == name and c['identical'] for c in results['comparisons']):
            return out / name / 'base', out / name / 'candidate'
        for arm in (('candidate', 'base') if reverse else ('base', 'candidate')):
            dest = out / name / arm
            assert not dest.exists(), dest
            roots[arm] = dest
            cmd = ['taskset', '-c', results['cpu_mask'], str(root / arm / 'build/motioncorr'),
                   '--i', str(inputs[fixture]), '--o', str(dest), '--use_own', '--j', str(threads),
                   '--angpix', '0.885' if fixture == 'tutorial' else '1.5', '--voltage', '300',
                   '--bfactor', '150', '--seed', '1', '--patch_x', str(patches), '--patch_y', str(patches)]
            if fixture == 'tutorial':
                cmd += ['--gainref', str(inputs['gain'])]
            if config != 'no-dose':
                cmd += ['--dose_weighting', '--dose_per_frame', '1.277']
            if config in ('noDW', 'split', 'odd-bin2', 'odd'):
                cmd += ['--save_noDW']
            if config in ('split', 'odd-bin2', 'odd'):
                cmd += ['--even_odd_split']
            if config in ('odd-bin2', 'odd'):
                cmd += ['--last_frame_sum', '23' if fixture == 'tutorial' else '7']
            if config == 'odd-bin2':
                cmd += ['--bin_factor', '2']
            timefile = evidence / f'{name}-{arm}.time'
            measured = ['/usr/bin/time', '-v', '-o', str(timefile)] + cmd
            with (evidence / f'{name}-{arm}.stdout').open('w') as log:
                rc = subprocess.run(measured, stdout=log, stderr=subprocess.STDOUT,
                                    env=dict(env, OMP_NUM_THREADS=str(threads))).returncode
            record = {'name': name, 'arm': arm, 'command': measured, 'exit': rc,
                      'OMP_NUM_THREADS': str(threads), 'time_file': timefile.name}
            if timefile.exists():
                for line in timefile.read_text().splitlines():
                    if 'Maximum resident set size (kbytes)' in line:
                        record['peak_rss_kib'] = int(line.rsplit(':', 1)[1])
            results['runs'].append(record)
            save()
            if rc:
                raise RuntimeError(f'{name}/{arm} exit {rc}')
        a, b = roots['base'], roots['candidate']
        comparison = identity.compare_trees(str(a), str(b))
        comparison.update(name=name, hashes={arm: hashes(path) for arm, path in roots.items()})
        results['comparisons'].append(comparison)
        save()
        if not comparison['identical']:
            raise RuntimeError(f'{name}: {comparison["problems"]}')
        print(name, 'PASS', flush=True)
        return a, b

    for patches in (1, 5):
        for threads in (1, 4):
            for config in ('default', 'noDW', 'split', 'odd-bin2'):
                run('synthetic', patches, threads, config)
    run('synthetic', 5, 4, 'no-dose')
    # Tutorial dimensions / 2 are odd, which main rejects; bin2 is exercised
    # on the seven-frame synthetic fixture, without changing that geometry gate.
    for config in ('default', 'noDW', 'split', 'odd'):
        run('tutorial', 5, 4, config)
    # Three matched, alternating pairs at full geometry, noDW + even/odd.
    run('tutorial', 5, 4, 'split', rep=1, reverse=True)
    a, b = run('tutorial', 5, 4, 'split', rep=2)
    # Flip one payload byte in place, demand failure, then restore original evidence.
    mrc = next(b.rglob('*.mrc'))
    with mrc.open('r+b') as f:
        header = f.read(1024)
        offset = 1024 + struct.unpack_from('<i', header, 92)[0]
        f.seek(offset)
        original = f.read(1)
        f.seek(offset)
        f.write(bytes([original[0] ^ 1]))
    try:
        control = identity.compare_trees(str(a), str(b))
        control['expected_exit'] = 1
        command = [sys.executable, '-c',
                   'import sys; from lib import identity; '
                   'sys.exit(0 if identity.compare_trees(sys.argv[1], sys.argv[2])["identical"] else 1)',
                   str(a), str(b)]
        control['command'] = command
        control['actual_exit'] = subprocess.run(command, env=dict(os.environ,
            PYTHONPATH=str(root / 'candidate/tools/profiling'))).returncode
        results['negative_control'] = control
        assert control['actual_exit'] == 1 and any('payload differs' in x['difference'] for x in control['differences'])
    finally:
        with mrc.open('r+b') as f:
            f.seek(offset)
            f.write(original)
        save()
    pairs = []
    for rep in range(3):
        name = f'tutorial-p5-j4-split-r{rep}'
        rr = {r['arm']: r['peak_rss_kib'] for r in results['runs'] if r['name'] == name}
        pairs.append(dict(rep=rep, **rr, saving_kib=rr['base'] - rr['candidate'],
                          saving_percent=100 * (rr['base'] - rr['candidate']) / rr['base']))
    results['rss_pairs'] = pairs
    results['exit'] = 0
    save()
    print(json.dumps(pairs, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
