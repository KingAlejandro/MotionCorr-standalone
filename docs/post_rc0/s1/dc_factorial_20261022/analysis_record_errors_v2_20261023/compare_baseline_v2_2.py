#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hash/read frozen record inputs in place; one v2 regeneration, no evaluator run.

Usage: compare_baseline.py COLLECTED_DIR NEW_ATTEMPT_DIR
Retain every command/exit/output. Never extract/copy the archive or per-case corpus.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(p, obj):
    p.write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def main():
    collected, out = (Path(s).resolve() for s in sys.argv[1:])
    out.mkdir(parents=True, exist_ok=False)
    frozen = HERE.parent / 'analysis_B_pass3_20261023/frozen'
    manifest = json.loads((frozen / 'EVALUATIONS.json').read_text())
    inputs = {p.stem: sha(p) for p in sorted((collected / 'eval/B').glob('*.json'))}
    checks = []

    def check(name, actual, expected):
        checks.append(dict(name=name, actual=actual, expected=expected, passed=actual == expected))

    check('all-record-input-bindings', inputs, manifest['sha256'])
    target = HERE / 'summarize_v2_2.py'
    argv = [sys.executable, '-B', str(target), str(collected / 'eval'), str(out / 'regen')]
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=HERE, text=True).strip()
    receipt = dict(source_sha=source, target_sha256=sha(target),
                   python=sys.executable, python_sha256=sha(Path(sys.executable).resolve()),
                   numeric_threads=1, inputs=inputs,
                   frozen_summary_sha256=sha(frozen / 'tierB.json'),
                   frozen_evaluations_manifest_sha256=sha(frozen / 'EVALUATIONS.json'),
                   archive_sha256=sha(frozen / 'snapshot.tgz'),
                   snapshot_sha256=sha(frozen / 'SNAPSHOT.json'), argv=argv,
                   scope='Evaluation JSON identity only; no independent raw-movie/native/binary audit')
    save(out / 'START.json', receipt)
    if not all(c['passed'] for c in checks):
        save(out / 'COMPARISON.json', dict(result='FAIL', checks=checks))
        return 1
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    child = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
    (out / 'stdout.log').write_text(child.stdout)
    (out / 'stderr.log').write_text(child.stderr)
    receipt['exit'] = child.returncode
    save(out / 'COMMAND.json', receipt)
    check('v2-exit', child.returncode, 0)
    if not (out / 'regen/tierB-v2.json').exists():
        check('v2-produced-summary', False, True)
    else:
        old = json.loads((frozen / 'tierB.json').read_text())
        new = json.loads((out / 'regen/tierB-v2.json').read_text())
        for section in ('rows', 'pairs', 'regressions'):
            check(section + '/count', len(new[section]), len(old[section]))
            # Project every original field, rather than choose a metric subset.
            projected = [{key: r.get(key) for key in old[section][0]} for r in new[section]]
            check(section + '/every-frozen-field-equal', projected == old[section], True)
        check('record-composition', dict(Counter(a['status'] for a in new['record_audit'])),
              dict(EVALUATED=734, CONTROL_ONLY=2))
        check('original-categories', dict(Counter(p['category'] for p in new['pairs'])),
              {'improves': 30, 'neutral/mixed': 185, 'harms': 1, 'IN_PROGRESS': 12, 'UNRUN': 12})
        check('record-errors', sum(bool(a['reasons']) for a in new['record_audit']), 0)
        totals = {k: sum(r['coverage'][k] for r in new['rows'])
                  for k in ['expected', 'present', 'evaluated', 'missing', 'unrun', 'error']}
        check('800-slot-record-coverage', totals,
              dict(expected=800, present=734, evaluated=734, missing=66, unrun=0, error=0))
        check('global-error-count', new['global_error_count'], 0)
        check('still-incomplete', new['state'], 'IN_PROGRESS')
        check('input-bytes-unchanged', {p.stem: sha(p) for p in sorted((collected / 'eval/B').glob('*.json'))}, inputs)
    result = 'PASS' if all(c['passed'] for c in checks) else 'FAIL'
    save(out / 'COMPARISON.json', dict(result=result, checks=checks))
    print(json.dumps(dict(result=result, checks=len(checks), failures=[c['name'] for c in checks if not c['passed']])))
    return 0 if result == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
