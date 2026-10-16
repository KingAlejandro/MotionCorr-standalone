#!/usr/bin/env python3
"""Summarise the CPU baseline: runs.jsonl plus the per-run --profile files.

Usage: analyse.py FAMILIES_JSON RESULTS_DIR OUT_DIR
Writes OUT_DIR/summary.json and OUT_DIR/tables.md (the tables embedded in README.md).
Standard library only. Flagged runs (foreign load, settle timeout) are reported, not dropped.
"""
import json
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfilter  # noqa: E402

CELLS = [(cfg, j) for cfg in 'GL' for j in (1, 4, 8)]


def med(v):
    return st.median(v) if v else None


def rng(v):
    return (min(v), max(v)) if v else (None, None)


def fmt(v, nd=1):
    return '-' if v is None else ('%.*f' % (nd, v))


def load_profile(path):
    movies, process = [], None
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get('type') == 'movie':
            movies.append(r)
        elif r.get('type') == 'process':
            process = r
    return movies, process


def main():
    fam_json, res, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    fams = json.loads(fam_json.read_text())['families']
    runs = [json.loads(l) for l in (res / 'runs.jsonl').read_text().splitlines() if l.strip()]
    summary, md = {}, []
    by = defaultdict(list)
    usable, excluded = runfilter.usable_records(runs)
    for r in usable.values():
        by[(r['family'], r['cfg'], r['j'], r['kind'])].append(r)

    for fam in fams:
        fid = fam['id']
        mpx_frame = fam['nx'] * fam['ny'] * fam['frames'] / 1e6
        S = summary.setdefault(fid, {'mpx_frame_per_movie': mpx_frame, 'cells': {}})
        for cfg, j in CELLS:
            u = [r for r in by[(fid, cfg, j, 'unprof')] if r['ok']]
            p = [r for r in by[(fid, cfg, j, 'prof')] if r['ok']]
            if not u and not p:
                continue
            nm = fam and len(fam['movies'])
            cell = {'n_unprof': len(u), 'n_prof': len(p)}
            w = [r['wall_s'] for r in u]
            cell['wall_s_median'] = med(w)
            cell['wall_s_range'] = rng(w)
            cell['wall_per_movie_s'] = med(w) / nm if w else None
            cell['wall_per_movie_range'] = tuple(x / nm for x in rng(w)) if w else (None, None)
            cell['user_s'] = med([r['user_s'] for r in u])
            cell['sys_s'] = med([r['sys_s'] for r in u])
            cell['maxrss_gib'] = med([r['maxrss_kb'] / 1048576 for r in u])
            cell['minflt'] = med([r['minflt'] for r in u])
            cell['foreign_cores_max'] = max([r['foreign_cores'] for r in u + p], default=None)
            cell['flagged'] = sum(1 for r in u + p if r['flag_foreign'])
            pw = [r['wall_s'] for r in p]
            cell['prof_wall_s_median'] = med(pw)
            if w and pw:
                cell['prof_overhead_s'] = med(pw) - med(w)
                cell['prof_overhead_pct'] = 100 * (med(pw) - med(w)) / med(w)
            # stage breakdown, per movie index, median over profile reps
            stages = {}
            subs = {}
            mw = defaultdict(list)
            outside = []
            for r in p:
                f = res / fid / ('%s-%s-j%d-prof-r%d.jsonl' % (fid, cfg, j, r['rep']))
                movies, proc = load_profile(f)
                outside.append(r['wall_s'] - sum(m['wall_ms'] for m in movies) / 1000.0)
                for m in movies:
                    mw[m['index']].append(m['wall_ms'])
                    sd = subs.setdefault(m['index'], defaultdict(list))
                    for sb in m.get('sub', []):
                        sd[sb['name']].append(sb['wall_ms'])
                    d = stages.setdefault(m['index'], defaultdict(list))
                    for s in m['stages']:
                        d[s['name']].append(s['wall_ms'])
            cell['outside_movies_s'] = med(outside)
            cell['movie_wall_ms'] = {i: med(v) for i, v in mw.items()}
            cell['subs'] = {i: {n: med(v) for n, v in d.items()} for i, d in subs.items()}
            cell['stages'] = {}
            for i, d in stages.items():
                tot = med(mw[i])
                rows = sorted(((n, med(v)) for n, v in d.items()), key=lambda kv: -kv[1])
                cell['stages'][i] = [(n, ms, 100 * ms / tot) for n, ms in rows]
            S['cells']['%s-j%d' % (cfg, j)] = cell

    # ---------- tables
    md.append('### Per-movie process wall (s), unprofiled: median [min-max]\n')
    md.append('Process wall / movies in the run (includes process start and the dataset report). n = unprofiled repetitions.\n')
    md.append('| family | movies | G j1 | G j4 | G j8 | L j1 | L j4 | L j8 | n |')
    md.append('|---|---:|---|---|---|---|---|---|---:|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        row = ['%s' % fam['label'], str(len(fam['movies']))]
        n = []
        for cfg, j in CELLS:
            c = S.get('%s-j%d' % (cfg, j))
            if c and c['wall_per_movie_s'] is not None:
                lo, hi = c['wall_per_movie_range']
                row.append('%s [%s-%s]' % (fmt(c['wall_per_movie_s']), fmt(lo), fmt(hi)))
                n.append(c['n_unprof'])
            else:
                row.append('-')
        row.append('/'.join(map(str, sorted(set(n)))) or '-')
        md.append('| ' + ' | '.join(row) + ' |')

    md.append('\n### Scaling (median wall, j1 to j4 and j8)\n')
    md.append('| family | cfg | j4 speedup | j4 eff. | j8 speedup | j8 eff. |')
    md.append('|---|---|---:|---:|---:|---:|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        for cfg in 'GL':
            c1, c4, c8 = (S.get('%s-j%d' % (cfg, j)) for j in (1, 4, 8))
            if not (c1 and c1['wall_s_median']):
                continue
            def sp(c, j):
                if c and c['wall_s_median']:
                    s = c1['wall_s_median'] / c['wall_s_median']
                    return '%.2f' % s, '%.0f%%' % (100 * s / j)
                return '-', '-'
            s4, e4 = sp(c4, 4)
            s8, e8 = sp(c8, 8)
            md.append('| %s | %s | %s | %s | %s | %s |' % (fam['label'], cfg, s4, e4, s8, e8))

    md.append('\n### Peak RSS (GiB), minor faults (millions), user+sys (s): median over unprofiled runs\n')
    md.append('| family | cfg | j1 RSS | j4 RSS | j8 RSS | j1 faults | j8 faults | j1 user+sys | j8 user+sys | j1 sys % | j8 sys % |')
    md.append('|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        for cfg in 'GL':
            cs = [S.get('%s-j%d' % (cfg, j)) for j in (1, 4, 8)]
            if not cs[0]:
                continue
            g = lambda c, k, nd, sc=1.0: fmt(c[k] / sc if c and c[k] is not None else None, nd)
            ut = lambda c: fmt((c['user_s'] + c['sys_s']) if c else None, 0)
            sy = lambda c: fmt(100 * c['sys_s'] / (c['user_s'] + c['sys_s']) if c else None, 0)
            md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                fam['label'], cfg, g(cs[0], 'maxrss_gib', 2), g(cs[1], 'maxrss_gib', 2), g(cs[2], 'maxrss_gib', 2),
                g(cs[0], 'minflt', 2, 1e6), g(cs[2], 'minflt', 2, 1e6), ut(cs[0]), ut(cs[2]), sy(cs[0]), sy(cs[2])))

    md.append('\n### Profile overhead: median profiled wall minus median unprofiled wall (process, whole run)\n')
    md.append('| family | cfg | j | n unprof / prof | unprof s | prof s | overhead s | overhead % |')
    md.append('|---|---|---:|---|---:|---:|---:|---:|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        for cfg, j in CELLS:
            c = S.get('%s-j%d' % (cfg, j))
            if c and c.get('prof_overhead_s') is not None:
                md.append('| %s | %s | %d | %d / %d | %s | %s | %s | %s |' % (
                    fam['label'], cfg, j, c['n_unprof'], c['n_prof'], fmt(c['wall_s_median']), fmt(c['prof_wall_s_median']),
                    fmt(c['prof_overhead_s'], 2), fmt(c['prof_overhead_pct'], 1)))

    md.append('\n### Time outside the per-movie stages (profiled runs): process wall minus the sum of movie walls (s)\n')
    md.append('Process start, option and STAR parsing, gain read where not in a movie, the dataset report and exit. Median over profiled runs.\n')
    md.append('| family | G j1 | G j8 | L j1 | L j8 | L j8 as % of run |')
    md.append('|---|---:|---:|---:|---:|---:|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        row = [fam['label']]
        for key in ('G-j1', 'G-j8', 'L-j1', 'L-j8'):
            c = S.get(key)
            row.append(fmt(c['outside_movies_s'], 2) if c and c.get('outside_movies_s') is not None else '-')
        c = S.get('L-j8')
        row.append(fmt(100 * c['outside_movies_s'] / c['prof_wall_s_median'], 1) if c and c.get('outside_movies_s') is not None else '-')
        md.append('| ' + ' | '.join(row) + ' |')

    md.append('\n### Top 3 stages (profiled; share of the movie wall, ms)\n')
    md.append('Movie 1 = first movie in the process; movie 2 = steady state. Median over profile repetitions.\n')
    md.append('| family | cell | n prof | movie | movie ms | top stage | 2nd | 3rd |')
    md.append('|---|---|---:|---|---:|---|---|---|')
    for fam in fams:
        S = summary[fam['id']]['cells']
        for key in ('L-j1', 'L-j8', 'G-j8'):
            c = S.get(key)
            if not c or not c['stages']:
                continue
            for i in sorted(c['stages']):
                t3 = ['%s %.0f%% (%.0f)' % (n, pct, ms) for n, ms, pct in c['stages'][i][:3]]
                md.append('| %s | %s | %d | %d | %.0f | %s |' % (fam['label'], key.replace('-', ' '), c['n_prof'], i + 1,
                                                          c['movie_wall_ms'][i], ' | '.join(t3)))

    md.append('\n### Cost per megapixel-frame (ms per Mpx-frame), steady movie from the profile\n')
    md.append('Mpx-frame = nx*ny*frames/1e6 (EER: grouped frames). Lower is cheaper per unit of data. Movie 2 where the run has two movies, else movie 1.\n')
    md.append('| family | Mpx-frame | G j1 | G j8 | L j1 | L j4 | L j8 |')
    md.append('|---|---:|---:|---:|---:|---:|---:|')
    for fam in fams:
        S = summary[fam['id']]
        row = [fam['label'], '%.0f' % S['mpx_frame_per_movie']]
        for key in ('G-j1', 'G-j8', 'L-j1', 'L-j4', 'L-j8'):
            c = S['cells'].get(key)
            if c and c['movie_wall_ms']:
                i = max(c['movie_wall_ms'])
                row.append('%.1f' % (c['movie_wall_ms'][i] / S['mpx_frame_per_movie']))
            else:
                row.append('-')
        md.append('| ' + ' | '.join(row) + ' |')

    md.append('\n### Sub-stage shares at j1 (steady movie; % of the movie wall)\n')
    md.append('Sub-stages come from the RCTIC/RCTOC markers on the main thread, so they are complete only at j1. '
              'DW = dose weighting; DW iFFT is the per-frame inverse FFT of the weighted frames; interpolation is the real-space sum.\n')
    SUBS = [('DW weight', 'dose weighting/DOSE_WEIGHTING/DW_WEIGHT'), ('DW iFFT', 'dose weighting/DOSE_WEIGHTING/DW_IFFT'),
            ('interpolation', 'dose weighting/DOSE_WEIGHTING/REAL_SPACE_INTERPOLATION'),
            ('patch FFT', 'patch alignment/PREP_PATCH/PATCH_FFT'), ('read movie', 'host read movie/READ_MOVIE')]
    md.append('| family | cfg | n prof | movie s | ' + ' | '.join(n for n, _ in SUBS) + ' |')
    md.append('|---|---|---:|---:|' + '---:|' * len(SUBS))
    for fam in fams:
        for cfg in 'GL':
            c = summary[fam['id']]['cells'].get('%s-j1' % cfg)
            if not c or not c.get('subs'):
                continue
            i = max(c['subs'])
            tot = c['movie_wall_ms'][i]
            md.append('| %s | %s | %d | %.1f | ' % (fam['label'], cfg, c['n_prof'], tot / 1000) +
                      ' | '.join('%.1f' % (100 * c['subs'][i].get(k, 0) / tot) for _, k in SUBS) + ' |')

    # per-stage cost per Mpx-frame, L j1 (steady movie): separates size from format effects
    stage_names = []
    for fam in fams:
        c = summary[fam['id']]['cells'].get('L-j1')
        if c and c['stages']:
            i = max(c['stages'])
            for n, ms, pct in c['stages'][i]:
                if pct >= 2.0 and n not in stage_names:
                    stage_names.append(n)
    md.append('\n### Stage cost per megapixel-frame, L j1, steady movie (ms per Mpx-frame)\n')
    md.append('Stages that reach 2% of a movie in any family. Rows are families; the same code and options, so differences are shape or format.\n')
    md.append('| family | ' + ' | '.join(stage_names) + ' |')
    md.append('|---|' + '---:|' * len(stage_names))
    for fam in fams:
        S = summary[fam['id']]
        c = S['cells'].get('L-j1')
        if not c or not c['stages']:
            continue
        i = max(c['stages'])
        d = {n: ms for n, ms, pct in c['stages'][i]}
        md.append('| %s | ' % fam['label'] + ' | '.join('%.1f' % (d.get(n, 0) / S['mpx_frame_per_movie']) for n in stage_names) + ' |')

    md.append('\n### Run filtering\n')
    allr = [r for r in runs if r['kind'] != 'warmup']
    md.append('%d measured run records. %d usable arms are used in the tables above; %d records are excluded '
              '(rules in `tools/runfilter.py`: foreign load or settle timeout on the lane, or CPU time more than '
              '%d%% above the cell minimum). Arms with no usable record: %d.\n' % (
                  len(allr), len(usable), len(excluded), round(100 * runfilter.CPU_SUSPECT),
                  len({runfilter.arm_key(r) for r, _ in excluded} - set(usable))))
    md.append('| family | cfg | j | kind | rep | wall s | reason |')
    md.append('|---|---|---:|---|---:|---:|---|')
    for r, why in sorted(excluded, key=lambda x: runfilter.arm_key(x[0])):
        md.append('| %s | %s | %d | %s | %d | %.1f | %s |' % (r['family'], r['cfg'], r['j'], r['kind'], r['rep'], r['wall_s'], why))
    summary['_excluded'] = [[runfilter.arm_key(r), why] for r, why in excluded]
    allr = [r for r in runs if r['kind'] == 'unprof' and r['ok']]
    raw, clean = defaultdict(list), defaultdict(list)
    for r in allr:
        raw[(r['family'], r['cfg'], r['j'])].append(r['wall_s'])
    for r in usable.values():
        if r['kind'] == 'unprof':
            clean[(r['family'], r['cfg'], r['j'])].append(r['wall_s'])
    shifts = sorted(((100 * abs(med(raw[k]) / med(clean[k]) - 1), k) for k in raw if clean.get(k)), reverse=True)
    md.append('\nSensitivity of the unprofiled medians to the exclusions: using every ok record instead of the usable ones changes a cell median by at most %.1f%% (%s); the next largest are %s.\n' % (
        shifts[0][0], '/'.join(map(str, shifts[0][1])), ', '.join('%.1f%% (%s)' % (v, '/'.join(map(str, k))) for v, k in shifts[1:4])))
    short = []
    for fam in fams:
        for cfg, j in CELLS:
            if j in fam.get('skip_j', []):
                continue
            c = summary[fam['id']]['cells'].get('%s-j%d' % (cfg, j), {})
            if c.get('n_unprof', 0) < 3 or c.get('n_prof', 0) < 2:
                short.append('%s %s j%d (%d unprof, %d prof)' % (fam['id'], cfg, j, c.get('n_unprof', 0), c.get('n_prof', 0)))
    md.append('Cells below the planned 3 unprofiled / 2 profiled usable repetitions: %d of %d. %s\n' % (
        len(short), sum(1 for fam in fams for cfg, j in CELLS if j not in fam.get('skip_j', [])), '; '.join(short)))
    summary['_short_cells'] = short
    out.mkdir(parents=True, exist_ok=True)
    (out / 'tables.md').write_text('\n'.join(md) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=list) + '\n')


if __name__ == '__main__':
    main()
