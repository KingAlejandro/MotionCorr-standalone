#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual CLI R1 range discriminators. Usage: range_controls_v2_1.py NEW_ATTEMPT_DIR.

Reuses immutable R1 probe input sets in place; stdlib only. New runs and restore
mutants never overwrite a previous attempt. Child exit1 is expected only for
restore mutants; the contract rejects their missing reports.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ENV = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def strict_json(path):
    def float_value(token):
        from math import isfinite
        value = float(token)
        if not isfinite(value):
            raise ValueError('nonfinite numeric output')
        return value
    def constant(token):
        raise ValueError(f'nonstandard output token {token}')
    return json.loads(path.read_text(), parse_float=float_value, parse_constant=constant)


def main():
    attempt = Path(sys.argv[1]).resolve()
    attempt.mkdir(parents=True, exist_ok=False)
    target = HERE / 'summarize_v2_1.py'
    receipt = dict(source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=HERE, text=True).strip(),
                   target_sha256=sha(target), python=sys.executable,
                   python_sha256=sha(Path(sys.executable).resolve()), numeric_threads=1,
                   checks=[], commands=[])
    save(attempt / 'START.json', {k: v for k, v in receipt.items() if k not in ('checks', 'commands')})

    def check(name, actual, expected):
        receipt['checks'].append(dict(name=name, actual=actual, expected=expected, passed=actual == expected))

    def run(name, ev, script=target, mutant=False, global_error=False):
        folder = attempt / name
        folder.mkdir(exist_ok=False)
        input_hashes = {p.name: sha(p) for p in sorted((ev / 'B').glob('*.json'))}
        argv = [sys.executable, '-B', str(script), str(ev), str(folder / 'out')]
        child = subprocess.run(argv, env=ENV, capture_output=True, text=True, timeout=30)
        (folder / 'stdout.log').write_text(child.stdout)
        (folder / 'stderr.log').write_text(child.stderr)
        summary, coverage = folder / 'out/tierB-v2.json', folder / 'out/coverage.md'
        row = dict(name=name, argv=argv, exit=child.returncode, script_sha256=sha(script),
                   inputs=input_hashes, has_summary=summary.exists(), has_coverage=coverage.exists())
        receipt['commands'].append(row)
        check(name + '/immutable-inputs', {p.name: sha(p) for p in sorted((ev / 'B').glob('*.json'))}, input_hashes)
        if mutant:
            check(name + '/reproduces-diagnostic-loss', [child.returncode, summary.exists(), coverage.exists()], [1, False, False])
            check(name + '/expected-mechanism', ('OverflowError: int too large' in child.stderr) if 'integer' in name else ('ValueError: Out of range float' in child.stderr), True)
            row['contract_verdict'] = 'REJECT' if child.returncode != 2 or not summary.exists() or not coverage.exists() else 'ACCEPT'
            check(name + '/contract-rejects-mutant', row['contract_verdict'], 'REJECT')
            return
        check(name + '/exit-and-files', [child.returncode, summary.exists(), coverage.exists()], [2, True, True])
        if not summary.exists():
            return
        try:
            result = strict_json(summary)
        except (ValueError, UnicodeError) as exc:
            check(name + '/strict-json-output', str(exc), 'valid strict JSON')
            return
        check(name + '/strict-json-output', True, True)
        selected = next(p for p in result['pairs'] if (p['condition'], p['backend'], p['arm'], p['metric']) == ('pedestal32', 'cpu', 'global', 'rms'))
        selected_row = next(r for r in result['rows'] if (r['condition'], r['backend'], r['arm']) == ('pedestal32', 'cpu', 'global'))
        check(name + '/error-state', [result['state'], selected['category'], selected_row['state']], ['EVALUATION_ERROR'] * 3)
        check(name + '/no-selected-cohort-inference', [selected['sign_p'], selected['failure_mcnemar_p']], [None, None])
        errors = [a for a in result['record_audit'] if a['reasons']]
        check(name + '/audit-retains-hash-reason', all(a['sha256'] == input_hashes[Path(a['path']).name] and a['reasons'] for a in errors) and bool(errors), True)
        check(name + '/no-invented-motion-FAIL', selected_row['failures']['field_distance_fail'], 0)
        if global_error:
            check(name + '/unlocatable-global-error', result['global_error_count'], 1)
            check(name + '/no-fabricated-slot', selected['coverage'], dict(expected=10, matched=10, error=0, missing=0, unrun=0))
            check(name + '/all-inference-blocked', all(p['category'] == 'EVALUATION_ERROR' and p['sign_p'] is None and p['failure_mcnemar_p'] is None for p in result['pairs']), True)
        else:
            check(name + '/one-error-seed-retained', selected['coverage'], dict(expected=10, matched=9, error=1, missing=0, unrun=0))
            check(name + '/cell-denominator', selected_row['coverage'], dict(expected=10, present=10, evaluated=9, missing=0, unrun=0, error=1))
            check(name + '/explicit-error-id', 'B-pedestal32-s00-cpu-global' in selected['error_ids'], True)
        row['contract_verdict'] = 'ACCEPT' if all(x['passed'] for x in receipt['checks'] if x['name'].startswith(name + '/')) else 'REJECT'

    retained = HERE / 'review-r1-retained'
    for case in strict_json(retained / 'PROBES.json'):
        ev = retained / 'probes-01' / case['name'] / 'eval'
        check(case['name'] + '/review-input-binding', {p.name: sha(p) for p in sorted((ev / 'B').glob('*.json'))}, case['inputs'])
        run(case['name'], ev)

    # Pinned old generator only; do not run the old harness or mutate its module.
    pins = strict_json(HERE / 'HARNESS_BINDINGS_v2_1.json')['original_harness_sha256']
    check('generator-pin', sha(HERE / 'run_controls.py'), pins['run_controls.py'])
    spec = importlib.util.spec_from_file_location('frozen_generator', HERE / 'run_controls.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    def fixture(name, change):
        ev = attempt / 'fixtures' / name / 'B'
        ev.mkdir(parents=True, exist_ok=False)
        data = {r['id'] + '.json': r for r in [generator.record(s, a) for s in range(10) for a in ['none', 'global']]}
        change(data)
        for filename, value in data.items():
            path = ev / filename
            if isinstance(value, str):
                path.write_text(value)
            else:
                save(path, value)
        return ev.parent

    gid = 'B-pedestal32-s00-cpu-global.json'
    def negative_overflow(data):
        data[gid]['exit'] = 'OVERFLOW_TOKEN'
        data[gid] = json.dumps(data[gid]).replace('"OVERFLOW_TOKEN"', '-1e999')
    def nested_nan(data):
        data[gid]['status'] = 'INPUT_ERROR'
        data[gid]['reason'] = {'nested': ['NAN_TOKEN']}
        data[gid] = json.dumps(data[gid]).replace('"NAN_TOKEN"', 'NaN')
    def unlocatable(data):
        data['unknown.json'] = '{"status":"INPUT_ERROR","reason":{"range":1e999}}'
    run('negative-overflow', fixture('negative-overflow', negative_overflow))
    run('nested-NaN', fixture('nested-NaN', nested_nan))
    run('unlocatable-range', fixture('unlocatable-range', unlocatable), global_error=True)

    original = target.read_text()
    mutants = attempt / 'mutants'
    mutants.mkdir(exist_ok=False)
    parser_anchor = 'object_pairs_hook=strict_object, parse_float=finite_float,'
    assert original.count(parser_anchor) == 1
    parser_mutant = mutants / 'restore-default-float.py'
    parser_mutant.write_text(original.replace(parser_anchor, 'object_pairs_hook=strict_object,'))
    number_anchor = '''    try:
        return type(v) in (int, float) and math.isfinite(v)
    except OverflowError:
        # A JSON integer may exceed the float range used by required metrics.
        return False'''
    assert original.count(number_anchor) == 1
    number_mutant = mutants / 'restore-uncaught-integer.py'
    number_mutant.write_text(original.replace(number_anchor, '    return type(v) in (int, float) and math.isfinite(v)'))
    for case in ['overflow-exit', 'overflow-audit-reason']:
        run('mutant-' + case, retained / 'probes-01' / case / 'eval', script=parser_mutant, mutant=True)
    run('mutant-huge-integer-metric', retained / 'probes-01/huge-integer-metric/eval', script=number_mutant, mutant=True)

    def negative_finite(data):
        for m in data.values():
            if m['arm'] == 'global':
                m['truth']['field']['px']['rms'] *= -1
    ev = fixture('finite-negative-compatibility', negative_finite)
    folder = attempt / 'finite-negative-compatibility'
    folder.mkdir(exist_ok=False)
    argv = [sys.executable, '-B', str(target), str(ev), str(folder / 'out')]
    child = subprocess.run(argv, env=ENV, capture_output=True, text=True, timeout=30)
    (folder / 'stdout.log').write_text(child.stdout)
    (folder / 'stderr.log').write_text(child.stderr)
    receipt['commands'].append(dict(name=folder.name, argv=argv, exit=child.returncode, script_sha256=sha(target),inputs={p.name:sha(p) for p in sorted((ev/'B').glob('*.json'))}))
    check('finite-negative/exit', child.returncode, 0)
    if (folder/'out/tierB-v2.json').exists():
        data = strict_json(folder/'out/tierB-v2.json')
        row = next(r for r in data['rows'] if (r['condition'],r['backend'],r['arm']) == ('pedestal32','cpu','global'))
        check('finite-negative/not-coerced-or-regraded', [row['n'],row['median_rms_px'],row['coverage']['error']], [10,-1.95,0])
    else:
        check('finite-negative/output', False, True)
    receipt['result'] = 'PASS' if all(c['passed'] for c in receipt['checks']) else 'FAIL'
    save(attempt / 'RANGE_CONTROLS.json', receipt)
    print(json.dumps(dict(result=receipt['result'], checks=len(receipt['checks']),
                          failures=[c for c in receipt['checks'] if not c['passed']])))
    return 0 if receipt['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
