#!/usr/bin/env python3
"""Small end-to-end regressions for movie selection and output completion."""
import argparse
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star

FIXTURES = Path(__file__).resolve().parents[1] / 'test-data' / 'fixtures'
# MetaDataTable serialises a shift of this magnitude as "%12.6f" when positive and
# "%12.5f" when negative (src/metadata_table.cpp:266-277), so each value carries up to
# 5e-6 of rounding. The linearity residual below is s(4) - 2*s(3) + s(2), which weights
# four such errors, giving a 2e-5 bound; 3e-5 leaves headroom above it.
STAR_TOLERANCE = 3e-5


def read_local_shifts(star):
    """Parse data_local_shift into {(patch_x, patch_y): {frame: (shift_x, shift_y)}}."""
    labels, patches, in_block = [], {}, False
    for line in star.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith('#'):
            continue
        if fields[0].startswith('data_'):
            in_block = fields[0] == 'data_local_shift'
            labels = []
            continue
        if not in_block or fields[0] == 'loop_':
            continue
        if fields[0].startswith('_rln'):
            labels.append(fields[0])
            continue
        assert len(fields) == len(labels), (labels, fields)
        row = dict(zip(labels, fields))
        key = (float(row['_rlnCoordinateX']), float(row['_rlnCoordinateY']))
        frame = int(row['_rlnMicrographFrameNumber'])
        patch_frames = patches.setdefault(key, {})
        assert frame not in patch_frames, f'duplicate local-shift row for patch {key}, frame {frame}'
        patch_frames[frame] = (
            float(row['_rlnMicrographShiftX']), float(row['_rlnMicrographShiftY']))
    return patches


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
    text = star.read_text().replace('_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n',
                                  '_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n_rlnMicrographPreExposure #3\n')
    for name, dose in [('a', 0), ('b', 5), ('c', 11)]:
        text = text.replace(f'{name}.mrc 1', f'{name}.mrc 1 {dose}')
    star.write_text(text)
    single = work / 'single.star'
    single.write_text(text.replace('a.mrc 1 0\n', '').replace('c.mrc 1 11\n', ''))
    options = ['--write_resume_receipts', '--dose_weighting', '--preexposure', '3.5']
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


def failure(binary, work):
    star = fixture(work)
    # A readable but two-frame movie takes the native false-return path.
    short = bytearray((work / 'b.mrc').read_bytes())
    struct.pack_into('<i', short, 8, 2)
    (work / 'b.mrc').write_bytes(short[:1024 + 96 * 96 * 2 * 4])
    result = invoke(binary, work, star, 'failed', success=False)
    assert result.returncode != 0, 'A failed movie must fail the command'
    assert 'b.mrc' in result.stderr and 'failed' in result.stderr.lower()
    for name in ['a', 'c']:
        assert (work / f'failed/{name}.mrc').exists(), 'Successful movies must be retained'
        assert (work / f'failed/{name}.star').exists()
    assert not (work / 'failed/b.star').exists()
    assert not (work / 'failed/corrected_micrographs.star').exists()


def invalid(binary, work):
    star = fixture(work)
    for flag in ['--group_frames', '--eer_grouping', '--j', '--max_io_threads']:
        result = invoke(binary, work, star, 'invalid', [flag, '0'], success=False)
        assert result.returncode != 0, flag
        assert flag + ' must be positive' in result.stderr, result.stderr
        assert not (work / 'invalid/a.star').exists()


def resume(binary, work):
    star = fixture(work)
    single = work / 'single.star'
    write_star(single, ['a.mrc'])
    options = ['--write_resume_receipts', '--dose_weighting', '--save_noDW', '--even_odd_split',
               '--grouping_for_ps', '2', '--ps_size', '48']
    invoke(binary, work, single, 'reference', options)
    for suffix in ['.mrc', '.star', '_noDW.mrc', '_EVN.mrc', '_ODD.mrc', '_PS.mrc']:
        for damage in ['missing', 'truncated']:
            out = work / 'resume'
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(work / 'reference', out)
            damaged = out / ('a' + suffix)
            if damage == 'missing':
                damaged.unlink()
            else:
                damaged.write_bytes(damaged.read_bytes()[:1030 if suffix != '.star' else 120])
            invoke(binary, work, single, 'resume', options + ['--only_do_unfinished'])
            for image_suffix in ['.mrc', '_noDW.mrc', '_EVN.mrc', '_ODD.mrc', '_PS.mrc']:
                assert read_mrc_pixels(out / ('a' + image_suffix)) == read_mrc_pixels(work / 'reference' / ('a' + image_suffix)), (suffix, damage, image_suffix)
            assert (out / 'a.star').read_text() == (work / 'reference/a.star').read_text()
    # A complete movie is skipped, including its metadata and optional outputs.
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in out.glob('a.*')}
    invoke(binary, work, single, 'resume', options + ['--only_do_unfinished'])
    assert before == {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in out.glob('a.*')}
    # Even/odd output is requested independently of saving the unweighted sum.
    invoke(binary, work, single, 'split', ['--dose_weighting', '--even_odd_split'])
    for suffix in ['.mrc', '_EVN.mrc', '_ODD.mrc', '.star']:
        assert (work / ('split/a' + suffix)).exists(), suffix
    assert not (work / 'split/a_noDW.mrc').exists()


def late_bin(binary, work):
    fixture(work)
    star = work / 'single.star'
    write_star(star, ['a.mrc'])
    for name, options, suffixes in [
        ('unweighted', ['--even_odd_split'], ['.mrc', '_EVN.mrc', '_ODD.mrc']),
        ('weighted', ['--dose_weighting', '--save_noDW', '--even_odd_split'],
         ['.mrc', '_noDW.mrc', '_EVN.mrc', '_ODD.mrc'])]:
        invoke(binary, work, star, 'full_' + name, options)
        invoke(binary, work, star, 'binned_' + name, options + ['--no_early_binning', '--bin_factor', '2'])
        for suffix in suffixes:
            subprocess.run([str(HELPER), 'bin', str(work / ('full_' + name) / ('a' + suffix)),
                            str(work / ('binned_' + name) / ('a' + suffix))], check=True)


def exported_units(binary, work):
    fixture(work)
    (work / 'export').mkdir()
    subprocess.run([str(HELPER), 'model', 'a.mrc', 'export/'], cwd=work, check=True)


def tomography(binary, work):
    fixture(work)
    star = work / 'tomograms.star'
    star.write_text('data_global\n\nloop_\n_rlnTomoName #1\n'
                    '_rlnTomoTiltSeriesStarFile #2\n_rlnMicrographOriginalPixelSize #3\n'
                    '_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
                    'tomo1 tilts.star 1.0 300 2.7 0.1\n')
    (work / 'tilts.star').write_text('data_tomo1\n\nloop_\n_rlnMicrographMovieName #1\n'
                                   '_rlnMicrographPreExposure #2\nc.mrc 11\na.mrc 0\nb.mrc 5\n')
    options = ['--write_resume_receipts', '--dose_weighting', '--preexposure', '3.5', '--even_odd_split', '--save_noDW']
    invoke(binary, work, star, 'full', options)
    original = (work / 'b.mrc').read_bytes()
    short = bytearray(original[:1024 + 96 * 96 * 2 * 4])
    struct.pack_into('<i', short, 8, 2)
    (work / 'b.mrc').write_bytes(short)
    failed = invoke(binary, work, star, 'resume', options, success=False)
    assert failed.returncode != 0
    assert (work / 'resume/a.star').exists() and (work / 'resume/c.star').exists()
    (work / 'b.mrc').write_bytes(original)
    invoke(binary, work, star, 'resume', options + ['--only_do_unfinished'])
    for name in ['a', 'b', 'c']:
        for suffix in ['.mrc', '_EVN.mrc', '_ODD.mrc']:
            assert read_mrc_pixels(work / ('full/' + name + suffix)) == read_mrc_pixels(work / ('resume/' + name + suffix)), name
        assert (work / f'full/{name}.star').read_text() == (work / f'resume/{name}.star').read_text(), name
    tilt_files = [p for p in (work / 'resume').rglob('*.star') if 'data_tomo1' in p.read_text()]
    assert len(tilt_files) == 1
    labels, exposures = [], {}
    for line in tilt_files[0].read_text().splitlines():
        values = line.split()
        if not values or values[0].startswith('#'):
            continue
        if values[0].startswith('_rln'):
            labels.append(values[0])
        elif len(values) == len(labels) and '_rlnMicrographName' in labels:
            name = Path(values[labels.index('_rlnMicrographName')]).stem
            exposures[name] = float(values[labels.index('_rlnMicrographPreExposure')])
    assert exposures == {'a': 0, 'b': 5, 'c': 11}, exposures


def model_parser(binary, work):
    fixture(work)
    (work / 'export').mkdir()
    subprocess.run([str(HELPER), 'write_model', 'a.mrc', 'export/'], cwd=work, check=True)
    original = (work / 'export/a.star').read_text().splitlines()
    start = original.index('data_local_motion_model')
    first = next(i for i in range(start + 1, len(original)) if original[i].split() and original[i].split()[0] == '0')
    accepted = []
    for problem in ['duplicate', 'nonfinite', 'truncated', 'negative_index', 'trailing', 'invalid_index', 'missing_coefficient']:
        lines = original.copy()
        if problem == 'truncated':
            del lines[first]
        elif problem == 'missing_coefficient':
            lines[first + 35] = '35'
        else:
            fields = lines[first].split()
            if problem == 'duplicate':
                fields[0] = '1'
            elif problem == 'nonfinite':
                fields[1] = 'nan'
            elif problem == 'trailing':
                fields[1] += 'junk'
            elif problem == 'invalid_index':
                fields[0] = 'garbage'
            else:
                fields[0] = '-1'
            lines[first] = ' '.join(fields)
        malformed = work / (problem + '.star')
        malformed.write_text('\n'.join(lines) + '\n')
        result = subprocess.run([str(HELPER), 'read', str(malformed), 'unused'], capture_output=True, text=True)
        print(problem, 'accepted' if result.returncode == 0 else 'rejected')
        if result.returncode == 0:
            accepted.append(problem)
    assert not accepted, f'Invalid local model accepted: {accepted}'
    legacy = work / 'legacy_mtf.star'
    legacy.write_text('data_optics\n\nloop_\n_rlnOpticsGroup #1\n_rlnMtfFileName #2\n1\n\n')
    subprocess.run([str(HELPER), 'legacy_mtf', str(legacy), 'unused'], check=True)
    print('legacy empty trailing string preserved')


def interpolate_shifts(binary, work, gpu=None):
    """Issue #97: --interpolate_shifts recentered against an origin it had already zeroed.

    Drives the real binary rather than the helper, so it covers the parts the unit
    regression cannot reach: --first_frame_sum > 1, the unequal final group the
    remainder distribution produces, and interpolated origins that are nonzero on both
    axes because the fixture moves in X and Y.

    8 frames with --first_frame_sum 2 select original frames 2..8, so n_frames = 7;
    --group_frames 2 gives n_groups = 3 and hands the remainder to the last group,
    producing sizes {2,2,3}, starts {0,2,4} and centres {1,3,5.5}.

    Two assertions below discriminate against the defect: the cross-arm anchor equality
    and the segment linearity. The frame numbering, the group layout and the zero at the
    first selected frame are coverage of the configuration, not detectors -- the original
    code satisfies all three, and in particular it is the code that manufactures the zero.
    """
    for name in ('synthetic_128x128_8frames.mrcs', 'synthetic_128x128_8frames.star'):
        shutil.copy(FIXTURES / name, work / name)
    duplicate = work / 'duplicate_local_shift.star'
    duplicate.write_text('''data_local_shift

loop_
_rlnCoordinateX #1
_rlnCoordinateY #2
_rlnMicrographFrameNumber #3
_rlnMicrographShiftX #4
_rlnMicrographShiftY #5
0 0 2 1.0 2.0
0 0 2 1.0 2.0
''')
    try:
        read_local_shifts(duplicate)
    except AssertionError as error:
        assert 'duplicate local-shift row' in str(error), error
    else:
        raise AssertionError('duplicate local-shift rows must not be silently overwritten')
    trailing_block = work / 'local_shift_with_receipt.star'
    trailing_block.write_text(duplicate.read_text().split('0 0 2 1.0 2.0')[0] +
                             '0 0 2 1.0 2.0\n\n# version 50001\n\n' +
                             'data_motioncorr_processing\n_rlnMotioncorrProcessingVersion 1\n')
    assert read_local_shifts(trailing_block) == {(0.0, 0.0): {2: (1.0, 2.0)}}, (
        'following STAR block/comment changed local shift parsing')
    arms = {}
    backend = [] if gpu is None else ['--gpu', str(gpu)]
    for arm, extra in (('off', []), ('on', ['--interpolate_shifts'])):
        result = subprocess.run([str(binary), '--i', 'synthetic_128x128_8frames.star',
                                 '--o', arm + '/', '--use_own', '--j', '1',
                                 '--patch_x', '3', '--patch_y', '3', '--angpix', '1',
                                 '--voltage', '300', '--dose_per_frame', '1',
                                 '--first_frame_sum', '2', '--group_frames', '2', *backend, *extra],
                                cwd=work, text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        log = (work / arm / 'synthetic_128x128_8frames.log').read_text()
        # The runner states the selection and the grouping it actually used.
        assert 'Frames to be used: 2 3 4 5 6 7 8' in log, log
        assert ' | 2 3 | 4 5 | 6 7 8 | ' in log, 'unequal final group not reached: ' + log
        assert f'interpolate_shifts = {int(arm == "on")}' in log, log
        if gpu is not None:
            # An accepted --gpu flag alone does not prove that the local shifts
            # came from native CUDA rather than the CPU fallback.
            assert log.count('[CUDA Patch Alignment] completed; converged=yes') == 9, log
            assert '[CUDA Patch Alignment] completed; converged=no' not in log, log
        arms[arm] = read_local_shifts(work / arm / 'synthetic_128x128_8frames.star')

    on, off = arms['on'], arms['off']
    # An empty block here means fitting was skipped before the rows were pushed --
    # fewer than 19 converged observations, or a local model that failed the
    # neighbouring-pixel check -- not that a shift was wrong. The fit-RMSD gate cannot
    # cause it; that one only zeroes the localFit columns.
    assert len(on) == 9 and set(on) == set(off), (
        'expected 9 patches in both arms', sorted(on), sorted(off))

    steps_over_floor = {0: 0, 1: 0}
    for patch, frames in sorted(on.items()):
        # Serialised frame numbers are original 1-indexed frames, so --first_frame_sum
        # must shift the whole per-frame field, not just its first entry.
        assert sorted(frames) == [2, 3, 4, 5, 6, 7, 8], (patch, sorted(frames))
        # Group centres 1 and 3 are integral, so they land on frames 3 and 5; 5.5 is
        # truncated to 7 on write. That triple is unique to the {2,2,3} layout --
        # {2,3,2} would put the centres at frames 3, 5 and 8.
        assert sorted(off[patch]) == [3, 5, 7], (patch, sorted(off[patch]))
        # Shape check on the recentering anchor. NOT defect coverage: the original
        # code sets frame 0 to zero too, which is exactly how it loses the origin.
        assert frames[2] == (0.0, 0.0), (patch, frames[2])

        for axis in (0, 1):
            # The interpolated field passes through its anchors and both branches
            # subtract the same first-frame origin, so at an integral group centre the
            # two arms must agree. The original code fails here by exactly the origin it
            # discarded. At frame 3 (centre 1) this is bit-identical: alignPatch leaves
            # the first group shift at exactly +0.0, so interp(1) reduces to (0*2 + x1*0)/2
            # and both arms then evaluate the same subtraction. Frame 5 (centre 3) goes
            # through (x1*2.5)/2.5, which need not round back to x1, so it is only equal
            # to within serialisation rounding.
            assert frames[3][axis] == off[patch][3][axis], (
                patch, axis, frames[3][axis], off[patch][3][axis])
            assert abs(frames[5][axis] - off[patch][5][axis]) <= STAR_TOLERANCE, (
                patch, axis, frames[5][axis], off[patch][5][axis])
            # Frames 0, 1 and 2 of the selection all sit in the first interpolation
            # segment (cur_group only advances at iframe >= centre 3), so the
            # recentered field is linear across original frames 2, 3 and 4. The
            # original code broke that line by the discarded origin at frame 3.
            step = frames[3][axis] - frames[2][axis]
            residual = abs(frames[4][axis] - frames[3][axis] - step)
            assert residual <= STAR_TOLERANCE, (patch, axis, residual, step)
            if abs(step) >= 100 * STAR_TOLERANCE:
                steps_over_floor[axis] += 1
    # Calibration, not decoration. For this geometry the step asserted above is exactly
    # the origin the original code discarded: the first group shift is +0.0 and the first
    # centre is frame 1, so the correct field has interp(1) = 0 and step = -interp(0).
    # Requiring patches whose step clears 100x the tolerance therefore states how far
    # above the noise floor the two discriminating checks are actually resolving.
    # Measured on this fixture: 9/9 patches in X and 6/9 in Y.
    assert min(steps_over_floor.values()) >= 3, steps_over_floor


CASES = {'exposure': exposure, 'failure': failure, 'invalid': invalid, 'resume': resume, 'late_bin': late_bin, 'exported_units': exported_units, 'tomography': tomography, 'model_parser': model_parser, 'interpolate_shifts': interpolate_shifts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--helper', type=Path)
    parser.add_argument('--gpu', type=int, help='Native CUDA device for interpolate_shifts only')
    args = parser.parse_args()
    if args.gpu is not None and (args.case != 'interpolate_shifts' or args.gpu < 0):
        parser.error('--gpu requires --case interpolate_shifts and a nonnegative device')
    global HELPER
    HELPER = args.helper.resolve() if args.helper else None
    with tempfile.TemporaryDirectory(prefix='motioncorr-contract-') as directory:
        if args.gpu is None:
            CASES[args.case](args.binary.resolve(), Path(directory))
        else:
            interpolate_shifts(args.binary.resolve(), Path(directory), gpu=args.gpu)
    print(f'PASS runner {args.case}')


if __name__ == '__main__':
    main()
