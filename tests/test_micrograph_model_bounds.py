#!/usr/bin/env python3
"""Saved-model bounds, sparse queries, and actual resume rejection (issue #67)."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def saved_model(*, width=8, height=6, frames=4, first=2, shifts=None,
                hotpixels=((0, 0), (7, 5)), local=False):
    if shifts is None:
        shifts = [(1, -9999, -9999), (2, 1.25, -2.5),
                  (3, 3.5, 7.25), (4, 8.0, -1.0)]
    text = (f"data_general\n\n_rlnImageSizeX {width}\n_rlnImageSizeY {height}\n"
            f"_rlnImageSizeZ {frames}\n_rlnMicrographMovieName movie.mrc\n"
            f"_rlnMicrographStartFrame {first}\n_rlnMicrographBinning 1\n"
            f"_rlnMotionModelVersion {int(local)}\n\n"
            "data_global_shift\n\nloop_\n_rlnMicrographFrameNumber #1\n"
            "_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n")
    text += ''.join(f'{frame} {x} {y}\n' for frame, x, y in shifts)
    if local:
        text += ("\ndata_local_motion_model\n\nloop_\n"
                 "_rlnMotionModelCoeffsIdx #1\n_rlnMotionModelCoeff #2\n")
        text += ''.join(f'{i} {2 if i == 0 else -4 if i == 18 else 0}\n'
                        for i in range(36))
    text += "\ndata_hot_pixels\n\nloop_\n_rlnCoordinateX #1\n_rlnCoordinateY #2\n"
    text += ''.join(f'{x} {y}\n' for x, y in hotpixels)
    return text


def run(helper, mode, path, arg='unused'):
    return subprocess.run([str(helper), mode, str(path), str(arg)],
                          text=True, capture_output=True, timeout=15)


def rejected(result, diagnostic, name):
    require(result.returncode == 1, f'{name}: expected clean exit 1, got '
            f'{result.returncode}\n{result.stdout}{result.stderr}')
    require(diagnostic in result.stderr, f'{name}: missing {diagnostic!r}: {result.stderr}')


def parser_and_queries(helper, work):
    valid = work / 'valid.star'
    valid.write_text(saved_model(local=True))
    require(run(helper, 'read', valid).returncode == 0, 'valid model rejected')
    # Local polynomial receives 0.5; the global component uses saved frame 2.
    result = run(helper, 'model_query', valid, '2.5')
    require(result.returncode == 0 and result.stdout.split() == ['0', '2.25', '-4.5'],
            f'fractional local/global query changed: {result.stdout}{result.stderr}')
    require(run(helper, 'model_mask', valid).stdout.strip() == '2', 'edge hot pixels lost')
    rewritten = work / 'roundtrip.star'
    require(run(helper, 'model_roundtrip', valid, rewritten).returncode == 0, 'write failed')
    result = run(helper, 'model_query', rewritten, '2.5')
    require(result.returncode == 0 and result.stdout.split() == ['0', '2.25', '-4.5'],
            'model round trip changed shifts')
    rejected(run(helper, 'model_mask', valid, 'invalid'), 'hot pixel out of range', 'in-memory mask')
    for frame in ('0', '-1', '0.5', '4.5', '5', 'nan', 'inf', '-inf', '1e100'):
        rejected(run(helper, 'model_query', valid, frame), 'frame out of range', f'query {frame}')

    # Missing leading, interior and trailing rows remain unobserved. Y-only
    # sentinels must return the nearest earlier shift with both axes observed.
    sparse = work / 'sparse.star'
    sparse.write_text(saved_model(shifts=[(3, 9, -9999), (2, 1.25, -2.5)]))
    for frame, expected in [('1', ['-1', '0', '0']), ('2', ['0', '1.25', '-2.5']),
                            ('3', ['-1', '1.25', '-2.5']), ('4', ['-1', '1.25', '-2.5'])]:
        result = run(helper, 'model_query', sparse, frame)
        require(result.returncode == 0 and result.stdout.split() == expected,
                f'sparse/Y-only query {frame}: {result.stdout}{result.stderr}')
    empty = work / 'unobserved.star'
    empty.write_text(saved_model(shifts=[(1, -9999, -9999), (4, -9999, -9999)]))
    result = run(helper, 'model_query', empty, '4')
    require(result.returncode == 0 and result.stdout.split() == ['-1', '0', '0'],
            'fully unobserved model changed')

    cases = []
    for key in ('width', 'height', 'frames'):
        for value in (0, -1, 4294967300):
            cases.append((f'{key}_{value}', {key: value}, 'invalid dimensions'))
    for value in (0, -1, 5, 4294967298):
        cases.append((f'first_{value}', {'first': value}, 'start frame out of range'))
    for value in (0, -1, 5, 4294967298):
        cases.append((f'frame_{value}', {'shifts': [(value, 1, 2)]}, 'frame out of range'))
    cases.append(('duplicate', {'shifts': [(2, 1, 2), (2, 3, 4)]}, 'duplicate global_shift'))
    for axis in (0, 1):
        for value in ('nan', 'inf', '-inf'):
            shift = [1, 2]
            shift[axis] = value
            cases.append((f'shift_{axis}_{value}', {'shifts': [(2, *shift)]}, 'Invalid floating-point STAR value'))
        for value in ('nan', 'inf', '-inf', -0.5, -1, 8 if axis == 0 else 6, 1e100):
            pixel = [1, 2]
            pixel[axis] = value
            diagnostic = ('Invalid floating-point STAR value' if value in ('nan', 'inf', '-inf')
                          else 'hot pixel out of range')
            cases.append((f'hotpixel_{axis}_{value}', {'hotpixels': [pixel]}, diagnostic))
    for name, settings, diagnostic in cases:
        path = work / (name + '.star')
        # Always parse a real local model first, covering constructor cleanup
        # when a later global-shift/hot-pixel table throws.
        path.write_text(saved_model(local=True, **settings))
        rejected(run(helper, 'read', path), diagnostic, name)
    print(f'PASS {len(cases)} malformed saved models; sparse, fractional, mask and round-trip controls')


def resume(binary, work):
    write_movie(work / 'movie.mrc', 17, None, [])
    write_star(work / 'movies.star', ['movie.mrc'])
    args = [str(binary), '--i', 'movies.star', '--use_own', '--j', '1',
            '--patch_x', '1', '--patch_y', '1', '--seed', '1', '--skip_logfile']

    def invoke(out, extra=()):
        result = subprocess.run([*args, '--o', out, *extra], cwd=work,
                                text=True, capture_output=True, timeout=30)
        require(result.returncode == 0, result.stdout + result.stderr)

    invoke('reference')
    original = (work / 'reference/movie.star').read_text()
    # Leave valid frames/MRCs in place. Only Micrograph's new hot-pixel check
    # can make the completion helper reject these corrupt completion records.
    for name, coordinate in [('edge', '96 0'), ('negative', '-1 0'), ('nan', '0 nan')]:
        out = work / name
        shutil.copytree(work / 'reference', out)
        replacement = ('data_hot_pixels\n\nloop_\n_rlnCoordinateX #1\n'
                       f'_rlnCoordinateY #2\n{coordinate}\n\n')
        start = original.find('data_hot_pixels')
        end = original.find('\ndata_', start + len('data_hot_pixels')) if start >= 0 else -1
        damaged = (original + '\n' + replacement if start < 0 else
                   original[:start] + replacement + (original[end:] if end >= 0 else ''))
        (out / 'movie.star').write_text(damaged)
        invoke(name, ['--only_do_unfinished'])
        require((out / 'movie.star').read_text() == original, f'{name}: corrupt STAR was resumed')
        require(read_mrc_pixels(out / 'movie.mrc') == read_mrc_pixels(work / 'reference/movie.mrc'),
                f'{name}: repair changed pixels')
        require((out / 'corrected_micrographs.star').read_bytes() ==
                (work / 'reference/corrected_micrographs.star').read_bytes().replace(
                    b'reference/', name.encode() + b'/'), f'{name}: joint metadata changed')
    products = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in out.glob('movie.*')}
    invoke(name, ['--only_do_unfinished'])
    require(products == {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in out.glob('movie.*')},
            'valid completed products were rewritten')
    print('PASS actual resume repairs invalid hot-pixel records; valid resume is unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    opts = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='micrograph-bounds-') as tmp:
        work = Path(tmp)
        parser_and_queries(opts.helper.resolve(), work)
        resume(opts.binary.resolve(), work)


if __name__ == '__main__':
    main()
