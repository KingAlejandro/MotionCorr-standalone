#!/usr/bin/env python3
"""Summarise the GPU corpus pass: runs.jsonl plus the per-run --profile files.

Usage: analyse_gpu.py FAMILIES_JSON RESULTS_DIR OUT_DIR [CPU_SUMMARY_JSON]
Writes OUT_DIR/summary.json and OUT_DIR/tables.md. Standard library only.

Usable run = ok, rc 0, expected product count, and no discard flag. A flagged attempt is
reported in the filtering table and never enters a median. Medians are over unprofiled runs
of the same cell; stage figures come from --profile runs only (never mixed with unprofiled
walls). Replayed rows (one movie listed 6 times) are labelled and only used for the steady
per-movie figures and the first-movie overhead.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

MIB = 2 ** 20
GIB = 2 ** 30
# stages that hold movie input handling: decode, upload and gain/sum
INGEST_STAGES = ('session and device ingest', 'host read movie', 'allocate host sum', 'gain and sum')


def med(v):
    return st.median(v) if v else None


def fmt(v, nd=1):
    return '-' if v is None else '%.*f' % (nd, v)


def rng(v):
    return (min(v), max(v)) if v else (None, None)


def load_profile(path):
    movies, proc = [], None
    p = Path(path)
    if not p.exists():
        return movies, proc
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get('type') == 'movie':
                movies.append(r)
            elif r.get('type') == 'process':
                proc = r
    return movies, proc


def stage_ms(movie, names):
    return sum(s['wall_ms'] for s in movie['stages'] if s['name'] in names)


def main():
    fam_json, res, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cpu = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None
    fams = json.loads(fam_json.read_text())['families']
    runs = [json.loads(l) for l in (res / 'runs.jsonl').read_text().splitlines() if l.strip()]
    usable, excluded = {}, []
    for r in runs:
        k = (r['family'], r['variant'], r['cfg'], r['kind'], r['rep'])
        if r['kind'] == 'warmup':
            continue
        if r['ok'] and not r['discard']:
            usable.setdefault(k, r)
        else:
            excluded.append(r)
    by = defaultdict(list)
    for k, r in usable.items():
        by[k[:4]].append(r)
    warm = {(r['family'], r['cfg']): r for r in runs if r['kind'] == 'warmup' and r['ok']}
    failed = [r for r in runs if not r['ok']]
    summary, md = {}, []

    for fam in fams:
        fid, nm = fam['id'], len(fam['movies'])
        mpx = fam['nx'] * fam['ny'] * fam['frames'] / 1e6
        S = summary.setdefault(fid, {'mpx_frame_per_movie': mpx, 'movies': nm, 'cells': {}})
        for variant in ('auto', 'nvcomp'):
            for cfg in 'GL':
                u = by.get((fid, variant, cfg, 'unprof'), [])
                p = by.get((fid, variant, cfg, 'prof'), [])
                p0 = by.get((fid, variant, cfg, 'prof0'), [])
                rp = by.get((fid, variant, cfg, 'replay'), [])
                if not (u or p or rp):
                    continue
                c = {'n_unprof': len(u), 'n_prof': len(p), 'n_replay': len(rp)}
                w = [r['wall_s'] for r in u]
                c['wall_s'] = {'median': med(w), 'min': rng(w)[0], 'max': rng(w)[1], 'values': w}
                c['wall_per_movie_s'] = med(w) / nm if w else None
                c['user_s'] = med([r['user_s'] for r in u])
                c['sys_s'] = med([r['sys_s'] for r in u])
                c['cpu_s'] = med([r['cpu_s'] for r in u])
                c['cpu_over_wall'] = (c['cpu_s'] / c['wall_s']['median']) if w else None
                c['rss_gib'] = med([r['peak_rss_bytes'] / GIB for r in u])
                c['rss_gib_max'] = max([r['peak_rss_bytes'] / GIB for r in u], default=None)
                c['minflt'] = med([r['minflt'] for r in u])
                c['majflt'] = med([r['majflt'] for r in u])
                vp = [(r.get('vram') or {}).get('peak_process_bytes') for r in u + p + rp]
                vd = [(r.get('vram') or {}).get('peak_device_delta_bytes') for r in u + p + rp]
                c['vram_proc_mib'] = med([x / MIB for x in vp if x]) if any(vp) else None
                c['vram_proc_mib_max'] = max([x / MIB for x in vp if x], default=None)
                c['vram_dev_delta_mib'] = med([x / MIB for x in vd if x]) if any(vd) else None
                c['vram_dev_delta_mib_max'] = max([x / MIB for x in vd if x], default=None)
                wit = defaultdict(int)
                for r in u + p + rp:
                    for k, v in r['ingest_witness'].items():
                        wit[k] += v
                c['ingest_witness'] = dict(wit)
                c['foreign_cores_max'] = max([((r.get('lane') or {}).get('foreign_cores') or 0) for r in u + p + rp],
                                             default=None)
                pw = [r['wall_s'] for r in p]
                c['prof_wall_s'] = med(pw)
                if w and pw:
                    c['prof_overhead_s'] = med(pw) - med(w)
                    c['prof_overhead_pct'] = 100 * (med(pw) - med(w)) / med(w)
                p0w = [r['wall_s'] for r in p0]
                if w and p0w:
                    c['prof0_wall_s'] = med(p0w)
                    c['prof0_overhead_s'] = med(p0w) - med(w)
                # per-movie profile breakdown over profiled repetitions
                for label, recs, tagname in (('prof', p, 'prof'), ('replay', rp, 'replay')):
                    mw, stages, fixed, ing = defaultdict(list), defaultdict(lambda: defaultdict(list)), [], defaultdict(list)
                    for r in recs:
                        movies, proc = load_profile(res / 'profiles' / (r['tag'] + '.jsonl'))
                        if not movies:
                            continue
                        fixed.append(r['wall_s'] - sum(m['wall_ms'] for m in movies) / 1000.0)
                        for m in movies:
                            mw[m['index']].append(m['wall_ms'])
                            ing[m['index']].append(stage_ms(m, INGEST_STAGES))
                            for s in m['stages']:
                                stages[m['index']][s['name']].append(s['wall_ms'])
                    if not mw:
                        continue
                    n_idx = max(mw) + 1
                    d = {'outside_movies_s': med(fixed), 'run_wall_s': med([r['wall_s'] for r in recs]),
                         'movie_wall_ms': {i: med(v) for i, v in mw.items()},
                         'ingest_ms': {i: med(v) for i, v in ing.items()}, 'stages': {}}
                    # steady = median over movies 2.. of the per-movie medians (replay has 5, 2-movie families 1)
                    steady_idx = [i for i in range(1, n_idx)]
                    if steady_idx:
                        d['steady_movie_ms'] = med([d['movie_wall_ms'][i] for i in steady_idx])
                        d['steady_ingest_ms'] = med([d['ingest_ms'][i] for i in steady_idx])
                        names = {n for i in steady_idx for n in stages[i]}
                        d['steady_stages'] = sorted(
                            ((n, med([med(stages[i][n]) for i in steady_idx if n in stages[i]])) for n in names),
                            key=lambda kv: -kv[1])
                    d['first_movie_ms'] = d['movie_wall_ms'][0]
                    d['first_stages'] = sorted(((n, med(v)) for n, v in stages[0].items()), key=lambda kv: -kv[1])
                    c[label] = d
                S['cells']['%s-%s-%s' % (variant, cfg, 'x')] = c
                S['cells']['%s-%s' % (variant, cfg)] = S['cells'].pop('%s-%s-%s' % (variant, cfg, 'x'))
        if ('auto', 'L') in [(k[1], k[2]) for k in by if k[0] == fid]:
            pass

    # ------------------------------------------------------------------ tables
    def cell(fid, variant, cfg):
        return summary[fid]['cells'].get('%s-%s' % (variant, cfg))

    md.append('### 1. Unprofiled wall, CPU and memory (median [min-max] over repetitions)\n')
    md.append('Process wall for the whole run (process start, all movies, dataset report, exit). '
              'Default `--ingest auto` unless marked. CPU = user+sys of the process tree. '
              'VRAM proc = NVML per-process peak (includes the CUDA context); sampled at ~10 ms, so a lower bound.\n')
    md.append('| family | movies | cfg | n | wall s | s/movie | CPU s | CPU/wall | RSS GiB | VRAM proc MiB | VRAM dev delta MiB | minflt (M) | majflt |')
    md.append('|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for fam in fams:
        fid = fam['id']
        for variant in ('auto', 'nvcomp'):
            for cfg in 'GL':
                c = cell(fid, variant, cfg)
                if not c or not c['n_unprof']:
                    continue
                w = c['wall_s']
                lab = fam['label'] + ('' if variant == 'auto' else ' `--ingest nvcomp`')
                md.append('| %s | %d | %s | %d | %s [%s-%s] | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                    lab, summary[fid]['movies'], cfg, c['n_unprof'], fmt(w['median'], 2), fmt(w['min'], 2), fmt(w['max'], 2),
                    fmt(c['wall_per_movie_s'], 2), fmt(c['cpu_s'], 1), fmt(c['cpu_over_wall'], 2), fmt(c['rss_gib'], 2),
                    fmt(c['vram_proc_mib_max'], 0), fmt(c['vram_dev_delta_mib_max'], 0),
                    fmt(c['minflt'] / 1e6 if c['minflt'] else None, 2), fmt(c['majflt'], 0)))

    md.append('\n### 2. Ingest path that ran (`--ingest_witness`, every run of the family) and host decode\n')
    md.append('Steady = movie 2..6 of the six-row replay (labelled replay), config L. `host read movie` is the host decode/render/convert '
              'stage; the nvCOMP path has none (decode runs inside `session and device ingest`). Share = stage / steady movie wall. '
              'Share ex-retry removes `patch alignment` from the denominator for families with non-converging patches (section 8).\n')
    md.append('| family | witness (movies per path, all runs) | host read, movie 1 (ms) | session and device ingest, movie 1 (ms) | host read, steady (ms) | share of steady movie | share ex-retry | ingest group, steady (ms) | host read ms/Mpx |')
    md.append('|---|---|---:|---:|---:|---:|---:|---:|---:|')
    for fam in fams:
        fid = fam['id']
        c = cell(fid, 'auto', 'L')
        if not c:
            continue
        fs = dict((c.get('replay') or {}).get('first_stages', [])) or dict((c.get('prof') or {}).get('first_stages', []))
        rp = c.get('replay') if (c.get('replay') or {}).get('steady_stages') else (c.get('prof') or {})
        ss = dict(rp.get('steady_stages', []))
        hr, tot = ss.get('host read movie'), rp.get('steady_movie_ms')
        pa = ss.get('patch alignment', 0)
        summary[fid]['host_read_steady_ms'] = hr
        summary[fid]['host_read_share'] = hr / tot if hr is not None and tot else None
        summary[fid]['host_read_share_ex_retry'] = hr / (tot - pa) if hr is not None and tot else None
        mp = summary[fid]['mpx_frame_per_movie']
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            fam['label'], ', '.join('%s: %d' % kv for kv in sorted(c['ingest_witness'].items())) or 'NO WITNESS',
            fmt(fs.get('host read movie'), 0), fmt(fs.get('session and device ingest'), 0), fmt(hr, 0),
            '%.0f%%' % (100 * hr / tot) if hr is not None and tot else '-',
            '%.0f%%' % (100 * hr / (tot - pa)) if hr is not None and tot else '-',
            fmt(rp.get('steady_ingest_ms'), 0), fmt(hr / mp if hr is not None else None, 2)))

    md.append('\n### 3. Per-movie time from `--profile`: first movie vs steady, config L (ms)\n')
    md.append('Two-movie families: movie 1 vs movie 2 (profiled, device timing on). Replay: movie 1 vs the median of movies 2-6 of a '
              'six-row replay of movie 1 (**replayed rows, not distinct inputs**). Fixed = process wall minus the sum of movie walls.\n')
    md.append('| family | source | first movie | steady movie | first - steady | fixed outside movies (s) | process wall (s) |')
    md.append('|---|---|---:|---:|---:|---:|---:|')
    for fam in fams:
        c = cell(fam['id'], 'auto', 'L')
        if not c:
            continue
        for label, name in (('prof', '2 distinct movies'), ('replay', 'replay x6')):
            d = c.get(label)
            if not d or d.get('steady_movie_ms') is None:
                if d:
                    md.append('| %s | %s | %s | - | - | %s | %s |' % (fam['label'], name, fmt(d['first_movie_ms'], 0),
                                                                      fmt(d['outside_movies_s'], 2), fmt(d['run_wall_s'], 2)))
                continue
            md.append('| %s | %s | %s | %s | %s | %s | %s |' % (
                fam['label'], name, fmt(d['first_movie_ms'], 0), fmt(d['steady_movie_ms'], 0),
                fmt(d['first_movie_ms'] - d['steady_movie_ms'], 0), fmt(d['outside_movies_s'], 2), fmt(d['run_wall_s'], 2)))

    md.append('\n### 4. Top stages, config L, steady movie (replay where available): ms and share of the movie\n')
    md.append('| family | steady movie ms | stage 1 | stage 2 | stage 3 | stage 4 | stage 5 |')
    md.append('|---|---:|---|---|---|---|---|')
    for fam in fams:
        c = cell(fam['id'], 'auto', 'L')
        if not c:
            continue
        d = c.get('replay') if c.get('replay', {}).get('steady_stages') else c.get('prof')
        if not d or not d.get('steady_stages'):
            continue
        tot = d['steady_movie_ms']
        md.append('| %s | %s | %s |' % (fam['label'], fmt(tot, 0), ' | '.join(
            '%s %.0f (%.0f%%)' % (n, ms, 100 * ms / tot) for n, ms in d['steady_stages'][:5])))

    md.append('\n### 5. First-movie stages, config L (ms): what the first movie pays extra\n')
    md.append('| family | first movie ms | top stages (first movie) |')
    md.append('|---|---:|---|')
    for fam in fams:
        c = cell(fam['id'], 'auto', 'L')
        d = (c or {}).get('replay') or (c or {}).get('prof')
        if not d:
            continue
        md.append('| %s | %s | %s |' % (fam['label'], fmt(d['first_movie_ms'], 0), '; '.join(
            '%s %.0f' % (n, ms) for n, ms in d['first_stages'][:5])))

    md.append('\n### 6. Cost per megapixel-frame (steady movie, ms per Mpx-frame)\n')
    md.append('Mpx-frame = nx*ny*frames/1e6 (EER: grouped frames). Steady movie from the replay when present, else movie 2. '
              'Lower is cheaper. `ingest` = ingest group stages.\n')
    md.append('| family | container | Mpx-frame/movie | G steady ms/Mpx | L steady ms/Mpx | L ingest ms/Mpx | L tutorial ratio |')
    md.append('|---|---|---:|---:|---:|---:|---:|')
    tut = None
    rows6 = []
    for fam in fams:
        fid = fam['id']
        vals = {}
        for cfg in 'GL':
            c = cell(fid, 'auto', cfg)
            d = ((c or {}).get('replay') if (c or {}).get('replay', {}).get('steady_movie_ms') is not None
                 else (c or {}).get('prof')) if c else None
            vals[cfg] = (d.get('steady_movie_ms') if d else None, d.get('steady_ingest_ms') if d else None)
        mp = summary[fid]['mpx_frame_per_movie']
        l = vals['L'][0] / mp if vals['L'][0] else None
        if fid == 'tutorial':
            tut = l
        rows6.append((fam, mp, vals['G'][0] / mp if vals['G'][0] else None, l,
                      vals['L'][1] / mp if vals['L'][1] else None))
    for fam, mp, g, l, i in rows6:
        md.append('| %s | %s | %.0f | %s | %s | %s | %s |' % (
            fam['label'], fam['container'], mp, fmt(g, 1), fmt(l, 1), fmt(i, 1), fmt(l / tut if l and tut else None, 2)))
        summary[fam['id']]['ms_per_mpx_L_steady'] = l

    md.append('\n### 7. Profile overhead (profiled vs unprofiled process wall)\n')
    md.append('`--profile` records clocks/rusage at ~45 stage boundaries per movie and, with device timing on (default), '
              'synchronises each timed CUDA step. `prof0` = `--profile_device_timing 0`, config L, one run.\n')
    md.append('| family | cfg | unprof s | prof s | overhead s | overhead % | prof0 (L) s | prof0 overhead s |')
    md.append('|---|---|---:|---:|---:|---:|---:|---:|')
    for fam in fams:
        for cfg in 'GL':
            c = cell(fam['id'], 'auto', cfg)
            if c and c.get('prof_overhead_s') is not None:
                md.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
                    fam['label'], cfg, fmt(c['wall_s']['median'], 2), fmt(c['prof_wall_s'], 2), fmt(c['prof_overhead_s'], 2),
                    fmt(c['prof_overhead_pct'], 1), fmt(c.get('prof0_wall_s'), 2), fmt(c.get('prof0_overhead_s'), 2)))

    # ------------------------------------------------------------------ patch convergence (from per-movie logs)
    import gzip
    import re
    md.append('\n### 8. Patch-alignment convergence and traced device peak (per-movie logs, first usable L unprofiled run)\n')
    md.append('A patch whose first attempt reports `converged=no` takes the inherited retry path, which downloads the resident real frames to the host and '
              'repeats the patch alignment. `traced peak` = largest `Peak GPU memory allocated` line in the movie logs '
              '(device buffers of the alignment stages the code accounts for; not a process peak).\n')
    md.append('| family | movies | patches | retried (first attempt converged=no) | retry converged | traced peak MiB |')
    md.append('|---|---:|---:|---:|---:|---:|')
    for fam in fams:
        recs = by.get((fam['id'], 'auto', 'L', 'unprof'), [])
        if not recs:
            continue
        r = sorted(recs, key=lambda x: x['rep'])[0]
        f = res / 'movielogs' / (r['tag'] + '.log.gz')
        if not f.exists():
            continue
        txt = gzip.open(f, 'rt', errors='replace').read()
        blocks = re.split(r'\nPatch \(\d+, \d+\): ', txt)[1:]
        retried = rconv = 0
        for b in blocks:
            verdicts = re.findall(r'completed; converged=(yes|no)', b)
            if verdicts and verdicts[0] == 'no':
                retried += 1
                rconv += len(verdicts) > 1 and verdicts[-1] == 'yes'
        peaks = [float(x) for x in re.findall(r'Peak GPU memory allocated:\s+([\d.]+) MiB', txt)]
        S = summary[fam['id']]
        S['patches'], S['patches_retried'], S['patch_retry_converged'] = len(blocks), retried, rconv
        S['traced_peak_mib'] = max(peaks) if peaks else None
        md.append('| %s | %d | %d | %d | %d | %s |' % (fam['label'], S['movies'], len(blocks), retried, rconv,
                                                      fmt(max(peaks) if peaks else None, 0)))

    # ------------------------------------------------------------------ VRAM measured vs arithmetic estimate
    md.append('\n### 9. VRAM: measured peak on the 80 GB A100 and arithmetic estimate for smaller cards\n')
    md.append('Measured = NVML per-process peak over every run of the family (all cells; sampled, so a lower bound; includes the CUDA '
              'context). **Estimate** = 2 x one float32 movie (resident `d_Fframes` half-spectra + `d_Iframes` real frames, '
              'docs/vram_live_ranges.md) + the overhead measured on the families. It is arithmetic, not a measurement on a small card.\n')
    md.append('| family | float32 movie GiB | 2x movie GiB | measured peak GiB (G / L) | measured - 2x movie GiB | fits 24 GiB | fits 40 GiB | fits 48 GiB |')
    md.append('|---|---:|---:|---|---:|---|---|---|')
    over = []
    rows9 = []
    for fam in fams:
        fid = fam['id']
        movie = fam['nx'] * fam['ny'] * fam['frames'] * 4 / GIB
        pk = {}
        for cfg in 'GL':
            vals = []
            for variant in ('auto', 'nvcomp'):
                c = cell(fid, variant, cfg)
                if c and c.get('vram_proc_mib_max'):
                    vals.append(c['vram_proc_mib_max'])
            pk[cfg] = max(vals) / 1024 if vals else None
        top = max([v for v in pk.values() if v], default=None)
        rows9.append((fam, movie, pk, top))
        if top:
            over.append((top - 2 * movie, movie))
    for fam, movie, pk, top in rows9:
        def fit(cap):
            if not top:
                return '-'
            return 'yes' if top < 0.95 * cap else ('borderline' if top < cap else 'no')
        md.append('| %s | %.2f | %.2f | %s / %s | %s | %s | %s | %s |' % (
            fam['label'], movie, 2 * movie, fmt(pk['G'], 1), fmt(pk['L'], 1), fmt(top - 2 * movie if top else None, 2),
            fit(24), fit(40), fit(48)))
        summary[fam['id']]['vram_peak_gib'] = top
        summary[fam['id']]['movie_f32_gib'] = movie
    md.append('\n**Estimate: how many frames of each geometry fit** (same arithmetic: peak = 2 x frames x nx x ny x 4 B + that family\'s measured '
              'overhead; fits when peak < 95% of the nominal capacity; the 80 GB measurement is the only calibration).\n')
    md.append('| geometry | measured overhead GiB | max frames, 24 GiB | 40 GiB | 48 GiB | frames in the corpus movie |')
    md.append('|---|---:|---:|---:|---:|---:|')
    for fam, movie, pk, top in rows9:
        if not top:
            continue
        fr = movie / fam['frames']
        ov = top - 2 * movie
        n = [int((0.95 * cap - ov) // (2 * fr)) for cap in (24, 40, 48)]
        md.append('| %s (%dx%d) | %.2f | %d | %d | %d | %d |' % (fam['label'], fam['nx'], fam['ny'], ov, n[0], n[1], n[2], fam['frames']))
    md.append('')
    md.append('\nFit rule on the measured peak: `yes` below 95%% of the nominal capacity, `borderline` below 100%%, `no` above. '
              'The overhead (measured minus 2x movie) is %.2f to %.2f GiB across the families.\n' % (
                  min(o for o, _ in over), max(o for o, _ in over)) if over else '')

    if cpu:
        md.append('\n### 10. Context: CPU baseline on cpu64 (different host; not a speedup comparison)\n')
        md.append('CPU = `--use_own` without CUDA on cpu64 (EPYC 7763, Release, 8 CPUs, `--j 8`, L), movie 2 of the run (movie 1 for one-movie '
                  'families), from the CPU thread\'s `cpu/summary.json`. GPU = 4GPUs (EPYC 7452, A100), L, steady movie of the replay. '
                  'Both run main 116eb04a with 8 CPUs and `--j 8`. The hosts differ (EPYC 7763 vs 7452, kernel, page cache vs tmpfs), so '
                  'differences in host-decode times are not attributable to the code. No speedup is claimed.\n')
        md.append('| family | CPU L j8 movie ms | CPU ms/Mpx | CPU host read ms | GPU L steady movie ms | GPU ms/Mpx | GPU host read ms |')
        md.append('|---|---:|---:|---:|---:|---:|---:|')
        for fam in fams:
            fid = fam['id']
            cc = (cpu.get(fid) or {}).get('cells', {}).get('L-j8')
            cms = crd = None
            if cc and cc.get('movie_wall_ms'):
                i = max(cc['movie_wall_ms'], key=int)
                cms = cc['movie_wall_ms'][i]
                crd = dict((n, ms) for n, ms, _ in cc['stages'][i]).get('host read movie')
            S = summary[fid]
            g = cell(fid, 'auto', 'L') or {}
            gd = g.get('replay') if (g.get('replay') or {}).get('steady_movie_ms') is not None else (g.get('prof') or {})
            gms = gd.get('steady_movie_ms')
            mp = S['mpx_frame_per_movie']
            md.append('| %s | %s | %s | %s | %s | %s | %s |' % (
                fam['label'], fmt(cms, 0), fmt(cms / mp if cms else None, 1), fmt(crd, 0), fmt(gms, 0),
                fmt(gms / mp if gms else None, 1), fmt(S.get('host_read_steady_ms'), 0)))

    md.append('\n### Run filtering and failures\n')
    md.append('%d measured records (excluding warm-ups): %d usable arms, %d excluded attempts, %d failed runs.\n' % (
        len([r for r in runs if r['kind'] != 'warmup']), len(usable), len(excluded), len(failed)))
    if excluded or failed:
        md.append('| tag | ok | wall s | reason |')
        md.append('|---|---|---:|---|')
        for r in excluded + [x for x in failed if x not in excluded]:
            md.append('| %s | %s | %s | %s |' % (r['tag'], r['ok'], fmt(r.get('wall_s'), 1),
                                                '; '.join(r.get('discard') or []) or (r.get('error') or '')[:120]))
    out.mkdir(parents=True, exist_ok=True)
    (out / 'tables.md').write_text('\n'.join(md) + '\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=list) + '\n')
    print('\n'.join(md))


if __name__ == '__main__':
    main()
