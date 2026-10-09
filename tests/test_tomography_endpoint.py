#!/usr/bin/env python3
"""Real-binary tomography and SPA controls for the multi-GPU dataset endpoint.

For tomography input MotioncorrRunner publishes corrected_tilt_series.star,
whose data_global rows reference one per-series table each. The merge validator
must check that file -- series order, each reference, and each table's images in
pre-exposure order -- and not corrected_micrographs.star, which a tomography run
never writes. Both runs go through run_dataset.py, i.e. partition, two workers,
staging, the --aggregate_only binary and the validator.

Ghostscript is replaced by a stub that writes a minimal PDF (--fake-gs), so PDF
rendering is not validated here.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/multi_gpu'))
import merge_workers  # noqa: E402

ARGS = ['--use_own', '--j', '1', '--skip_defect', '--angpix', '1.0',
        '--voltage', '300', '--patch_x', '1', '--patch_y', '1', '--bfactor', '150']
OPTICS = ('data_optics\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n'
          '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n'
          '_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\none 1 1.0 300 2.7 0.1\n\n')
# File order within each table deliberately disagrees with pre-exposure order,
# so a validator that ignored the sort would see a different image order.
SERIES = {'one': [('b', 5), ('a', 0)], 'two': [('d', 11), ('c', 17)]}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def run_dataset(binary: Path, cwd: Path, star: str, name: str):
    out = cwd / name
    cp = subprocess.run([sys.executable, str(ROOT / 'tools/multi_gpu/run_dataset.py'),
                         '--binary', str(binary), '--star', star, '--out', str(out),
                         '--required-products', '.mrc,.star,_shifts.eps',
                         '--launcher-args=--workers 2 --no-witness', '--', *ARGS],
                        cwd=cwd, capture_output=True, text=True)
    def tail(path):
        return path.read_text()[-3000:] if path.exists() else ''
    diag = cp.stdout + cp.stderr + tail(out / 'workers.log') + tail(out / 'aggregate.log') \
        + tail(out / 'merged/_workers/merge.log')
    status = json.loads((out / 'dataset_status.json').read_text())
    manifest = json.loads((out / 'workers/shards/shard_manifest.json').read_text())
    return cp, status, manifest, out, diag


def mutate(path: Path, edit) -> bytes:
    original = path.read_bytes()
    path.write_text(edit(original.decode()))
    return original


def swap_rows(text: str, marker: str) -> str:
    lines = text.split('\n')
    rows = [i for i, line in enumerate(lines) if marker in line and not line.startswith('_')]
    require(len(rows) >= 2, f'fixture has fewer than two {marker!r} rows')
    lines[rows[0]], lines[rows[1]] = lines[rows[1]], lines[rows[0]]
    return '\n'.join(lines)


def tomography(binary: Path, tmp: Path) -> None:
    (tmp / 'tilt_series').mkdir()
    (tmp / 'tomo.star').write_text(
        'data_global\nloop_\n_rlnTomoName #1\n_rlnTomoTiltSeriesStarFile #2\n'
        '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n'
        '_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
        'one tilt_series/one.star 1.0 300 2.7 0.1\n'
        'two tilt_series/two.star 1.0 300 2.7 0.1\n')
    for name, rows in SERIES.items():
        (tmp / 'tilt_series' / f'{name}.star').write_text(
            f'data_{name}\nloop_\n_rlnMicrographMovieName #1\n_rlnMicrographPreExposure #2\n'
            + ''.join(f'Movies/{m}.tiff {dose}\n' for m, dose in rows))

    cp, status, manifest, out, diag = run_dataset(binary, tmp, 'tomo.star', 'tomo')
    require(cp.returncode == 0 and status['dataset_ready'] and status['verdict'] == 'PASS',
            'tomography dataset did not complete: ' + diag)
    report = json.loads((out / 'aggregate.json').read_text())
    require(manifest['input_type'] == 'tomography' and report['input_type'] == 'tomography',
            str(report))
    require(report['aggregate_star'].get('row_order') == 'canonical'
            and report['aggregate_star'].get('n_series') == 2
            and report['aggregate_star'].get('n_rows') == 4, str(report['aggregate_star']))
    merged = out / 'merged'
    require(not (merged / 'corrected_micrographs.star').exists(),
            'tomography run published an SPA joint STAR')
    # one series per worker; each worker's own per-series table is staged, not merged
    for k, name in enumerate(SERIES):
        require((merged / '_workers' / f'w{k}' / 'tilt_series' / f'{name}.star').is_file(),
                f'worker {k} per-series table not staged')
    print('PASS tomography dataset through run_dataset: corrected_tilt_series.star, '
          'two series, four tilts, canonical order')

    agg: dict = {}
    require(merge_workers.joint_star_problems(merged, manifest, 'tomography', agg) == [],
            'validator rejects the healthy published tree')
    # The pre-fix validator checked corrected_micrographs.star whatever the input.
    spa_view = merge_workers.joint_star_problems(merged, manifest, 'spa', {})
    require(spa_view and 'corrected_micrographs.star' in spa_view[0], str(spa_view))
    print('PASS SPA-only validation fails on this tree; input-type selection is what passes it')

    joint = merged / 'corrected_tilt_series.star'
    one = merged / 'tilt_series/one.star'
    controls = [
        ('tilt order swapped', one, lambda t: swap_rows(t, '.mrc'), 'pre-exposure order'),
        ('series order swapped', joint, lambda t: swap_rows(t, 'tilt_series/'), 'global order'),
        ('reference to staged worker table', joint,
         lambda t: t.replace(str(one), str(merged / '_workers/w0/tilt_series/one.star')),
         'per-series table'),
    ]
    for label, path, edit, expect in controls:
        original = mutate(path, edit)
        try:
            problems = merge_workers.joint_star_problems(merged, manifest, 'tomography', {})
        finally:
            path.write_bytes(original)
        require(problems and expect in ' '.join(problems), f'{label}: {problems}')
    moved = copy.deepcopy(manifest)
    moved['tomography']['series'].reverse()
    problems = merge_workers.joint_star_problems(merged, moved, 'tomography', {})
    require(problems and 'global order' in problems[0], str(problems))
    joint.rename(joint.with_suffix('.bak'))
    problems = merge_workers.joint_star_problems(merged, manifest, 'tomography', {})
    joint.with_suffix('.bak').rename(joint)
    require(problems and 'corrected_tilt_series.star' in problems[0], str(problems))
    print('PASS validator rejects swapped tilts, swapped series, a misdirected reference, '
          'a different canonical order and a missing joint STAR')
    shutil.rmtree(out)


def spa(binary: Path, tmp: Path) -> None:
    (tmp / 'spa.star').write_text(OPTICS + 'data_movies\nloop_\n_rlnMicrographMovieName #1\n'
                                  '_rlnOpticsGroup #2\n'
                                  + ''.join(f'Movies/{m}.tiff 1\n' for m in 'bdac'))
    cp, status, manifest, out, diag = run_dataset(binary, tmp, 'spa.star', 'spa')
    require(cp.returncode == 0 and status['dataset_ready'] and status['verdict'] == 'PASS',
            'SPA dataset did not complete: ' + diag)
    report = json.loads((out / 'aggregate.json').read_text())
    require(manifest['input_type'] == 'spa' and report['input_type'] == 'spa'
            and report['aggregate_star'].get('row_order') == 'canonical'
            and report['aggregate_star'].get('n_rows') == 4, str(report))
    merged = out / 'merged'
    require(not (merged / 'corrected_tilt_series.star').exists(),
            'SPA run published a tomography joint STAR')
    tomo_view = merge_workers.joint_star_problems(merged, manifest, 'tomography', {})
    require(tomo_view and 'corrected_tilt_series.star' in tomo_view[0], str(tomo_view))
    original = mutate(merged / 'corrected_micrographs.star', lambda t: swap_rows(t, '.mrc'))
    problems = merge_workers.joint_star_problems(merged, manifest, 'spa', {})
    (merged / 'corrected_micrographs.star').write_bytes(original)
    require(problems and 'canonical input order' in problems[0], str(problems))
    print('PASS SPA control: corrected_micrographs.star in canonical order; swapped rows rejected')
    shutil.rmtree(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', type=Path, required=True)
    ap.add_argument('--fake-gs', action='store_true',
                    help='stub Ghostscript; PDF rendering is then not validated')
    a = ap.parse_args()
    binary = a.binary.resolve()
    fixture = ROOT / 'test-data/synthetic/synthetic_movie.tiff'
    with tempfile.TemporaryDirectory(prefix='tomo-endpoint-') as td:
        tmp = Path(td)
        (tmp / 'Movies').mkdir()
        for m in 'abcd':
            shutil.copyfile(fixture, tmp / 'Movies' / f'{m}.tiff')
        if a.fake_gs:
            fake = tmp / 'fake-gs'
            fake.mkdir()
            gs = fake / 'gs'
            gs.write_text('#!' + str(Path(sys.executable).resolve()) + '\n'
                          'import pathlib,sys\n'
                          'for arg in sys.argv[1:]:\n'
                          ' if arg.lower().startswith("-soutputfile="):\n'
                          '  pathlib.Path(arg.split("=",1)[1]).write_bytes(b"%PDF-1.4 control\\n%%EOF\\n")\n')
            gs.chmod(0o755)
            os.environ['PATH'] = str(fake) + os.pathsep + os.environ.get('PATH', '')
        else:
            require(shutil.which('gs') is not None, 'real Ghostscript required, or pass --fake-gs')
        # tomography first: it is the defect under test, and the SPA case is its control
        tomography(binary, tmp)
        spa(binary, tmp)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
