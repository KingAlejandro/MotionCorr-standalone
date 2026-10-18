#!/usr/bin/env python3
"""DRAFT / NOT RUN. W-D11 confirmatory paired timing (tutG, e10216L) for #228 against D14.

The declared design is rule.txt next to this file. Subcommands:
  freeze   write manifest.json: driver/rule hashes, source SHAs, expected binary hashes, build settings,
           workload arguments, input file hashes, venue, N, windows and the full planned run order.
           Run once, before any resource is requested; the manifest is then never edited.
  run      verify the manifest (all hashes) BEFORE taking any resource, then run ONE window under a hard
           deadline that covers lock waits, idle-GPU waits and every payload. Locks are taken here
           (4GPUs) and released in a finally block, together with the samplers and any payload.
  combine  validate a workload's evidence against the manifest, then compute the D14 label.
           Anything missing, malformed or truncated gives INCOMPLETE, never an exception.
Labels are emitted exactly as PASS / UNRESOLVED / FAIL / INCOMPLETE.

Arm labels are [a-z]+ (main, fix, mainb); run directories are <seq>-<label>.
Standard library only, plus tools/profiling/lib (stats, identity) from the frozen source tree.
"""
import argparse, fcntl, hashlib, json, math, os, re, resource, shutil, signal, struct, subprocess, sys, threading, time
from pathlib import Path

TARGET_FRAC = 0.005                 # D14 margin
NULL_BLOCKS = 8                     # 16 null pairs per workload
MAX_ATTEMPTS = 3
WINDOW_BUDGET_S = 45 * 60           # whole bench-lock tenure, from the first lock request
PAYLOAD_TIMEOUT_S = 120             # a healthy run takes 4.5-6 s
LABELS = ('main', 'fix', 'mainb')
LABEL_RE = re.compile(r'^[a-z]+$')
PASS, UNRESOLVED, FAIL, INCOMPLETE = 'PASS', 'UNRESOLVED', 'FAIL', 'INCOMPLETE'
PAYLOAD_FAILURES = ('exit', 'timeout', 'product')      # arm-attributable; 'resource' is environmental


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- plan
def plan_window(n, windows):
    """Run order of one window, identical for every window of a workload: a list of (first, second, kind).
    n/2 comparison blocks and NULL_BLOCKS null blocks are split into `windows` equal windows. Inside a window
    with B comparison blocks and K null blocks, null block j (1..K) follows comparison block ceil(j*B/K), so
    the last null block always follows the last comparison block."""
    if n % 2 or (n // 2) % windows or NULL_BLOCKS % windows:
        raise ValueError(f'n={n} cannot be split into {windows} equal balanced windows')
    b, k = n // 2 // windows, NULL_BLOCKS // windows
    if k > b:
        raise ValueError('more null blocks than comparison blocks')
    after = {math.ceil(j * b / k) for j in range(1, k + 1)}
    plan = []
    for blk in range(1, b + 1):
        plan += [('main', 'fix', 'AB'), ('fix', 'main', 'BA')]
        if blk in after:
            plan += [('main', 'mainb', 'null'), ('mainb', 'main', 'null')]
    return plan


# ---------------------------------------------------------------- products
def star_loop(path, block, column):
    """Values of one column of one loop; None if the file, block or column is absent or malformed."""
    try:
        lines = Path(path).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    vals, inside, cols = [], False, []
    for line in lines:
        t = line.strip()
        if t.startswith('data_'):
            if inside and cols:
                break
            inside, cols = (t == block), []
        elif inside and t.startswith('_rln'):
            cols.append(t.split()[0])
        elif inside and t and not t.startswith(('#', 'loop_')) and cols:
            if column not in cols:
                return None
            f = t.split()
            if len(f) < len(cols):
                return None
            vals.append(f[cols.index(column)])
    return vals if cols else None


def expected_pdf_pages(n_movies):
    """logfile.pdf: 3 accumulated-motion plots, 3 histograms when there are more than 3 micrographs
    (src/motioncorr_runner.cpp:1723-1745), then one shift plot per movie."""
    return 3 + (3 if n_movies > 3 else 0) + n_movies


def pdf_pages(path):
    try:
        r = subprocess.run(['gs', '-q', '-dNODISPLAY', '-dNOSAFER', '-c',
                            f'({path}) (r) file runpdfbegin pdfpagecount = quit'],
                           capture_output=True, text=True, timeout=60)
        return int(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def product_problems(out, movies):
    """Complete product of one healthy job; an empty list means complete."""
    out = Path(out)
    problems = []
    stems = [str(Path(m).with_suffix('')) for m in movies]
    for stem in stems:
        mrc, star = out / (stem + '.mrc'), out / (stem + '.star')
        if not mrc.is_file():
            problems.append(f'{stem}.mrc missing')
        else:
            with mrc.open('rb') as f:
                h = f.read(1024)
            if len(h) != 1024:
                problems.append(f'{stem}.mrc header {len(h)} bytes')
            else:
                nx, ny, nz, mode = struct.unpack_from('<4i', h, 0)
                nsymbt = struct.unpack_from('<i', h, 92)[0]
                if min(nx, ny, nz) <= 0 or nsymbt < 0 or mode != 2 or h[208:212] != b'MAP ':
                    problems.append(f'{stem}.mrc header invalid (dims {nx}x{ny}x{nz}, mode {mode}, nsymbt {nsymbt})')
                elif mrc.stat().st_size != 1024 + nsymbt + nx * ny * nz * 4:
                    problems.append(f'{stem}.mrc size {mrc.stat().st_size}, expected {1024 + nsymbt + nx * ny * nz * 4}')
        if not star.is_file() or star.stat().st_size == 0:
            problems.append(f'{stem}.star missing or empty')
    joint = star_loop(out / 'corrected_micrographs.star', 'data_micrographs', '_rlnMicrographName')
    want = sorted(s + '.mrc' for s in stems)
    if joint is None:
        problems.append('joint STAR missing or malformed')
    else:
        got = sorted('/'.join(Path(v).parts[-2:]) for v in joint)
        if got != want:
            problems.append(f'joint STAR lists {len(got)} micrographs, not the expected {len(want)}')
    pdf = out / 'logfile.pdf'
    pages = pdf_pages(pdf) if pdf.is_file() else None
    if pages != expected_pdf_pages(len(movies)):
        problems.append(f'logfile.pdf pages {pages}, expected {expected_pdf_pages(len(movies))}')
    return problems, pages


# ---------------------------------------------------------------- resources
class Gpu:
    """Occupancy checks on one GPU, selected by UUID. uuid None = dry run (no GPU checks; never a verdict)."""
    def __init__(self, uuid):
        self.uuid = uuid

    def pids(self):
        if self.uuid is None:
            return set()
        try:
            r = subprocess.run(['nvidia-smi', '-i', self.uuid, '--query-compute-apps=pid', '--format=csv,noheader'],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        return {int(x) for x in r.stdout.split() if x.strip().isdigit()}

    def local_cpus(self):
        r = subprocess.run(['nvidia-smi', '-i', self.uuid, '--query-gpu=pci.bus_id', '--format=csv,noheader'],
                           capture_output=True, text=True)
        bus = r.stdout.strip().lower()
        if r.returncode != 0 or not bus:
            raise RuntimeError(f'cannot resolve the PCI bus of {self.uuid}')
        bus = bus[-12:]                                  # 0000:09:00.0
        return parse_cpus(Path(f'/sys/bus/pci/devices/{bus}/local_cpulist').read_text().strip())


def parse_cpus(text):
    cpus = set()
    for part in text.split(','):
        if '-' in part:
            a, b = part.split('-')
            cpus.update(range(int(a), int(b) + 1))
        elif part.strip():
            cpus.add(int(part))
    return cpus


def fmt_cpus(cpus):
    return ','.join(str(c) for c in sorted(cpus))


class Window:
    """Owns every resource of one window; release() is idempotent and runs on any exit path."""
    def __init__(self, deadline, locks):
        self.deadline, self.lock_paths, self.fds, self.children, self.samplers = deadline, locks, [], [], []

    def remaining(self):
        return self.deadline - time.monotonic()

    def acquire(self):
        for path in self.lock_paths:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o664)
            self.fds.append(fd)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if self.remaining() <= 0:
                        raise TimeoutError(f'deadline passed waiting for {path}')
                    time.sleep(5)
            if os.stat(path).st_ino != os.fstat(fd).st_ino:
                raise RuntimeError(f'{path} was replaced while locked')

    def release(self):
        for p in self.children + self.samplers:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
        self.children, self.samplers = [], []
        for fd in self.fds:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
            except OSError:
                pass
        self.fds = []


# ---------------------------------------------------------------- freeze / verify
def freeze(o):
    src = Path(o.src)
    git = lambda *a: subprocess.run(['git', '-C', str(src)] + list(a), capture_output=True, text=True, check=True).stdout.strip()
    here = Path(__file__).resolve().parent
    data = {}
    for w in o.workload:
        name, n, ddir, args = w.split(':', 3)
        ddir = Path(ddir)
        movies = star_loop(ddir / 'movies.star', 'data_movies', '_rlnMicrographMovieName')
        if not movies:
            raise SystemExit(f'{name}: no movies in {ddir}/movies.star')
        inputs = {m: sha256(ddir / m) for m in movies}
        inputs['movies.star'] = sha256(ddir / 'movies.star')
        gain = re.search(r'--gainref (\S+)', args)
        if gain:
            inputs[gain.group(1)] = sha256(ddir / gain.group(1))
        data[name] = {'n': int(n), 'windows': o.windows, 'data': str(ddir), 'args': args.split(),
                      'movies': movies, 'expected_pdf_pages': expected_pdf_pages(len(movies)), 'inputs': inputs,
                      'plan': [f'{a},{b},{k}' for a, b, k in plan_window(int(n), o.windows)]}
    m = {'status': 'DRAFT / NOT RUN' if o.draft else 'frozen', 'venue': o.venue,
         'driver_sha256': sha256(here / 'confirm_pairs.py'), 'rule_sha256': sha256(here / 'rule.txt'),
         'source_tree': str(src), 'source_head': git('rev-parse', 'HEAD'),
         'source_clean': git('status', '--porcelain') == '',
         'main_sha': o.main_sha, 'fix_sha': o.fix_sha, 'fix_build_sha': o.fix_build_sha,
         'binaries': {'main': {'path': o.a, 'sha256': o.a_sha256}, 'fix': {'path': o.b, 'sha256': o.b_sha256}},
         'build_settings': o.build_settings, 'workloads': data,
         'budget_s': WINDOW_BUDGET_S, 'payload_timeout_s': PAYLOAD_TIMEOUT_S, 'max_attempts': MAX_ATTEMPTS}
    if not m['source_clean']:
        raise SystemExit('source tree not clean')
    if o.fix_build_sha != o.fix_sha:
        # A reused fix binary must be source-equivalent to the head: identical src/, and CMakeLists.txt
        # differing only in comment lines. Anything else needs a rebuild from the exact head.
        if git('diff', '--name-only', o.fix_build_sha, o.fix_sha, '--', 'src'):
            raise SystemExit(f'src/ differs between {o.fix_build_sha} and {o.fix_sha}: rebuild from the head')
        changed = [l[1:].strip() for l in git('diff', '-U0', o.fix_build_sha, o.fix_sha, '--', 'CMakeLists.txt').splitlines()
                   if l[:1] in '+-' and not l.startswith(('+++', '---'))]
        if any(c and not c.startswith('#') for c in changed):
            raise SystemExit('CMakeLists.txt differs beyond comments: rebuild from the head')
        m['fix_build_equivalence'] = (f'binary built from {o.fix_build_sha}; src/ identical to {o.fix_sha}; '
                                      f'CMakeLists.txt differs in {len(changed)} comment line(s) only')
    Path(o.manifest).write_text(json.dumps(m, indent=1))
    print(f'manifest {o.manifest} sha256 {sha256(o.manifest)}')


def verify(m, workload, check_inputs=True):
    """Every frozen identity, checked before any resource is requested. Raises on any mismatch."""
    here = Path(__file__).resolve().parent
    bad = []
    if sha256(here / 'confirm_pairs.py') != m['driver_sha256']:
        bad.append('driver hash')
    if sha256(here / 'rule.txt') != m['rule_sha256']:
        bad.append('rule hash')
    for arm, b in m['binaries'].items():
        if not Path(b['path']).is_file() or sha256(b['path']) != b['sha256']:
            bad.append(f'{arm} binary hash')
    w = m['workloads'][workload]
    if check_inputs:
        for rel, h in w['inputs'].items():
            p = Path(w['data']) / rel
            if not p.is_file() or sha256(p) != h:
                bad.append(f'input {rel}')
    if bad:
        raise SystemExit('provenance check failed: ' + ', '.join(bad))
    return w


# ---------------------------------------------------------------- run
def run_window(o):
    m = json.loads(Path(o.manifest).read_text())
    w = verify(m, o.workload, check_inputs=not o.dry_run_inputs)    # before any lock, GPU or sampler
    out = Path(o.out) / o.workload / f'window{o.window}'
    if out.exists():
        raise SystemExit(f'{out} exists: a window runs once')
    (out / 'logs').mkdir(parents=True)
    gpu = Gpu(o.gpu_uuid)
    log = open(out / 'runs.jsonl', 'w')

    def emit(rec):
        log.write(json.dumps(rec) + '\n'); log.flush(); os.fsync(log.fileno())

    budget_s, payload_timeout_s = m.get('budget_s', WINDOW_BUDGET_S), m.get('payload_timeout_s', PAYLOAD_TIMEOUT_S)
    deadline = time.monotonic() + budget_s
    win = Window(deadline, o.lock or [])
    status, reason = 'incomplete', 'not started'

    def on_signal(sig, frame):
        raise KeyboardInterrupt(f'signal {sig}')
    signal.signal(signal.SIGTERM, on_signal)
    bins = {'main': m['binaries']['main']['path'], 'fix': m['binaries']['fix']['path']}
    bins['mainb'] = bins['main']
    try:
        allowed = os.sched_getaffinity(0)
        payload, runner = parse_cpus(o.cpus), parse_cpus(o.runner_cpus)
        gpu_cpus = gpu.local_cpus() if o.gpu_uuid else allowed
        if not (payload <= allowed & gpu_cpus) or not (runner <= allowed) or payload & runner:
            raise SystemExit(f'CPU masks invalid: payload {fmt_cpus(payload)}, runner {fmt_cpus(runner)}, '
                             f'allowed {fmt_cpus(allowed)}, GPU-local {fmt_cpus(gpu_cpus)}')
        os.sched_setaffinity(0, runner)
        emit({'header': {'manifest_sha256': sha256(o.manifest), 'workload': o.workload, 'window': o.window,
                         'venue': m['venue'], 'gpu_uuid': o.gpu_uuid, 'payload_cpus': fmt_cpus(payload),
                         'runner_cpus': fmt_cpus(runner), 'gpu_local_cpus': fmt_cpus(gpu_cpus),
                         'locks': o.lock or [], 'dry_run': o.gpu_uuid is None or o.dry_run_inputs}})
        t_lock = time.monotonic()
        win.acquire()
        emit({'locks_acquired_after_s': round(time.monotonic() - t_lock, 1)})
        while gpu.pids() != set():                      # wait for an idle GPU, inside the deadline
            if win.remaining() <= 0:
                raise TimeoutError('deadline passed waiting for an idle GPU')
            time.sleep(10)
        if o.samplers:
            for cmd, name in ((['mpstat', '-P', 'ALL', '10'], 'mpstat.txt'),
                              (['nvidia-smi', '--query-gpu=timestamp,uuid,utilization.gpu,memory.used',
                                '--format=csv', '-l', '10'], 'nvidia-smi.csv')):
                win.samplers.append(subprocess.Popen(cmd, stdout=open(out / name, 'w'), stderr=subprocess.STDOUT,
                                                     start_new_session=True))
        seq = [0]

        def run(phase, label, keep=False):
            seq[0] += 1
            tag = f'{seq[0]:04d}-{label}'
            dst = Path(o.scratch) / f'wd11c-{o.workload}-w{o.window}' / tag
            dst.mkdir(parents=True)
            rec = {'seq': seq[0], 'phase': phase, 'label': label}
            before = gpu.pids()
            if before is None or before:
                rec.update(failure='resource', detail=f'GPU occupied or query failed before the run: {before}')
                emit(rec); return rec, dst
            budget = min(payload_timeout_s, win.remaining())
            if budget <= 0:
                raise TimeoutError('deadline reached')
            violations = []
            r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
            with open(out / 'logs' / f'{tag}.txt', 'w') as so:
                t0 = time.monotonic()
                p = subprocess.Popen(['taskset', '-c', fmt_cpus(payload), bins[label], '--i', 'movies.star',
                                      '--o', str(dst) + '/'] + w['args'], cwd=w['data'], stdout=so,
                                     stderr=subprocess.STDOUT, start_new_session=True)
                win.children.append(p)

                def watch():
                    mask_seen = False
                    while p.poll() is None:
                        now = gpu.pids()
                        if now is None:
                            violations.append('GPU query failed during the run')
                        elif now - {p.pid}:
                            violations.append(f'foreign GPU process {sorted(now - {p.pid})}')
                        if not mask_seen:
                            try:
                                st = Path(f'/proc/{p.pid}/status').read_text()
                                cur = parse_cpus(re.search(r'Cpus_allowed_list:\s*(\S+)', st).group(1))
                                if Path(f'/proc/{p.pid}/exe').resolve() == Path(bins[label]).resolve():
                                    mask_seen = True
                                    if cur != payload:
                                        violations.append(f'payload mask {fmt_cpus(cur)}')
                            except (OSError, AttributeError):
                                pass
                        time.sleep(0.25)
                th = threading.Thread(target=watch, daemon=True); th.start()
                try:
                    p.wait(timeout=budget)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL); p.wait(); timed_out = True
                wall = time.monotonic() - t0              # payload only; checks below are not timed
                th.join(); win.children.remove(p)
            r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
            rec.update(rc=p.returncode, wall_s=round(wall, 4),
                       cpu_s=round((r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime), 3))
            if timed_out:
                rec.update(failure='timeout', detail=f'killed after {budget:.0f} s')
            elif p.returncode != 0:
                rec.update(failure='exit', detail=f'exit {p.returncode}')
            elif violations:
                rec.update(failure='resource', detail='; '.join(sorted(set(violations))[:5]))
            else:
                problems, pages = product_problems(dst, w['movies'])
                rec['pdf_pages'] = pages
                if problems:
                    rec.update(failure='product', detail='; '.join(problems[:5]))
            emit(rec)
            if not keep:
                shutil.rmtree(dst, ignore_errors=True)
            return rec, dst

        run('warmup', 'main'); run('warmup', 'fix')       # discarded
        plan = [tuple(x.split(',')) for x in w['plan']]
        for pos, (first, second, kind) in enumerate(plan, 1):
            keep = pos == 1
            done = False
            for attempt in range(1, MAX_ATTEMPTS + 1):
                (r1, d1), (r2, d2) = run('timed', first, keep), run('timed', second, keep)
                ok = 'failure' not in r1 and 'failure' not in r2
                emit({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': attempt,
                      'retained': ok, 'walls': {first: r1.get('wall_s'), second: r2.get('wall_s')}})
                if keep and ok:
                    sys.path.insert(0, str(Path(m['source_tree']) / 'tools' / 'profiling'))
                    from lib import identity  # noqa: E402
                    ident = identity.compare_trees(str(d1), str(d2))
                    emit({'identity': {'position': pos, 'identical': ident['identical'],
                                       'problems': ident['problems'], 'compared': ident['compared'],
                                       'mrc_compared': ident['mrc_compared']}})
                    if not ident['identical']:                # keep the evidence; never retried
                        keepdir = out / 'identity-failure'
                        shutil.copytree(d1, keepdir / d1.name); shutil.copytree(d2, keepdir / d2.name)
                if keep:
                    shutil.rmtree(d1, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)
                if ok:
                    done = True
                    break
            if not done:
                raise RuntimeError(f'position {pos} ({kind}) failed {MAX_ATTEMPTS} attempts')
        status, reason = 'complete', ''
    except (TimeoutError, RuntimeError, KeyboardInterrupt, SystemExit, OSError) as exc:
        status, reason = 'incomplete', f'{type(exc).__name__}: {exc}'
    finally:
        win.release()
        shutil.rmtree(Path(o.scratch) / f'wd11c-{o.workload}-w{o.window}', ignore_errors=True)
        marker = {'status': status, 'reason': reason, 'workload': o.workload, 'window': o.window,
                  'positions': len(w['plan']), 'manifest_sha256': sha256(o.manifest),
                  'remaining_budget_s': round(win.remaining(), 1)}
        (out / ('complete.json' if status == 'complete' else 'incomplete.json')).write_text(json.dumps(marker, indent=1))
        subprocess.run(['gzip', '-rq', str(out / 'logs')])
        print(json.dumps(marker))
    return 0 if status == 'complete' else 1


# ---------------------------------------------------------------- combine
def combine(o):
    reasons, res = [], {'workload': o.workload}
    try:
        m = json.loads(Path(o.manifest).read_text())
        w = m['workloads'][o.workload]
        plan = [tuple(x.split(',')) for x in w['plan']]
        sys.path.insert(0, str(Path(o.src) / 'tools' / 'profiling'))
        from lib import stats  # noqa: E402
        comp, null, wa, wb, per_window = [], [], [], [], []
        attempts = {a: 0 for a in LABELS}
        failures = {a: {k: 0 for k in PAYLOAD_FAILURES + ('resource',)} for a in LABELS}
        identity_failed = []
        for i in range(1, w['windows'] + 1):
            wd = Path(o.out) / o.workload / f'window{i}'
            diag = {'window': i}
            per_window.append(diag)
            marker = wd / 'complete.json'
            if not marker.is_file():
                reasons.append(f'window {i}: no completion marker'
                               + (f' ({json.loads((wd / "incomplete.json").read_text()).get("reason")})'
                                  if (wd / 'incomplete.json').is_file() else ''))
                continue
            mk = json.loads(marker.read_text())
            if mk.get('status') != 'complete' or mk.get('manifest_sha256') != sha256(o.manifest):
                reasons.append(f'window {i}: completion marker does not match the frozen manifest')
            retained = {}
            for n_line, line in enumerate((wd / 'runs.jsonl').read_text().splitlines(), 1):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    reasons.append(f'window {i}: malformed record at line {n_line}'); continue
                if 'header' in rec and rec['header'].get('manifest_sha256') != sha256(o.manifest):
                    reasons.append(f'window {i}: header manifest hash differs')
                if 'header' in rec and rec['header'].get('dry_run'):
                    reasons.append(f'window {i}: dry run (no GPU checks or no input hashing), never a verdict')
                if 'label' in rec and rec.get('phase') == 'timed':
                    attempts[rec['label']] += 1
                    if 'failure' in rec:
                        failures[rec['label']][rec['failure']] += 1
                if 'identity' in rec and not rec['identity'].get('identical'):
                    identity_failed.append(f'window {i}: {rec["identity"].get("problems")}')
                if rec.get('retained'):
                    pos = rec['position']
                    if pos in retained:
                        reasons.append(f'window {i}: position {pos} retained twice')
                    retained[pos] = rec
            if sorted(retained) != list(range(1, len(plan) + 1)):
                reasons.append(f'window {i}: retained positions {len(retained)} of {len(plan)}')
            nc = nn = 0
            for pos, (first, second, kind) in enumerate(plan, 1):
                rec = retained.get(pos)
                if rec is None:
                    continue
                if rec.get('order') != f'{first},{second}' or rec.get('pair') != kind:
                    reasons.append(f'window {i}: position {pos} order {rec.get("order")} differs from the plan')
                    continue
                ws = rec['walls']
                if kind == 'null':
                    null.append(ws['mainb'] - ws['main']); nn += 1
                else:
                    comp.append({'order': kind, 'd': ws['fix'] - ws['main']}); nc += 1
                    wa.append(ws['main']); wb.append(ws['fix'])
            diag.update(comparison_pairs=nc, null_pairs=nn)
        n_ab = sum(c['order'] == 'AB' for c in comp); n_ba = len(comp) - n_ab
        if len(comp) != w['n'] or n_ab != n_ba:
            reasons.append(f'comparison pairs {len(comp)} ({n_ab} AB / {n_ba} BA), declared {w["n"]} balanced')
        if len(null) != 2 * NULL_BLOCKS:
            reasons.append(f'null pairs {len(null)}, declared {2 * NULL_BLOCKS}')
        # Declared failure classification (rule.txt "Failures").
        payload_fail = {a: sum(failures[a][k] for k in PAYLOAD_FAILURES) for a in LABELS}
        systematic = []
        if sum(payload_fail.values()) >= 2:
            systematic.append(f'{sum(payload_fail.values())} payload failures (exit/timeout/product)')
        if payload_fail['fix'] >= 1 and payload_fail['main'] + payload_fail['mainb'] == 0:
            systematic.append('payload failures on the fix arm only (arm-dependent)')
        res.update(attempts_by_arm=attempts, failures_by_arm=failures, systematic_failures=systematic,
                   identity_failures=identity_failed, per_window=per_window, pairs=len(comp), pairs_AB=n_ab,
                   pairs_BA=n_ba, null_pairs=len(null))
        ci = stats.median_ci([c['d'] for c in comp]) if len(comp) >= stats.MIN_PAIRS else None
        if ci is None:
            reasons.append('no confidence interval (too few pairs)')
        else:
            ma = stats.median(wa)
            lo, hi, conf = ci
            res.update(median_d_s=stats.median([c['d'] for c in comp]), ci95_s=[lo, hi], ci_confidence=conf,
                       ci_pct_of_main_wall=[100 * lo / ma, 100 * hi / ma], median_wall_main_s=ma,
                       median_wall_fix_s=stats.median(wb), iqr_main_s=stats.iqr(wa) if len(wa) > 3 else None,
                       iqr_fix_s=stats.iqr(wb) if len(wb) > 3 else None)
            res['statistical_label'] = FAIL if lo > 0 else PASS if hi <= TARGET_FRAC * ma else UNRESOLVED
        ci0 = stats.median_ci(null) if len(null) >= stats.MIN_PAIRS else None
        res.update(null_median_s=stats.median(null) if null else None, null_ci95_s=ci0[:2] if ci0 else None,
                   null_range_s=[min(null), max(null)] if null else None)
        if identity_failed:
            reasons.append('product identity failed')
        if systematic:
            reasons.append('systematic payload failures: ' + '; '.join(systematic))
    except Exception as exc:                              # never an exception instead of a verdict
        reasons.append(f'evidence unreadable: {type(exc).__name__}: {exc}')
    if reasons:
        label = INCOMPLETE
    else:
        label = res['statistical_label']
    res.update(label=label, incomplete_reasons=reasons)
    Path(o.result).write_text(json.dumps(res, indent=1))
    print(label, json.dumps({k: res.get(k) for k in ('workload', 'pairs', 'median_d_s', 'ci95_s',
                                                      'ci_pct_of_main_wall', 'incomplete_reasons')}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('freeze')
    for k in ('manifest', 'venue', 'src', 'main-sha', 'fix-sha', 'fix-build-sha', 'a', 'a-sha256', 'b', 'b-sha256',
              'build-settings'):
        f.add_argument('--' + k, required=True)
    f.add_argument('--windows', type=int, default=2)
    f.add_argument('--workload', action='append', required=True, help='name:N:datadir:motioncorr args')
    f.add_argument('--draft', action='store_true')
    r = sub.add_parser('run')
    for k in ('manifest', 'workload', 'out', 'cpus', 'runner-cpus', 'scratch'):
        r.add_argument('--' + k, required=True)
    r.add_argument('--window', type=int, required=True)
    r.add_argument('--gpu-uuid', default=None, help='omit only for a dry run with a stub payload')
    r.add_argument('--lock', action='append', help='lock file to hold for the whole window (4GPUs)')
    r.add_argument('--samplers', action='store_true', help='mpstat and nvidia-smi every 10 s')
    r.add_argument('--dry-run-inputs', action='store_true', help='controls only: skip input hashing')
    c = sub.add_parser('combine')
    for k in ('manifest', 'workload', 'out', 'src', 'result'):
        c.add_argument('--' + k, required=True)
    o = ap.parse_args()
    if o.cmd == 'freeze':
        return freeze(o)
    if o.cmd == 'run':
        return run_window(o)
    return combine(o)


if __name__ == '__main__':
    sys.exit(main())
