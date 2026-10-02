#!/usr/bin/env python3
"""Default-off exactness control for the issue-97 port: base vs fixed, same backend.

Compares the MRC pixel payload from byte 1024 -- the MRC header carries a creation
timestamp, so a whole-file hash cannot answer this question -- and the per-movie STAR
line by line, reporting the whole-file line count as the denominator so no line can be
silently excluded from the comparison.

Usage: port_option_off_control.py <base-binary> <fixed-binary> <fixtures-dir>
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE, FIXED, FIXTURES = (Path(a).resolve() for a in sys.argv[1:4])
MOVIE = 'synthetic_128x128_8frames'
products = {}

for tree, binary in (('base', BASE), ('fixed', FIXED)):
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        for suffix in ('.mrcs', '.star'):
            shutil.copy(FIXTURES / (MOVIE + suffix), work / (MOVIE + suffix))
        for arm, extra in (('off', []), ('on', ['--interpolate_shifts'])):
            subprocess.run([str(binary), '--i', MOVIE + '.star', '--o', arm + '/',
                            '--use_own', '--j', '1', '--patch_x', '3', '--patch_y', '3',
                            '--angpix', '1', '--voltage', '300', '--dose_per_frame', '1',
                            '--first_frame_sum', '2', '--group_frames', '2', *extra],
                           cwd=work, check=True, capture_output=True, text=True, timeout=300)
            mrc = (work / arm / (MOVIE + '.mrc')).read_bytes()
            star = (work / arm / (MOVIE + '.star')).read_text().splitlines()
            products[(tree, arm)] = (hashlib.sha256(mrc[1024:]).hexdigest(),
                                     len(mrc) - 1024, star)

for arm in ('off', 'on'):
    b, f = products[('base', arm)], products[('fixed', arm)]
    assert len(b[2]) == len(f[2]), (len(b[2]), len(f[2]))
    differing = sum(1 for x, y in zip(b[2], f[2]) if x != y)
    verdict = 'IDENTICAL' if b[0] == f[0] else 'DIFFERS'
    print(f'option-{arm:3s}  MRC pixel payload ({b[1]} B): {verdict}   '
          f'per-movie STAR: {differing}/{len(b[2])} lines differ')
