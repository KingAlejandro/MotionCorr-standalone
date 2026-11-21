#!/usr/bin/env python3
"""CPU-only qualification helpers (evidence readers; no GPU, no native run). Part of the frozen `cpu1` plan.

  cpu1_sums.py compare CENSUS_ROOT RESULTS REF_DIR OUT.json EXPECT [PREFIX]
        decoded published-sum payload equality of every CENSUS_ROOT/RESULTS/<movie>/cpu-none (RUN.json exit 0) against REF_DIR/<movie>/cpu-none/output/movie.mrc.
        exit 0 all EXPECT movies equal; 1 some differ (everything else complete and valid); 2 incomplete/invalid (count != EXPECT, nonzero native exit, missing/unreadable file)
  cpu1_sums.py v2check C1_EVAL.json F_EVAL.json PUBLISHED_EVAL.json OUT.json
        #267 eight cases: C1 CPU vs same-host frozen-F CPU, exact field metrics and native exits (exit 0 only if identical and all native exits 0); the cross-host published CPU values are
        recorded as information, never as the pass criterion
  cpu1_sums.py decide CENSUS_ROOT C1_RESULTS REF_DIR F_RESULTS CMP_JSON OUT.json
        K269 CPU verdict from the C1-vs-retained comparison and the same-host F-cpu control on the control movies. exit 0 PASS; 3 INCONCLUSIVE (C1 differs from the retained cross-host sums while
        equal to same-host F, so a host effect is not excluded); 4 FAIL (C1 differs from same-host F); 5 incomplete
No tolerance anywhere: equality is exact.
"""
import json, os, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(os.environ.get('C1_SCR', '.')) / 'src/tools'))


def read_sum(path):
    from motion_field import read_mrc
    return read_mrc(path)[0]


def _exit(arm):
    try:
        return json.loads((arm / 'RUN.json').read_text()).get('exit')
    except (OSError, ValueError):
        return None


def movies(results_dir):
    return sorted(p.name for p in Path(results_dir).iterdir() if p.is_dir()) if Path(results_dir).is_dir() else []


def compare_one(arm, ref_mrc):
    row = {'exit': _exit(arm)}
    try:
        a, b = read_sum(arm / 'output/movie.mrc'), read_sum(ref_mrc)
        row['shape_equal'] = a.shape == b.shape
        row['equal'] = bool(a.shape == b.shape and np.array_equal(a, b))
        row['max_abs_diff'] = None if a.shape != b.shape else float(np.max(np.abs(a.astype(np.float64) - b)))
    except Exception as exc:                      # a row, never a skip
        row['error'] = f'{type(exc).__name__}: {exc}'
    return row


def compare(root, results, ref, out, expect, prefix=''):
    names = [n for n in movies(Path(root) / results) if n.startswith(prefix)]
    rows = {n: compare_one(Path(root) / results / n / 'cpu-none', Path(ref) / n / 'cpu-none/output/movie.mrc') for n in names}
    s = {'n': len(rows), 'expected': int(expect), 'equal': sum(r.get('equal') is True for r in rows.values()),
         'different': sorted(n for n, r in rows.items() if r.get('equal') is False), 'errors': sorted(n for n, r in rows.items() if 'error' in r),
         'nonzero_exit': sorted(n for n, r in rows.items() if r['exit'] != 0)}
    code = 2 if (s['n'] != s['expected'] or s['errors'] or s['nonzero_exit']) else (1 if s['different'] else 0)
    Path(out).write_text(json.dumps({'results': results, 'reference': str(ref), 'summary': s, 'rows': rows}, indent=1) + '\n')
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in s.items()}))
    return code


def v2check(c1, f, published, out):
    a, b = json.loads(Path(c1).read_text()), json.loads(Path(f).read_text())
    pub = {r['case']: r for r in json.loads(Path(published).read_text())}
    rows, bad = {}, []
    if [r['case'] for r in a] != [r['case'] for r in b] or len(a) != 8: bad.append('case lists differ or are not 8')
    for ra, rb in zip(a, b):
        keys = ('native_exit', 'field_px', 'field_angstrom', 'checker_exit', 'checker_status', 'sampling_status')
        same = all(ra.get(k) == rb.get(k) for k in keys)
        p = pub.get(ra['case'], {})
        rows[ra['case']] = {'c1_equals_same_host_F': same, 'native_exit_c1': ra.get('native_exit'), 'native_exit_F': rb.get('native_exit'),
                            'field_equals_published_cross_host': ra.get('field_px') == p.get('field_px') and ra.get('field_angstrom') == p.get('field_angstrom'),
                            'field_gate_c1': ra.get('field_gate'), 'checker_status_c1': ra.get('checker_status'), 'checker_status_published': p.get('checker_status')}
        if not same: bad.append(f'{ra["case"]}: C1 differs from same-host F')
        if ra.get('native_exit') != 0 or rb.get('native_exit') != 0: bad.append(f'{ra["case"]}: nonzero native exit')
    Path(out).write_text(json.dumps({'problems': bad, 'rows': rows, 'note': 'published values are cross-host and informational; no gate or tolerance applied'}, indent=1) + '\n')
    print('v2check', 'PASS' if not bad else 'FAIL', bad[:3])
    return 0 if not bad else 1


def decide(root, c1_results, ref, f_results, cmp_json, out):
    cmp = json.loads(Path(cmp_json).read_text())['summary']
    ctl = movies(Path(root) / f_results)
    c1_vs_f = {n: compare_one(Path(root) / c1_results / n / 'cpu-none', Path(root) / f_results / n / 'cpu-none/output/movie.mrc') for n in ctl}
    f_vs_ref = {n: compare_one(Path(root) / f_results / n / 'cpu-none', Path(ref) / n / 'cpu-none/output/movie.mrc') for n in ctl}
    complete = bool(ctl) and all(r['exit'] == 0 and 'error' not in r for r in c1_vs_f.values()) and all('error' not in r for r in f_vs_ref.values()) and cmp['n'] == cmp['expected'] and not cmp['errors'] and not cmp['nonzero_exit']
    c1_eq_f = complete and all(r['equal'] for r in c1_vs_f.values())
    f_eq_ref = complete and all(r['equal'] for r in f_vs_ref.values())
    if not complete: verdict, code = 'INCOMPLETE', 5
    elif not c1_eq_f: verdict, code = 'FAIL: C1 CPU differs from the same-host frozen-F CPU control', 4
    elif cmp['different']: verdict, code = 'INCONCLUSIVE: C1 differs from the retained cross-host sums but equals same-host F on the controls; host effect not excluded', 3
    else: verdict, code = 'PASS', 0
    Path(out).write_text(json.dumps({'verdict': verdict, 'c1_vs_retained': cmp, 'control_movies': ctl, 'c1_equals_same_host_F_on_controls': c1_eq_f,
                                     'same_host_F_equals_retained_on_controls': f_eq_ref, 'c1_vs_F': c1_vs_f, 'F_vs_retained': f_vs_ref}, indent=1) + '\n')
    print(verdict); return code


if __name__ == '__main__':
    c = sys.argv[1]
    sys.exit({'compare': lambda: compare(*sys.argv[2:7], *(sys.argv[7:8] or ['']) ), 'v2check': lambda: v2check(*sys.argv[2:6]), 'decide': lambda: decide(*sys.argv[2:8])}[c]())
