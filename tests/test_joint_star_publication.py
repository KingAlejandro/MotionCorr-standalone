#!/usr/bin/env python3
"""Exercise checked STAR publication and its actual runner call site.

GPL-2.0-or-later. All injected faults stay in a private temporary directory.
The helper's finite hard file limit is confined to its subprocess. Acceptance
uses explicit checks, also when Python's optimized interpreter is selected.
"""
import argparse
import hashlib
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

from test_hotpixel_rng_determinism import write_movie, write_star


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(command, work):
    return subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def star_rows(path, block):
    labels, rows, selected = [], [], False
    for line in path.read_text().splitlines():
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        if fields[0].startswith('data_'):
            selected = fields[0] == 'data_' + block
            continue
        if not selected or fields[0] == 'loop_':
            continue
        if fields[0].startswith('_rln'):
            labels.append(fields[0])
            continue
        require(len(fields) == len(labels), 'malformed ' + block + ' row: ' + str(fields))
        rows.append(dict(zip(labels, fields)))
    require(rows, 'missing ' + block + ' rows: ' + str(path))
    return rows


def direct_optics(binary, work):
    """Direct and glob callers must publish the same bound group as STAR input."""
    work.mkdir()
    for index, name in enumerate(('a', 'b')):
        write_movie(work / (name + '.mrc'), 17 + index, None, [])
    write_star(work / 'movies.star', ['a.mrc', 'b.mrc'])
    reference = work / 'reference'
    errors = []
    for route, input_name, names in [('star', 'movies.star', ('a', 'b')),
                                    ('direct', 'a.mrc', ('a',)),
                                    ('glob', '?.mrc', ('a', 'b'))]:
        out = reference if route == 'star' else work / route
        command = [str(binary), '--i', input_name, '--o', str(out) + '/',
                   '--use_own', '--j', '1', '--angpix', '1', '--voltage', '300',
                   '--bin_factor', '2', '--patch_x', '1', '--patch_y', '1',
                   '--seed', '1', '--skip_logfile']
        result = run(command, work)
        require(result.returncode == 0, route + ' caller failed: ' + result.stdout + result.stderr)
        try:
            joint = out / 'corrected_micrographs.star'
            optics = star_rows(joint, 'optics')
            require(len(optics) == 1 and optics[0].get('_rlnOpticsGroup') == '1',
                    route + ': output optics group1 is missing or ambiguous')
            for label, expected in [('_rlnMicrographOriginalPixelSize', 1),
                                    ('_rlnMicrographPixelSize', 2), ('_rlnVoltage', 300)]:
                require(float(optics[0][label]) == expected, route + ': wrong ' + label)
            rows = star_rows(joint, 'micrographs')
            require(len(rows) == len(names), route + ': incomplete joint movie inventory')
            for row, name in zip(rows, names):
                require(row.get('_rlnOpticsGroup') == '1', route + ': unresolved movie optics')
                for label, suffix in [('_rlnMicrographName', '.mrc'),
                                      ('_rlnMicrographMetadata', '.star')]:
                    require((work / row[label]).resolve() == (out / (name + suffix)).resolve(),
                            route + ': wrong movie association for ' + label)
                fields = shlex.split((out / (name + '.star')).read_text(), comments=True)
                movie = fields[fields.index('_rlnMicrographMovieName') + 1]
                require((work / movie).resolve() == (work / (name + '.mrc')).resolve(),
                        route + ': per-movie STAR names another input')
                for label, expected in [('_rlnMicrographOriginalPixelSize', 1),
                                        ('_rlnMicrographBinning', 2), ('_rlnImageSizeZ', 7)]:
                    require(float(fields[fields.index(label) + 1]) == expected,
                            route + ': wrong per-movie ' + label)
                data = (out / (name + '.mrc')).read_bytes()
                require(struct.unpack_from('<4i', data) == (48, 48, 1, 2),
                        route + ': incorrect binned product shape/mode')
                require(len(data) == 1024 + 48 * 48 * 4, route + ': incomplete MRC product')
                require(struct.unpack_from('<2i', data, 28) == (48, 48) and
                        struct.unpack_from('<2f', data, 40) == (96, 96),
                        route + ': incorrect binned image sampling')
                if route != 'star':
                    original = (reference / (name + '.mrc')).read_bytes()
                    require(data[:224] == original[:224] and data[1024:] == original[1024:],
                            route + ': core MRC header or pixel bytes differ from STAR caller')
        except (RuntimeError, KeyError) as exc:
            errors.append(str(exc))
    require(not errors, '; '.join(errors))
    print('PASS direct/glob optics association and binned sampling; STAR-reference pixels unchanged')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for case in ('healthy', 'open', 'rename', 'limit', 'write-limit'):
            result = run([str(args.helper.resolve()), case, str(work / (case + '.star'))], work)
            require(result.returncode == 0, result.stdout + result.stderr)
            require('PASS joint STAR ' + case in result.stdout, 'helper did not execute ' + case)
            print(result.stdout.strip())
        write_movie(work / 'a.mrc', 17, None, [])
        write_star(work / 'movies.star', ['a.mrc'])
        out = work / 'out'
        command = [str(args.binary.resolve()), '--i', 'movies.star', '--o', str(out) + '/',
                   '--use_own', '--j', '1', '--patch_x', '1', '--patch_y', '1',
                   '--seed', '1', '--skip_logfile']
        healthy = run(command, work)
        require(healthy.returncode == 0, 'healthy runner failed: ' + healthy.stdout + healthy.stderr)
        joint = out / 'corrected_micrographs.star'
        require(joint.is_file(), 'healthy runner omitted joint STAR')
        joint_bytes = joint.read_bytes()
        products = [out / 'a.mrc', out / 'a.star']
        before = [(digest(p), p.stat().st_mtime_ns) for p in products]
        joint.unlink()
        joint.mkdir()
        failed = run(command + ['--only_do_unfinished'], work)
        require(failed.returncode > 0, 'false success: runner joint STAR destination-directory failure')
        require('Failed to rename temporary STAR file' in failed.stderr and str(joint) in failed.stderr,
                'runner did not report the named STAR rename failure: ' + failed.stderr)
        require('Written: ' + str(joint) not in failed.stdout, 'runner claimed joint STAR publication after failure')
        require(joint.is_dir(), 'failed runner replaced the destination directory')
        require(not Path(str(joint) + '.tmp').exists(), 'failed runner retained temporary STAR')
        require([(digest(p), p.stat().st_mtime_ns) for p in products] == before,
                'joint publication failure altered completed movie products')
        joint.rmdir()
        recovered = run(command + ['--only_do_unfinished'], work)
        require(recovered.returncode == 0, 'repaired publication failed: ' + recovered.stderr)
        require(joint.read_bytes() == joint_bytes, 'healthy resume changed joint STAR bytes')
        require([(digest(p), p.stat().st_mtime_ns) for p in products] == before,
                'repaired publication recomputed completed movie products')
        direct_optics(args.binary.resolve(), work / 'direct-optics')
    print('PASS joint STAR actual runner failure and repair; completed products unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
