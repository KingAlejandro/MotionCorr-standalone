#!/usr/bin/env python3
"""Regression guard for eliding the unused global inverse FFT (Issue #26).

The runner skips the inverse transform after global alignment when no consumer
reads the real-space frames. Correctness rests entirely on one predicate,
`need_real_space_before_dw`, matching the true consumer set. When it does not,
the failure is quiet: the dose-weighted micrograph still looks right because a
later transform recomputes it, only `_EVN.mrc`/`_ODD.mrc` are wrong, and the
wrong values come from an uninitialised buffer, so they vary between runs.

Three independent oracles, none of which needs a stored reference fixture:

  A. dose-weighting independence -- `_EVN`/`_ODD` are unweighted sums, so with
     the same selected frames they must not change when `--dose_weighting` is
     added. This is what fails if the predicate omits a consumer.
  B. determinism -- repeating an identical run must reproduce identical bytes.
     This targets the uninitialised buffer directly, so a single lucky pass of
     oracle A cannot carry the test.
  C. the predicate is not too broad -- `--patch_x 3` must not collapse onto the
     `--patch_x 1` result, which is what happens if the elision swallows the
     frames that patch clipping needs.

Oracle A is also exercised in the configuration where the elision actually
fires (no `--even_odd_split`, no `--save_noDW`), via oracle D: the dose-weighted
micrograph must not depend on `--save_noDW`, because those two invocations take
opposite branches at the elision.

Comparisons are on the full pixel payload and the core header, never on file
existence. The MRC label area at offset 224 holds a strftime timestamp and is
excluded; everything before it is compared byte for byte.
"""

import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star

# Frame selection is pinned identically across every arm. Oracle A is only
# valid for matched selected frames: changing the selection legitimately
# changes the unweighted sums, which would look like a failure.
SELECTION = ['--first_frame_sum', '1', '--last_frame_sum', '6']
N_SELECTED = 6


def core_header(path: Path) -> bytes:
    """Header bytes before the label area (offset 224), which is timestamped."""
    return path.read_bytes()[:224]


def check_complete(path: Path, tag: str):
    """A truncated or mode-wrong MRC must not be mistaken for a passing one."""
    data = path.read_bytes()
    assert len(data) >= 1024, f'{tag}: {path.name} shorter than an MRC header'
    nx, ny, nz, mode = struct.unpack('<4i', data[:16])
    assert mode == 2, f'{tag}: {path.name} mode {mode}, expected 2 (float32)'
    assert nx > 0 and ny > 0 and nz > 0, f'{tag}: {path.name} degenerate extent'
    expected = 1024 + nx * ny * nz * 4
    assert len(data) == expected, (
        f'{tag}: {path.name} is {len(data)} bytes, header declares {expected}')


def check_star_association(star: Path, movie: str, tag: str):
    """The per-movie STAR must name its own movie and carry a full shift table."""
    assert star.is_file(), f'{tag}: missing per-movie STAR {star}'
    text = star.read_text()
    assert '_rlnMicrographMovieName' in text, f'{tag}: STAR has no movie association'
    named = [ln.split()[-1] for ln in text.splitlines()
             if ln.strip().startswith('_rlnMicrographMovieName')]
    assert named and named[0].endswith(movie), (
        f'{tag}: STAR associates {named} rather than {movie}')
    rows = 0
    in_shift = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('data_global_shift'):
            in_shift = True
            continue
        if in_shift:
            if s.startswith('data_'):
                break
            parts = s.split()
            if len(parts) == 3 and parts[0].isdigit():
                rows += 1
    assert rows == N_SELECTED, (
        f'{tag}: STAR global shift table has {rows} frames, expected {N_SELECTED}')


def invoke(binary, work, star, out, extra=()):
    args = [str(binary), '--i', str(star), '--o', str(out), '--use_own',
            '--j', '1', '--seed', '1', '--skip_logfile', *SELECTION, *extra]
    res = subprocess.run(args, cwd=work, text=True, capture_output=True, timeout=300)
    assert res.returncode == 0, f'{out}: {res.stdout}\n{res.stderr}'
    return work / out


def products(out_dir: Path, tag: str, movie='a.mrc'):
    """Pixel payload + core header of every product, with completeness checked."""
    stem = movie[:-4]
    got = {}
    for suffix in ('.mrc', '_EVN.mrc', '_ODD.mrc', '_noDW.mrc'):
        p = out_dir / (stem + suffix)
        if p.is_file():
            check_complete(p, tag)
            got[suffix] = (read_mrc_pixels(p), core_header(p))
    check_star_association(out_dir / (stem + '.star'), movie, tag)
    return got


def same(a, b, keys, left, right):
    for k in keys:
        assert k in a, f'{left}: expected product {k} was not written'
        assert k in b, f'{right}: expected product {k} was not written'
        px_a, hd_a = a[k]
        px_b, hd_b = b[k]
        assert len(px_a) == len(px_b), f'{k}: payload sizes differ, {left} vs {right}'
        if px_a != px_b:
            n = sum(x != y for x, y in zip(px_a, px_b))
            raise AssertionError(
                f'{k}: {n} of {len(px_a)} pixel bytes differ between {left} and {right}')
        assert hd_a == hd_b, f'{k}: core header differs between {left} and {right}'


def test_global_ifft_elision(binary: Path = None):
    if binary is None:
        binary = Path(__file__).resolve().parent.parent / 'build' / 'motioncorr'
    if not Path(binary).is_file():
        raise FileNotFoundError(f'motioncorr binary not found at {binary}')

    with tempfile.TemporaryDirectory(prefix='ifft_elision_') as tmp:
        work = Path(tmp)
        write_movie(work / 'a.mrc', 23, None, [])
        star = work / 'movies.star'
        write_star(star, ['a.mrc'])

        flat = ['--patch_x', '1', '--patch_y', '1']
        dw = ['--dose_weighting', '--dose_per_frame', '1.0']

        # --- Oracle A: EVN/ODD must not depend on --dose_weighting ---------
        # The dose-weighted arm is the one that elides when the predicate is
        # wrong; the unweighted arm never elides, so it is the reference.
        eo_plain = products(invoke(binary, work, star, 'eo_plain',
                                   flat + ['--even_odd_split']), 'eo_plain')
        eo_dw = products(invoke(binary, work, star, 'eo_dw',
                                flat + ['--even_odd_split'] + dw), 'eo_dw')
        same(eo_plain, eo_dw, ('_EVN.mrc', '_ODD.mrc'),
             'no dose weighting', 'with dose weighting')

        # --- Oracle B: determinism -----------------------------------------
        # An elided buffer is uninitialised, so its contents can differ run to
        # run. Oracle A passing once is not evidence; this makes a lucky match
        # insufficient.
        eo_dw2 = products(invoke(binary, work, star, 'eo_dw2',
                                 flat + ['--even_odd_split'] + dw), 'eo_dw2')
        same(eo_dw, eo_dw2, ('.mrc', '_EVN.mrc', '_ODD.mrc'),
             'dose-weighted run 1', 'dose-weighted run 2')

        # --- Oracle D: the branch where the elision actually fires ----------
        # Without --even_odd_split and without --save_noDW the predicate is
        # false and the transform is skipped; adding --save_noDW makes it true.
        # The dose-weighted micrograph must be identical either way.
        elide = products(invoke(binary, work, star, 'elide', flat + dw), 'elide')
        keep = products(invoke(binary, work, star, 'keep',
                               flat + dw + ['--save_noDW']), 'keep')
        same(elide, keep, ('.mrc',), 'elided', 'not elided')
        assert '_noDW.mrc' not in elide, \
            'elided run wrote _noDW.mrc, which it was not asked for'
        assert '_noDW.mrc' in keep, '--save_noDW did not write _noDW.mrc'
        assert '_EVN.mrc' not in elide and '_EVN.mrc' not in keep, \
            'even/odd output appeared without --even_odd_split'

        # --- Oracle C: the predicate is not too broad -----------------------
        # If the elision also swallowed the frames patch clipping reads, every
        # patch would report zero shift and --patch_x 3 would collapse onto the
        # --patch_x 1 answer.
        local = products(invoke(binary, work, star, 'local',
                                ['--patch_x', '3', '--patch_y', '3'] + dw), 'local')
        assert local['.mrc'][0] != elide['.mrc'][0], (
            'patch 3x3 reproduced the patch 1x1 result exactly: local alignment '
            'contributed nothing, which is what an over-broad elision looks like')

    print('PASS: global inverse FFT elision preserves every product')
    print('  A dose-weighting independence of EVN/ODD  ok')
    print('  B run-to-run determinism                  ok')
    print('  C patch alignment still contributes       ok')
    print('  D elided branch matches non-elided branch ok')
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary', type=Path, default=None)
    args = ap.parse_args()
    sys.exit(0 if test_global_ifft_elision(args.binary) else 1)


if __name__ == '__main__':
    main()
