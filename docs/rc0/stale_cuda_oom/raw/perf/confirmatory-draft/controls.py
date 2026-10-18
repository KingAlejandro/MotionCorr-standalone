#!/usr/bin/env python3
"""DRAFT controls for confirm_pairs.py (review R-D11 round 4, findings 1-3, 5, 7, 8, 10). No GPU payload.

usage: controls.py --work DIR --cpu-binary MOTIONCORR_CPU --tutorial DIR --src SRCTREE --cpus A-B
  A  products: real CPU-build trees of 4 and 3 tutorial movies, mutated copies, and synthetic 24-movie
     trees with 30- and 27-page PDFs (findings 1, 8)
  B  combine: synthetic evidence against a synthetic manifest (findings 2, 3, 7, 10)
  C  run: dry-run windows with stub payloads, a private lock file, short frozen budgets (findings 3, 5, 7)
Every case states the required outcome; the script exits non-zero if any case differs.
"""
import argparse, json, os, shutil, stat, struct, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import confirm_pairs as cp  # noqa: E402

RESULTS = []


def case(group, name, ok, detail=''):
    RESULTS.append({'group': group, 'case': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(f"[{'PASS' if ok else 'FAIL'}] {group} {name}" + (f'  ({detail})' if detail and not ok else ''))


def make_pdf(path, pages):
    subprocess.run(['gs', '-q', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pdfwrite', f'-sOutputFile={path}', '-c',
                    f'1 1 {pages} {{ pop /Helvetica findfont 12 scalefont setfont 72 72 moveto (p) show showpage }} for'],
                   check=True)


def write_mrc(path, nx=8, ny=8, nz=1, nsymbt=0, fill=0.0):
    h = bytearray(1024)
    struct.pack_into('<4i', h, 0, nx, ny, nz, 2)
    struct.pack_into('<i', h, 92, nsymbt)
    h[208:212] = b'MAP '
    h[212:214] = b'DA'
    path.write_bytes(bytes(h) + b'\0' * max(nsymbt, 0) + struct.pack(f'<{max(nx * ny * nz, 0)}f',
                                                                     *([fill] * max(nx * ny * nz, 0))))


def synthetic_tree(root, movies, pages):
    (root / 'Movies').mkdir(parents=True, exist_ok=True)
    rows = []
    for m in movies:
        stem = str(Path(m).with_suffix(''))
        write_mrc(root / (stem + '.mrc'))
        (root / (stem + '.star')).write_text('data_general\n_rlnImageSizeX 8\n')
        rows.append(f'{root}/{stem}.mrc {root}/{stem}.star 1 1.0 0.5 0.5')
    (root / 'corrected_micrographs.star').write_text(
        'data_optics\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\nopticsGroup1 1\n\n'
        'data_micrographs\nloop_\n_rlnMicrographName #1\n_rlnMicrographMetadata #2\n_rlnOpticsGroup #3\n'
        '_rlnAccumMotionTotal #4\n_rlnAccumMotionEarly #5\n_rlnAccumMotionLate #6\n' + '\n'.join(rows) + '\n')
    make_pdf(root / 'logfile.pdf', pages)


# ---------------------------------------------------------------- A
def group_a(o, work):
    tut = Path(o.tutorial)
    all_movies = cp.star_loop(tut / 'movies.star', 'data_movies', '_rlnMicrographMovieName')
    for n in (4, 3):
        movies = all_movies[:n]
        data = work / f'a-data{n}'
        (data / 'Movies').mkdir(parents=True)
        for m in movies + ['Movies/gain.mrc']:
            os.symlink(tut / m, data / m)
        star = (tut / 'movies.star').read_text().split('data_movies')[0]
        (data / 'movies.star').write_text(star + 'data_movies\n\nloop_\n_rlnMicrographMovieName #1\n'
                                          '_rlnOpticsGroup #2\n' + ''.join(f'{m} 1\n' for m in movies))
        out = work / f'a-out{n}'
        r = subprocess.run(['taskset', '-c', o.cpus, o.cpu_binary, '--i', 'movies.star', '--o', str(out) + '/',
                            '--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150',
                            '--gainref', 'Movies/gain.mrc', '--seed', '1', '--j', '16'],
                           cwd=data, capture_output=True, text=True)
        problems, pages = cp.product_problems(out, movies)
        case('A', f'real CPU product, {n} movies: complete, {cp.expected_pdf_pages(n)} pages',
             r.returncode == 0 and not problems and pages == cp.expected_pdf_pages(n),
             f'rc={r.returncode} pages={pages} problems={problems}')
    movies4 = all_movies[:4]
    base = work / 'a-out4'

    def mutated(name, change):
        t = work / f'a-mut-{name}'
        shutil.copytree(base, t)
        change(t)
        return cp.product_problems(t, movies4)[0]

    stem = str(Path(movies4[0]).with_suffix(''))

    def poke(offset, value):
        def f(t):
            p = t / (stem + '.mrc'); b = bytearray(p.read_bytes()); struct.pack_into('<i', b, offset, value)
            p.write_bytes(bytes(b))
        return f

    def joint(edit):
        def f(t):
            p = t / 'corrected_micrographs.star'; p.write_text(edit(p.read_text()))
        return f

    drop_row = lambda s: '\n'.join(l for l in s.splitlines() if not l.strip().startswith(str(base / stem)))
    no_rows = lambda s: '\n'.join(l for l in s.splitlines() if '.mrc' not in l)
    cases = [
        ('zero dimension (nx = 0)', poke(0, 0)),
        ('negative nsymbt', poke(92, -4)),
        ('truncated MRC', lambda t: os.truncate(t / (stem + '.mrc'), 4096)),
        ('per-movie STAR empty', lambda t: (t / (stem + '.star')).write_text('')),
        ('joint STAR missing one movie', joint(drop_row)),
        ('joint STAR with no rows', joint(no_rows)),
        ('joint STAR deleted', lambda t: (t / 'corrected_micrographs.star').unlink()),
        ('logfile.pdf deleted', lambda t: (t / 'logfile.pdf').unlink()),
    ]
    for name, change in cases:
        problems = mutated(name.replace(' ', '_'), change)
        case('A', f'mutation rejected: {name}', bool(problems), problems)
    movies24 = all_movies[:24]
    for pages, want_ok in ((30, True), (27, False), (24, False)):
        t = work / f'a-syn24-{pages}'
        synthetic_tree(t, movies24, pages)
        problems, got = cp.product_problems(t, movies24)
        case('A', f'synthetic 24-movie tree with a {pages}-page PDF {"accepted" if want_ok else "rejected"}',
             (not problems) == want_ok and got == pages, f'pages={got} problems={problems}')
    e10216 = ['Movies/e10216_1.mrcs', 'Movies/e10216_2.mrcs', 'Movies/e10216_3.mrcs']
    for pages, want_ok in ((6, True), (9, False)):
        t = work / f'a-syn3-{pages}'
        synthetic_tree(t, e10216, pages)
        problems, got = cp.product_problems(t, e10216)
        case('A', f'synthetic e10216 (3 movies) tree with a {pages}-page PDF {"accepted" if want_ok else "rejected"}',
             (not problems) == want_ok, f'pages={got} problems={problems}')
    case('A', 'expected pages: 24 movies -> 30, 3 movies -> 6',
         cp.expected_pdf_pages(24) == 30 and cp.expected_pdf_pages(3) == 6)


# ---------------------------------------------------------------- B
def manifest(path, n=16, windows=2, extra=None):
    m = {'status': 'CONTROL', 'venue': 'control', 'driver_sha256': cp.sha256(HERE / 'confirm_pairs.py'),
         'rule_sha256': cp.sha256(HERE / 'rule.txt'), 'binaries': {},
         'workloads': {'w': {'n': n, 'windows': windows, 'movies': [], 'args': [], 'data': '/nonexistent',
                             'inputs': {}, 'plan': [f'{a},{b},{k}' for a, b, k in cp.plan_window(n, windows)]}}}
    m.update(extra or {})
    path.write_text(json.dumps(m))
    return m


def synth_window(out, mpath, i, d_fix=0.0, spread=0.01, fail=(), drop_after=None, marker=True,
                 swap_pos=None, identity_ok=True, header_extra=None, malformed=False):
    m = json.loads(mpath.read_text())
    wd = out / 'w' / f'window{i}'
    wd.mkdir(parents=True)
    mh = cp.sha256(mpath)
    lines = [{'header': dict({'manifest_sha256': mh, 'workload': 'w', 'window': i, 'dry_run': False},
                             **(header_extra or {}))}]
    for pos, x in enumerate(m['workloads']['w']['plan'], 1):
        if drop_after is not None and pos > drop_after:
            break
        first, second, kind = x.split(',')
        if (pos, 'fail') in [(p, 'fail') for p, _ in fail]:
            arm = dict(fail)[pos]
            lines.append({'seq': 0, 'phase': 'timed', 'label': arm, 'failure': 'product', 'detail': 'synthetic'})
            lines.append({'seq': 0, 'phase': 'timed', 'label': first if arm != first else second, 'wall_s': 5.0})
            lines.append({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': 1, 'retained': False,
                          'walls': {}})
        # independent deterministic noise per arm, so d has spread around d_fix
        jit = lambda k: ((pos * k + i * 31) % 13 - 6) / 6 * spread
        walls = {'main': 5.0 + jit(7919), 'mainb': 5.0 + jit(6007), 'fix': 5.0 + jit(104729) + d_fix}
        for lab in (first, second):
            lines.append({'seq': 0, 'phase': 'timed', 'label': lab, 'rc': 0, 'wall_s': walls[lab]})
        order = f'{second},{first}' if pos == swap_pos else f'{first},{second}'
        lines.append({'pair': kind, 'position': pos, 'order': order, 'attempt': 1, 'retained': True,
                      'walls': {first: walls[first], second: walls[second]}})
        if pos == 1:
            lines.append({'identity': {'position': 1, 'identical': identity_ok,
                                       'problems': [] if identity_ok else ['1 file(s) differ']}})
    text = '\n'.join(json.dumps(x) for x in lines) + '\n'
    if malformed:
        text = text.replace('"retained": true', '"retained": tru', 1)
    (wd / 'runs.jsonl').write_text(text)
    if marker:
        (wd / 'complete.json').write_text(json.dumps({'status': 'complete', 'manifest_sha256': mh}))
    else:
        (wd / 'incomplete.json').write_text(json.dumps({'status': 'incomplete', 'reason': 'synthetic truncation'}))


def combine_label(work, name, mpath, src):
    out = work / f'b-{name}'
    res = out / 'result.json'
    r = subprocess.run([sys.executable, str(HERE / 'confirm_pairs.py'), 'combine', '--manifest', str(mpath),
                        '--workload', 'w', '--out', str(out), '--src', src, '--result', str(res)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not res.is_file():
        return None, r.stderr[-300:]
    j = json.loads(res.read_text())
    return j['label'], j


def group_b(o, work):
    def scenario(name, want, build, mextra=None, check=None):
        out = work / f'b-{name}'; out.mkdir(parents=True)
        mpath = out / 'manifest.json'
        manifest(mpath, extra=mextra)
        build(out, mpath)
        label, j = combine_label(work, name, mpath, o.src)
        ok = label == want and (check is None or check(j))
        case('B', f'{name}: {want}', ok, f'label={label} reasons={(j or {}).get("incomplete_reasons") if isinstance(j, dict) else j}')

    both = lambda **kw: (lambda out, mp: [synth_window(out, mp, i, **kw) for i in (1, 2)])
    scenario('complete-null-effect', 'PASS', both(d_fix=0.0, spread=0.004))
    scenario('complete-resolved-slowdown', 'FAIL', both(d_fix=0.2, spread=0.004))
    scenario('complete-wide-spread', 'UNRESOLVED', both(d_fix=0.02, spread=0.5))
    scenario('window-2-missing', 'INCOMPLETE', lambda out, mp: synth_window(out, mp, 1))
    scenario('window-1-truncated-no-marker', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, drop_after=5, marker=False), synth_window(out, mp, 2)))
    scenario('window-1-truncated-forged-marker', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, drop_after=5), synth_window(out, mp, 2)))
    scenario('zero-pairs', 'INCOMPLETE',
             lambda out, mp: [synth_window(out, mp, i, drop_after=0) for i in (1, 2)],
             check=lambda j: 'no confidence interval (too few pairs)' in ' '.join(j['incomplete_reasons']))
    scenario('malformed-record', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, malformed=True), synth_window(out, mp, 2)))
    scenario('order-swapped-at-one-position', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, swap_pos=3), synth_window(out, mp, 2)))
    scenario('identity-failed', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, identity_ok=False), synth_window(out, mp, 2)),
             check=lambda j: 'product identity failed' in j['incomplete_reasons'] and j['identity_failures'])
    scenario('fix-arm-product-failure (arm-dependent)', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, fail=((2, 'fix'),)), synth_window(out, mp, 2)),
             check=lambda j: j['failures_by_arm']['fix']['product'] == 1)
    scenario('two-payload-failures (recurrent)', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, fail=((2, 'main'),)), synth_window(out, mp, 2, fail=((4, 'mainb'),))))
    scenario('one-isolated-main-failure', 'PASS',
             lambda out, mp: (synth_window(out, mp, 1, fail=((2, 'main'),), spread=0.004), synth_window(out, mp, 2, spread=0.004)),
             check=lambda j: j['failures_by_arm']['main']['product'] == 1)
    scenario('dry-run-header', 'INCOMPLETE',
             lambda out, mp: (synth_window(out, mp, 1, header_extra={'dry_run': True}), synth_window(out, mp, 2)))
    # manifest missing altogether
    out = work / 'b-manifest-missing'; out.mkdir()
    label, j = combine_label(work, 'manifest-missing', out / 'absent.json', o.src)
    case('B', 'manifest-missing: INCOMPLETE (no exception)', label == 'INCOMPLETE', j)
    case('B', 'labels are exactly PASS / UNRESOLVED / FAIL / INCOMPLETE',
         all(json.loads((p / 'result.json').read_text())['label'] in ('PASS', 'UNRESOLVED', 'FAIL', 'INCOMPLETE')
             for p in work.glob('b-*') if (p / 'result.json').is_file()))


# ---------------------------------------------------------------- C
STUB = '''#!/bin/bash
# control stub payload: reproduce a template product tree at --o; behaviour from the arm name in $0
out=""; while [ $# -gt 0 ]; do [ "$1" = --o ] && out=$2; shift; done
arm=$(basename "$0")
cp -r "{template}/." "$out"
n=$(cat "{state}/count-$arm" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{state}/count-$arm"
mode=$(cat "{state}/mode-$arm" 2>/dev/null)
case "$mode" in
  product-once) [ $n -eq 5 ] && rm -f "$out/logfile.pdf" ;;
  differ) python3 -c "import sys; p=sys.argv[1]; b=bytearray(open(p,'rb').read()); b[-1]^=1; open(p,'wb').write(b)" "$out/Movies/m1.mrc" ;;
  hang-once) [ $n -eq 3 ] && sleep 600 ;;
  slow) sleep 4 ;;
esac
exit 0
'''


def group_c(o, work):
    tpl = work / 'c-template'
    movies = ['Movies/m1.tiff', 'Movies/m2.tiff', 'Movies/m3.tiff', 'Movies/m4.tiff']
    synthetic_tree(tpl, movies, cp.expected_pdf_pages(4))
    data = work / 'c-data'; data.mkdir()
    (data / 'movies.star').write_text('data_movies\nloop_\n_rlnMicrographMovieName #1\n' + '\n'.join(movies) + '\n')
    lockfile = work / 'c-private.lock'

    def setup(name, modes, budget=600, timeout=20):
        d = work / f'c-{name}'; (d / 'state').mkdir(parents=True)
        bins = {}
        for arm in ('main', 'fix'):
            p = d / arm
            p.write_text(STUB.replace('{template}', str(tpl)).replace('{state}', str(d / 'state')))
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
            bins[arm] = p
            if arm in modes:
                (d / 'state' / f'mode-{arm}').write_text(modes[arm])
        mp = d / 'manifest.json'
        m = manifest(mp, n=16, extra={'source_tree': o.src, 'budget_s': budget, 'payload_timeout_s': timeout,
                                      'binaries': {a: {'path': str(b), 'sha256': cp.sha256(b)} for a, b in bins.items()}})
        m['workloads']['w'].update(movies=movies, data=str(data), args=['--x', '1'])
        mp.write_text(json.dumps(m))
        return d, mp

    def run(d, mp, window=1, lock=True):
        cmd = [sys.executable, str(HERE / 'confirm_pairs.py'), 'run', '--manifest', str(mp), '--workload', 'w',
               '--window', str(window), '--out', str(d / 'out'), '--cpus', o.payload_cpus,
               '--runner-cpus', o.runner_cpus, '--scratch', str(d / 'scratch'), '--dry-run-inputs']
        if lock:
            cmd += ['--lock', str(lockfile)]
        t0 = time.monotonic()
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r, time.monotonic() - t0

    def lock_free():
        return subprocess.run(['flock', '-n', str(lockfile), 'true']).returncode == 0

    def no_orphans(d):
        r = subprocess.run(['pgrep', '-f', str(d)], capture_output=True, text=True)
        return r.stdout.strip() == ''

    d, mp = setup('healthy', {})
    r, _ = run(d, mp)
    wd = d / 'out' / 'w' / 'window1'
    case('C', 'healthy dry-run window completes (complete.json)', (wd / 'complete.json').is_file(), r.stdout[-300:] + r.stderr[-300:])
    case('C', 'healthy window: lock released, no orphans', lock_free() and no_orphans(d))
    run(d, mp, window=2)
    res = d / 'combined.json'
    subprocess.run([sys.executable, str(HERE / 'confirm_pairs.py'), 'combine', '--manifest', str(mp), '--workload', 'w',
                    '--out', str(d / 'out'), '--src', o.src, '--result', str(res)], capture_output=True)
    jj = json.loads(res.read_text())
    case('C', 'dry-run windows combine to INCOMPLETE (never a verdict), counts otherwise complete',
         jj['label'] == 'INCOMPLETE' and jj['pairs'] == 16 and jj['null_pairs'] == 16
         and all('dry run' in x for x in jj['incomplete_reasons']), jj['incomplete_reasons'])

    d, mp = setup('product-once', {'fix': 'product-once'})
    r, _ = run(d, mp)
    recs = [json.loads(l) for l in (d / 'out' / 'w' / 'window1' / 'runs.jsonl').read_text().splitlines()]
    fails = [x for x in recs if x.get('failure')]
    reruns = [x for x in recs if 'retained' in x and x['attempt'] == 2]
    case('C', 'exit-0 product failure on fix: classified "product", pair rerun in the same position',
         len(fails) == 1 and fails[0]['failure'] == 'product' and fails[0]['label'] == 'fix'
         and len(reruns) == 1 and (d / 'out' / 'w' / 'window1' / 'complete.json').is_file(), fails + reruns)

    d, mp = setup('identity', {'fix': 'differ'})
    r, _ = run(d, mp)
    wd = d / 'out' / 'w' / 'window1'
    recs = [json.loads(l) for l in (wd / 'runs.jsonl').read_text().splitlines()]
    ident = [x['identity'] for x in recs if 'identity' in x]
    case('C', 'identity failure recorded once, evidence kept, not retried',
         len(ident) == 1 and ident[0]['identical'] is False and (wd / 'identity-failure').is_dir(), ident)

    d, mp = setup('hang', {'main': 'hang-once'}, timeout=3)
    r, el = run(d, mp)
    recs = [json.loads(l) for l in (d / 'out' / 'w' / 'window1' / 'runs.jsonl').read_text().splitlines()]
    to = [x for x in recs if x.get('failure') == 'timeout']
    case('C', 'per-payload timeout kills and reaps the payload, pair rerun',
         len(to) == 1 and no_orphans(d) and (d / 'out' / 'w' / 'window1' / 'complete.json').is_file(), to)

    d, mp = setup('deadline', {'main': 'slow', 'fix': 'slow'}, budget=20, timeout=30)
    r, el = run(d, mp)
    inc = d / 'out' / 'w' / 'window1' / 'incomplete.json'
    case('C', 'window deadline: stops within budget, incomplete.json, lock released, no orphans',
         inc.is_file() and el < 20 + 35 and lock_free() and no_orphans(d)
         and 'deadline' in json.loads(inc.read_text())['reason'], f'elapsed {el:.0f} s; {inc.read_text() if inc.is_file() else "no marker"}')

    d, mp = setup('lock-held', {}, budget=12)
    holder = subprocess.Popen(['flock', str(lockfile), 'sleep', '40'], start_new_session=True)
    time.sleep(1)
    r, el = run(d, mp)
    os.killpg(holder.pid, 9); holder.wait()        # the whole group: sleep inherits the lock fd
    time.sleep(1)
    inc = d / 'out' / 'w' / 'window1' / 'incomplete.json'
    case('C', 'deadline covers the lock wait: incomplete, no payload started',
         inc.is_file() and 'waiting' in json.loads(inc.read_text())['reason'] and not (d / 'state' / 'count-main').exists(),
         inc.read_text() if inc.is_file() else r.stderr[-300:])

    d, mp = setup('provenance', {})
    (d / 'main').write_text((d / 'main').read_text() + '# changed after freeze\n')
    r, _ = run(d, mp)
    case('C', 'provenance mismatch (binary changed after freeze) is fatal before any resource',
         r.returncode != 0 and 'provenance check failed' in (r.stdout + r.stderr)
         and not (d / 'out').exists() and lock_free(), (r.stdout + r.stderr)[-200:])


def main():
    ap = argparse.ArgumentParser()
    for k in ('work', 'cpu-binary', 'tutorial', 'src', 'cpus', 'payload-cpus', 'runner-cpus'):
        ap.add_argument('--' + k, required=True)
    o = ap.parse_args()
    work = Path(o.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    group_a(o, work)
    group_b(o, work)
    group_c(o, work)
    n_bad = sum(not r['ok'] for r in RESULTS)
    (work / 'controls.json').write_text(json.dumps(RESULTS, indent=1))
    print(f'\n{len(RESULTS) - n_bad}/{len(RESULTS)} controls as required')
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
