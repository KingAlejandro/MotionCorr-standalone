#!/usr/bin/env python3
"""Controls for confirm_pairs.py (review R-D11 rounds 4 and 5). No GPU payload.

usage: controls.py --work DIR --cpu-binary MOTIONCORR_CPU --tutorial DIR --cpus A-B --payload-cpus L --runner-cpus L
  A  products: real CPU-build trees of 4 and 3 tutorial movies, mutated copies, and synthetic 24-movie
     trees with 30- and 27-page PDFs (findings 1, 8)
  B  combine: synthetic evidence against a synthetic manifest (findings 2, 3, 7, 10)
  C  run: dry-run windows with stub payloads, a private lock file, short frozen budgets
  D  timing: completions 25 ms apart recorded 25 +- 1 ms apart; the legacy polled wait fails the same check
  E  unit rules: completion marker after the deadline, CPU-mask rule, per-window source re-verification
Every case states the required outcome; the script exits non-zero if any case differs.
"""
import argparse, json, os, shutil, stat, statistics, struct, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
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


# ---------------------------------------------------------------- B (combine, synthetic record streams)
VENUE, UUID = 'control venue', 'GPU-control'


def manifest(path, n=16, windows=2, extra=None):
    m = {'status': 'CONTROL', 'venue': VENUE, 'gpu_uuid': UUID, 'payload_cpus': '88,89,90,91,92,93,94,95',
         'runner_cpus': '120,121,122,123', 'locks': ['/tmp/b.lock', '/tmp/g.lock'],
         'frozen_files': {f: cp.sha256(HERE / f) for f in cp.FROZEN_FILES}, 'binaries': {},
         'budget_s': 2700, 'payload_timeout_s': 120,
         'workloads': {'w': {'n': n, 'windows': windows, 'movies': [], 'args': [], 'data': '/nonexistent',
                             'expected_pdf_pages': 30, 'inputs': {},
                             'plan': [f'{a},{b},{k}' for a, b, k in cp.plan_window(n, windows)]}}}
    m.update(extra or {})
    path.write_text(json.dumps(m))
    return m


def stream(mpath, i, d_fix=0.0, spread=0.01, fail=(), warm_fail=None, identity_ok=True, dry=False):
    """A record stream in exactly the format run_window writes. fail: {position: arm} first-attempt
    product failures; warm_fail: arm whose warm-up failed."""
    m = json.loads(mpath.read_text())
    recs = [{'header': {'manifest_sha256': cp.sha256(mpath), 'workload': 'w', 'window': i, 'venue': VENUE,
                        'gpu_uuid': UUID, 'payload_cpus': m['payload_cpus'], 'runner_cpus': m['runner_cpus'],
                        'gpu_local_cpus': '0-123', 'locks': m['locks'], 'dry_run': dry,
                        'start_epoch': 1000.0, 'deadline_epoch': 3700.0}},
            {'locks_acquired_after_s': 0.0}]
    seq = [0]

    def pl(phase, label, wall, failure=None):
        seq[0] += 1
        r = {'seq': seq[0], 'phase': phase, 'label': label, 'rc': 0, 'wall_s': wall,
             'observed_mask': m['payload_cpus'], 'pdf_pages': 30}
        if failure:
            r.update(failure=failure, detail='synthetic')
        recs.append(r)
        return r
    for lab in ('main', 'fix'):
        pl('warmup', lab, 5.0, 'product' if warm_fail == lab else None)
    fail = dict(fail)
    for pos, x in enumerate(m['workloads']['w']['plan'], 1):
        first, second, kind = x.split(',')
        jit = lambda k: round(((pos * k + i * 31) % 13 - 6) / 6 * spread, 6)
        walls = {'main': 5.0 + jit(7919), 'mainb': 5.0 + jit(6007), 'fix': round(5.0 + jit(104729) + d_fix, 6)}
        attempt = 1
        if pos in fail:
            arm = fail[pos]
            r1 = pl('timed', first, walls[first], 'product' if first == arm else None)
            r2 = pl('timed', second, walls[second], 'product' if second == arm else None)
            recs.append({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': 1, 'retained': False,
                         'seqs': [r1['seq'], r2['seq']], 'walls': {first: r1['wall_s'], second: r2['wall_s']}})
            attempt = 2
        r1, r2 = pl('timed', first, walls[first]), pl('timed', second, walls[second])
        recs.append({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': attempt, 'retained': True,
                     'seqs': [r1['seq'], r2['seq']], 'walls': {first: r1['wall_s'], second: r2['wall_s']}})
        if pos == 1:
            recs.append({'identity': {'position': 1, 'identical': identity_ok, 'problems': [] if identity_ok else ['x'],
                                      'compared': 3, 'mrc_compared': 1}})
    return recs


def write_window(out, mpath, i, recs, marker=None):
    wd = out / 'w' / f'window{i}'
    wd.mkdir(parents=True, exist_ok=True)
    (wd / 'runs.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in recs))
    mk = {'status': 'complete', 'manifest_sha256': cp.sha256(mpath), 'workload': 'w', 'window': i,
          'positions': len(json.loads(mpath.read_text())['workloads']['w']['plan']), 'budget_s': 2700,
          'start_epoch': 1000.0, 'deadline_epoch': 3700.0, 'end_epoch': 3600.0, 'remaining_budget_s': 100.0,
          'released_after_s': 2600.0, 'cleanup_margin_s': 10, 'unreaped_pids': []}
    mk.update(marker or {})
    (wd / 'complete.json').write_text(json.dumps(mk))


def combine_label(out, mpath):
    res = out / 'result.json'
    r = subprocess.run([sys.executable, str(HERE / 'confirm_pairs.py'), 'combine', '--manifest', str(mpath),
                        '--workload', 'w', '--out', str(out), '--result', str(res)], capture_output=True, text=True)
    if r.returncode != 0 or not res.is_file():
        return None, {'stderr': r.stderr[-300:]}
    j = json.loads(res.read_text())
    return j['label'], j


def group_b(o, work):
    def scenario(name, want, mutate=None, n=16, gen=None, marker=None, check=None):
        out = work / f'b-{name}'; out.mkdir(parents=True)
        mpath = out / 'manifest.json'
        manifest(mpath, n=n)
        for i in (1, 2):
            recs = (gen or (lambda mp, i: stream(mp, i)))(mpath, i)
            if mutate and i == 1:
                recs = mutate(recs)
            if recs is not None:
                write_window(out, mpath, i, recs, marker if i == 1 else None)
        label, j = combine_label(out, mpath)
        ok = label == want and (check is None or check(j))
        case('B', f'{name}: {want}', ok, f'label={label} reasons={j.get("incomplete_reasons", j)}')

    is_payload = lambda r: 'phase' in r
    scenario('complete, null effect', 'PASS', gen=lambda mp, i: stream(mp, i, spread=0.004))
    scenario('complete, N=256 null effect', 'PASS', n=256, gen=lambda mp, i: stream(mp, i, spread=0.004))
    scenario('complete, resolved slowdown', 'FAIL', gen=lambda mp, i: stream(mp, i, d_fix=0.2, spread=0.004))
    scenario('complete, wide spread', 'UNRESOLVED', gen=lambda mp, i: stream(mp, i, d_fix=0.02, spread=0.5))
    # the reviewer's round-5 cases, at N=256 and on both windows
    for name, mut in (
        ('headers removed', lambda rs: [r for r in rs if 'header' not in r]),
        ('identity removed', lambda rs: [r for r in rs if 'identity' not in r]),
        ('payload records removed', lambda rs: [r for r in rs if not is_payload(r)]),
        ('every payload a resource failure', lambda rs: [dict(r, failure='resource') if is_payload(r) else r for r in rs]),
        ('record order reversed', lambda rs: rs[::-1]),
        ('retained walls differ from payloads',
         lambda rs: [dict(r, walls={k: v + 0.001 for k, v in r['walls'].items()}) if r.get('retained') else r for r in rs]),
    ):
        scenario(name, 'INCOMPLETE', n=256, gen=lambda mp, i, mut=mut: mut(stream(mp, i, spread=0.004)))
    for name, mut in (
        ('every payload reports CPU mask 0', lambda rs: [dict(r, observed_mask='0') if is_payload(r) else r for r in rs]),
        ('mask and PDF-page observations removed',
         lambda rs: [{k: v for k, v in r.items() if k not in ('observed_mask', 'pdf_pages')} if is_payload(r) else r
                     for r in rs]),
        ('header with overlapping masks and no locks',
         lambda rs: [{'header': dict(rs[0]['header'], runner_cpus='88,120', locks=[])}] + rs[1:]),
        ('identity true but with problems, zero comparisons, position 99',
         lambda rs: [{'identity': dict(r['identity'], problems=['x'], compared=0, mrc_compared=0, position=99)}
                     if 'identity' in r else r for r in rs]),
    ):
        scenario(name, 'INCOMPLETE', n=256, gen=lambda mp, i, mut=mut: mut(stream(mp, i, spread=0.004)))
    scenario('marker deadline beyond the header deadline', 'INCOMPLETE', n=256,
             gen=lambda mp, i: stream(mp, i, spread=0.004), marker={'deadline_epoch': 9700.0, 'end_epoch': 3600.0})
    scenario('marker records an unreaped process', 'INCOMPLETE', n=256, gen=lambda mp, i: stream(mp, i, spread=0.004),
             marker={'unreaped_pids': [4242]})
    scenario('window 2 missing', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i) if i == 1 else None)
    scenario('window 1 truncated', 'INCOMPLETE', mutate=lambda rs: rs[:len(rs) // 2])
    scenario('zero pairs', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i)[:4],
             check=lambda j: 'no confidence interval (too few pairs)' in ' '.join(j['incomplete_reasons']))
    scenario('malformed record', 'INCOMPLETE', mutate=lambda rs: rs[:5] + ['{not json'] + rs[5:])
    scenario('one position in the wrong order', 'INCOMPLETE',
             mutate=lambda rs: [dict(r, order=','.join(r['order'].split(',')[::-1])) if r.get('position') == 3 else r
                                for r in rs])
    scenario('identity failed', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i, identity_ok=(i == 2)),
             check=lambda j: any('identity' in x for x in j['incomplete_reasons']))
    scenario('dry-run header', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i, dry=(i == 1)))
    scenario('header for another venue', 'INCOMPLETE',
             mutate=lambda rs: [{'header': dict(rs[0]['header'], venue='elsewhere')}] + rs[1:])
    scenario('warm-up failure (fix)', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i, warm_fail='fix' if i == 1 else None))
    scenario('fix-arm product failure (arm-dependent)', 'INCOMPLETE',
             gen=lambda mp, i: stream(mp, i, spread=0.004, fail={2: 'fix'} if i == 1 else {}),
             check=lambda j: j['attempts_and_failures_by_arm']['fix']['product'] == 1)
    scenario('two payload failures (recurrent)', 'INCOMPLETE',
             gen=lambda mp, i: stream(mp, i, spread=0.004, fail={2: 'main'} if i == 1 else {4: 'mainb'}))
    scenario('one isolated main failure', 'PASS',
             gen=lambda mp, i: stream(mp, i, spread=0.004, fail={2: 'main'} if i == 1 else {}),
             check=lambda j: j['attempts_and_failures_by_arm']['main']['product'] == 1)
    scenario('marker with negative remaining budget', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i, spread=0.004),
             marker={'remaining_budget_s': -2.0})
    scenario('marker written after the deadline', 'INCOMPLETE', gen=lambda mp, i: stream(mp, i, spread=0.004),
             marker={'end_epoch': 3702.0})
    out = work / 'b-manifest missing'; out.mkdir()
    label, j = combine_label(out, out / 'absent.json')
    case('B', 'manifest missing: INCOMPLETE (no exception)', label == 'INCOMPLETE', j)
    case('B', 'labels are exactly PASS / UNRESOLVED / FAIL / INCOMPLETE',
         all(json.loads((p / 'result.json').read_text())['label'] in ('PASS', 'UNRESOLVED', 'FAIL', 'INCOMPLETE')
             for p in work.glob('b-*') if (p / 'result.json').is_file()))


# ---------------------------------------------------------------- C (run, dry-run windows with stubs)
STUB = '''#!/bin/bash
# control stub payload: reproduce a template product tree at --o; behaviour from the arm name in $0
out=""; while [ $# -gt 0 ]; do [ "$1" = --o ] && out=$2; shift; done
arm=$(basename "$0")
n=$(cat "{state}/count-$arm" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{state}/count-$arm"
mode=$(cat "{state}/mode-$arm" 2>/dev/null)
sleep 0.2
cp -r "{template}/." "$out"
case "$mode" in
  product-once) [ $n -eq 5 ] && rm -f "$out/logfile.pdf" ;;
  warmup-product) [ $n -eq 1 ] && rm -f "$out/logfile.pdf" ;;
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
        m = manifest(mp, n=16, extra={'budget_s': budget, 'payload_timeout_s': timeout, 'gpu_uuid': None,
                                      'payload_cpus': cp.fmt_cpus(cp.parse_cpus(o.payload_cpus)),
                                      'runner_cpus': cp.fmt_cpus(cp.parse_cpus(o.runner_cpus)), 'locks': [str(lockfile)],
                                      'binaries': {a: {'path': str(b), 'sha256': cp.sha256(b)} for a, b in bins.items()}})
        m['workloads']['w'].update(movies=movies, data=str(data), args=['--x', '1'],
                                   expected_pdf_pages=cp.expected_pdf_pages(len(movies)))
        mp.write_text(json.dumps(m))
        return d, mp

    def run(d, mp, window=1, path_stub=None, extra=()):
        cmd = [sys.executable, '-B', str(HERE / 'confirm_pairs.py'), 'run', '--manifest', str(mp), '--workload', 'w',
               '--window', str(window), '--out', str(d / 'out'), '--scratch', str(d / 'scratch'), '--dry-run-inputs',
               *extra]
        env = dict(os.environ)
        if path_stub:                                     # e.g. a slow gs or rm earlier on PATH
            env['PATH'] = f'{path_stub}:{env["PATH"]}'
        t0 = time.monotonic()
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return r, time.monotonic() - t0

    lock_free = lambda: subprocess.run(['flock', '-n', str(lockfile), 'true']).returncode == 0
    no_orphans = lambda d: subprocess.run(['pgrep', '-f', str(d)], capture_output=True, text=True).stdout.strip() == ''
    recs_of = lambda d, i=1: [json.loads(l) for l in (d / 'out' / 'w' / f'window{i}' / 'runs.jsonl').read_text().splitlines()]

    d, mp = setup('healthy', {})
    r, _ = run(d, mp)
    run(d, mp, window=2)
    wd = d / 'out' / 'w' / 'window1'
    timed = [x for x in recs_of(d) if x.get('phase') == 'timed']
    case('C', 'healthy dry-run windows complete; lock released; no orphans',
         (wd / 'complete.json').is_file() and (d / 'out' / 'w' / 'window2' / 'complete.json').is_file()
         and lock_free() and no_orphans(d), r.stdout[-300:] + r.stderr[-300:])
    case('C', 'every timed payload has an observed CPU mask equal to the payload mask',
         timed and all(x.get('observed_mask') == cp.fmt_cpus(cp.parse_cpus(o.payload_cpus)) for x in timed),
         timed[:1])
    res = d / 'combined.json'
    subprocess.run([sys.executable, str(HERE / 'confirm_pairs.py'), 'combine', '--manifest', str(mp), '--workload', 'w',
                    '--out', str(d / 'out'), '--result', str(res)], capture_output=True)
    jj = json.loads(res.read_text())
    case('C', "real driver streams pass the sequence validation; only the dry-run flag makes them INCOMPLETE",
         jj['label'] == 'INCOMPLETE' and jj['pairs'] == 16 and jj['null_pairs'] == 16
         and all('dry run' in x for x in jj['incomplete_reasons']), jj['incomplete_reasons'])

    d, mp = setup('product-once', {'fix': 'product-once'})
    run(d, mp)
    recs = recs_of(d)
    fails = [x for x in recs if x.get('failure')]
    reruns = [x for x in recs if 'retained' in x and x['attempt'] == 2]
    case('C', 'exit-0 product failure on fix: classified "product", pair rerun in the same position',
         len(fails) == 1 and fails[0]['failure'] == 'product' and fails[0]['label'] == 'fix'
         and len(reruns) == 1 and (d / 'out' / 'w' / 'window1' / 'complete.json').is_file(), fails + reruns)

    d, mp = setup('warmup-fail', {'fix': 'warmup-product'})
    run(d, mp)
    inc = d / 'out' / 'w' / 'window1' / 'incomplete.json'
    case('C', 'unsuccessful warm-up ends the window as incomplete',
         inc.is_file() and 'warm-up fix failed' in json.loads(inc.read_text())['reason'] and lock_free(),
         inc.read_text() if inc.is_file() else 'no marker')

    d, mp = setup('identity', {'fix': 'differ'})
    run(d, mp)
    ident = [x['identity'] for x in recs_of(d) if 'identity' in x]
    case('C', 'identity failure recorded once, evidence kept, not retried',
         len(ident) == 1 and ident[0]['identical'] is False and (d / 'out' / 'w' / 'window1' / 'identity-failure').is_dir(),
         ident)

    d, mp = setup('hang', {'main': 'hang-once'}, timeout=3)
    run(d, mp)
    to = [x for x in recs_of(d) if x.get('failure') == 'timeout']
    case('C', 'watchdog kills and reaps a hung payload at the per-payload timeout; pair rerun',
         len(to) == 1 and 3.0 <= to[0]['wall_s'] < 4.0 and no_orphans(d)
         and (d / 'out' / 'w' / 'window1' / 'complete.json').is_file(), to)

    d, mp = setup('deadline', {'main': 'slow', 'fix': 'slow'}, budget=20, timeout=30)
    r, el = run(d, mp)
    inc = d / 'out' / 'w' / 'window1' / 'incomplete.json'
    case('C', 'window deadline: payload killed at the deadline, incomplete, lock released, no orphans',
         inc.is_file() and el < 20 + 10 and lock_free() and no_orphans(d)
         and not (d / 'out' / 'w' / 'window1' / 'complete.json').exists(),
         f'elapsed {el:.1f} s; {inc.read_text() if inc.is_file() else "no marker"}')

    d, mp = setup('lock-held', {}, budget=12)
    holder = subprocess.Popen(['flock', str(lockfile), 'sleep', '40'], start_new_session=True)
    time.sleep(1)
    r, el = run(d, mp)
    os.killpg(holder.pid, 9); holder.wait(); time.sleep(1)
    inc = d / 'out' / 'w' / 'window1' / 'incomplete.json'
    case('C', 'deadline covers the lock wait: incomplete, no payload started',
         inc.is_file() and 'waiting' in json.loads(inc.read_text())['reason'] and not (d / 'state' / 'count-main').exists(),
         inc.read_text() if inc.is_file() else r.stderr[-300:])

    # Each window budget (here 15 s, standing for 2700 s) must contain the cleanup: work ends at
    # budget - CLEANUP_MARGIN_S and the locks are released by the budget.
    for name, tools, extra in (('delayed product check', ('gs',), ()), ('delayed cleanup', ('rm',), ()),
                               ('aggregate release: pending samplers and a stalled registered child',
                                ('gs', 'mpstat', 'nvidia-smi'), ('--samplers',))):
        d, mp = setup(name.split(':')[0].replace(' ', '-'), {}, budget=15)
        stub_dir = d / 'slowbin'; stub_dir.mkdir()
        for tool in tools:
            (stub_dir / tool).write_text(f'#!/bin/sh\nexec sleep 1000 # slow {tool} for {d}\n')
            (stub_dir / tool).chmod(0o755)
        r, el = run(d, mp, path_stub=stub_dir, extra=extra)
        wd = d / 'out' / 'w' / 'window1'
        inc = wd / 'incomplete.json'
        mk = json.loads(inc.read_text()) if inc.is_file() else {}
        case('C', f'{name}: locks released within the 15 s budget (cleanup inside it), INCOMPLETE, no orphans',
             inc.is_file() and not (wd / 'complete.json').exists() and mk.get('released_after_s', 1e9) <= 15
             and mk.get('remaining_budget_s', -1) >= 0 and mk.get('unreaped_pids') == [] and lock_free()
             and no_orphans(d), f'elapsed {el:.1f} s, marker {mk}')

    d, mp = setup('provenance', {})
    (d / 'main').write_text((d / 'main').read_text() + '# changed after freeze\n')
    r, _ = run(d, mp)
    case('C', 'binary changed after freezing: fatal before any resource',
         r.returncode != 0 and 'provenance check failed' in (r.stdout + r.stderr)
         and not (d / 'out').exists() and lock_free(), (r.stdout + r.stderr)[-200:])


# ---------------------------------------------------------------- D (timing measurement)
def group_d(o, work):
    """True completions 25 ms apart must be recorded 25 ms apart (within 1 ms). The legacy measurement
    (Popen.wait(timeout=...)) is run on the same payloads to show the control can fail."""
    def legacy(cmd, timeout=120):
        t0 = time.monotonic()
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        p.wait(timeout=timeout)
        return time.monotonic() - t0

    def current(cmd):
        _, rc, wall, fired = cp.timed_payload(cmd, None, subprocess.DEVNULL, 120)
        return wall

    rows = {}
    for name, fn in (('current', current), ('legacy', legacy)):
        a, b = [], []
        for rep in range(12):
            for dur, acc in ((0.300, a), (0.325, b)) if rep % 2 == 0 else ((0.325, b), (0.300, a)):
                acc.append(fn(['taskset', '-c', o.payload_cpus, 'sleep', f'{dur:.3f}']))
        delta = statistics.median(b) - statistics.median(a)
        rows[name] = (delta, [round(x - 0.300, 4) for x in a], [round(x - 0.325, 4) for x in b])
    d_cur, d_leg = rows['current'][0], rows['legacy'][0]
    case('D', f'blocking wait: completions 25 ms apart recorded {1000 * d_cur:.2f} ms apart (|error| <= 1 ms)',
         abs(d_cur - 0.025) <= 0.001, rows['current'])
    case('D', f'control discriminates: legacy polled wait records {1000 * d_leg:.2f} ms (error > 1 ms)',
         abs(d_leg - 0.025) > 0.001, rows['legacy'])
    (work / 'timing-control.json').write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------- E (unit rules: deadline marker, mask, source)
def group_e(o, work):
    case('E', 'completion marker after the release deadline, or with an unreaped process, becomes incomplete',
         cp.completion_status('complete', time.monotonic() - 0.001) == 'incomplete'
         and cp.completion_status('complete', time.monotonic() + 10, [123]) == 'incomplete'
         and cp.completion_status('complete', time.monotonic() + 10) == 'complete')

    class Unreapable:                                     # a process SIGKILL cannot reap (e.g. stuck in D state)
        def __init__(self, pid):
            self.pid = pid

        def wait(self, timeout=None):
            time.sleep(timeout)
            raise subprocess.TimeoutExpired('x', timeout)
    lockfile = work / 'e-release.lock'
    now = time.monotonic()
    win = cp.Window(now, now + 2.0, [str(lockfile)])
    win.acquire()
    fakes = [Unreapable(4_000_000 + k) for k in range(3)]
    win.children, win.samplers = [fakes[0]], [fakes[1]]
    with cp.CHILD_LOCK:
        cp.CHILDREN.add(fakes[2])
    t0 = time.monotonic()
    win.release()
    el = time.monotonic() - t0
    with cp.CHILD_LOCK:
        cp.CHILDREN.discard(fakes[2])
    free = subprocess.run(['flock', '-n', str(lockfile), 'true']).returncode == 0
    case('E', f'release: one shared reap deadline for 3 unreapable processes ({el:.2f} s for a 2 s deadline; '
              f'5 s each before), unreaped recorded, lock released',
         el <= 2.5 and sorted(win.unreaped) == [f.pid for f in fakes] and free, f'{el:.2f} s {win.unreaped}')
    mask = cp.parse_cpus(o.payload_cpus)
    for name, args, want in (
        ('no CPU-mask observation', (False, 0, False, None, mask, [], 1), 'no CPU-mask observation'),
        ('sampler did not finish', (False, 0, True, mask, mask, [], 1), 'sampler did not finish'),
        ('different observed mask', (False, 0, False, {0}, mask, [], 1), 'payload mask'),
        ('valid observation', (False, 0, False, mask, mask, [], 1), None),
    ):
        v = cp.classify(*args)
        case('E', f'mask rule: {name} -> {"invalid (" + want + ")" if want else "valid"}',
             (v is None) if want is None else (v is not None and v[0] == 'resource' and want in v[1]), v)
    # source re-verification: a throwaway git repository holding a copy of the frozen driver directory
    repo = work / 'e-repo'
    ddir = repo / 'docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft'
    ddir.mkdir(parents=True)
    for f in cp.FROZEN_FILES:
        (ddir / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / f, ddir / f)
    g = lambda *a: subprocess.run(['git', '-C', str(repo)] + list(a), capture_output=True, text=True, check=True).stdout.strip()
    g('init', '-q'); g('add', '-A'); g('-c', 'user.name=c', '-c', 'user.email=c@c', 'commit', '-qm', 'x')
    head = g('rev-parse', 'HEAD')
    stub = work / 'e-stub'; stub.write_text('#!/bin/sh\nexit 0\n'); stub.chmod(0o755)
    data = work / 'e-data'; data.mkdir(); (data / 'movies.star').write_text('data_movies\nloop_\n_rlnMicrographMovieName #1\nMovies/x.tif\n')

    def attempt(name, edit_manifest=None, edit_repo=None, want_ok=False):
        mp = work / f'e-{name}.json'
        m = manifest(mp, extra={'source_tree': str(repo), 'source_head': head, 'fix_build_sha': head, 'locks': [],
                                'payload_cpus': cp.fmt_cpus(cp.parse_cpus(o.payload_cpus)),
                                'runner_cpus': cp.fmt_cpus(cp.parse_cpus(o.runner_cpus)),
                                'fix_build_equivalence': 'binary built from the frozen head',
                                'frozen_files': {f: cp.sha256(ddir / f) for f in cp.FROZEN_FILES},
                                'binaries': {a: {'path': str(stub), 'sha256': cp.sha256(stub)} for a in ('main', 'fix')}})
        m['workloads']['w'].update(data=str(data), inputs={})
        if edit_manifest:
            edit_manifest(m)
        mp.write_text(json.dumps(m))
        if edit_repo:
            edit_repo()
        out = work / f'e-out-{name}'
        r = subprocess.run([sys.executable, str(ddir / 'confirm_pairs.py'), 'run', '--manifest', str(mp), '--workload', 'w',
                            '--window', '1', '--out', str(out), '--scratch', str(work / 'e-scratch')],
                           capture_output=True, text=True)
        refused = r.returncode != 0 and 'provenance check failed' in (r.stdout + r.stderr) and not out.exists()
        passed_verify = out.exists()
        ok = passed_verify if want_ok else refused
        case('E', f'source re-verification: {name} -> {"accepted" if want_ok else "fatal before any resource"}', ok,
             (r.stdout + r.stderr)[-200:])
        shutil.rmtree(out, ignore_errors=True)

    attempt('clean frozen head', want_ok=True)
    attempt('wrong source_head', edit_manifest=lambda m: m.update(source_head='0' * 40))
    attempt('invalid source path', edit_manifest=lambda m: m.update(source_tree=str(work / 'no-such-repo')))
    attempt('changed build equivalence', edit_manifest=lambda m: m.update(fix_build_equivalence='other'))
    attempt('vendored stats changed', edit_repo=lambda: (ddir / 'vendor/stats.py').write_text(
        (HERE / 'vendor/stats.py').read_text() + '\n# changed\n'))
    shutil.copy(HERE / 'vendor/stats.py', ddir / 'vendor/stats.py')
    attempt('untracked file in the tree (not clean)', edit_repo=lambda: (repo / 'stray.txt').write_text('x'))


def main():
    ap = argparse.ArgumentParser()
    for k in ('work', 'cpu-binary', 'tutorial', 'cpus', 'payload-cpus', 'runner-cpus'):
        ap.add_argument('--' + k, required=True)
    o = ap.parse_args()
    work = Path(o.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    group_a(o, work)
    group_b(o, work)
    group_c(o, work)
    group_d(o, work)
    group_e(o, work)
    n_bad = sum(not r['ok'] for r in RESULTS)
    (work / 'controls.json').write_text(json.dumps(RESULTS, indent=1))
    print(f'\n{len(RESULTS) - n_bad}/{len(RESULTS)} controls as required')
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
