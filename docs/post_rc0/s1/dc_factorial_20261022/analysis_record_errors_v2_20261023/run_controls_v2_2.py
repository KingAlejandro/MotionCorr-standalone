#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Black-box, immutable fixture controls for F8; stdlib only.

Usage: run_controls.py NEW_ATTEMPT_DIR
Retains each fixture, child output, exit, hash and assertion, including failures.
Run under the task lifetime lease, one numeric thread. No native execution.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
           MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_json(p, obj):
    p.write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def record(seed, arm):
    base = 2 + seed / 10
    value = base - (0.5 if arm == 'global' else 0)
    return dict(id=f'B-pedestal32-s{seed:02d}-cpu-{arm}', exit=0, backend='cpu',
                arm=arm, group=f'pedestal32-s{seed:02d}', status='EVALUATED',
                truth=dict(schema='motion-counting-metrics/2', sampling_status='VALID',
                           field_distance_status='PASS' if arm == 'global' else 'FAIL',
                           local_enabled=True, convergence=dict(global_converged=True),
                           field=dict(px=dict(rms=value, p95=value + 1, max=value + 2),
                                      angstrom=dict(rms=value * .885)),
                           global_trajectory=dict(px=dict(rms=value)),
                           local_component=dict(px=dict(rms=value))),
                image=dict(schema='motion-image-truth/1', interior=dict(
                    transfer_inband=.6 if arm == 'global' else .5,
                    bands=[dict(transfer=.4 if arm == 'global' else .3)])))


def main():
    attempt = Path(sys.argv[1]).resolve()
    attempt.mkdir(parents=True, exist_ok=False)
    target = HERE / 'summarize_v2_2.py'
    receipt = dict(source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=HERE, text=True).strip(),
                   target_sha256=sha(target), python=sys.executable,
                   python_sha256=sha(Path(sys.executable).resolve()), numeric_threads=1,
                   checks=[], commands=[])
    write_json(attempt / 'START.json', {k: v for k, v in receipt.items() if k not in ('checks', 'commands')})
    fixtures = {}

    def check(name, actual, expected):
        receipt['checks'].append(dict(name=name, actual=actual, expected=expected, passed=actual == expected))

    def run(name, transform=None, script=target):
        folder = attempt / name
        folder.mkdir(exist_ok=False)
        ev = folder / 'eval' / 'B'
        ev.mkdir(parents=True)
        data = {r['id'] + '.json': r for r in [record(s, a) for s in range(10) for a in ['none', 'global']]}
        if transform:
            transform(data)
        for filename, obj in data.items():
            p = ev / filename
            if isinstance(obj, str):
                p.write_text(obj)
            else:
                write_json(p, obj)
        fixtures[name] = ev.parent
        argv = [sys.executable, '-B', str(script), str(ev.parent), str(folder / 'out')]
        child = subprocess.run(argv, env=ENV, capture_output=True, text=True, timeout=30)
        (folder / 'stdout.log').write_text(child.stdout)
        (folder / 'stderr.log').write_text(child.stderr)
        receipt['commands'].append(dict(name=name, argv=argv, exit=child.returncode,
                                        source_sha256=sha(script),
                                        inputs={p.name: sha(p) for p in sorted(ev.glob('*.json'))}))
        result_path = folder / 'out' / ('tierB-v2.json' if script.name != 'frozen_summarize.py' else 'tierB.json')
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        if result is None:
            check(name + '/produced-summary', False, True)
            return child.returncode, None, None
        pair = next(p for p in result['pairs'] if (p['condition'], p['backend'], p['arm'], p['metric']) == ('pedestal32', 'cpu', 'global', 'rms'))
        row = next(r for r in result['rows'] if (r['condition'], r['backend'], r['arm']) == ('pedestal32', 'cpu', 'global'))
        return child.returncode, result, (pair, row)

    code, result, (pair, row) = run('complete')
    check('complete/exit', code, 0)
    check('complete/paired-arithmetic', [pair[k] for k in ['pairs', 'wins', 'losses', 'ties', 'sign_p', 'median_delta', 'category', 'failure_fixed', 'failure_new', 'failure_mcnemar_p']],
          [10, 10, 0, 0, .001953125, -.5, 'improves', 10, 0, .001953125])
    check('complete/medians', [row[k] for k in ['median_rms_px', 'median_p95_px', 'worst_max_px', 'median_global_rms_px', 'median_local_rms_px', 'median_transfer', 'median_transfer_top']],
          [1.95, 2.95, 4.4, 1.95, 1.95, .6, .4])
    check('complete/coverage', pair['coverage'], dict(expected=10, matched=10, error=0, missing=0, unrun=0))
    global_id = 'B-pedestal32-s00-cpu-global'
    none_id = 'B-pedestal32-s00-cpu-none'

    def failed(data, ident=global_id, status='NATIVE_FAILURE'):
        data[ident + '.json'] = dict(id=ident, exit=1, arm=ident.rsplit('-', 1)[1],
                                    backend='cpu', group='pedestal32-s00', status=status,
                                    reason='constructed evaluator failure, not measured motion')

    def both(data):
        failed(data)
        failed(data, none_id)

    def unknown(data):
        data[global_id + '.json']['status'] = 'FUTURE_UNKNOWN'

    def malformed(data):
        data[global_id + '.json'] = '{"id":'

    def duplicate(data):
        data['duplicate.json'] = copy.deepcopy(data[global_id + '.json'])

    def conflict(data):
        data[global_id + '.json']['id'] = none_id

    def null(data):
        data[global_id + '.json']['truth']['field']['px']['rms'] = None

    def unrun(data):
        data[global_id + '.json'] = dict(id=global_id, status='UNRUN', arm='global',
                                         backend='cpu', group='pedestal32-s00')

    def absence(data):
        del data[global_id + '.json']

    def outside(data):
        data[global_id + '.json']['truth']['sampling_status'] = 'OUTSIDE_FIXED_ROI'

    def input_error(data):
        failed(data, status='INPUT_ERROR')
        data[global_id + '.json']['exit'] = 0
        data[global_id + '.json']['reason'] = 'receipt hash mismatch'

    def image_null(data):
        outside(data)
        data[global_id + '.json']['image']['interior']['transfer_inband'] = None

    def status_missing(data):
        del data[global_id + '.json']['status']

    def nonobject(data):
        data[global_id + '.json'] = '[]'

    def duplicate_key(data):
        data[global_id + '.json'] = '{"status":"UNRUN","status":"EVALUATED"}'

    def nonfinite(data):
        data[global_id + '.json'] = '{"metric":NaN}'

    def foreign(data):
        data['unlocatable.json'] = '{"status":"INPUT_ERROR","reason":"unknown input"}'

    error_cases = [('one-arm-error', failed), ('both-arm-error', both), ('unknown-status', unknown),
                   ('malformed', malformed), ('duplicate', duplicate), ('identity-conflict', conflict),
                   ('field-null', null), ('input-error', input_error), ('outside-image-null', image_null),
                   ('status-missing', status_missing), ('nonobject', nonobject),
                   ('duplicate-key', duplicate_key), ('nonfinite', nonfinite), ('unlocatable', foreign)]
    for name, transform in error_cases:
        code, result, selected = run(name, transform)
        if selected is None:
            continue
        pair, row = selected
        check(name + '/exit', code, 2)
        check(name + '/state', [result['state'], pair['category'], row['state']], ['EVALUATION_ERROR'] * 3)
        check(name + '/no-selected-set-inference', [pair['sign_p'], pair['failure_mcnemar_p']], [None, None])
        # Error/native failure does not become a numeric truth FAIL; 9 valid global records remain PASS.
        check(name + '/truth-failure-denominator', [row['failures']['field_distance_fail'], row['failures']['union']], [0, 0])
        if name != 'unlocatable':
            check(name + '/pair-counts', pair['coverage'], dict(expected=10, matched=9, error=1, missing=0, unrun=0))
            check(name + '/record-denominator', sum(row['coverage'][k] for k in ['evaluated', 'missing', 'unrun', 'error']), 10)
        check(name + '/error-audit', any(a['reasons'] and len(a['sha256']) == 64 for a in result['record_audit']), True)

    for name, transform, expected_missing, expected_unrun in [('absent', absence, 1, 0), ('unrun', unrun, 0, 1)]:
        code, result, (pair, row) = run(name, transform)
        check(name + '/exit', code, 0)
        check(name + '/legacy-partial-label', pair['category'], 'IN_PROGRESS')
        check(name + '/pair-coverage', pair['coverage'], dict(expected=10, matched=9, error=0, missing=expected_missing, unrun=expected_unrun))
        check(name + '/cell-coverage', [row['coverage'][k] for k in ['missing', 'unrun', 'error']], [expected_missing, expected_unrun, 0])

    code, result, (pair, row) = run('outside-finite', outside)
    check('outside-finite/exit', code, 0)
    check('outside-finite/retains-field-and-image', [row['n'], row['median_rms_px'], row['median_transfer'], row['failures']['outside_roi']], [10, 1.95, .6, 1])

    # This semantic removal recreates the latent F8 selection, not a numeric mutant.
    mutant = attempt / 'drop-non-evaluated-mutant.py'
    original = target.read_text()
    anchor = "        declared = m.get('id') if isinstance(m, dict) else None"
    assert original.count(anchor) == 1
    mutant.write_text(original.replace(anchor, "        if isinstance(m, dict) and m.get('status') != 'EVALUATED':\n            continue\n" + anchor))
    code, result, (pair, row) = run('drop-mutant', failed, mutant)
    check('drop-mutant/discriminator-rejects', code == 2 and pair['category'] == 'EVALUATION_ERROR', False)
    check('drop-mutant/restored-bug', [code, pair['category'], pair['coverage']['matched'], pair['coverage']['missing']], [0, 'IN_PROGRESS', 9, 1])
    frozen = HERE.parent / 'analysis_B_pass3_20261023/frozen/frozen_summarize.py'
    code, result, (pair, row) = run('frozen-base', failed, frozen)
    check('frozen-base/discriminator-rejects', code == 2 and pair['category'] == 'EVALUATION_ERROR', False)
    check('frozen-base/restored-bug', [code, pair['category'], pair['pairs']], [0, 'IN_PROGRESS', 9])

    receipt['result'] = 'PASS' if all(c['passed'] for c in receipt['checks']) else 'FAIL'
    write_json(attempt / 'CONTROLS.json', receipt)
    print(json.dumps(dict(result=receipt['result'], checks=len(receipt['checks']), failures=[c for c in receipt['checks'] if not c['passed']])))
    return 0 if receipt['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
