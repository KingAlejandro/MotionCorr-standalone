#!/usr/bin/env python3
"""W-D11 paired timing on one exclusive SCARF GPU node: main vs fix, with AA nulls.

DECLARED DESIGN (fixed before any timed run; the job copies this text to rule.txt first):
  Arms      A = main 71ab841e, B = fix. Null: A vs A' (the same main binary under two labels).
  Measures  d  = wall(B) - wall(A) per comparison pair; d0 = wall(A') - wall(A) per null pair.
            Wall is CLOCK_MONOTONIC from spawn to reap of the payload.
  Per workload, in this order:
   1. Warm-up: one run of A, one of B. Discarded.
   2. PILOT: 6 comparison pairs, orders AB BA AB BA AB BA. Recorded separately (pilot.json),
      never part of the result.
   3. SIZING, from the pilot only, written to design.json before the definitive phase:
        s = 1.4826 * MAD(pilot d), M = median(pilot wall A), target T = 0.005 * M.
        Assuming a true median difference of 0, the expected upper 95% bound of median(d) is
        about 1.96 * 1.2533 * s / sqrt(N). N = smallest even number with that <= T,
        floored at 32 and capped at 128. If the cap binds, design.json says the target is not
        expected to be reachable; the cap is run anyway.
   4. DEFINITIVE, run exactly once, never extended: N comparison pairs, exactly N/2 AB and N/2 BA,
      and 16 null pairs (8 AA', 8 A'A). Run order: blocks [AB, BA]; after every k-th block
      one null block [AA', A'A], k = N/16 (N/2 blocks, 8 null blocks), the last null block
      following the last comparison block.
  Exclusion: a pair is discarded only if a run in it exits non-zero, or a recorded resource
      violation occurred (a GPU compute process that is not the payload appeared, or the GPU
      process query failed). A discarded pair is rerun immediately in the same position and
      order, up to 3 attempts; if all fail, the workload stops and is reported incomplete.
  Report, per workload: median(d), its distribution-free 95% CI
      (tools/profiling/lib/stats.median_ci), the CI upper bound as % of median wall A, the null
      median/CI/range, per-arm median and IQR, and "upper <= 0.5%" or "unresolved". No pass/fail.
  Identity: the first definitive AB pair's products are compared with
      tools/profiling/lib/identity.compare_trees (full MRC header except the writer timestamp,
      payload, path-normalised STAR/EPS).

usage: wd11_pairs.py --name W --a BIN --b BIN --data DIR --cpus LIST --src SRCTREE --out DIR -- ARGS...
"""
import argparse, json, math, os, resource, shutil, subprocess, sys, threading, time
from pathlib import Path

TARGET_FRAC = 0.005
PILOT_PAIRS, N_MIN, N_MAX, NULL_PAIRS, MAX_ATTEMPTS = 6, 32, 128, 16, 3
Z_MEDIAN = 1.96 * 1.2533


def gpu_pids():
    r = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {int(x) for x in r.stdout.split() if x.strip().isdigit()}


def size_n(s, target):
    if target <= 0:
        return N_MAX, False
    need = math.ceil((Z_MEDIAN * s / target) ** 2) if s > 0 else 0
    n = max(N_MIN, need + (need % 2))
    return min(n, N_MAX), n <= N_MAX


def main():
    ap = argparse.ArgumentParser()
    for k in ('name', 'a', 'b', 'data', 'cpus', 'src', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('args', nargs=argparse.REMAINDER)
    o = ap.parse_args()
    args = [x for x in o.args if x != '--']
    sys.path.insert(0, str(Path(o.src) / 'tools' / 'profiling'))
    from lib import stats, identity  # noqa: E402
    out = Path(o.out); out.mkdir(parents=True, exist_ok=True)
    scratch = Path(os.environ.get('TMPDIR', '/tmp')) / f'wd11-{o.name}'
    shutil.rmtree(scratch, ignore_errors=True); scratch.mkdir(parents=True)
    log = open(out / 'runs.jsonl', 'w')
    seq = [0]

    def emit(rec):
        log.write(json.dumps(rec) + '\n'); log.flush()

    def run(phase, arm, binary, keep=False):
        seq[0] += 1
        dst = scratch / f'{seq[0]:04d}-{arm}'
        dst.mkdir()
        before = gpu_pids()
        r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        t0 = time.monotonic()
        p = subprocess.Popen(['taskset', '-c', o.cpus, binary, '--i', 'movies.star', '--o', str(dst) + '/'] + args,
                             cwd=o.data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        foreign = set() if before is not None else {-1}
        before = before or set()

        def sample():                       # GPU occupancy off the timing thread
            while p.poll() is None:
                now = gpu_pids()
                if now is None:
                    foreign.add(-1)
                else:
                    foreign.update(x for x in now - before if x != p.pid)
                time.sleep(0.25)
        th = threading.Thread(target=sample, daemon=True); th.start()
        p.wait()
        wall = time.monotonic() - t0
        th.join()
        r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        rec = {'seq': seq[0], 'phase': phase, 'arm': arm, 'rc': p.returncode, 'wall_s': round(wall, 4),
               'cpu_s': round((r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime), 3),
               'foreign_gpu_pids': sorted(foreign)}
        emit(rec)
        if not keep:
            shutil.rmtree(dst, ignore_errors=True)
        return rec, dst

    def pair(phase, first, second, kind, pos, keep=False):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            r1, d1 = run(phase, *first, keep=keep)
            r2, d2 = run(phase, *second, keep=keep)
            ok = all(r['rc'] == 0 and not r['foreign_gpu_pids'] for r in (r1, r2))
            emit({'phase': phase, 'pair': kind, 'position': pos, 'order': first[0] + second[0],
                  'attempt': attempt, 'retained': ok})
            if ok:
                return {first[0]: r1['wall_s'], second[0]: r2['wall_s']}, (d1, d2)
            shutil.rmtree(d1, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)
        return None, None

    A, B, A2 = ('A', o.a), ('B', o.b), ("A'", o.a)
    run('warmup', *A); run('warmup', *B)

    # Pilot: excluded from the result.
    pilot = []
    for i in range(PILOT_PAIRS):
        first, second = (A, B) if i % 2 == 0 else (B, A)
        w, _ = pair('pilot', first, second, 'AB' if i % 2 == 0 else 'BA', i + 1)
        if w is None:
            (out / 'pilot.json').write_text(json.dumps({'incomplete': True, 'pairs': pilot}, indent=1))
            sys.exit(f'{o.name}: pilot pair {i + 1} rejected {MAX_ATTEMPTS} times')
        pilot.append({'order': 'AB' if i % 2 == 0 else 'BA', 'd': w['B'] - w['A'], 'A': w['A'], 'B': w['B']})
    pd = [p['d'] for p in pilot]
    s = 1.4826 * stats.mad(pd)
    m_pilot = stats.median([p['A'] for p in pilot])
    n, reachable = size_n(s, TARGET_FRAC * m_pilot)
    k = n // 2 // (NULL_PAIRS // 2)
    design = {'workload': o.name, 'pilot_robust_sd_s': s, 'pilot_median_wall_A_s': m_pilot,
              'target_s': TARGET_FRAC * m_pilot, 'N': n, 'N_AB': n // 2, 'N_BA': n // 2,
              'null_pairs': NULL_PAIRS, 'null_block_every_k_blocks': k,
              'expected_upper_s_at_N': Z_MEDIAN * s / math.sqrt(n),
              'target_expected_reachable': reachable}
    (out / 'pilot.json').write_text(json.dumps({'pairs': pilot, 'median_d_s': stats.median(pd),
                                                'robust_sd_s': s}, indent=1))
    (out / 'design.json').write_text(json.dumps(design, indent=1))
    print('design', json.dumps(design), flush=True)

    # Definitive: exactly once.
    comp, null, walls_a, walls_b, ident, incomplete = [], [], [], [], None, None
    plan = []
    nulls_done = 0
    for blk in range(1, n // 2 + 1):
        plan += [(A, B, 'AB'), (B, A, 'BA')]
        if blk % k == 0 and nulls_done < NULL_PAIRS // 2:
            plan += [(A, A2, 'null'), (A2, A, 'null')]; nulls_done += 1
    while nulls_done < NULL_PAIRS // 2:
        plan += [(A, A2, 'null'), (A2, A, 'null')]; nulls_done += 1
    (out / 'plan.json').write_text(json.dumps([f[0] + s_[0] for f, s_, _ in plan]))
    for pos, (first, second, kind) in enumerate(plan, 1):
        keep = ident is None and kind == 'AB'
        w, dirs = pair('definitive', first, second, kind, pos, keep)
        if w is None:
            incomplete = f'position {pos} ({kind}) rejected {MAX_ATTEMPTS} times'
            break
        if kind == 'null':
            null.append({'order': first[0] + second[0], 'd': w["A'"] - w['A']})
        else:
            comp.append({'order': kind, 'd': w['B'] - w['A'], 'A': w['A'], 'B': w['B']})
            walls_a.append(w['A']); walls_b.append(w['B'])
        if keep:
            ident = identity.compare_trees(str(dirs[0]), str(dirs[1]))
            shutil.rmtree(dirs[0], ignore_errors=True); shutil.rmtree(dirs[1], ignore_errors=True)

    d = [c['d'] for c in comp]; d0 = [x['d'] for x in null]
    ci = stats.median_ci(d) if len(d) >= stats.MIN_PAIRS else None
    ci0 = stats.median_ci(d0) if len(d0) >= stats.MIN_PAIRS else None
    ma = stats.median(walls_a) if walls_a else None
    upper_pct = 100 * ci[1] / ma if ci else None
    res = {
        'workload': o.name, 'args': args, 'cpus': o.cpus, 'design': design, 'incomplete': incomplete,
        'pairs': len(d), 'pairs_AB': sum(c['order'] == 'AB' for c in comp),
        'pairs_BA': sum(c['order'] == 'BA' for c in comp),
        'median_d_s': stats.median(d) if d else None,
        'ci95_s': ci[:2] if ci else None, 'ci_confidence': ci[2] if ci else None,
        'median_wall_A_s': ma, 'median_wall_B_s': stats.median(walls_b) if walls_b else None,
        'iqr_A_s': stats.iqr(walls_a) if len(walls_a) > 3 else None,
        'iqr_B_s': stats.iqr(walls_b) if len(walls_b) > 3 else None,
        'median_d_pct': 100 * stats.median(d) / ma if d else None,
        'ci_lower_pct': 100 * ci[0] / ma if ci else None,
        'ci_upper_pct': upper_pct,
        'reading': ('upper <= 0.5%' if upper_pct is not None and upper_pct <= 100 * TARGET_FRAC
                    else 'unresolved'),
        'null_pairs': len(d0), 'null_median_s': stats.median(d0) if d0 else None,
        'null_ci95_s': ci0[:2] if ci0 else None,
        'null_range_s': [min(d0), max(d0)] if d0 else None,
        'null_max_abs_s': max(abs(x) for x in d0) if d0 else None,
        'identity': ident, 'comparison_pairs': comp, 'null_pairs_detail': null,
    }
    (out / 'result.json').write_text(json.dumps(res, indent=1))
    shutil.rmtree(scratch, ignore_errors=True)
    print(json.dumps({k_: res[k_] for k_ in ('workload', 'incomplete', 'pairs', 'pairs_AB', 'pairs_BA',
                                             'median_d_s', 'ci95_s', 'median_d_pct', 'ci_upper_pct',
                                             'reading', 'null_median_s', 'null_ci95_s', 'null_max_abs_s',
                                             'median_wall_A_s')}))
    print('identity identical:', (ident or {}).get('identical'), (ident or {}).get('problems'))


if __name__ == '__main__':
    main()
