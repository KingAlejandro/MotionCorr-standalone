# SPDX-License-Identifier: GPL-2.0-or-later
"""Issue #264 review F1/F2 controls on the real model, with production-faithful mutants.

Exports HEAD into a new directory, builds runner_numerics (motioncorr_core included),
then for each guard-helper mutant rewrites src/local_motion_guard.h in the copy so the
runner and the test are both rebuilt against it. Call mutants edit a copy of
motioncorr_runner.cpp read by the source-pin mode. Never touches the worktree.
"""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('--out', type=pathlib.Path, required=True)
ap.add_argument('--python', required=True, help='Python with NumPy, required by BUILD_TESTING')
ap.add_argument('--jobs', type=int, default=1)
ap.add_argument('--cmake-arg', action='append', default=[])
args = ap.parse_args()
R = pathlib.Path(__file__).resolve().parents[3]
O = args.out.resolve(); O.mkdir(parents=True, exist_ok=False)
S, B = O / 'src', O / 'build'
sha = lambda b: hashlib.sha256(b).hexdigest()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()
dirty = subprocess.check_output(['git', 'status', '--porcelain', '--', 'src', 'tests', 'CMakeLists.txt'], cwd=R, text=True)
assert not dirty, 'compiled sources must be committed: ' + dirty
S.mkdir()
archive = subprocess.run(['git', 'archive', '--format=tar', head], cwd=R, check=True, capture_output=True).stdout
subprocess.run(['tar', '-x', '-C', str(S)], input=archive, check=True)
env = dict(os.environ, OMP_NUM_THREADS='1')
log = []

def run(label, argv, **kw):
    p = subprocess.run(argv, text=True, capture_output=True, env=env, **kw)
    (O / f'{label}.stdout').write_text(p.stdout); (O / f'{label}.stderr').write_text(p.stderr)
    log.append({'label': label, 'argv': argv, 'exit': p.returncode,
                'stdout_tail': p.stdout[-400:], 'stderr_tail': p.stderr[-400:]})
    return p

c = run('configure', ['cmake', '-S', str(S), '-B', str(B), '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=ON',
                      f'-DPython3_EXECUTABLE={args.python}'] + args.cmake_arg)
assert c.returncode == 0, c.stderr
cache = (B / 'CMakeCache.txt').read_text()
assert f'CMAKE_HOME_DIRECTORY:INTERNAL={S}' in cache, 'build tree does not point at the exported copy'
binary = B / 'runner_numerics'
header = S / 'src/local_motion_guard.h'; good_header = header.read_text()
runner = S / 'src/motioncorr_runner.cpp'; good_runner = runner.read_text()

def build(label):
    p = run(label, ['cmake', '--build', str(B), '--target', 'runner_numerics', '--parallel', str(args.jobs)])
    assert p.returncode == 0, (label, p.stderr[-2000:])
    return sha(binary.read_bytes())

def mutate(text, *pairs):
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text

old_runner = subprocess.check_output(['git', 'show', '3691374061f782bc84531fd1c79d017ddcb5a7c2:src/motioncorr_runner.cpp'], cwd=R, text=True)
a = old_runner.index('\t\t// Validation of the model:'); b = old_runner.index('\n\t\tif (largest_delta > MAXIMUM_TOLERANCE)', a)
legacy = ('#ifndef MOTIONCORR_LOCAL_MOTION_GUARD_H\n#define MOTIONCORR_LOCAL_MOTION_GUARD_H\n#include <cmath>\n'
          'namespace motioncorr {\ntemplate <typename Real, typename Model>\n'
          'Real maximumNeighbourShiftDelta(const Model &m, int nx, int ny, int n_frames, Real stop_above)\n{\n'
          'const Model *model = &m; (void)stop_above;\n' + old_runner[a:b] + '\nreturn largest_delta;\n}\n}\n#endif\n')
header_cases = [
    ('fixed', good_header, 0),
    ('legacy_exact_block_36913740', legacy, 1),
    ('mutant_ge_early_exit', mutate(good_header, ('if (largest_delta > stop_above) break;', 'if (largest_delta >= stop_above) break;')), 1),
    ('mutant_uncentred', good_header.replace(' - Real(0.5)', ''), 1),
    ('mutant_invalid_last_pair', mutate(good_header, ('nx - 1 - (axis == 0)', 'nx - 1'), ('ny - 1 - (axis == 1)', 'ny - 1')), 1),
    ('mutant_swapped_dimensions', mutate(good_header, ('Real(ix) / nx', 'Real(ix) / ny'), ('Real(iy) / ny', 'Real(iy) / nx'),
                                         ('Real(ix + (axis == 0)) / nx', 'Real(ix + (axis == 0)) / ny'),
                                         ('Real(iy + (axis == 1)) / ny', 'Real(iy + (axis == 1)) / nx')), 1),
    ('mutant_x_component_only', mutate(good_header, ('if (largest_delta < std::abs(y2 - y1)) largest_delta = std::abs(y2 - y1);\n', '')), 1),
]
rows = []
seen = set()
for label, text, expected in header_cases:
    # make compares mtimes at coarse resolution; a header rewritten within the
    # same tick as the last link is silently not rebuilt (attempt 01).
    time.sleep(2)
    header.write_text(text)
    binary_sha = build('build_' + label)
    assert binary_sha not in seen, (label, 'binary not rebuilt for this header')
    seen.add(binary_sha)
    p = run('model_' + label, [str(binary), 'local_motion_guard_model'])
    ordinary = p.stdout.startswith('PASS checks=' if expected == 0 else 'FAIL checks=')
    rows.append({'case': label, 'header_sha256': sha(text.encode()), 'binary_sha256': binary_sha,
                 'expected_exit': expected, 'exit': p.returncode, 'ordinary_outcome': ordinary,
                 'summary': p.stdout.strip().splitlines()[-1] if p.stdout.strip() else '',
                 'ok': p.returncode == expected and ordinary})
time.sleep(2)
header.write_text(good_header)
restored_sha = build('build_restored')
p = run('model_restored', [str(binary), 'local_motion_guard_model'])
rows.append({'case': 'fixed_restored', 'binary_sha256': restored_sha, 'expected_exit': 0, 'exit': p.returncode,
             'summary': p.stdout.strip(), 'ok': p.returncode == 0 and restored_sha == rows[0]['binary_sha256']})

call = 'motioncorr::maximumNeighbourShiftDelta<RFLOAT>(\n\t\t\t*model, nx, ny, n_frames, MAXIMUM_TOLERANCE);'
call_cases = [
    ('fixed', good_runner, 0),
    ('call_swapped_nx_ny', mutate(good_runner, (call, call.replace('nx, ny', 'ny, nx'))), 1),
    ('call_frames_minus_one', mutate(good_runner, (call, call.replace('n_frames,', 'n_frames - 1,'))), 1),
    ('runner_ge_decision', mutate(good_runner, ('\t\tif (largest_delta > MAXIMUM_TOLERANCE) {', '\t\tif (largest_delta >= MAXIMUM_TOLERANCE) {')), 1),
    ('runner_tolerance_4', mutate(good_runner, ('const RFLOAT MAXIMUM_TOLERANCE = 3; // px', 'const RFLOAT MAXIMUM_TOLERANCE = 4; // px')), 1),
    ('second_helper_call', good_runner + '\n// motioncorr::maximumNeighbourShiftDelta<RFLOAT>(*model, ny, nx, n_frames, 3);\n', 1),
]
for label, text, expected in call_cases:
    path = O / f'runner_{label}.cpp'; path.write_text(text)
    p = run('call_' + label, [str(binary), 'local_motion_guard_call', str(path)])
    rows.append({'case': 'call:' + label, 'runner_sha256': sha(text.encode()), 'expected_exit': expected,
                 'exit': p.returncode, 'message': (p.stdout + p.stderr).strip(), 'ok': p.returncode == expected})
ok = all(r['ok'] for r in rows)
record = {'kind': 'host runner_numerics controls on the real ThirdOrderPolynomialModel; no movie, no CUDA',
          'head': head, 'archive_sha256': sha(archive), 'python': args.python, 'jobs': args.jobs,
          'cmake_args': args.cmake_arg, 'test_source_sha256': sha((S / 'tests/test_runner_numerics.cpp').read_bytes()),
          'helper_sha256': sha(good_header.encode()), 'runner_sha256': sha(good_runner.encode()),
          'compiler': subprocess.check_output(['c++', '--version'], text=True), 'rows': rows, 'commands': log,
          'all_expected': ok}
(O / 'model_controls.json').write_text(json.dumps(record, indent=2) + '\n')
for r in rows: print(('ok  ' if r['ok'] else 'BAD ') + r['case'], r['exit'], r.get('summary', r.get('message', ''))[:120])
sys.exit(0 if ok else 1)
