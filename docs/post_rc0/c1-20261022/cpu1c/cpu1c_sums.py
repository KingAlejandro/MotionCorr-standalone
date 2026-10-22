#!/usr/bin/env python3
"""CPU-only qualification helpers, version c (strict). Evidence readers; no GPU, no native run. Supersedes cpu1b_sums.py (never launched).

Fixed contract (not read from the inputs): 100 census identities, 10 control identities `dose1-s00..09`, 8 #267 cases. Every native RUN.json must be a JSON object whose `exit` is the integer 0
(not a bool, float or string), carry the expected binary sha256 and be bound to its fixture. Decoded sums must be non-empty and finite before they are compared; equality is exact, no tolerance.
All JSON read is parsed strictly (NaN/Infinity tokens are rejected) and all JSON written uses allow_nan=False. Any unexpected input problem is reported as invalid (compare 2, decide 5, v2check 2), never as a crash or a difference.

  cpu1c_sums.py compare CENSUS_ROOT RESULTS REF_DIR OUT IDS GROUP BINARY_SHA256   GROUP all|control; exit 0 all equal, 1 some differ (rest complete and valid), 2 incomplete/invalid
  cpu1c_sums.py v2check C1_EVAL F_EVAL PUBLISHED_EVAL OUT   K267 field metrics and checker statuses only: exactly the 8 cases, complete finite metric dictionaries, a valid checker contract, C1 == same-host F; exit 0 / 1 mismatch / 2 invalid
  cpu1c_sums.py decide CENSUS_ROOT C1_RESULTS F_RESULTS REF_DIR IDS OUT C1_SHA F_SHA   exit 0 PASS; 3 INCONCLUSIVE (host effect not excluded; the status is preserved, never an aggregate PASS); 4 FAIL; 5 incomplete/invalid

Checker contract used by v2check (from tools/check_motion_diagnostics.py): roles gate = zero, integer, fractional, affine, pedestal; characterization = noisy, flat, repeated; accuracy_status is UNIDENTIFIABLE
for flat and repeated and PASS or FAIL otherwise; the checker exits 1 when sampling_status != VALID or (role gate and FAIL), else 0; exit 2 / ABORT_NO_RESULT means no report and is rejected here.
FAIL and UNIDENTIFIABLE are valid truth outcomes (evidence), not errors; nothing requires every case to PASS.
"""
import json, math, os, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(os.environ.get('C1_SCR', '.')) / 'src/tools'))
FIXTURES = lambda: Path(os.environ.get('C1_KM_FIXTURES', '/mnt/clathrin/alex-motioncorr-km-truth/fixtures'))
EXPECT_ALL, EXPECT_CONTROL = 100, 10
CONTROL_NAMES = [f'dose1-s{i:02d}' for i in range(10)]
CASES = ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']
ROLE = {'zero': 'gate', 'integer': 'gate', 'fractional': 'gate', 'affine': 'gate', 'pedestal': 'gate', 'noisy': 'characterization', 'flat': 'characterization', 'repeated': 'characterization'}
REQUIRED_V2 = ('case', 'native_exit', 'dc', 'field_px', 'field_angstrom', 'field_gate', 'checker_exit', 'checker_status', 'sampling_status')
OPTIONAL_V2 = ('checker_message',)
MISSING = object()


class Invalid(ValueError):
    pass


def _reject(token):
    raise Invalid(f'non-finite JSON token {token}')


def load_json(path):
    return json.loads(Path(path).read_text(), parse_constant=_reject)


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, allow_nan=False) + '\n')


def is_int0(x):
    return type(x) is int and x == 0


def is_real(x):
    return type(x) in (int, float) and math.isfinite(x)


def read_sum(path):
    from motion_field import read_mrc
    return read_mrc(path)[0]


def load_ids(path):
    ids = load_json(path)
    if not isinstance(ids, dict): raise Invalid('identity file is not an object')
    for g, n in (('all', EXPECT_ALL), ('control', EXPECT_CONTROL)):
        v = ids.get(g)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v) or len(set(v)) != len(v) or v != sorted(v): raise Invalid(f'identity group {g!r} missing, not strings, duplicated or unsorted')
        if len(v) != n: raise Invalid(f'identity group {g!r} has {len(v)} entries, the fixed contract is {n}')
    if ids['control'] != CONTROL_NAMES or not set(ids['control']) <= set(ids['all']): raise Invalid('control identities are not exactly dose1-s00..09 within the full set')
    return ids


def run_ok(arm, bin_sha, name):
    """RUN.json of one native arm. Returns an error string or None."""
    try:
        r = load_json(Path(arm) / 'RUN.json')
    except (OSError, ValueError):
        return 'RUN.json missing, unreadable or not strict JSON'
    if not isinstance(r, dict): return 'RUN.json is not a JSON object'
    if not is_int0(r.get('exit')): return f'native exit {r.get("exit")!r} is not the integer 0'
    if r.get('binary_sha256') != bin_sha: return f'binary {str(r.get("binary_sha256"))[:12]} is not the expected {bin_sha[:12]}'
    try:
        want = load_json(FIXTURES() / name / 'RECEIPT.json')['files']['movie.mrcs']
    except (OSError, ValueError, KeyError, TypeError):
        return 'fixture receipt missing or malformed'
    if r.get('movie_sha256') != want: return 'run is not bound to this fixture (movie hash mismatch)'
    return None


def dirs(results_dir):
    p = Path(results_dir)
    return sorted(x.name for x in p.iterdir() if x.is_dir()) if p.is_dir() else []


def set_problems(found, expected):
    exp = set(expected)
    return {'missing': sorted(exp - set(found)), 'extra': sorted(set(found) - exp)}


def finite_sum(path):
    a = np.asarray(read_sum(path))
    if a.size == 0: raise Invalid('empty decoded sum')
    if not np.isfinite(a).all(): raise Invalid('non-finite decoded sum')
    return a


def compare_rows(root, results, ref, expected, bin_sha):
    rows = {}
    for n in expected:
        arm = Path(root) / results / n / 'cpu-none'
        row = {}
        err = run_ok(arm, bin_sha, n)
        if err: row['error'] = err
        else:
            try:
                a, b = finite_sum(arm / 'output/movie.mrc'), finite_sum(Path(ref) / n / 'cpu-none/output/movie.mrc')
                row['equal'] = bool(a.shape == b.shape and np.array_equal(a, b))
                row['max_abs_diff'] = None if a.shape != b.shape else float(np.max(np.abs(a.astype(np.float64) - b)))
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
        rows[n] = row
    return rows


def compare(root, results, ref, out, ids_path, group, bin_sha):
    try:
        ids = load_ids(ids_path); expected = ids[group]
    except (Invalid, OSError, ValueError, KeyError) as exc:
        dump_json(out, {'invalid': f'{type(exc).__name__}: {exc}'}); print('compare INVALID', exc); return 2
    sp = set_problems(dirs(Path(root) / results), expected)
    rows = compare_rows(root, results, ref, expected, bin_sha)
    s = {'group': group, 'expected': len(expected), 'present': len(dirs(Path(root) / results)), **sp, 'equal': sum(r.get('equal') is True for r in rows.values()),
         'different': sorted(n for n, r in rows.items() if r.get('equal') is False), 'errors': {n: r['error'] for n, r in rows.items() if 'error' in r}}
    code = 2 if (sp['missing'] or sp['extra'] or s['errors']) else (1 if s['different'] else 0)
    dump_json(out, {'results': results, 'reference': str(ref), 'summary': s, 'rows': rows})
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in s.items()}))
    return code


def metric_problem(d, label):
    if not isinstance(d, dict): return f'{label} is not a metric dictionary'
    for k in ('rms', 'p95', 'max'):
        if k not in d: return f'{label}.{k} is absent'
        if not is_real(d[k]) or d[k] < 0: return f'{label}.{k} is not a finite non-negative number ({d[k]!r})'
    return None


def row_problem(r, case):
    if not isinstance(r, dict): return 'row is not an object'
    miss = [k for k in REQUIRED_V2 if k not in r]
    if miss: return f'missing keys {miss}'
    if r['case'] != case: return f'case {r["case"]!r} is not {case!r}'
    if not is_int0(r['native_exit']): return f'native_exit {r["native_exit"]!r} is not the integer 0'
    if r['dc'] != 'unset': return f'dc {r["dc"]!r} is not "unset"'
    for k in ('field_px', 'field_angstrom'):
        p = metric_problem(r[k], k)
        if p: return p
    if r['field_gate'] not in ('PASS', 'FAIL'): return f'field_gate {r["field_gate"]!r}'
    st, ex, sm = r['checker_status'], r['checker_exit'], r['sampling_status']
    if st not in ('PASS', 'FAIL', 'UNIDENTIFIABLE'): return f'checker_status {st!r} is not PASS, FAIL or UNIDENTIFIABLE (ABORT_NO_RESULT means no report)'
    if sm not in ('VALID', 'OUTSIDE_FIXED_ROI'): return f'sampling_status {sm!r}'
    if type(ex) is not int or ex not in (0, 1): return f'checker_exit {ex!r} is not 0 or 1 (2 means input error: no report)'
    if (st == 'UNIDENTIFIABLE') != (case in ('flat', 'repeated')): return f'checker_status {st} inconsistent with the case signal'
    if st != 'UNIDENTIFIABLE' and st != r['field_gate']: return f'checker_status {st} disagrees with the field gate {r["field_gate"]}'
    if st == 'PASS' and sm != 'VALID': return 'PASS with sampling outside the fixed ROI'
    want = 1 if (sm != 'VALID' or (ROLE[case] == 'gate' and st == 'FAIL')) else 0
    if ex != want: return f'checker_exit {ex} does not follow the checker contract (expected {want})'
    return None


def v2check(c1, f, published, out):
    try:
        a, b, pub = load_json(c1), load_json(f), load_json(published)
    except (OSError, ValueError) as exc:
        dump_json(out, {'invalid': f'{type(exc).__name__}: {exc}'}); print('v2check INVALID', exc); return 2
    invalid, mismatch, rows = [], [], {}
    for label, rs in (('c1', a), ('f', b)):
        if not isinstance(rs, list) or len(rs) != len(CASES): invalid.append(f'{label}: not a list of exactly {len(CASES)} rows'); continue
        for case, r in zip(CASES, rs):
            p = row_problem(r, case)
            if p: invalid.append(f'{label}/{case}: {p}')
    if not invalid:
        pubm = {r.get('case'): r for r in pub if isinstance(r, dict)} if isinstance(pub, list) else {}
        for ra, rb in zip(a, b):
            same = all(ra.get(k, MISSING) == rb.get(k, MISSING) for k in (*REQUIRED_V2, *OPTIONAL_V2))
            p = pubm.get(ra['case'], {})
            rows[ra['case']] = {'c1_equals_same_host_F': same, 'checker_status': ra['checker_status'], 'checker_exit': ra['checker_exit'], 'sampling_status': ra['sampling_status'],
                                'field_gate': ra['field_gate'], 'field_equals_published_cross_host': ra['field_px'] == p.get('field_px', MISSING) and ra['field_angstrom'] == p.get('field_angstrom', MISSING),
                                'checker_status_published': p.get('checker_status')}
            if not same: mismatch.append(f'{ra["case"]}: C1 differs from same-host F')
    bad = invalid + mismatch
    dump_json(out, {'invalid': invalid, 'problems': bad, 'rows': rows, 'scope': 'K267 field metrics and checker statuses only (no image block, no signal metrics); FAIL and UNIDENTIFIABLE are valid outcomes recorded as evidence',
                    'note': 'published values are cross-host and informational; no gate or tolerance applied'})
    print('v2check', 'PASS' if not bad else 'FAIL', bad[:3])
    return 2 if invalid else (1 if mismatch else 0)


def decide(root, c1_results, f_results, ref, ids_path, out, c1_sha, f_sha):
    try:
        ids = load_ids(ids_path)
    except (Invalid, OSError, ValueError, KeyError) as exc:
        dump_json(out, {'verdict': f'INCOMPLETE: identity file invalid ({exc})'}); print('INCOMPLETE', exc); return 5
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
            a, b = finite_sum(Path(root) / c1_results / n / 'cpu-none/output/movie.mrc'), finite_sum(Path(root) / f_results / n / 'cpu-none/output/movie.mrc')
            c1_vs_f[n] = {'equal': bool(a.shape == b.shape and np.array_equal(a, b))}
        except Exception as exc:
            c1_vs_f[n] = {'error': f'{type(exc).__name__}: {exc}'}
    problems = {'c1_set': c1_sp, 'f_control_set': f_sp, 'c1_row_errors': {n: r['error'] for n, r in c1_all.items() if 'error' in r},
                'f_row_errors': {n: r['error'] for n, r in f_ref.items() if 'error' in r}, 'c1_vs_f_errors': {n: r['error'] for n, r in c1_vs_f.items() if 'error' in r}}
    complete = not (c1_sp['missing'] or c1_sp['extra'] or f_sp['missing'] or f_sp['extra'] or problems['c1_row_errors'] or problems['f_row_errors'] or problems['c1_vs_f_errors'])
    c1_eq_f = complete and all(r['equal'] for r in c1_vs_f.values())
    c1_diff = sorted(n for n, r in c1_all.items() if r.get('equal') is False)
    if not complete: verdict, code = 'INCOMPLETE: expected identities, native exits, binaries, fixture bindings or finite sums not satisfied', 5
    elif not c1_eq_f: verdict, code = 'FAIL: C1 CPU differs from the same-host frozen-F CPU control', 4
    elif c1_diff: verdict, code = 'INCONCLUSIVE: C1 differs from the retained cross-host sums but equals same-host F on the controls; host effect not excluded (status preserved; not a PASS)', 3
    else: verdict, code = 'PASS', 0
    dump_json(out, {'verdict': verdict, 'problems': problems, 'c1_vs_retained_different': c1_diff, 'control_movies': ids['control'],
                    'c1_equals_same_host_F_on_controls': c1_eq_f, 'same_host_F_equals_retained_on_controls': complete and all(r['equal'] for r in f_ref.values()),
                    'c1_vs_F': c1_vs_f, 'F_vs_retained': f_ref})
    print(verdict); return code


def main(argv):
    c = argv[1]
    try:
        return {'compare': lambda: compare(*argv[2:9]), 'v2check': lambda: v2check(*argv[2:6]), 'decide': lambda: decide(*argv[2:10])}[c]()
    except Exception as exc:                       # never a crash that reads as "differences": invalid-input exit codes
        print(f'{c}: unexpected {type(exc).__name__}: {exc}', file=sys.stderr)
        return {'compare': 2, 'v2check': 2, 'decide': 5}[c]


if __name__ == '__main__':
    sys.exit(main(sys.argv))
