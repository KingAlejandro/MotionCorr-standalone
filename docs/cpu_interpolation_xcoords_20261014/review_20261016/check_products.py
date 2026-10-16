#!/usr/bin/env python3
"""Correctness only: one 5x5-patch pair per fixture; no timing collection.

Run on the allocated cpu64 CPUs (taskset -c 44-49), without timing. Binary source SHAs are caller-attested;
archive/build commands and binary hashes in the accompanying evidence bind them.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys


def sha(path, offset=0):
    h = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'candidate', 'data', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('base', 'candidate'):
        p.add_argument('--' + name + '-source-sha', required=True)
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo / 'tools/profiling'))
    from lib import identity
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {'binaries': {}, 'inputs': {}, 'runs': [], 'comparisons': [], 'hashes': [],
               'scope': 'same-backend exact output, no timing or scientific-equivalence claim'}
    for arm in ('base', 'candidate'):
        binary = getattr(args, arm).resolve(strict=True)
        receipt['binaries'][arm] = {'path': str(binary), 'sha256': sha(binary),
                                  'source_sha': getattr(args, arm + '_source_sha')}
    for name in ('tutorial.tiff', 'gain.mrc', 'synthetic_512x512_16frames.mrcs'):
        receipt['inputs'][name] = sha(args.data / name)

    def save():
        (args.out / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')

    for fixture in ('synthetic', 'tutorial'):
        roots = {}
        for arm in ('base', 'candidate'):
            roots[arm] = (args.out / (fixture + '-' + arm)).resolve()
            movie = args.data / ('tutorial.tiff' if fixture == 'tutorial' else 'synthetic_512x512_16frames.mrcs')
            command = [receipt['binaries'][arm]['path'], '--i', str(movie), '--o', str(roots[arm]),
                       '--use_own', '--j', '4', '--angpix', '0.885' if fixture == 'tutorial' else '1',
                       '--voltage', '300', '--bfactor', '150', '--seed', '1',
                       '--patch_x', '5', '--patch_y', '5', '--dose_weighting',
                       '--dose_per_frame', '1.277', '--save_noDW', '--even_odd_split']
            if fixture == 'tutorial':
                command += ['--gainref', str(args.data / 'gain.mrc')]
            with (args.out / (fixture + '-' + arm + '.log')).open('w') as log:
                rc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                    env=dict(os.environ, OMP_DYNAMIC='false', OMP_NUM_THREADS='4',
                                             OPENBLAS_NUM_THREADS='1')).returncode
            receipt['runs'].append({'fixture': fixture, 'arm': arm, 'command': command, 'rc': rc})
            save()
            if rc:
                raise RuntimeError(f'{fixture}/{arm}: exit {rc}')
        comparison = identity.compare_trees(str(roots['base']), str(roots['candidate']))
        receipt['comparisons'].append(comparison)
        save()
        if not comparison['identical']:
            raise RuntimeError(f'{fixture}: exact comparison failed')
        for rel in identity.inventory(str(roots['base'])):
            suffix = Path(rel).suffix.lower()
            if suffix not in ('.mrc', '.mrcs', '.star'):
                continue
            hashes = {}
            for arm, root in roots.items():
                path = root / rel
                if suffix in ('.mrc', '.mrcs'):
                    with path.open('rb') as f:
                        header = f.read(1024)
                    offset = 1024 + struct.unpack('<i', header[92:96])[0]
                    hashes[arm] = {'payload_sha256': sha(path, offset),
                                   'canonical_file_sha256': hashlib.sha256(
                                       identity.normalise_mrc_header(header) + path.read_bytes()[1024:]).hexdigest()}
                else:
                    hashes[arm] = {'canonical_star_sha256': hashlib.sha256(
                        identity.normalise(path.read_bytes(), str(root))).hexdigest()}
            assert hashes['base'] == hashes['candidate'], (fixture, rel)
            receipt['hashes'].append({'fixture': fixture, 'file': rel, **hashes})
        # Discriminate: flip one payload bit, demand rejection, then restore it.
        if fixture == 'synthetic':
            rel = next(r for r in identity.inventory(str(roots['candidate'])) if r.endswith('.mrc'))
            path = roots['candidate'] / rel
            with path.open('r+b') as f:
                header = f.read(1024)
                offset = 1024 + struct.unpack('<i', header[92:96])[0]
                f.seek(offset)
                original = f.read(1)
                f.seek(offset)
                f.write(bytes([original[0] ^ 1]))
            try:
                negative = identity.compare_trees(str(roots['base']), str(roots['candidate']))
                receipt['negative_control'] = {'mutation': f'{rel}: XOR 1 at byte {offset}', **negative}
                save()
                if negative['identical']:
                    raise RuntimeError('payload mutant escaped comparator')
            finally:
                with path.open('r+b') as f:
                    f.seek(offset)
                    f.write(original)
        save()
    print('PASS two exact 5x5-patch trees; payload-bit negative control rejected')


if __name__ == '__main__':
    main()
