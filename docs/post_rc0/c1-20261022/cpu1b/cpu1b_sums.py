#!/usr/bin/env python3
"""CPU-only qualification helpers, version b (fail-closed). Evidence readers; no GPU, no native run. Supersedes cpu1_sums.py (never launched).

Expected identities come from a frozen JSON (IDS): {"all": [100 sorted unique fixture names], "control": [10 sorted unique names, subset of all]}.
Every result set must equal its expected identity set exactly (no missing, extra or duplicate identity), every native RUN.json must have exit 0, carry the expected binary sha256
and be bound to its fixture (movie_sha256 equals the fixture RECEIPT movie hash). Equality of decoded sums is exact; there is no tolerance.

  cpu1b_sums.py compare CENSUS_ROOT RESULTS REF_DIR OUT IDS GROUP BINARY_SHA256     GROUP all|control; exit 0 all equal, 1 some differ (rest complete and valid), 2 incomplete/invalid
  cpu1b_sums.py v2check C1_EVAL F_EVAL PUBLISHED_EVAL OUT                           exactly the 8 expected cases, all required keys, C1 == same-host F, native exits 0
  cpu1b_sums.py decide CENSUS_ROOT C1_RESULTS F_RESULTS REF_DIR IDS OUT C1_SHA F_SHA exit 0 PASS; 3 INCONCLUSIVE (host effect not excluded); 4 FAIL; 5 incomplete/invalid
"""
import json, os, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(os.environ.get('C1_SCR', '.')) / 'src/tools'))
FIXTURES = lambda: Path(os.environ.get('C1_KM_FIXTURES', '/mnt/clathrin/alex-motioncorr-km-truth/fixtures'))
CASES = ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']
REQUIRED_V2 = ('case', 'native_exit', 'dc', 'field_px', 'field_angstrom', 'field_gate', 'checker_exit', 'checker_status')
OPTIONAL_V2 = ('sampling_status', 'checker_message')
MISSING = object()


def read_sum(path):
    from motion_field import read_mrc
    return read_mrc(path)[0]


def load_ids(path):
    ids = json.loads(Path(path).read_text())
    for g in ('all', 'control'):
        v = ids.get(g)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v) or len(set(v)) != len(v) or v != sorted(v):
            raise ValueError(f'identity group {g!r} missing, empty, not strings, duplicated or unsorted')
    if len(ids['all']) != ids.get('expected_all', 100) or len(ids['control']) != ids.get('expected_control', 10) or not set(ids['control']) <= set(ids['all']):
        raise ValueError('identity counts or control subset invalid')
    return ids


def run_ok(arm, bin_sha, name):
    """RUN.json of one native arm: exit 0, expected binary, bound to the fixture it ran on. Returns an error string or None."""
    try:
        r = json.loads((arm / 'RUN.json').read_text())
    except (OSError, ValueError):
        return 'RUN.json missing or unreadable'
    if r.get('exit') != 0: return f'native exit {r.get("exit")!r}'
    if r.get('binary_sha256') != bin_sha: return f'binary {str(r.get("binary_sha256"))[:12]} is not the expected {bin_sha[:12]}'
    try:
        want = json.loads((FIXTURES() / name / 'RECEIPT.json').read_text())['files']['movie.mrcs']
    except (OSError, ValueError, KeyError):
        return 'fixture receipt missing'
    if r.get('movie_sha256') != want: return 'run is not bound to this fixture (movie hash mismatch)'
    return None


def dirs(results_dir):
    p = Path(results_dir)
    return sorted(x.name for x in p.iterdir() if x.is_dir()) if p.is_dir() else []


def set_problems(found, expected):
    exp = set(expected)
    return {'missing': sorted(exp - set(found)), 'extra': sorted(set(found) - exp)}


def compare_rows(root, results, ref, expected, bin_sha):
    rows = {}
    for n in expected:
        arm = Path(root) / results / n / 'cpu-none'
        row = {}
        err = run_ok(arm, bin_sha, n)
        if err: row['error'] = err
        else:
            try:
                a, b = read_sum(arm / 'output/movie.mrc'), read_sum(Path(ref) / n / 'cpu-none/output/movie.mrc')
                row['equal'] = bool(a.shape == b.shape and np.array_equal(a, b))
                row['max_abs_diff'] = None if a.shape != b.shape else float(np.max(np.abs(a.astype(np.float64) - b)))
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
        rows[n] = row
    return rows


def compare(root, results, ref, out, ids_path, group, bin_sha):
    ids = load_ids(ids_path); expected = ids[group]
    sp = set_problems(dirs(Path(root) / results), expected)
    rows = compare_rows(root, results, ref, expected, bin_sha)
    s = {'group': group, 'expected': len(expected), 'present': len(dirs(Path(root) / results)), **sp, 'equal': sum(r.get('equal') is True for r in rows.values()),
         'different': sorted(n for n, r in rows.items() if r.get('equal') is False), 'errors': {n: r['error'] for n, r in rows.items() if 'error' in r}}
    code = 2 if (sp['missing'] or sp['extra'] or s['errors']) else (1 if s['different'] else 0)
    Path(out).write_text(json.dumps({'results': results, 'reference': str(ref), 'summary': s, 'rows': rows}, indent=1) + '\n')
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in s.items()}))
    return code


def v2check(c1, f, published, out):
    a, b = json.loads(Path(c1).read_text()), json.loads(Path(f).read_text())
    pub = json.loads(Path(published).read_text())
    bad, rows = [], {}
    for label, rs in (('c1', a), ('f', b)):
        names = [r.get('case') for r in rs] if isinstance(rs, list) else None
        if names != CASES: bad.append(f'{label}: cases {names} are not exactly {CASES}')
        elif any(k not in r for r in rs for k in REQUIRED_V2): bad.append(f'{label}: a row lacks a required key ({[(r["case"], k) for r in rs for k in REQUIRED_V2 if k not in r][:3]})')
    if not bad:
        pubm = {r.get('case'): r for r in pub} if isinstance(pub, list) else {}
        for ra, rb in zip(a, b):
            same = all(ra.get(k, MISSING) == rb.get(k, MISSING) for k in (*REQUIRED_V2, *OPTIONAL_V2))
            p = pubm.get(ra['case'], {})
            rows[ra['case']] = {'c1_equals_same_host_F': same, 'native_exit': [ra['native_exit'], rb['native_exit']],
                                'field_equals_published_cross_host': ra['field_px'] == p.get('field_px', MISSING) and ra['field_angstrom'] == p.get('field_angstrom', MISSING),
                                'field_gate_c1': ra['field_gate'], 'checker_status_c1': ra['checker_status'], 'checker_status_published': p.get('checker_status')}
            if not same: bad.append(f'{ra["case"]}: C1 differs from same-host F')
            if ra['native_exit'] != 0 or rb['native_exit'] != 0: bad.append(f'{ra["case"]}: nonzero native exit')
            if ra['dc'] != 'unset' or rb['dc'] != 'unset': bad.append(f'{ra["case"]}: dc is not "unset"')
    Path(out).write_text(json.dumps({'problems': bad, 'rows': rows, 'note': 'published values are cross-host and informational; no gate or tolerance applied'}, indent=1) + '\n')
    print('v2check', 'PASS' if not bad else 'FAIL', bad[:3])
    return 0 if not bad else 1


def decide(root, c1_results, f_results, ref, ids_path, out, c1_sha, f_sha):
    ids = load_ids(ids_path)
    c1_sp, f_sp = set_problems(dirs(Path(root) / c1_results), ids['all']), set_problems(dirs(Path(root) / f_results), ids['control'])
    c1_all = compare_rows(root, c1_results, ref, ids['all'], c1_sha)              # recomputed here; no stale comparison file is trusted
    f_ref = compare_rows(root, f_results, ref, ids['control'], f_sha)             # same-host F vs retained, with F's own RUN.json validated
    c1_vs_f = {}
    for n in ids['control']:
        err = run_ok(Path(root) / c1_results / n / 'cpu-none', c1_sha, n)
        if err: c1_vs_f[n] = {'error': 'C1: ' + err}; continue
        err = run_ok(Path(root) / f_results / n / 'cpu-none', f_sha, n)
        if err: c1_vs_f[n] = {'error': 'F: ' + err}; continue
        try:
            a, b = read_sum(Path(root) / c1_results / n / 'cpu-none/output/movie.mrc'), read_sum(Path(root) / f_results / n / 'cpu-none/output/movie.mrc')
            c1_vs_f[n] = {'equal': bool(a.shape == b.shape and np.array_equal(a, b))}
        except Exception as exc:
            c1_vs_f[n] = {'error': f'{type(exc).__name__}: {exc}'}
    problems = {'c1_set': c1_sp, 'f_control_set': f_sp, 'c1_row_errors': {n: r['error'] for n, r in c1_all.items() if 'error' in r},
                'f_row_errors': {n: r['error'] for n, r in f_ref.items() if 'error' in r}, 'c1_vs_f_errors': {n: r['error'] for n, r in c1_vs_f.items() if 'error' in r}}
    complete = not (c1_sp['missing'] or c1_sp['extra'] or f_sp['missing'] or f_sp['extra'] or problems['c1_row_errors'] or problems['f_row_errors'] or problems['c1_vs_f_errors'])
    c1_eq_f = complete and all(r['equal'] for r in c1_vs_f.values())
    c1_diff = sorted(n for n, r in c1_all.items() if r.get('equal') is False)
    if not complete: verdict, code = 'INCOMPLETE: expected identities, native exits, binaries or fixture bindings not satisfied', 5
    elif not c1_eq_f: verdict, code = 'FAIL: C1 CPU differs from the same-host frozen-F CPU control', 4
    elif c1_diff: verdict, code = 'INCONCLUSIVE: C1 differs from the retained cross-host sums but equals same-host F on the controls; host effect not excluded', 3
    else: verdict, code = 'PASS', 0
    Path(out).write_text(json.dumps({'verdict': verdict, 'problems': problems, 'c1_vs_retained_different': c1_diff, 'control_movies': ids['control'],
                                     'c1_equals_same_host_F_on_controls': c1_eq_f, 'same_host_F_equals_retained_on_controls': complete and all(r['equal'] for r in f_ref.values()),
                                     'c1_vs_F': c1_vs_f, 'F_vs_retained': f_ref}, indent=1) + '\n')
    print(verdict); return code


if __name__ == '__main__':
    c = sys.argv[1]
    sys.exit({'compare': lambda: compare(*sys.argv[2:9]), 'v2check': lambda: v2check(*sys.argv[2:6]), 'decide': lambda: decide(*sys.argv[2:10])}[c]())
