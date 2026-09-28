#!/usr/bin/env python3
"""Regression guard for eliding the unused global inverse FFT (Issue #26).

The runner skips the inverse transform after global alignment when no consumer
reads the real-space frames. Correctness rests entirely on one predicate,
`need_real_space_before_dw`, matching the true consumer set. When it does not,
the failure is quiet: the dose-weighted micrograph still looks right because a
later transform recomputes it, only `_EVN.mrc`/`_ODD.mrc` are wrong, and the
wrong values come from an uninitialised buffer, so they vary between runs.

Five independent oracles, none of which needs a stored reference fixture:

  A. dose-weighting independence -- `_EVN`/`_ODD` are unweighted sums, so with
     the same selected frames they must not change when `--dose_weighting` is
     added. This is what fails if the predicate omits a consumer.
  B. determinism -- repeating the ELIDING configuration must reproduce identical
     bytes. It has to be that configuration: with --even_odd_split the predicate
     is true and nothing is elided, so a repeat there could not observe an
     elided buffer even in principle. Defence in depth only -- its power is NOT
     demonstrated (every negative control trips A, C or D first) and a large
     fresh allocation usually arrives zero-filled from the kernel, so it may
     never fire. Do not count it as coverage on its own.
  C. the predicate is not too broad -- `--patch_x 3` must not collapse onto the
     `--patch_x 1` result, which is what happens if the elision swallows the
     frames that patch clipping needs. The mechanism is that alignPatch fails to
     converge on an uninitialised buffer, each patch is skipped, and the motion
     model is then rejected for too few observations -- not that patches report
     zero shift. This one needs a movie that actually contains motion, so it
     uses the repository's synthetic fixture rather than the generated flat one,
     on which patch alignment legitimately finds nothing and the two would agree
     even on correct code. It is therefore also sensitive to the polynomial fit
     being accepted, which is why --bfactor is pinned below.

  D. the dose-weighted micrograph must not depend on `--save_noDW`, because
     those two invocations take opposite branches at the elision. Note what
     this oracle can and cannot see: the `.mrc` it compares is recomputed by
     the post-dose-weighting transform, so that comparison cannot be perturbed
     by any elision-predicate error. D's power against the predicate comes from
     its product-set assertions, not from its pixels.
  E. the unweighted micrograph must not depend on `--dose_weighting` -- oracle
     A's invariant applied to `_noDW.mrc`, the product `_EVN`/`_ODD` cannot
     reach. `keep` is the only arm where `save_noDW` alone makes
     `pre_dw_sum_needed` true, so without E, restating the elision guard so it
     drops `save_noDW` while the consumer at the sum keeps it -- the same
     copy-drift as the PR #57 case, one variable over -- corrupts `_noDW.mrc`
     and leaves every other oracle, and the rest of the suite, green.

Comparisons are on the full pixel payload and the core header. The product-set
assertions additionally check that each arm wrote exactly the products it asked
for and no others; oracle D's demonstrated power is one of those. The MRC label
area at offset 224 holds a strftime timestamp and is excluded; everything
before it is compared byte for byte.

What this does NOT guard: the existence of the optimisation. Nothing here
observes whether the transform was actually skipped, so reverting the elision to
an unconditional call leaves every oracle green. This is a correctness guard on
the predicate, not a performance guard -- deliberately, since no timing claim is
made anywhere in this change.
"""

import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import NFRAMES, read_mrc_pixels, write_movie, write_star

# Frame selection is pinned identically across every arm. Oracle A is only
# valid for matched selected frames: changing the selection legitimately
# changes the unweighted sums, which would look like a failure.
SELECTION = ['--first_frame_sum', '1', '--last_frame_sum', '6']
# Frame selection restricts which frames enter the sums; the global shift table
# still covers every frame in the movie, so that is what the STAR must report.
N_TRAJECTORY = NFRAMES


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
    assert rows == N_TRAJECTORY, (
        f'{tag}: STAR global shift table has {rows} frames, expected {N_TRAJECTORY}')


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


def same_across(a, ka, b, kb, left, right):
    """Compare one product against its counterpart under a different name."""
    assert ka in a, f'{left}: expected product {ka} was not written'
    assert kb in b, f'{right}: expected product {kb} was not written'
    px_a, hd_a = a[ka]
    px_b, hd_b = b[kb]
    assert len(px_a) == len(px_b), \
        f'{ka} vs {kb}: payload sizes differ, {left} vs {right}'
    if px_a != px_b:
        n = sum(x != y for x, y in zip(px_a, px_b))
        raise AssertionError(
            f'{ka} vs {kb}: {n} of {len(px_a)} pixel bytes differ '
            f'between {left} and {right}')
    assert hd_a == hd_b, f'{ka} vs {kb}: core header differs between {left} and {right}'


def test_global_ifft_elision(binary: Path = None):
    if binary is None:
        binary = Path(__file__).resolve().parent.parent / 'build' / 'motioncorr'
    # Resolve once: every invocation runs with cwd set to a temp dir, so a
    # relative --binary would otherwise be looked up in the wrong place.
    binary = Path(binary).resolve()
    if not binary.is_file():
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

        # --- Oracle D: the branch where the elision actually fires ----------
        # Without --even_odd_split and without --save_noDW the predicate is
        # false and the transform is skipped; adding --save_noDW makes it true.
        # The dose-weighted micrograph must be identical either way.
        elide = products(invoke(binary, work, star, 'elide', flat + dw), 'elide')

        # --- Oracle B: determinism, on the eliding configuration -------------
        # Repeating the arm that actually elides is the only repeat that could
        # ever see an uninitialised buffer. See the module docstring for why
        # this is defence in depth rather than demonstrated coverage.
        elide2 = products(invoke(binary, work, star, 'elide2', flat + dw), 'elide2')
        same(elide, elide2, ('.mrc',), 'eliding run 1', 'eliding run 2')

        keep = products(invoke(binary, work, star, 'keep',
                               flat + dw + ['--save_noDW']), 'keep')
        same(elide, keep, ('.mrc',), 'elided', 'not elided')
        assert '_noDW.mrc' not in elide, \
            'elided run wrote _noDW.mrc, which it was not asked for'
        assert '_noDW.mrc' in keep, '--save_noDW did not write _noDW.mrc'
        for absent in ('_EVN.mrc', '_ODD.mrc'):
            assert absent not in elide and absent not in keep, \
                f'{absent} appeared without --even_odd_split'

        # --- Oracle E: _noDW.mrc must not depend on --dose_weighting --------
        # Without dose weighting the unweighted sum IS the micrograph, so with
        # matched selected frames it must equal the _noDW.mrc of the weighted
        # run.
        #
        # Other tests do read _noDW.mrc pixels -- test_runner_contract.py:97
        # and :117 -- but both pass --even_odd_split, which holds
        # pre_dw_sum_needed true so the elision never fires there, and both
        # compare one binary against itself, so a uniform corruption cancels.
        # Neither can see this.
        #
        # The second comparison anchors on an --even_odd_split arm on purpose.
        # `plain` and `keep` can both be elided by a single restatement that
        # drops !do_dose_weighting and save_noDW together, and two buffers of
        # uninitialised heap may happen to agree; even_odd_split is a term of
        # pre_dw_sum_needed, so `eo_keep` cannot elide unless that term is
        # dropped too -- and oracle A catches that.
        plain = products(invoke(binary, work, star, 'plain', flat), 'plain')
        same_across(plain, '.mrc', keep, '_noDW.mrc',
                    'no dose weighting', 'dose weighted with --save_noDW')
        eo_keep = products(invoke(binary, work, star, 'eo_keep',
                                  flat + ['--even_odd_split', '--save_noDW'] + dw), 'eo_keep')
        same(eo_keep, keep, ('_noDW.mrc',),
             'even/odd split (cannot elide)', 'dose weighted with --save_noDW')

    # --- Oracle C: the predicate is not too broad --------------------------
    # If the elision also swallowed the frames patch clipping reads, alignPatch
    # fails to converge, the patches are skipped, the model is rejected for too
    # few observations, and --patch_x 3 collapses onto the --patch_x 1 answer.
    # The generated fixture above is motionless, so patch alignment finds
    # nothing there and the two agree even on correct code; this check therefore
    # uses the repository's synthetic movie, which carries real motion.
    movie = Path(__file__).resolve().parent.parent / 'test-data/synthetic/synthetic_movie.tiff'
    if not movie.is_file():
        raise FileNotFoundError(f'synthetic fixture not found at {movie}')
    with tempfile.TemporaryDirectory(prefix='ifft_elision_local_') as tmp:
        work = Path(tmp)
        # --bfactor is pinned: oracle C needs the 3x3 polynomial fit to survive
        # both validation gates (largest-delta and fit-RMSD), and a change to
        # the bfactor default would otherwise turn this into a spurious failure.
        common = ['--use_own', '--j', '1', '--seed', '1', '--skip_logfile',
                  '--voltage', '300', '--angpix', '1.0', '--bfactor', '150',
                  '--dose_weighting', '--dose_per_frame', '1.0']
        sums = {}
        for patch in ('1', '3'):
            out = work / f'p{patch}'
            res = subprocess.run(
                [str(binary), '--i', str(movie), '--o', str(out), *common,
                 '--patch_x', patch, '--patch_y', patch],
                cwd=work, text=True, capture_output=True, timeout=300)
            assert res.returncode == 0, res.stdout + res.stderr
            hits = list(out.glob('**/synthetic_movie.mrc'))
            assert len(hits) == 1, f'patch {patch}: expected 1 micrograph, got {len(hits)}'
            check_complete(hits[0], f'patch{patch}')
            sums[patch] = read_mrc_pixels(hits[0])
        assert sums['1'] != sums['3'], (
            'patch 3x3 reproduced the patch 1x1 result exactly on a movie that '
            'contains motion: local alignment contributed nothing, which is what '
            'an over-broad elision looks like')

    print('PASS: global inverse FFT elision preserves every product')
    print('  A dose-weighting independence of EVN/ODD  ok')
    print('  C patch alignment still contributes       ok')
    print('  D elided branch matches non-elided branch ok (product set;')
    print('                                                pixels cannot fail)')
    print('  E _noDW.mrc independent of --dose_weighting ok')
    print('  B determinism on the eliding arm          ok (defence in depth;')
    print('                                                power undemonstrated)')
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary', type=Path, default=None)
    args = ap.parse_args()
    sys.exit(0 if test_global_ifft_elision(args.binary) else 1)


if __name__ == '__main__':
    main()
