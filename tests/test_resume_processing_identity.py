#!/usr/bin/env python3
"""Actual own-engine receipt acceptance/refusal; checks also run under -O.

SPDX-License-Identifier: GPL-2.0-or-later. All faults remain in private scratch.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from test_hotpixel_rng_determinism import write_movie, write_star, read_mrc_pixels, NFRAMES
from test_gain_cache import write_mrc
from test_tiff_read import write_tiff

CHECKS = 0
DEFAULTS = {'--use_own': True, '--j': '1', '--patch_x': '1', '--patch_y': '1',
            '--seed': '1', '--skip_logfile': True}
PRODUCTS = {'--dose_weighting': True, '--save_noDW': True, '--even_odd_split': True,
            '--grouping_for_ps': '2', '--ps_size': '48'}


def require(ok, message):
    global CHECKS
    CHECKS += 1
    if not ok:
        raise RuntimeError(message)


def command(binary, out, options=None, star='movies.star'):
    values = dict(DEFAULTS)
    values.update(options or {})
    result = [str(binary), '--i', star, '--o', str(out)]
    for key, value in values.items():
        if value is True:
            result.append(key)
        elif value is not False and value is not None:
            result.extend((key, str(value)))
    return result


def invoke(binary, work, out, options=None, star='movies.star'):
    return subprocess.run(command(binary, out, options, star), cwd=work, capture_output=True,
                          text=True, timeout=60)


def healthy(binary, work, out, options=None, star='movies.star'):
    result = invoke(binary, work, out, options, star)
    require(result.returncode == 0, 'healthy failed: ' + result.stdout + result.stderr)
    return result


def snapshot(out):
    return {str(p.relative_to(out)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in out.rglob('*') if p.is_file()}


def refused(binary, work, out, options, named, star='movies.star'):
    before = snapshot(out)
    result = invoke(binary, work, out, {**options, '--only_do_unfinished': True}, star)
    require(result.returncode > 0, 'false resume success for ' + named + ': ' + result.stdout + result.stderr)
    require('a.mrc' in result.stderr and named in result.stderr,
            'refusal not named (' + named + '): ' + result.stderr)
    require(snapshot(out) == before, 'refusal mutated retained products: ' + named)
    require('Written: ' + str(out) not in result.stdout, 'refusal claimed joint publication')


def fixture(work):
    write_movie(work / 'a.mrc', 17, None, [])
    write_movie(work / 'b.mrc', 18, None, [])
    write_movie(work / 'c.mrc', 19, None, [])
    write_star(work / 'movies.star', ['a.mrc'])


def payloads(out):
    return {p.name: read_mrc_pixels(p) for p in out.glob('a*.mrc')}


def replace_same_metadata(path, data):
    old = path.stat()
    require(len(data) == old.st_size, 'replacement must preserve length')
    path.write_bytes(data)
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    require(path.stat().st_size == old.st_size and path.stat().st_mtime_ns == old.st_mtime_ns,
            'replacement failed to restore metadata')


def changed_movie(path):
    data = bytearray(path.read_bytes())
    for index in range(1024, len(data), 4):
        struct.pack_into('<f', data, index, struct.unpack_from('<f', data, index)[0] * 1.25)
    return data


def control(binary, work, name):
    out = work / 'control'
    options = {'--dose_weighting': True} if name == 'dose' else {}
    if name == 'gain':
        write_mrc(work / 'gain.mrc', [[1.0] * (96 * 96)], nx=96, ny=96)
        options['--gainref'] = 'gain.mrc'
    healthy(binary, work, out, options)
    if name == 'input':
        replace_same_metadata(work / 'a.mrc', changed_movie(work / 'a.mrc'))
        refused(binary, work, out, options, 'input_digest')
    elif name == 'gain':
        data = bytearray((work / 'gain.mrc').read_bytes()); struct.pack_into('<f', data, 1024, 2.0)
        replace_same_metadata(work / 'gain.mrc', data)
        refused(binary, work, out, options, 'gain_digest')
    elif name == 'sampling':
        p = work / 'movies.star'; p.write_text(p.read_text().replace('1.000', '2.000'))
        refused(binary, work, out, options, 'angpix')
    else:
        change = {'binning': ('--bin_factor', '2', 'bin_factor'),
                  'selection': ('--last_frame_sum', '6', 'selected_frames'),
                  'dose': ('--dose_per_frame', '2', 'dose_per_frame')}[name]
        refused(binary, work, out, {**options, change[0]: change[1]}, change[2])


def stale_marker(binary, work, sync=False):
    out = work / ('late-failure-sync' if sync else 'late-failure')
    options = {**PRODUCTS, '--sync_output': sync}
    healthy(binary, work, out, options)
    expected = payloads(out)
    original = (work / 'a.mrc').read_bytes()
    odd = out / 'a_ODD.mrc'
    old_odd = odd.read_bytes()
    odd.unlink(); odd.mkdir()
    replace_same_metadata(work / 'a.mrc', changed_movie(work / 'a.mrc'))
    old_joint = (out / 'corrected_micrographs.star').read_bytes()
    failed = invoke(binary, work, out, options)
    require(failed.returncode > 0, 'owned late product failure returned success')
    require('a_ODD.mrc' in failed.stderr, 'late product failure did not name product')
    require(not (out / 'a.star').exists(), 'old completion marker survived mixed-generation writes')
    require((out / 'corrected_micrographs.star').read_bytes() == old_joint, 'late failure published new joint STAR')
    require(read_mrc_pixels(out / 'a_noDW.mrc') != expected['a_noDW.mrc'],
            'late failure control did not overwrite an earlier product')
    odd.rmdir(); odd.write_bytes(old_odd)
    replace_same_metadata(work / 'a.mrc', original)
    healthy(binary, work, out, {**options, '--only_do_unfinished': True})
    require(payloads(out) == expected, 'repaired mixed-generation attempt did not reprocess exactly')


def model_marker(binary, work):
    out = work / 'model-failure'
    healthy(binary, work, out)
    expected = payloads(out)
    original = (work / 'a.mrc').read_bytes()
    joint = (out / 'corrected_micrographs.star').read_bytes()
    temporary = out / 'a.star.tmp'; temporary.mkdir()
    replace_same_metadata(work / 'a.mrc', changed_movie(work / 'a.mrc'))
    failed = invoke(binary, work, out)
    require(failed.returncode > 0, 'model publication fault did not fail')
    require('Micrograph::write' in failed.stderr and 'a.star' in failed.stderr,
            'model publication fault not named')
    require(not (out / 'a.star').exists(), 'model publication retained old completion marker')
    require((out / 'corrected_micrographs.star').read_bytes() == joint,
            'model publication fault replaced joint STAR')
    require(read_mrc_pixels(out / 'a.mrc') != expected['a.mrc'],
            'model fault control did not execute prior numerical product')
    temporary.rmdir(); replace_same_metadata(work / 'a.mrc', original)
    healthy(binary, work, out, {'--only_do_unfinished': True})
    require(payloads(out) == expected, 'model publication repair did not reprocess exactly')


def parser_identity(binary, work, case):
    # Actual interpretation, not a full pathname, is the compatibility key.
    gain = case.startswith('gain-')
    source = work / ('gain.mrc' if gain else 'defect.txt')
    if gain:
        write_mrc(source, [[1.0] * (96 * 96)], nx=96, ny=96)
    else:
        source.write_text('8 8 1 1\n')
    flag = '--gainref' if gain else '--defect_file'
    out = work / case
    healthy(binary, work, out, {flag: source.name})
    relocation = work / (case + ('-relocated.map' if gain else '-relocated.txt'))
    shutil.copyfile(source, relocation)
    require(source.read_bytes() == relocation.read_bytes(), 'relocation changed source bytes')
    link = work / (case + ('-relocated-link.mrc' if gain else '-relocated-link.txt'))
    link.symlink_to(source.name)
    before = snapshot(out)
    healthy(binary, work, out, {flag: relocation.name, '--only_do_unfinished': True})
    require(all(snapshot(out)[name] == value for name, value in before.items() if name.startswith('a.')),
            'same-parser content relocation rewrote completed products')
    healthy(binary, work, out, {flag: link.name, '--only_do_unfinished': True})
    require(all(snapshot(out)[name] == value for name, value in before.items() if name.startswith('a.')),
            'same-parser symlink alias rewrote completed products')
    # The changed extension selects a different reader/admission contract.
    suffix = '.dm4' if case == 'gain-parser-dm' else ('.tiff' if gain else '.map')
    alternative = work / ('different-parser' + suffix)
    shutil.copyfile(source, alternative)
    require(source.read_bytes() == alternative.read_bytes(), 'parser control changed content')
    fresh = invoke(binary, work, work / (case + '-fresh'), {flag: alternative.name})
    require(fresh.returncode > 0, 'changed-parser fresh attempt unexpectedly succeeded')
    refused(binary, work, out, {flag: alternative.name}, 'gain_parser' if gain else 'defect_parser')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--control-case', choices=['binning', 'selection', 'dose', 'sampling', 'gain', 'input', 'stale-marker', 'model-marker', 'defect-parser', 'gain-parser-tiff', 'gain-parser-dm'])
    args = parser.parse_args()
    binary = args.binary.resolve()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory); fixture(work)
        if args.control_case:
            if args.control_case == 'stale-marker': stale_marker(binary, work)
            elif args.control_case == 'model-marker': model_marker(binary, work)
            elif 'parser' in args.control_case: parser_identity(binary, work, args.control_case)
            else: control(binary, work, args.control_case)
            print('PASS ResumeProcessingIdentity control ' + args.control_case)
            return 0

        base = work / 'base'; healthy(binary, work, base)
        model = (base / 'a.star').read_text()
        require('data_motioncorr_processing' in model, 'fresh run omitted processing receipt')
        receipt = bytes.fromhex(model.split('_rlnMotioncorrProcessingIdentity')[1].split()[0]).decode()
        require(f'selected_frames=1:{NFRAMES}\n' in receipt and 'engine=own-cpu\n' in receipt, 'receipt lacks actual native selection/engine')

        before = snapshot(base)
        healthy(binary, work, base, {'--only_do_unfinished': True, '--j': '2', '--max_io_threads': '1',
                                    '--sync_output': True, '--last_frame_sum': str(NFRAMES), '--first_frame_sum': '0',
                                    '--angpix': '9', '--voltage': '200', '--expected_frames': str(NFRAMES)})
        after = snapshot(base)
        require(all(after[name] == value for name, value in before.items() if name.startswith('a.')),
                'matching normalized resume rewrote completed movie')
        for flag, value, name in [('--bin_factor', '2', 'bin_factor'), ('--first_frame_sum', '2', 'selected_frames'),
                                  ('--last_frame_sum', '6', 'selected_frames'), ('--group_frames', '2', 'group_frames'),
                                  ('--patch_x', '3', 'patch_x'), ('--patch_y', '3', 'patch_y'),
                                  ('--bfactor', '100', 'bfactor'), ('--max_iter', '1', 'max_iter'),
                                  ('--ccf_downsample', '0.5', 'ccf_downsample'), ('--interpolate_shifts', True, 'interpolate_shifts'),
                                  ('--dose_weighting', True, 'dose_weighting'), ('--dose_per_frame', '2', 'dose_per_frame'),
                                  ('--preexposure', '5', 'pre_exposure'), ('--seed', '2', 'seed'),
                                  ('--skip_defect', True, 'skip_defect'), ('--even_odd_split', True, 'even_odd_split')]:
            refused(binary, work, base, {flag: value}, name)

        original_star = (work / 'movies.star').read_text()
        (work / 'movies.star').write_text(original_star.replace('1.000', '2.000'))
        refused(binary, work, base, {}, 'angpix')
        (work / 'movies.star').write_text(original_star)

        # Bind the sum actually used by dose weighting, allowing equivalent
        # CLI/row spellings and refusing a change to effective pre-exposure.
        head, rows = original_star.split('data_movies', 1)
        row_star = work / 'row-exposure.star'
        row_star.write_text(head + 'data_movies' + rows.replace('_rlnOpticsGroup #2',
                            '_rlnOpticsGroup #2\n_rlnMicrographPreExposure #3')
                            .replace('a.mrc 1', 'a.mrc 1 2'))
        row_out = work / 'row-exposure'
        healthy(binary, work, row_out, {'--dose_weighting': True, '--preexposure': '3'}, 'row-exposure.star')
        before = snapshot(row_out)
        row_star.write_text(row_star.read_text().replace('a.mrc 1 2', 'a.mrc 1 4'))
        healthy(binary, work, row_out, {'--dose_weighting': True, '--preexposure': '1',
                                      '--only_do_unfinished': True}, 'row-exposure.star')
        require(all(snapshot(row_out)[name] == value for name, value in before.items() if name.startswith('a.')),
                'equivalent effective pre-exposure rewrote products')
        row_star.write_text(row_star.read_text().replace('a.mrc 1 4', 'a.mrc 1 5'))
        refused(binary, work, row_out, {'--dose_weighting': True, '--preexposure': '1'},
                'pre_exposure', 'row-exposure.star')

        original = (work / 'a.mrc').read_bytes()
        replace_same_metadata(work / 'a.mrc', changed_movie(work / 'a.mrc'))
        refused(binary, work, base, {}, 'input_digest')
        replace_same_metadata(work / 'a.mrc', original)

        write_mrc(work / 'gain.mrc', [[1.0] * (96 * 96)], nx=96, ny=96)
        gain_options = {'--gainref': 'gain.mrc', '--gain_rot': '1', '--gain_flip': '1'}
        gain = work / 'gain'; healthy(binary, work, gain, gain_options)
        before = snapshot(gain)
        healthy(binary, work, gain, {**gain_options, '--only_do_unfinished': True})
        require(snapshot(gain)['gain.mrc'] == before['gain.mrc'], 'no-op resume rewrote prepared gain')
        data = bytearray((work / 'gain.mrc').read_bytes()); struct.pack_into('<f', data, 1024, 2.0)
        replace_same_metadata(work / 'gain.mrc', data)
        refused(binary, work, gain, gain_options, 'gain_digest')
        # Restore a valid source for the following independent controls.
        write_mrc(work / 'gain.mrc', [[1.0] * (96 * 96)], nx=96, ny=96)

        (work / 'defect.txt').write_text('8 8 1 1\n')
        defect_options = {'--defect_file': 'defect.txt'}
        defect = work / 'defect'; healthy(binary, work, defect, defect_options)
        replace_same_metadata(work / 'defect.txt', b'9 8 1 1\n')
        refused(binary, work, defect, defect_options, 'defect_digest')

        products = work / 'products'; healthy(binary, work, products, PRODUCTS)
        refused(binary, work, products, {**PRODUCTS, '--ps_size': '24'}, 'ps_size')
        refused(binary, work, products, {**PRODUCTS, '--float16': True}, 'write_float16')
        expected = payloads(products)
        for suffix in ('.mrc', '.star', '_noDW.mrc', '_EVN.mrc', '_ODD.mrc', '_PS.mrc'):
            target = products / ('a' + suffix); target.unlink()
            healthy(binary, work, products, {**PRODUCTS, '--only_do_unfinished': True})
            require(payloads(products) == expected, 'same-config missing-product repair changed payload ' + suffix)

        for label, transform, name in [
                ('legacy', lambda s: s.split('data_motioncorr_processing')[0], 'legacy'),
                ('version', lambda s: re.sub(r'(_rlnMotioncorrProcessingVersion\s+)2', r'\g<1>3', s), 'version'),
                ('duplicate', lambda s: s + s[s.index('data_motioncorr_processing'):], 'duplicate'),
                ('model-sampling', lambda s: re.sub(r'(_rlnMicrographOriginalPixelSize\s+)\S+', r'\g<1>9.000000', s), 'saved model')]:
            out = work / label; shutil.copytree(base, out)
            path = out / 'a.star'; path.write_text(transform(path.read_text()))
            refused(binary, work, out, {}, name)

        # Precision, selected subsets and early/late-bin semantics use the same
        # normalized resolver as execution, not rounded saved STAR values.
        precise = work / 'precise.star'
        precise.write_text(original_star.replace('1.000', '1.234567891'))
        out = work / 'precise'
        opts = {'--first_frame_sum': '2', '--last_frame_sum': '6', '--bin_factor': '1.5'}
        healthy(binary, work, out, opts, 'precise.star')
        before = snapshot(out)
        healthy(binary, work, out, {**opts, '--only_do_unfinished': True}, 'precise.star')
        require(all(snapshot(out)[name] == value for name, value in before.items() if name.startswith('a.')),
                'precise/subset/binned matching resume rewrote products')
        refused(binary, work, out, {**opts, '--no_early_binning': True}, 'early_binning', 'precise.star')
        precise.write_text(precise.read_text().replace('1.234567891', '1.234567892'))
        refused(binary, work, out, opts, 'angpix', 'precise.star')

        # No-op resume must not silently treat an existing prepared gain as a
        # mutable source. A fresh aliasing preparation is refused before write.
        out = work / 'gain-alias'; out.mkdir()
        write_mrc(out / 'gain.mrc', [[1.0] * (96 * 96)], nx=96, ny=96)
        before = snapshot(out)
        result = invoke(binary, work, out, {'--gainref': str(out / 'gain.mrc'), '--gain_rot': '1'})
        require(result.returncode > 0 and 'aliases immutable gain source' in result.stderr,
                'fresh gain alias was not refused')
        require(snapshot(out) == before, 'gain alias refusal overwrote source')

        out = work / 'legacy-incomplete'; shutil.copytree(base, out)
        path = out / 'a.star'; path.write_text(path.read_text().split('data_motioncorr_processing')[0])
        (out / 'a.mrc').unlink()
        healthy(binary, work, out, {'--only_do_unfinished': True})
        require('data_motioncorr_processing' in path.read_text(), 'incomplete legacy retry failed to migrate')
        out = work / 'engine-receipt'; shutil.copytree(base, out)
        path = out / 'a.star'; text = path.read_text()
        match = re.search(r'(_rlnMotioncorrProcessingIdentity\s+)([0-9a-f]+)', text)
        require(match is not None, 'engine receipt fixture lacks payload')
        raw = bytes.fromhex(match.group(2)).decode()
        raw = re.sub(r'engine_digest=[0-9a-f]{64}', 'engine_digest=' + '0' * 64, raw)
        path.write_text(text[:match.start(2)] + raw.encode().hex() + text[match.end(2):])
        refused(binary, work, out, {}, 'engine_digest')

        geometry = work / 'geometry'; shutil.copytree(base, geometry)
        p = geometry / 'a.mrc'; data = bytearray(p.read_bytes()); struct.pack_into('<i', data, 0, 48); p.write_bytes(data)
        refused(binary, work, geometry, {}, 'geometry')

        # A negative seed requests the current wall-clock seed. Preserve fresh
        # and incomplete operation, but never certify repeatability for it.
        timed = work / 'time-seeded'; healthy(binary, work, timed, {'--seed': '-1'})
        refused(binary, work, timed, {'--seed': '-1'}, 'time-seeded')
        (timed / 'a.mrc').unlink()
        healthy(binary, work, timed, {'--seed': '-1', '--only_do_unfinished': True})
        no_rng = work / 'seed-unused'; healthy(binary, work, no_rng, {'--seed': '-1', '--skip_defect': True})
        before = snapshot(no_rng)
        healthy(binary, work, no_rng, {'--seed': '-1', '--skip_defect': True, '--only_do_unfinished': True})
        require(all(snapshot(no_rng)[name] == value for name, value in before.items() if name.startswith('a.')),
                'unused time seed did not preserve matching resume')

        # Existing completed b may come from another input STAR/shard.
        write_star(work / 'single.star', ['b.mrc'])
        write_star(work / 'all.star', ['a.mrc', 'b.mrc', 'c.mrc'])
        out = work / 'nonprefix'; healthy(binary, work, out, star='single.star')
        b_before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.glob('b.*')}
        healthy(binary, work, out, {'--only_do_unfinished': True, '--do_at_most': '1'}, star='all.star')
        healthy(binary, work, out, {'--only_do_unfinished': True, '--do_at_most': '1'}, star='all.star')
        require(all((out / name).read_bytes() == values[0] and (out / name).stat().st_mtime_ns == values[1]
                    for name, values in b_before.items()), 'non-prefix/shard resume rewrote completed b')

        # Two optics groups, reordered rows and CLI values contradicted by STAR.
        optics = work / 'optics.star'
        optics.write_text('data_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n'
                          '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n'
                          '_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
                          'g1 1 1 300 2.7 0.1\ng2 2 2 200 2.7 0.1\n\ndata_movies\n\nloop_\n'
                          '_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\na.mrc 1\nb.mrc 2\n')
        multi = work / 'multi'; healthy(binary, work, multi, {'--angpix': '9', '--voltage': '100'}, 'optics.star')
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in multi.glob('[ab].*')}
        optics.write_text(optics.read_text().replace('a.mrc 1\nb.mrc 2', 'b.mrc 2\na.mrc 1'))
        healthy(binary, work, multi, {'--only_do_unfinished': True, '--angpix': '1', '--voltage': '300'}, 'optics.star')
        require(all((multi / name).read_bytes() == value[0] and (multi / name).stat().st_mtime_ns == value[1]
                    for name, value in before.items()), 'effective multi-optics/reorder resume failed')

        optics.write_text(optics.read_text().replace('g1 1 1 300', 'g1 7 1 300')
                          .replace('g2 2 2 200', 'g2 9 2 200')
                          .replace('b.mrc 2', 'b.mrc 9').replace('a.mrc 1', 'a.mrc 7'))
        healthy(binary, work, multi, {'--only_do_unfinished': True}, 'optics.star')
        require(all((multi / name).read_bytes() == value[0] and (multi / name).stat().st_mtime_ns == value[1]
                    for name, value in before.items()), 'optics group renumbering changed identity')

        # External resume refusal must precede adapter execution and gain writes.
        adapter = work / 'fake-motioncor2'
        adapter.write_text('#!/bin/sh\ntouch ADAPTER_EXECUTED\nexit 0\n'); adapter.chmod(0o755)
        refused(binary, work, base, {'--use_own': False, '--use_motioncor2': True,
                                    '--motioncor2_exe': str(adapter), '--gainref': 'gain.mrc', '--gain_rot': '1'}, 'external MotionCor2')
        require(not (work / 'ADAPTER_EXECUTED').exists(), 'external adapter ran before refusal')
        require(not (base / 'gain.mrc').exists(), 'external refusal prepared gain')
        for case in ('defect-parser', 'gain-parser-tiff', 'gain-parser-dm'):
            parser_identity(binary, work, case)
        # TIFF gain aliases use the same generic Image decoder for non-EER.
        tif = work / 'gain-alias.tif'
        write_tiff(tif, [[struct.pack('<96H', *([1] * 96))] * 96], 16, 1, 24, 96)
        gain_alias = work / 'gain-alias.gain'; shutil.copyfile(tif, gain_alias)
        alias_out = work / 'tiff-alias'; healthy(binary, work, alias_out, {'--gainref': tif.name})
        before = snapshot(alias_out)
        healthy(binary, work, alias_out, {'--gainref': gain_alias.name, '--only_do_unfinished': True})
        require(all(snapshot(alias_out)[name] == value for name, value in before.items() if name.startswith('a.')),
                'TIFF/gain alias changed generic reader identity')
        # A single-file digest cannot certify extra IMAGIC companions or Image
        # path selectors that may open a different pathname. Refuse named.
        for filename, named in [('paired.img', 'paired image'), ('gain.mrc:map', 'format specifiers')]:
            shutil.copyfile(work / 'gain.mrc', work / filename)
            refused(binary, work, gain, {**gain_options, '--gainref': filename}, named)
        stale_marker(binary, work)
        stale_marker(binary, work, sync=True)
        model_marker(binary, work)
    print('PASS ResumeProcessingIdentity ' + str(CHECKS) + ' explicit checks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
