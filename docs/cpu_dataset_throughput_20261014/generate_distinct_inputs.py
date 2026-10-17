#!/usr/bin/env python3
"""Create four deterministic distinct 512x512x16 float fixtures in a NEW directory.

The source is read only. Never write to the earlier hardlinks or shared inputs.
These are generated scheduling/association controls, not experimental diversity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    a = parser.parse_args()
    if a.out.exists():
        parser.error('output must be a new directory')
    raw = a.source.read_bytes()
    nx, ny, nz, mode = struct.unpack_from('<4i', raw)
    if (nx, ny, nz, mode) != (512, 512, 16, 2):
        parser.error('source must be 512x512x16 little-endian mode-2 MRC')
    nsymbt, = struct.unpack_from('<i', raw, 92)
    if nsymbt < 0 or len(raw) != 1024 + nsymbt + nx * ny * nz * 4:
        parser.error('source has an invalid extended header or payload length')
    base = np.frombuffer(raw, dtype='<f4', offset=1024 + nsymbt).reshape(nz, ny, nx)
    if not np.isfinite(base).all():
        parser.error('source has nonfinite pixels')
    a.out.mkdir(parents=True)
    x = np.arange(nx, dtype=np.int32)[None, :]
    y = np.arange(ny, dtype=np.int32)[:, None]
    manifest = {'source': str(a.source.resolve()), 'source_sha256': digest(a.source),
                'recipe_sha256': digest(__file__), 'numpy_version': np.__version__,
                'shape_xyz': [nx, ny, nz], 'files': [],
                'recipe': 'movie k=0..3: scale base by float32(1+k/32); per frame z add float32((((x+3*y+5*z+11*k)%29)-14)*(k+1)/128), then float32(k/4); store float32 at each step'}
    for k in range(4):
        pixels = np.multiply(base, np.float32(1 + k / 32), dtype=np.float32)
        for z in range(nz):
            marker = ((x + 3 * y + 5 * z + 11 * k) % 29 - 14).astype(np.float32)
            pixels[z] += marker * np.float32((k + 1) / 128)
            pixels[z] += np.float32(k / 4)
        if not np.isfinite(pixels).all():
            raise RuntimeError('generated nonfinite pixels')
        header = bytearray(raw[:1024])
        struct.pack_into('<3f', header, 76, float(pixels.min()), float(pixels.max()),
                         float(pixels.mean(dtype=np.float64)))
        struct.pack_into('<f', header, 216, float(pixels.std(dtype=np.float64)))
        struct.pack_into('<i', header, 220, 1)
        header[224:1024] = bytes(800)
        label = f'MotionCorr CPU throughput generated fixture {k}, fixed recipe 2026-10-14'.encode()
        header[224:224 + len(label)] = label
        path = (a.out / f'generated{k}.mrcs').resolve()
        with path.open('xb') as stream:
            stream.write(header); stream.write(raw[1024:1024 + nsymbt])
            pixels.astype('<f4', copy=False).tofile(stream)
        payload_sha = hashlib.sha256(pixels.astype('<f4', copy=False).tobytes()).hexdigest()
        manifest['files'].append({'path': str(path), 'sha256': digest(path),
                                  'payload_sha256': payload_sha, 'index': k})
    if len({item['payload_sha256'] for item in manifest['files']}) != 4:
        raise RuntimeError('generated inputs are not distinct')
    star = (a.out / 'generated4.star').resolve()
    star.write_text('data_optics\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n'
                    '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n'
                    '_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
                    'one 1 1.0 300 2.7 0.1\n\ndata_movies\nloop_\n'
                    '_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n' +
                    ''.join(item['path'] + ' 1\n' for item in manifest['files']))
    manifest['star'] = {'path': str(star), 'sha256': digest(star)}
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
