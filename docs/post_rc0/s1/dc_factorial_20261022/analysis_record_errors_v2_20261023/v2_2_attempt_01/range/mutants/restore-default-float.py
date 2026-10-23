#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Versioned Tier B adapter for #262 F8 / R1. See AMENDMENT_v2_2.md.

Usage: summarize_v2_2.py EVAL_DIR NEW_OUT_DIR
Exit 2: present record errors; exit 0: error-free descriptive summary, possibly
incomplete. Neither means scientific acceptance. Inputs and old outputs are read only.
"""
import hashlib
import json
import math
import statistics as st
import sys
from pathlib import Path

FORMAT = 'motioncorr-dc-tierB-record-errors/2.2'
ARMS = ['none', 'global', 'local', 'both']
ORDER = ['pedestal32', 'pedestal0', 'contrast025', 'contrast4', 'dose1', 'dose05', 'dose2', 'dose4', 'outmodel', 'nonsquare']
EXPECTED = {f'B-{c}-s{s:02d}-{b}-{a}': (c, s, b, a)
            for c in ORDER for s in range(10) for b in ['cpu', 'cuda'] for a in ARMS}
CONTROLS = {f'B-{c}-s{s:02d}-{b}-plain': (c, s, b, 'plain')
            for c in ORDER for s in range(10) for b in ['cpu', 'cuda']}
METRICS = {
    'rms': ('truth', 'field', 'px', 'rms'),
    'p95': ('truth', 'field', 'px', 'p95'),
    'max': ('truth', 'field', 'px', 'max'),
    'rms_A': ('truth', 'field', 'angstrom', 'rms'),
    'global_rms': ('truth', 'global_trajectory', 'px', 'rms'),
    'local_rms': ('truth', 'local_component', 'px', 'rms'),
    'transfer': ('image', 'interior', 'transfer_inband'),
}

def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)

def mcnemar_p(b, c): return sign_p(b, c)

def g(x, *ks):
    for k in ks:
        if x is None: return None
        x = x.get(k) if isinstance(x, dict) else None
    return x

def failure(m):
    t = m.get('truth') or {}
    conv = t.get('convergence') or {}
    comp = dict(native_exit=m['exit'] != 0,
                global_nonconverged=conv.get('global_converged') is False,
                global_ambiguous=conv.get('global_converged') is None and m['exit'] == 0,
                local_disabled=t.get('local_enabled') is False,
                outside_roi=t.get('sampling_status') == 'OUTSIDE_FIXED_ROI',
                field_distance_fail=t.get('field_distance_status') == 'FAIL')
    comp['union'] = any(v for k, v in comp.items() if k != 'global_ambiguous')
    return comp

def band_transfer(img, which):
    """check_realistic_image interior metrics: in-band transfer, or the top (0.12-0.16) band."""
    it = img['interior']
    return it['bands'][-1]['transfer'] if which == 'top' else it['transfer_inband']

def finite_number(v):
    try:
        return type(v) in (int, float) and math.isfinite(v)
    except OverflowError:
        # A JSON integer may exceed the float range used by required metrics.
        return False


def finite_float(token):
    # parse_constant does not see standard numeric tokens such as 1e999.
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f'out-of-range JSON float: {token}')
    return value


def strict_object(items):
    obj = {}
    for k, v in items:
        if k in obj:
            raise ValueError(f'duplicate JSON key: {k}')
        obj[k] = v
    return obj


def read_records(ev):
    """No last-record-wins. Retain every input hash, including malformed records."""
    directory = ev / 'B'
    if not directory.is_dir():
        raise ValueError(f'not a Tier B directory: {directory}')
    recs, audits, global_errors = {}, [], []
    owners = {}
    for path in sorted(directory.glob('*.json')):
        raw = path.read_bytes()
        audit = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                     filename_id=path.stem, reasons=[])
        reasons = audit['reasons']
        m = None
        try:
            if path.is_symlink():
                raise ValueError('symlink record input')
            m = json.loads(raw, object_pairs_hook=strict_object,
                           parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f'nonfinite JSON: {s}')))
            if not isinstance(m, dict):
                raise ValueError('record must be a JSON object')
        except (ValueError, UnicodeError) as exc:
            m = None
            reasons.append(f'malformed record: {exc}')
        declared = m.get('id') if isinstance(m, dict) else None
        audit.update(id=declared, status=m.get('status') if m else None,
                     native_exit=m.get('exit') if m else None,
                     supplied_error={k: m[k] for k in ('error', 'reason', 'errors') if m and k in m},
                     sampling=g(m, 'truth', 'sampling_status'))
        ids = {i for i in (path.stem, declared) if isinstance(i, str) and i in EXPECTED}
        ident = declared if isinstance(declared, str) else None
        spec = EXPECTED.get(ident) or CONTROLS.get(ident)
        if m is not None:
            if spec is None:
                reasons.append('unknown or missing record identity')
            elif path.stem != ident:
                reasons.append('filename/id identity mismatch')
            if spec:
                c, s, b, a = spec
                for key, value in [('backend', b), ('arm', a), ('group', f'{c}-s{s:02d}')]:
                    if m.get(key) != value:
                        reasons.append(f'identity mismatch: {key} expected {value}')
            status = m.get('status')
            if ident in CONTROLS:
                if status != 'CONTROL_ONLY' or type(m.get('exit')) is not int or m['exit'] != 0:
                    reasons.append('plain record is not successful CONTROL_ONLY')
            elif status == 'UNRUN':
                if m.get('exit') is not None and (type(m['exit']) is not int or m['exit'] != 0):
                    reasons.append('UNRUN has nonzero/invalid native exit')
                if m.get('truth') is not None or m.get('image') is not None or any(m.get(k) for k in ('error', 'errors')):
                    reasons.append('UNRUN contains evaluation data/error')
            elif status != 'EVALUATED':
                reasons.append(f'present unsuccessful/unknown evaluator status: {status!r}')
            else:
                if type(m.get('exit')) is not int or m['exit'] != 0:
                    reasons.append('EVALUATED requires integer native exit 0')
                if any(m.get(k) for k in ('error', 'errors')):
                    reasons.append('EVALUATED contains evaluator error')
                for key, expected in [('truth', 'motion-counting-metrics/2'), ('image', 'motion-image-truth/1')]:
                    if g(m, key, 'schema') != expected:
                        reasons.append(f'invalid {key} schema')
                    if g(m, key, 'error'):
                        reasons.append(f'{key} contains evaluator error')
                if g(m, 'truth', 'sampling_status') not in ('VALID', 'OUTSIDE_FIXED_ROI'):
                    reasons.append('invalid/missing sampling_status')
                if g(m, 'truth', 'field_distance_status') not in ('PASS', 'FAIL'):
                    reasons.append('invalid/missing field_distance_status')
                conv = g(m, 'truth', 'convergence')
                if not isinstance(conv, dict) or 'global_converged' not in conv or (
                        conv['global_converged'] is not None and type(conv['global_converged']) is not bool) or conv.get('error'):
                    reasons.append('invalid/missing convergence')
                if type(g(m, 'truth', 'local_enabled')) is not bool:
                    reasons.append('invalid/missing local_enabled')
                for key, ks in METRICS.items():
                    if not finite_number(g(m, *ks)):
                        reasons.append(f'nonfinite/null/missing metric: {key}')
                try:
                    top = band_transfer(m['image'], 'top')
                except (KeyError, TypeError, IndexError):
                    top = None
                if not finite_number(top):
                    reasons.append('nonfinite/null/missing metric: transfer_top')
        # Detect duplicates by both claimed and filename identities, even if bytes agree.
        for key in sorted(ids | ({ident} if ident in CONTROLS else set())):
            if key in owners:
                reasons.append(f'duplicate identity: {key}')
                for prior in owners[key]:
                    prior['reasons'].append(f'duplicate identity: {key}')
            owners.setdefault(key, []).append(audit)
        if reasons and not ids:
            global_errors.append(audit)
        audit['affected_ids'] = sorted(ids)
        audits.append(audit)
        for key in ids:
            # All colliding identities become error placeholders below, never chosen.
            recs[key] = m or {}
    for audit in audits:
        audit['state'] = 'EVALUATION_ERROR' if audit['reasons'] else audit['status']
        for key in audit['affected_ids']:
            if audit['reasons']:
                recs[key] = dict(status='EVALUATION_ERROR', exit=audit['native_exit'])
    return recs, audits, global_errors


def coverage(seeds):
    counts = dict(expected=10, present=sum(x is not None for x in seeds),
                  evaluated=0, missing=0, unrun=0, error=0)
    for x in seeds:
        state = x['status'] if x else 'MISSING'
        counts[{'MISSING': 'missing', 'EVALUATED': 'evaluated',
                'UNRUN': 'unrun', 'EVALUATION_ERROR': 'error'}[state]] += 1
    return counts


def pair_coverage(left, right):
    counts = dict(expected=10, matched=0, error=0, missing=0, unrun=0)
    for a, b in zip(left, right):
        states = [x['status'] if x else 'MISSING' for x in (a, b)]
        key = ('error' if 'EVALUATION_ERROR' in states else 'missing' if 'MISSING' in states
               else 'unrun' if 'UNRUN' in states else 'matched')
        counts[key] += 1
    return counts


def derived_error(errors, context, reason):
    errors.append(dict(context, id=len(errors), reason=reason))
    return None


def summary_median(values, errors, context):
    if not values:
        return None
    try:
        value = st.median(values)
    except OverflowError as exc:
        return derived_error(errors, context, f'median arithmetic overflow: {exc}')
    if not finite_number(value):
        return derived_error(errors, context, f'nonrepresentable median result: {value!r}')
    return value


def paired_difference(left, right, errors, context):
    try:
        value = right - left
    except OverflowError as exc:
        return derived_error(errors, context, f'subtraction arithmetic overflow: {exc}')
    if not finite_number(value):
        return derived_error(errors, context, f'nonrepresentable subtraction result: {value!r}')
    return value


def tier_b(ev):
    recs, audits, global_errors = read_records(ev)
    rows, pairs, regress = [], [], []
    derived_errors = []
    for c in ORDER:
        for backend in ['cpu', 'cuda']:
            per_arm, cell_errors = {}, {}
            for arm in ARMS:
                seeds = []
                for s in range(10):
                    m = recs.get(f'B-{c}-s{s:02d}-{backend}-{arm}')
                    if m is None: seeds.append(None); continue
                    ok = m['status'] == 'EVALUATED'
                    f = failure(m) if ok else None
                    seeds.append(dict(seed=s, id=f'B-{c}-s{s:02d}-{backend}-{arm}', status=m['status'], failure=f,
                                      rms=g(m, 'truth', 'field', 'px', 'rms') if ok else None,
                                      p95=g(m, 'truth', 'field', 'px', 'p95') if ok else None,
                                      max=g(m, 'truth', 'field', 'px', 'max') if ok else None,
                                      rms_A=g(m, 'truth', 'field', 'angstrom', 'rms') if ok else None,
                                      global_rms=g(m, 'truth', 'global_trajectory', 'px', 'rms') if ok else None,
                                      local_rms=g(m, 'truth', 'local_component', 'px', 'rms') if ok else None,
                                      transfer=band_transfer(m['image'], 'all') if ok else None,
                                      transfer_top=band_transfer(m['image'], 'top') if ok else None,
                                      wall=m.get('wall_s_unqualified'), native_exit=m.get('exit')))
                per_arm[arm] = seeds
                done = [x for x in seeds if x and x['status'] == 'EVALUATED']
                cell_error_start = len(derived_errors)
                med = lambda k: summary_median([x[k] for x in done], derived_errors,
                    dict(operation='cell_median', condition=c, backend=backend, arm=arm,
                         metric=k, input_ids=[x['id'] for x in done]))
                fails = {k: sum(1 for x in seeds if x and x['failure'] and x['failure'][k]) for k in
                         ['native_exit', 'global_nonconverged', 'global_ambiguous', 'local_disabled', 'outside_roi', 'field_distance_fail', 'union']}
                rows.append(dict(condition=c, backend=backend, arm=arm, n=len(done), n_records=sum(1 for x in seeds if x),
                                 median_rms_px=med('rms'), median_p95_px=med('p95'), worst_max_px=max((x['max'] for x in done), default=None),
                                 median_rms_A=med('rms_A'), median_global_rms_px=med('global_rms'), median_local_rms_px=med('local_rms'),
                                 median_transfer=med('transfer'), median_transfer_top=med('transfer_top'), failures=fails,
                                 coverage=coverage(seeds),
                                 error_ids=[f'B-{c}-s{x["seed"]:02d}-{backend}-{arm}' for x in seeds if x and x['status'] == 'EVALUATION_ERROR'],
                                 derived_error_ids=list(range(cell_error_start, len(derived_errors))),
                                 derived_error_count=len(derived_errors) - cell_error_start,
                                 state=('EVALUATION_ERROR' if global_errors or coverage(seeds)['error'] or len(derived_errors) > cell_error_start else
                                        'COMPLETE' if len(done) == 10 else 'IN_PROGRESS' if done else 'UNRUN'),
                                 observed_native_failures=sum(1 for x in seeds if x and type(x['native_exit']) is int and x['native_exit'] != 0)))
                cell_errors[arm] = list(range(cell_error_start, len(derived_errors)))
            for arm in ARMS[1:]:
                for metric, better in [('rms', -1), ('max', -1), ('transfer', 1), ('transfer_top', 1)]:
                    w = l = t = 0; deltas = []
                    pair_error_start = len(derived_errors)
                    matched_ids = []
                    for a, b in zip(per_arm['none'], per_arm[arm]):
                        if not a or not b or a['status'] != 'EVALUATED' or b['status'] != 'EVALUATED': continue
                        matched_ids.extend([a['id'], b['id']])
                        d = paired_difference(a[metric], b[metric], derived_errors,
                            dict(operation='paired_subtraction', condition=c, backend=backend,
                                 arm=arm, metric=metric, seed=a['seed'], input_ids=[a['id'], b['id']]))
                        deltas.append(d)
                        if d is None:
                            # Ordering can retain a regression diagnosis without inventing its delta.
                            worse = b[metric] > a[metric] if better < 0 else b[metric] < a[metric]
                            if worse:
                                regress.append(dict(condition=c, backend=backend, arm=arm, seed=a['seed'], metric=metric,
                                                    none=a[metric], arm_value=b[metric], delta=None,
                                                    derived_error_id=len(derived_errors) - 1))
                            continue
                        if d * better > 0: w += 1
                        elif d * better < 0:
                            l += 1
                            regress.append(dict(condition=c, backend=backend, arm=arm, seed=a['seed'], metric=metric,
                                                none=a[metric], arm_value=b[metric], delta=d))
                        else: t += 1
                    p = sign_p(w, l)
                    md = (summary_median(deltas, derived_errors,
                        dict(operation='paired_median', condition=c, backend=backend, arm=arm,
                             metric=metric, input_ids=matched_ids)) if all(d is not None for d in deltas) else None)
                    cat = 'improves' if p < .05 and w > l else ('harms' if p < .05 and l > w else 'neutral/mixed')
                    fb = sum(1 for a, b in zip(per_arm['none'], per_arm[arm]) if a and b and a['failure'] and b['failure'] and a['failure']['union'] and not b['failure']['union'])
                    fc = sum(1 for a, b in zip(per_arm['none'], per_arm[arm]) if a and b and a['failure'] and b['failure'] and not a['failure']['union'] and b['failure']['union'])
                    cov = pair_coverage(per_arm['none'], per_arm[arm])
                    error = bool(global_errors or cov['error'] or cell_errors['none'] or cell_errors[arm]
                                 or len(derived_errors) > pair_error_start)
                    pairs.append(dict(condition=c, backend=backend, arm=arm, metric=metric, pairs=len(deltas), wins=w, losses=l, ties=t,
                                      sign_p=None if error else p, median_delta=md, category=('EVALUATION_ERROR' if error else (cat if len(deltas) == 10 else ('IN_PROGRESS' if deltas else 'UNRUN'))),
                                      failure_fixed=fb, failure_new=fc, failure_mcnemar_p=None if error else mcnemar_p(fb, fc),
                                      finite_delta_count=sum(d is not None for d in deltas),
                                      unrepresentable_delta_count=sum(d is None for d in deltas),
                                      derived_error_ids=list(range(pair_error_start, len(derived_errors))),
                                      derived_error_count=len(derived_errors) - pair_error_start,
                                      cell_derived_error_ids=cell_errors['none'] + cell_errors[arm],
                                      coverage=cov, none_coverage=coverage(per_arm['none']), arm_coverage=coverage(per_arm[arm]),
                                      error_ids=[f'B-{c}-s{x["seed"]:02d}-{backend}-{side}' for side in ['none', arm]
                                                 for x in per_arm[side] if x and x['status'] == 'EVALUATION_ERROR']))
    return dict(format=FORMAT, rows=rows, pairs=pairs, regressions=regress,
                record_audit=audits, global_error_count=len(global_errors),
                derived_errors=derived_errors, derived_error_count=len(derived_errors),
                state=('EVALUATION_ERROR' if derived_errors or any(x['reasons'] for x in audits) else
                       'COMPLETE' if all(r['n'] == 10 for r in rows) else 'IN_PROGRESS'))

def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    ev, out = Path(sys.argv[1]), Path(sys.argv[2])
    result = tier_b(ev)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'tierB-v2.json').write_text(json.dumps(result, indent=1, allow_nan=False) + '\n')
    # A compact state/coverage view; full metrics and audit remain in versioned JSON.
    lines = ['# Tier B record-error summary v2.2', '',
             f"Summary state: {result['state']}; derived arithmetic errors: {result['derived_error_count']}.", '',
             'Descriptive only. EVALUATION_ERROR blocks inferential p-values.', '',
             '|condition|backend|arm|state|expected|evaluated|missing|UNRUN|input error|derived errors|',
             '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in result['rows']:
        c = r['coverage']
        lines.append('|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|' %
                     (r['condition'], r['backend'], r['arm'], r['state'], c['expected'],
                      c['evaluated'], c['missing'], c['unrun'], c['error'], r['derived_error_count']))
    lines += ['', 'Affected comparisons retain matched INPUT counts; W/L/T use finite deltas only.', '',
              '|condition|backend|arm|metric|matched|finite deltas|unrepresentable deltas|own derived errors|cell error references|',
              '|---|---|---|---|---:|---:|---:|---:|---:|']
    for q in result['pairs']:
        if q['derived_error_count'] or q['cell_derived_error_ids']:
            lines.append('|%s|%s|%s|%s|%s|%s|%s|%s|%s|' %
                         (q['condition'], q['backend'], q['arm'], q['metric'], q['coverage']['matched'],
                          q['finite_delta_count'], q['unrepresentable_delta_count'],
                          q['derived_error_count'], len(q['cell_derived_error_ids'])))
    (out / 'coverage.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(format=FORMAT, state=result['state'],
                         present_record_errors=sum(bool(x['reasons']) for x in result['record_audit']),
                         global_error_count=result['global_error_count'], derived_error_count=result['derived_error_count'])))
    return 2 if result['state'] == 'EVALUATION_ERROR' else 0


if __name__ == '__main__':
    sys.exit(main())
