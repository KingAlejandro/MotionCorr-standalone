#!/usr/bin/env python3
"""#226 D3: refuse below the Fourier-stack lower bound, then process movie b."""
import argparse
import os
import re
from pathlib import Path
import subprocess
import tempfile

from test_gain_cache import synthetic_frames, write_mrc, write_star, NX, NY
from run_stale_cuda_error_controls import products, compare_movie


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    binary = parser.parse_args().binary.resolve()
    with tempfile.TemporaryDirectory(prefix='mc-early-oom-') as temp:
        root = Path(temp)
        (root / 'Movies').mkdir()
        frames = synthetic_frames()
        for name in ('a', 'b'):
            write_mrc(root / f'Movies/{name}.mrcs', frames)
        write_star(root / 'reference.star', ['Movies/b.mrcs'])
        write_star(root / 'batch.star', ['Movies/a.mrcs', 'Movies/b.mrcs'])
        base_env = {k: v for k, v in os.environ.items()
                    if not k.startswith('MC_')}
        def run(star, output, env):
            return subprocess.run([str(binary), '--i', star, '--o', output + '/',
                                   '--use_own', '--gpu', '0', '--ingest', 'float',
                                   '--j', '1', '--seed', '1'], cwd=root, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=90)
        ref = run('reference.star', 'ref', base_env)
        if ref.returncode != 0:
            raise AssertionError(ref.stdout)
        expected, problems = products(root / 'ref', 'b')
        if problems:
            raise AssertionError(problems)
        fault = run('batch.star', 'out', dict(base_env, MC_FAULT_ORDINAL='1',
                                             MC_AVAILABLE_BYTES='1'))
        (root / 'fault.log').write_text(fault.stdout)
        required = len(frames) * NY * (NX // 2 + 1) * 8
        message = re.search(r'streaming global alignment requires at least (\d+) bytes; available 1 bytes', fault.stdout)
        if fault.returncode != 1 or not message or int(message[1]) < required:
            raise AssertionError(fault.stdout)
        if 'incompatible' in fault.stdout.lower():
            raise AssertionError('misleading incompatible-GPU diagnostic')
        for suffix in ('.mrc', '.star'):
            if (root / ('out/Movies/a' + suffix)).exists():
                raise AssertionError('failed movie published a product')
        if (root / 'out/corrected_micrographs.star').exists():
            raise AssertionError('failed batch published joint STAR')
        problems = compare_movie(root / 'out', 'b', expected)
        if problems:
            raise AssertionError(problems)
        print('PASS: early named OOM, no failed/joint products, next movie identical')


if __name__ == '__main__':
    main()
