#!/usr/bin/env python3
"""Per-assertion outcome and margin for the issue-97 end-to-end case, base vs fixed.

Runs the option-off and option-on arms with each binary and reports, for every
assertion in tests/test_runner_contract.py's interpolate_shifts case, how many of the
9 patches x 2 axes observations violate it -- and, for the three that discriminate,
the magnitude distribution of the violation against the tolerance the test uses.

The minimum margin matters more than the maximum: it is the weakest observation the
detectors are asked to resolve.

Usage: port_assertion_margins.py <base-binary> <fixed-binary> <fixtures-dir> <tests-dir>
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE, FIXED, FIXTURES, TESTS = (Path(a).resolve() for a in sys.argv[1:5])
sys.path.insert(0, str(TESTS))
from test_runner_contract import read_local_shifts, STAR_TOLERANCE  # noqa: E402

MOVIE = 'synthetic_128x128_8frames'


def arms(binary):
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        for suffix in ('.mrcs', '.star'):
            shutil.copy(FIXTURES / (MOVIE + suffix), work / (MOVIE + suffix))
        out = {}
        for arm, extra in (('off', []), ('on', ['--interpolate_shifts'])):
            subprocess.run([str(binary), '--i', MOVIE + '.star', '--o', arm + '/',
                            '--use_own', '--j', '1', '--patch_x', '3', '--patch_y', '3',
                            '--angpix', '1', '--voltage', '300', '--dose_per_frame', '1',
                            '--first_frame_sum', '2', '--group_frames', '2', *extra],
                           cwd=work, check=True, capture_output=True, text=True, timeout=300)
            out[arm] = read_local_shifts(work / arm / (MOVIE + '.star'))
        return out['on'], out['off']


def spread(values):
    return f'min {min(values):.6f}  max {max(values):.6f}'


def margins(values):
    lo, hi = min(values) / STAR_TOLERANCE, max(values) / STAR_TOLERANCE
    return f'{lo:.0f}x .. {hi:.0f}x the tolerance'


print(f'tolerance asserted by the test: {STAR_TOLERANCE:g}')
for label, binary in (('BASE  (unfixed)', BASE), ('FIXED', FIXED)):
    on, off = arms(binary)
    n = len(on)
    counts = {}
    detect = {'cross-arm anchor frame 3': [], 'cross-arm anchor frame 5': [],
              'segment linearity': []}
    steps = {0: [], 1: []}
    counts['frame numbers [2..8]'] = sum(sorted(on[p]) != [2, 3, 4, 5, 6, 7, 8] for p in on)
    counts['off-arm group layout [3,5,7]'] = sum(sorted(off[p]) != [3, 5, 7] for p in on)
    counts['value at first selected frame is 0'] = sum(on[p][2] != (0.0, 0.0) for p in on)
    for p in on:
        for ax in (0, 1):
            detect['cross-arm anchor frame 3'].append(abs(on[p][3][ax] - off[p][3][ax]))
            detect['cross-arm anchor frame 5'].append(abs(on[p][5][ax] - off[p][5][ax]))
            step = on[p][3][ax] - on[p][2][ax]
            steps[ax].append(abs(step))
            detect['segment linearity'].append(abs(on[p][4][ax] - on[p][3][ax] - step))
    print(f'\n{label}   {n} patches, {2 * n} patch-axis observations')
    print('  coverage assertions (these hold on both builds by design):')
    for name, bad in counts.items():
        print(f'    {name:44s} violations {bad}/{n}')
    print('  detectors:')
    for name, vals in detect.items():
        bad = sum(v > (0.0 if name.endswith('frame 3') else STAR_TOLERANCE) for v in vals)
        print(f'    {name:44s} violations {bad}/{len(vals)}   {spread(vals)}')
        if bad:
            print(f'    {"":44s} violating by {margins([v for v in vals if v > 0])}')
    for ax, axis in ((0, 'X'), (1, 'Y')):
        over = sum(s >= 100 * STAR_TOLERANCE for s in steps[ax])
        print(f'  first-segment step {axis}: {spread(steps[ax])}   '
              f'{over}/{n} patches clear the 100x floor')
