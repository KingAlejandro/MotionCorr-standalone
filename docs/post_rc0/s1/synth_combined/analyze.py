#!/usr/bin/env python3
"""Aggregate gathered small JSONs into tables (markdown + CSV). Run locally with NumPy.

usage: analyze.py DATA OUTDIR
DATA/comb/<cond>-sNN/<arm>/{RUN,metrics,image}.json   (arms cpu-none cpu-both cpu-double cuda-none cuda-both)
DATA/plain270|no270/<cond>-sNN/cuda-none/{RUN,image}.json
DATA/controls/<cond>-s00.json   DATA/effect270.json   DATA/v2/<tag>.json
"""
import csv, json, pathlib, sys
import numpy as np
REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO/'tools')]
from summarize_realistic_motion import paired
data, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(exist_ok=True, parents=True)
CONDS = ['dose05', 'dose1', 'dose2', 'dose4', 'outmodel', 'nonsquare', 'pedestal0', 'pedestal32', 'contrast025', 'contrast4']
ARMS = ['cpu-none', 'cpu-both', 'cuda-none', 'cuda-both', 'cpu-double']
J = lambda p: json.loads(p.read_text())


def load():
    rec = {}
    for c in CONDS:
        for s in range(10):
            n = f'{c}-s{s:02d}'
            for a in ARMS:
                d = data/'comb'/n/a
                if not (d/'RUN.json').exists(): continue
                run = J(d/'RUN.json'); m = J(d/'metrics.json') if (d/'metrics.json').exists() else None
                im = J(d/'image.json') if (d/'image.json').exists() else None
                rec[(c, s, a)] = dict(exit=run['exit'], field=m['field']['px']['rms'] if m else None,
                                      sampling=m['sampling_status'] if m else None, gconv=m['convergence']['global_converged'] if m else None, img=im)
    return rec


def imgvals(im):
    i, b = im['interior'], im['border']
    return dict(transfer=i['transfer_inband'], transfer_top=i['bands'][-1]['transfer'], frc=i['frc_inband'], relrmse=i['relrmse_inband'],
                border=b['border_rel_rms'], interior_px=b['interior_rel_rms'],
                **{f'transfer_b{k}': v['transfer'] for k, v in enumerate(i['bands'])}, **{f'frc_b{k}': v['frc'] for k, v in enumerate(i['bands'])})


def med(rec, c, a, f):
    v = [f(rec[(c, s, a)]) for s in range(10) if (c, s, a) in rec and f(rec[(c, s, a)]) is not None]
    return float(np.median(v)) if v else None


def fmt(x, k=4): return '—' if x is None else f'{x:.{k}g}'


def main():
    rec = load(); md = []
    bad = [k for k, v in rec.items() if v['exit']]
    md.append(f'native runs {len(rec)}; nonzero exits {len(bad)}')
    # per condition x arm table
    rows = []
    for c in CONDS:
        for a in ARMS:
            if not any((c, s, a) in rec for s in range(10)): continue
            r = dict(condition=c, arm=a, n=sum((c, s, a) in rec for s in range(10)), field_rms_px=med(rec, c, a, lambda v: v['field']))
            for k in ['transfer', 'transfer_b0', 'transfer_b1', 'transfer_b2', 'transfer_b3', 'frc', 'relrmse', 'interior_px', 'border']:
                r[k] = med(rec, c, a, lambda v, k=k: imgvals(v['img'])[k] if v['img'] else None)
            r['global_nonconverged'] = sum(1 for s in range(10) if (c, s, a) in rec and rec[(c, s, a)]['gconv'] is False)
            rows.append(r)
    with (out/'per_condition_arm.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    md.append('\n### Per condition and arm (median over seeds)\n\n|Condition|Arm|n|Field RMS px|Transfer in-band|T 0.01-.04|.04-.08|.08-.12|.12-.16|FRC|relRMSE|Border rel.RMS|Interior px rel.RMS|\n|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in rows:
        md.append(f"|{r['condition']}|{r['arm']}|{r['n']}|{fmt(r['field_rms_px'],5)}|{fmt(r['transfer'],4)}|{fmt(r['transfer_b0'],3)}|{fmt(r['transfer_b1'],3)}|{fmt(r['transfer_b2'],3)}|{fmt(r['transfer_b3'],3)}|{fmt(r['frc'],3)}|{fmt(r['relrmse'],4)}|{fmt(r['border'],4)}|{fmt(r['interior_px'],4)}|")
    # paired sign tests
    def pair(c, a, b, f, lower_better=True):
        xs = [(f(rec[(c, s, a)]), f(rec[(c, s, b)])) for s in range(10) if (c, s, a) in rec and (c, s, b) in rec and f(rec[(c, s, a)]) is not None and f(rec[(c, s, b)]) is not None]
        if len(xs) < 10: return None
        x, y = np.array(xs).T
        return paired(x, y) if lower_better else paired(-x, -y)
    comps = [('DC none -> both (CPU)', 'cpu-none', 'cpu-both'), ('DC none -> both (CUDA)', 'cuda-none', 'cuda-both'),
             ('CPU -> CUDA (DC none)', 'cpu-none', 'cuda-none'), ('CPU -> CUDA (DC both)', 'cpu-both', 'cuda-both')]
    metrics = [('field RMS', lambda v: v['field'], True), ('image transfer (in-band)', lambda v: imgvals(v['img'])['transfer'] if v['img'] else None, False),
               ('image relRMSE (in-band)', lambda v: imgvals(v['img'])['relrmse'] if v['img'] else None, True),
               ('border rel.RMS', lambda v: imgvals(v['img'])['border'] if v['img'] else None, True)]
    prow = []
    md.append('\n### Paired per-seed sign tests (b relative to a; "improves" = better for that metric; exact two-sided, ties |d|<=1e-9)\n\n|Condition|Comparison|Metric|wins/losses/ties|median delta|p|label|\n|---|---|---|---|---:|---:|---|')
    for c in CONDS:
        for cname, a, b in comps:
            for mname, f, lb in metrics:
                p = pair(c, a, b, f, lb)
                if not p: continue
                prow.append(dict(condition=c, comparison=cname, metric=mname, wins=p['wins'], losses=p['losses'], ties=p['ties'], median_delta=p['median_delta_px'], p=p['sign_test_two_sided_p'], label=p['interpretation']))
                md.append(f"|{c}|{cname}|{mname}|{p['wins']}/{p['losses']}/{p['ties']}|{fmt(p['median_delta_px'],3)}|{p['sign_test_two_sided_p']:.4g}|{p['interpretation']}|")
    with (out/'paired_tests.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(prow[0])); w.writeheader(); w.writerows(prow)
    # comparison with #269 published field numbers
    pub = {}
    p269 = REPO/'docs/post_rc0/s1/km_truth/accuracy_per_seed.csv'
    for r in csv.DictReader(p269.open()): pub[(r['condition'], int(r['seed']), r['arm'])] = float(r['field_rms_px'])
    arms269 = {'cpu-none': 'cpu-none', 'cpu-both': 'cpu-both', 'cuda-none': 'cuda-none', 'cuda-both': 'cuda-both', 'cpu-double': 'cpu-double'}
    md.append('\n### Field RMS versus #269 published (afba50a4-equivalent diag build; same movies)\n\n|Arm|pairs|max abs diff px|median abs diff px|bit-equal pairs|\n|---|---:|---:|---:|---:|')
    for a in ARMS:
        d = [abs(v['field']-pub[(c, s, a)]) for (c, s, aa), v in rec.items() if aa == a and v['field'] is not None and (c, s, a) in pub]
        if d: md.append(f'|{a}|{len(d)}|{max(d):.3g}|{np.median(d):.3g}|{sum(x == 0 for x in d)}|')
    (out/'tables.md').write_text('\n'.join(md)+'\n'); print('\n'.join(md[:3]))


main()
