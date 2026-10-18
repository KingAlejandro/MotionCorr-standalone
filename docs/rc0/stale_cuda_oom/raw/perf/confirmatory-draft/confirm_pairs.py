#!/usr/bin/env python3
"""DRAFT / NOT RUN. W-D11 confirmatory paired timing (tutG, e10216L) for #228 against D14.

The declared design is in rule.txt next to this file. This driver runs ONE window of one workload,
or combines a workload's finished windows. Standard library only, plus tools/profiling/lib.

  window:  confirm_pairs.py run --workload W --n N --windows K --window I --a BIN --b BIN
                                --data DIR --cpus LIST --src SRCTREE --out DIR [--gpu-uuid UUID] -- ARGS...
  combine: confirm_pairs.py combine --workload W --out DIR --src SRCTREE

Arms (labels are [a-z]+ only, so they are safe in paths and shell command lines):
  main = main 71ab841e, fix = the PR head build, mainb = the main binary under a second label.
"""
import argparse, json, math, os, re, resource, shutil, struct, subprocess, sys, threading, time
from pathlib import Path

TARGET_FRAC = 0.005          # D14 margin
NULL_PAIRS = 16              # 8 null blocks [main,mainb], [mainb,main] per workload
MAX_ATTEMPTS = 3
LABEL = re.compile(r'^[a-z]+$')
GPU_SEL = []


def plan_window(n, windows, index):
    """Run order of one window: a list of (first, second, kind).

    The workload has n/2 comparison blocks [main,fix],[fix,main] and 8 null blocks [main,mainb],
    [mainb,main], split into `windows` equal windows. Inside a window with B comparison blocks
    and K null blocks, null block j (1..K) follows comparison block ceil(j*B/K), so the last null
    block always follows the last comparison block, for every B and K.
    """
    if n % 2 or (n // 2) % windows or (NULL_PAIRS // 2) % windows:
        raise ValueError(f'n={n} cannot be split into {windows} equal balanced windows')
    b, k = n // 2 // windows, NULL_PAIRS // 2 // windows
    after = {math.ceil(j * b / k) for j in range(1, k + 1)}
    if len(after) != k or max(after) != b:
        raise ValueError('null placement failed')       # cannot happen for k <= b
    plan = []
    for blk in range(1, b + 1):
        plan += [('main', 'fix', 'AB'), ('fix', 'main', 'BA')]
        if blk in after:
            plan += [('main', 'mainb', 'null'), ('mainb', 'main', 'null')]
    return plan


def star_movies(star):
    """Movie paths of the data_movies loop (the only loop whose first column is the movie name)."""
    movies, in_movies, cols = [], False, []
    for line in Path(star).read_text().splitlines():
        t = line.strip()
        if t.startswith('data_'):
            in_movies, cols = (t == 'data_movies'), []
        elif in_movies and t.startswith('_rln'):
            cols.append(t.split()[0])
        elif in_movies and t and not t.startswith(('#', 'loop_')) and cols:
            movies.append(t.split()[cols.index('_rlnMicrographMovieName')])
    return movies


def pdf_pages(path):
    r = subprocess.run(['gs', '-q', '-dNODISPLAY', '-dNOSAFER', '-c',
                        f'({path}) (r) file runpdfbegin pdfpagecount = quit'],
                       capture_output=True, text=True, timeout=60)
    try:
        return int(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def product_problems(out, movies):
    """Complete product of one healthy job: per movie a structurally complete float MRC and a
    non-empty motion STAR, the joint STAR, and a logfile.pdf with 3 + len(movies) pages
    (three accumulated-motion plots, then one shift plot per movie). Empty list = complete."""
    problems = []
    for m in movies:
        stem = str(Path(m).with_suffix(''))
        mrc, star = out / (stem + '.mrc'), out / (stem + '.star')
        if not mrc.is_file():
            problems.append(f'{mrc.name} missing'); continue
        with mrc.open('rb') as f:
            h = f.read(1024)
        if len(h) != 1024:
            problems.append(f'{mrc.name} short header'); continue
        nx, ny, nz, mode = struct.unpack_from('<4i', h, 0)
        nsymbt = struct.unpack_from('<i', h, 92)[0]
        want = 1024 + nsymbt + nx * ny * nz * 4
        if mode != 2 or h[208:212] != b'MAP ' or mrc.stat().st_size != want:
            problems.append(f'{mrc.name} incomplete (mode {mode}, {mrc.stat().st_size} of {want} bytes)')
        if not star.is_file() or star.stat().st_size == 0:
            problems.append(f'{star.name} missing or empty')
    if not (out / 'corrected_micrographs.star').is_file():
        problems.append('joint STAR missing')
    pdf = out / 'logfile.pdf'
    pages = pdf_pages(pdf) if pdf.is_file() else None
    if pages != 3 + len(movies):
        problems.append(f'logfile.pdf pages {pages}, expected {3 + len(movies)}')
    return problems, pages


def gpu_pids():
    r = subprocess.run(['nvidia-smi'] + GPU_SEL + ['--query-compute-apps=pid', '--format=csv,noheader'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {int(x) for x in r.stdout.split() if x.strip().isdigit()}


def run_window(o, args):
    sys.path.insert(0, str(Path(o.src) / 'tools' / 'profiling'))
    from lib import identity  # noqa: E402
    bins = {'main': o.a, 'fix': o.b, 'mainb': o.a}
    assert all(LABEL.match(k) for k in bins)
    movies = star_movies(Path(o.data) / 'movies.star')
    out = Path(o.out) / f'window{o.window}'
    if out.exists():
        sys.exit(f'{out} exists: a window is run once')
    (out / 'logs').mkdir(parents=True)
    scratch = Path(os.environ.get('TMPDIR', '/tmp')) / f'wd11c-{o.workload}-w{o.window}'
    shutil.rmtree(scratch, ignore_errors=True); scratch.mkdir(parents=True)
    log = open(out / 'runs.jsonl', 'w')
    seq = [0]

    def emit(rec):
        log.write(json.dumps(rec) + '\n'); log.flush()

    def run(phase, label, keep=False):
        seq[0] += 1
        tag = f'{seq[0]:04d}-{label}'
        dst = scratch / tag
        dst.mkdir()
        before = gpu_pids()
        foreign = set() if before is not None else {-1}
        before = before or set()
        r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        with open(out / 'logs' / f'{tag}.txt', 'w') as so:
            t0 = time.monotonic()
            p = subprocess.Popen(['taskset', '-c', o.cpus, bins[label], '--i', 'movies.star',
                                  '--o', str(dst) + '/'] + args,
                                 cwd=o.data, stdout=so, stderr=subprocess.STDOUT)

            def sample():
                while p.poll() is None:
                    now = gpu_pids()
                    if now is None:
                        foreign.add(-1)
                    else:
                        foreign.update(x for x in now - before if x != p.pid)
                    time.sleep(0.25)
            th = threading.Thread(target=sample, daemon=True); th.start()
            p.wait()
            wall = time.monotonic() - t0          # payload only; the checks below are not timed
            th.join()
        r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        problems, pages = product_problems(dst, movies) if p.returncode == 0 else (['non-zero exit'], None)
        rec = {'seq': seq[0], 'phase': phase, 'label': label, 'rc': p.returncode, 'wall_s': round(wall, 4),
               'cpu_s': round((r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime), 3),
               'pdf_pages': pages, 'product_problems': problems, 'foreign_gpu_pids': sorted(foreign)}
        rec['ok'] = p.returncode == 0 and not problems and not foreign
        emit(rec)
        if not keep:
            shutil.rmtree(dst, ignore_errors=True)
        return rec, dst

    def pair(first, second, kind, pos):
        keep = pos == 1                                   # first comparison pair: product identity
        for attempt in range(1, MAX_ATTEMPTS + 1):
            (r1, d1), (r2, d2) = run('timed', first, keep), run('timed', second, keep)
            ok = r1['ok'] and r2['ok']
            emit({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': attempt,
                  'retained': ok, 'walls': {first: r1['wall_s'], second: r2['wall_s']}})
            if keep:
                if ok:
                    ident = identity.compare_trees(str(d1), str(d2))
                    emit({'identity': {k: ident[k] for k in ('identical', 'problems', 'compared', 'mrc_compared')}})
                shutil.rmtree(d1, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)
            if ok:
                return {first: r1['wall_s'], second: r2['wall_s']}
        return None

    run('warmup', 'main'); run('warmup', 'fix')          # discarded, one per arm per window
    plan = plan_window(o.n, o.windows, o.window)
    (out / 'plan.json').write_text(json.dumps([f'{a},{b}' for a, b, _ in plan]))
    for pos, (first, second, kind) in enumerate(plan, 1):
        w = pair(first, second, kind, pos)
        if w is None:
            emit({'incomplete': f'position {pos} ({kind}) failed {MAX_ATTEMPTS} attempts'})
            break
    shutil.rmtree(scratch, ignore_errors=True)
    subprocess.run(['gzip', '-r', str(out / 'logs')])


def combine(o):
    sys.path.insert(0, str(Path(o.src) / 'tools' / 'profiling'))
    from lib import stats  # noqa: E402
    comp, null, wa, wb, incomplete, windows = [], [], [], [], [], 0
    for wdir in sorted(Path(o.out).glob('window*')):
        windows += 1
        for line in (wdir / 'runs.jsonl').read_text().splitlines():
            rec = json.loads(line)
            if 'incomplete' in rec:
                incomplete.append(f'{wdir.name}: {rec["incomplete"]}')
            if not rec.get('retained'):
                continue
            w = rec['walls']
            if rec['pair'] == 'null':
                null.append(w['mainb'] - w['main'])
            else:
                comp.append({'order': rec['pair'], 'd': w['fix'] - w['main']})
                wa.append(w['main']); wb.append(w['fix'])
    d = [c['d'] for c in comp]
    lo, hi, conf = stats.median_ci(d)
    ma = stats.median(wa)
    label = ('Fail' if lo > 0 else 'Pass' if hi <= TARGET_FRAC * ma else 'Unresolved')
    if incomplete:
        label = 'Incomplete'
    ci0 = stats.median_ci(null)
    res = {'workload': o.workload, 'windows': windows, 'label_D14': label, 'incomplete': incomplete,
           'pairs': len(d), 'pairs_AB': sum(c['order'] == 'AB' for c in comp),
           'pairs_BA': sum(c['order'] == 'BA' for c in comp),
           'median_d_s': stats.median(d), 'ci95_s': [lo, hi], 'ci_confidence': conf,
           'ci_pct_of_main_wall': [100 * lo / ma, 100 * hi / ma], 'median_wall_main_s': ma,
           'median_wall_fix_s': stats.median(wb), 'iqr_main_s': stats.iqr(wa), 'iqr_fix_s': stats.iqr(wb),
           'null_pairs': len(null), 'null_median_s': stats.median(null),
           'null_ci95_s': ci0[:2] if ci0 else None, 'null_range_s': [min(null), max(null)]}
    (Path(o.out) / 'result.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    for k in ('workload', 'a', 'b', 'data', 'cpus', 'src', 'out'):
        r.add_argument('--' + k, required=True)
    for k in ('n', 'windows', 'window'):
        r.add_argument('--' + k, type=int, required=True)
    r.add_argument('--gpu-uuid', default=None)
    r.add_argument('args', nargs=argparse.REMAINDER)
    c = sub.add_parser('combine')
    for k in ('workload', 'out', 'src'):
        c.add_argument('--' + k, required=True)
    o = ap.parse_args()
    if o.cmd == 'combine':
        return combine(o)
    if o.gpu_uuid:
        GPU_SEL[:] = ['-i', o.gpu_uuid]
    run_window(o, [x for x in o.args if x != '--'])


if __name__ == '__main__':
    main()
