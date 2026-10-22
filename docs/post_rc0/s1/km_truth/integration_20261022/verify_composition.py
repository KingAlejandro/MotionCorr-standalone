#!/usr/bin/env python3
"""Local source-contract checks and retained-STAR replay; no native execution."""
import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT/'tools'))
import check_motion_diagnostics as current
import test_realistic_motion

OLD = '677abcfab0b55cf8c64ae511369a863383b21a59'
PARENT = '6695241523d7285d4f0480abf1c4a2c6423c3617'
COMMON = '88b34ae06416a3cde233889fe5a0f244b1c16bf4'
EVIDENCE = ROOT/'docs/post_rc0/s1/km_truth'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outdir', type=Path, required=True, help='new writable scratch directory')
    args = ap.parse_args()
    out = args.outdir.resolve()
    out.mkdir(exist_ok=False)
    result = dict(schema='pr269-parent-integration/1',
                  label='LOCAL REPLAY OF RETAINED ESTIMATES; NOT A NATIVE ESTIMATOR RUN',
                  old_pr269=OLD, parent_pr267=PARENT,
                  composition_commit=git('rev-parse', 'HEAD').decode().strip(),
                  python=sys.executable, python_version=sys.version,
                  numpy=np.__version__, platform=platform.platform(),
                  threads={k:os.environ.get(k) for k in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                           'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']})
    for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        if result['threads'][key] != '1': raise ValueError(f'require {key}=1')
    parent_files = git('diff', '--name-only', COMMON, PARENT).decode().splitlines()
    for path in parent_files:
        assert (ROOT/path).read_bytes() == git('show', f'{PARENT}:{path}'), path
    unchanged = git('diff', '--name-only', COMMON, OLD).decode().splitlines()
    unchanged.remove('tools/test_realistic_motion.py')
    for path in unchanged:
        assert (ROOT/path).read_bytes() == git('show', f'{OLD}:{path}'), path
    result['source_contract'] = dict(parent_files_identical=parent_files,
        pr269_files_identical=unchanged, test_sha256=digest((ROOT/'tools/test_realistic_motion.py').read_bytes()),
        production_diff=git('diff', '--name-only', OLD, '--', 'src').decode().splitlines())
    assert not result['source_contract']['production_diff']

    old_source = git('show', f'{OLD}:tools/check_motion_diagnostics.py')
    old_path = out/'old_checker.py'; old_path.write_bytes(old_source)
    spec = importlib.util.spec_from_file_location('old_checker', old_path)
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    for name in ['evaluate', 'check_case', 'validate_star_rows', 'vector_metrics']:
        assert inspect.signature(getattr(old, name)) == inspect.signature(getattr(current, name))
    for name in ['validate_star_rows', 'vector_metrics']:
        assert ast.dump(ast.parse(inspect.getsource(getattr(old, name)))) == ast.dump(ast.parse(inspect.getsource(getattr(current, name))))
    result['source_contract']['shared_helpers_unchanged'] = ['validate_star_rows', 'vector_metrics']
    fixtures = out/'regenerated-v2-fixtures'
    current.gen.generate(fixtures)
    result['regenerated_fixture_manifest_sha256'] = digest((fixtures/'MANIFEST.json').read_bytes())
    valid = 0
    for name in current.gen.CASES:
        r = current.gen.recipe(name); movie, target, truth = current.gen.render(r)
        for field in [truth, np.zeros_like(truth), -truth, truth+1]:
            before = old.evaluate(r, movie, target, truth, field, [12,84,12,116])
            after = current.evaluate(r, movie, target, truth, field, [12,84,12,116])
            assert after.pop('sampling_status') == 'VALID'
            assert before == after, name
            valid += 1
    result['valid_reports_identical_except_sampling_status'] = valid
    assert valid == 32
    r = current.gen.recipe('noisy'); movie, target, truth = current.gen.render(r)
    try:
        old.evaluate(r, movie, target, truth, truth+200, [12,84,12,116])
    except ValueError as exc:
        assert str(exc) == 'candidate samples outside fixed valid detector region'
        result['old_code_negative_control'] = str(exc)
    else:
        raise AssertionError('old checker unexpectedly emitted the outside-ROI report')

    archive = EVIDENCE/'native_v2_raw.tar.gz'
    index = json.loads((EVIDENCE/'native_v2_raw_index.json').read_text())
    retained = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            if not member.isfile(): continue
            key = member.name.removeprefix('raw/')
            assert key not in retained
            data = tar.extractfile(member).read()
            assert len(data) == index[key]['bytes'] and digest(data) == index[key]['sha256'], key
            retained[key] = data
    assert set(retained) == set(index)
    result['retained_archive'] = dict(sha256=digest(archive.read_bytes()), files_verified=len(retained))
    historical = {(m['backend'],m['case']):m for m in json.loads((EVIDENCE/'native_v2_metrics.json').read_text())}
    rows = []
    for backend in ['cpu', 'cuda']:
        for name in current.gen.CASES:
            key = f'native_v2/{backend}/{name}/{name}.star'
            star = out/f'{backend}-{name}.star'; star.write_bytes(retained[key])
            report = out/f'{backend}-{name}.json'
            command = [sys.executable,str(Path(current.__file__)),'--fixtures',str(fixtures),
                       '--case',name,'--candidate',str(star),'--json',str(report)]
            proc = subprocess.run(command, capture_output=True, text=True)
            data = json.loads(report.read_text())
            expected_exit = int(data['sampling_status'] != 'VALID' or
                                (data['role'] == 'gate' and data['accuracy_status'] == 'FAIL'))
            assert proc.returncode == expected_exit and not proc.stderr, (key,proc.stderr)
            for family in ['field_px', 'field_angstrom']:
                for metric, value in data[family].items():
                    np.testing.assert_allclose(value, historical[backend,name][family][metric], rtol=1e-12, atol=1e-12)
            row = dict(backend=backend, case=name, candidate_sha256=digest(retained[key]),
                       exit=proc.returncode, sampling_status=data['sampling_status'],
                       accuracy_status=data['accuracy_status'], field_px=data['field_px'])
            if data['sampling_status'] != 'VALID':
                assert data['signal']['estimated_motion_bilinear'] is None
                try: old.check_case(fixtures, name, star)
                except ValueError as exc:
                    assert str(exc) == 'candidate samples outside fixed valid detector region'
                    row['old_checker_error'] = str(exc)
                else: raise AssertionError('old checker did not abort')
            rows.append(row)
    assert [(r['backend'],r['case']) for r in rows if r['sampling_status'] != 'VALID'] == [('cpu','noisy'),('cpu','repeated'),('cuda','repeated')]
    result['retained_star_replay'] = rows
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_realistic_motion)
    result['focused_collection'] = dict(count=suite.countTestCases(),
        tests=unittest.defaultTestLoader.getTestCaseNames(test_realistic_motion.Realistic))
    assert suite.countTestCases() == 13
    result['native_execution'] = 'UNRUN; no estimator/build/GPU/remote command launched'
    result['status'] = 'PASS'
    (out/'RESULT.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status='PASS',valid_reports=valid,retained_stars=len(rows),
                         previous_aborts_now_reported=3,collection=suite.countTestCases())))


if __name__ == '__main__': main()
