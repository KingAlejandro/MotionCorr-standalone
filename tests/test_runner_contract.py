#!/usr/bin/env python3
"""Small end-to-end regressions for movie selection and output completion."""
import argparse
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star


def invoke(binary, work, star, out, extra=(), success=True):
    args = [str(binary), '--i', str(star), '--o', str(out), '--use_own',
            '--j', '1', '--patch_x', '1', '--patch_y', '1', '--seed', '1',
            '--skip_logfile', *extra]
    result = subprocess.run(args, cwd=work, text=True, capture_output=True, timeout=60)
    if success:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def fixture(work):
    for index, name in enumerate(('a', 'b', 'c')):
        write_movie(work / (name + '.mrc'), 17 + index, None, [])
    star = work / 'movies.star'
    write_star(star, ['a.mrc', 'b.mrc', 'c.mrc'])
    return star


def exposure(binary, work):
    star = fixture(work)
    text = star.read_text().replace('_rlnOpticsGroup #2\n',
                                  '_rlnOpticsGroup #2\n_rlnMicrographPreExposure #3\n')
    for name, dose in [('a', 0), ('b', 5), ('c', 11)]:
        text = text.replace(f'{name}.mrc 1', f'{name}.mrc 1 {dose}')
    star.write_text(text)
    single = work / 'single.star'
    single.write_text(text.replace('a.mrc 1 0\n', '').replace('c.mrc 1 11\n', ''))
    options = ['--dose_weighting', '--preexposure', '3.5']
    invoke(binary, work, star, 'full', options)
    invoke(binary, work, single, 'resumed', options)
    completed = (work / 'resumed/b.mrc').read_bytes()
    invoke(binary, work, star, 'resumed', options + ['--only_do_unfinished'])
    assert (work / 'resumed/b.mrc').read_bytes() == completed, 'Completed non-prefix movie was rewritten'
    for name, dose in [('a', 3.5), ('b', 8.5), ('c', 14.5)]:
        fields = (work / f'resumed/{name}.star').read_text().split()
        actual = float(fields[fields.index('_rlnMicrographPreExposure') + 1])
        assert actual == dose, f'{name}: expected exposure {dose}, got {actual}'
        assert read_mrc_pixels(work / f'full/{name}.mrc') == read_mrc_pixels(work / f'resumed/{name}.mrc'), name


CASES = {'exposure': exposure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--case', choices=CASES, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='motioncorr-contract-') as directory:
        CASES[args.case](args.binary.resolve(), Path(directory))
    print(f'PASS runner {args.case}')


if __name__ == '__main__':
    main()
