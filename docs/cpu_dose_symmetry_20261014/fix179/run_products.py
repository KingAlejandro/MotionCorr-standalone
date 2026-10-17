#!/usr/bin/env python3
"""Untimed strict product checks on the assigned cpu64 CPUs 38-43."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--variant', choices=('release', 'fma'), required=True)
args = parser.parse_args()
root = args.root.resolve()
sys.path.insert(0, str(root / 'candidate/tools/profiling'))
from lib import identity

out = root / ('products-' + args.variant)
out.mkdir(exist_ok=False)
result = {'variant': args.variant, 'runs': [], 'comparisons': [], 'hashes': {}}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()

def save():
    (root / 'evidence' / ('products-' + args.variant + '.json')).write_text(json.dumps(result, indent=2) + '\n')

result['input_sha256'] = {p.name: file_sha(p) for p in (
    root / 'inputs/20170629_00021_frameImage.tiff', root / 'inputs/gain.mrc',
    root / 'inputs/synthetic_512x512_16frames.mrcs')}
for geometry in ('synthetic', 'tutorial'):
    movie = root / 'inputs' / ('20170629_00021_frameImage.tiff' if geometry == 'tutorial' else 'synthetic_512x512_16frames.mrcs')
    for patch in (1, 5):
        trees = {}
        for arm in ('base', 'candidate'):
            tree = out / f'{geometry}-p{patch}-{arm}'
            trees[arm] = tree
            binary = root / arm / ('build-fma' if args.variant == 'fma' else 'build') / 'motioncorr'
            command = [str(binary), '--i', str(movie), '--o', str(tree), '--use_own', '--j', '4',
                       '--angpix', '0.885' if geometry == 'tutorial' else '1',
                       '--voltage', '300', '--bfactor', '150', '--seed', '1',
                       '--patch_x', str(patch), '--patch_y', str(patch),
                       '--dose_weighting', '--dose_per_frame', '1.277', '--save_noDW', '--even_odd_split']
            if geometry == 'tutorial':
                command += ['--gainref', str(root / 'inputs/gain.mrc')]
            locked = ['taskset', '-c', '38-43', *command]
            env = dict(os.environ, OMP_NUM_THREADS='4', OMP_DYNAMIC='false', OPENBLAS_NUM_THREADS='1')
            with (root / 'evidence' / f'{args.variant}-{tree.name}.log').open('w') as log:
                rc = subprocess.run(locked, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
            result['runs'].append({'command': locked, 'exit_status': rc, 'binary_sha256': file_sha(binary)})
            save()
            if rc:
                raise SystemExit(rc)
            hashes = {}
            for path in sorted(tree.rglob('*')):
                if path.suffix not in ('.mrc', '.mrcs', '.star'):
                    continue
                data = path.read_bytes()
                if path.suffix in ('.mrc', '.mrcs'):
                    payload = 1024 + struct.unpack('<i', data[92:96])[0]
                    hashes[str(path.relative_to(tree))] = {
                        'payload_sha256': sha(data[payload:]),
                        'clock_normalised_file_sha256': sha(identity.normalise_mrc_header(data[:1024]) + data[1024:])}
                else:
                    hashes[str(path.relative_to(tree))] = {'root_normalised_sha256': sha(identity.normalise(data, str(tree)))}
            result['hashes'][tree.name] = hashes
        comparison = identity.compare_trees(str(trees['base']), str(trees['candidate']), expect_mrc=4)
        result['comparisons'].append({'geometry': geometry, 'patch': patch, **comparison})
        save()
        print(args.variant, geometry, patch, 'identical=', comparison['identical'], flush=True)
        if not comparison['identical']:
            raise SystemExit(1)

# Discriminating control: flip one byte of the primary dose-weighted MRC payload.
source = out / 'synthetic-p5-candidate'
negative = out / 'negative-control'
shutil.copytree(source, negative)
# Preserve root-normalised non-MRC text before comparing the copied tree.
for path in negative.rglob('*'):
    if path.is_file() and path.suffix not in ('.mrc', '.mrcs', '.pdf'):
        path.write_bytes(path.read_bytes().replace(str(source).encode(), str(negative).encode()))
mrc = next(p for p in negative.rglob('*.mrc') if not any(s in p.stem for s in ('noDW', 'EVN', 'ODD', 'even', 'odd')))
with mrc.open('r+b') as stream:
    header = stream.read(1024)
    offset = 1024 + struct.unpack('<i', header[92:96])[0]
    stream.seek(offset)
    old = stream.read(1)
    stream.seek(offset)
    stream.write(bytes([old[0] ^ 1]))
control = identity.compare_trees(str(source), str(negative), expect_mrc=4)
result['negative_control'] = {'mutated': str(mrc), 'payload_offset': offset,
                              'comparator_exit_status': 0 if control['identical'] else 1, **control}
save()
print('negative control comparator exit:', result['negative_control']['comparator_exit_status'], flush=True)
if control['identical'] or len(control['differences']) != 1 or 'payload differs' not in control['differences'][0]['difference']:
    raise SystemExit(1)
