import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

R = Path(__file__).resolve().parent
D = R / 'exact/analysis_record_errors_v2_20261023'
spec = importlib.util.spec_from_file_location('controls', D / 'run_controls.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
gid = 'B-pedestal32-s00-cpu-global'

def changes(name, data):
    m = data[gid + '.json']
    if name == 'cross-condition-conflict':
        m['id'] = 'B-dose4-s02-cuda-both'
    elif name == 'wrong-group':
        m['group'] = 'dose1-s00'
    elif name == 'error-plus-absence':
        m['status'] = 'INPUT_ERROR'
        m['reason'] = 'hash mismatch'
        del data['B-pedestal32-s00-cpu-none.json']
    elif name == 'overflow-exit':
        m['exit'] = 'OVERFLOW_TOKEN'
        data[gid + '.json'] = json.dumps(m).replace('"OVERFLOW_TOKEN"', '1e999')
    elif name == 'overflow-audit-reason':
        m['status'] = 'INPUT_ERROR'
        m['reason'] = {'bad_number': 'OVERFLOW_TOKEN'}
        data[gid + '.json'] = json.dumps(m).replace('"OVERFLOW_TOKEN"', '1e999')
    elif name == 'huge-integer-metric':
        m['truth']['field']['px']['rms'] = 10 ** 400

receipts = []
for name in ['cross-condition-conflict', 'wrong-group', 'error-plus-absence',
             'overflow-exit', 'overflow-audit-reason', 'huge-integer-metric']:
    folder = R / 'probes-01' / name
    ev = folder / 'eval/B'
    ev.mkdir(parents=True, exist_ok=False)
    data = {r['id'] + '.json': r for r in [c.record(s, a) for s in range(10) for a in ['none', 'global']]}
    changes(name, data)
    for filename, obj in data.items():
        (ev / filename).write_text(obj if isinstance(obj, str) else json.dumps(obj, allow_nan=False))
    argv = [sys.executable, '-B', str(D / 'summarize_v2.py'), str(ev.parent), str(folder / 'out')]
    p = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
    (folder / 'stdout.log').write_text(p.stdout)
    (folder / 'stderr.log').write_text(p.stderr)
    summary = folder / 'out/tierB-v2.json'
    result = json.loads(summary.read_text()) if summary.exists() else None
    selected = next((q for q in result['pairs'] if (q['condition'], q['backend'], q['arm'], q['metric']) ==
                    ('pedestal32', 'cpu', 'global', 'rms')), None) if result else None
    receipts.append(dict(name=name, argv=argv, exit=p.returncode, has_summary=result is not None,
                         expected='exit2 with EVALUATION_ERROR diagnostics and affected p-values null',
                         selected_pair=selected,
                         error_rows=[dict(condition=q['condition'],backend=q['backend'],arm=q['arm'],coverage=q['coverage'])
                                     for q in result['rows'] if q['coverage']['error']] if result else None,
                         inputs={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in ev.glob('*.json')}))
    print(name, 'exit', p.returncode, 'summary', result is not None)
(R / 'PROBES.json').write_text(json.dumps(receipts, indent=1, allow_nan=False))
old = ast.parse((D.parent / 'analysis_B_pass3_20261023/frozen/frozen_summarize.py').read_text())
new = ast.parse((D / 'summarize_v2.py').read_text())
def funcs(tree):
    return {x.name: ast.dump(x, include_attributes=False) for x in tree.body if isinstance(x, ast.FunctionDef)}
of, nf = funcs(old), funcs(new)
checks = {name: of[name] == nf[name] for name in ['sign_p','mcnemar_p','g','failure','band_transfer']}
assert all(checks.values())
(R / 'AST.json').write_text(json.dumps(checks, indent=1))
