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
    text = star.read_text().replace('_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n',
                                  '_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n_rlnMicrographPreExposure #3\n')
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
    options = ['--dose_weighting', '--save_noDW', '--even_odd_split',
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
    options = ['--dose_weighting', '--preexposure', '3.5', '--even_odd_split']
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


CASES = {'exposure': exposure, 'failure': failure, 'invalid': invalid, 'resume': resume, 'late_bin': late_bin, 'exported_units': exported_units, 'tomography': tomography}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--helper', type=Path)
    args = parser.parse_args()
    global HELPER
    HELPER = args.helper.resolve() if args.helper else None
    with tempfile.TemporaryDirectory(prefix='motioncorr-contract-') as directory:
        CASES[args.case](args.binary.resolve(), Path(directory))
    print(f'PASS runner {args.case}')


if __name__ == '__main__':
    main()
