#!/usr/bin/env python3
"""W-D11 confirmatory paired timing (tutG, e10216L) for #228 against D14. NOT RUN until "GO".

The declared design is rule.txt next to this file. Subcommands:
  freeze   write manifest.json (no resource is touched): driver/rule/vendored-helper hashes, source SHAs,
           binary hashes, build settings, workload arguments, input hashes, venue, GPU, N, windows, plan.
  run      re-verify everything in the manifest (hashes, source head, clean tree, build equivalence)
           BEFORE taking any lock, then run ONE window under a hard deadline.
  combine  validate a workload's complete record streams against the manifest, then assign the D14 label.
           Missing, reordered, contradictory or late evidence gives INCOMPLETE, never an exception.
Labels: PASS / UNRESOLVED / FAIL / INCOMPLETE. Arm labels are [a-z]+; run directories are <seq>-<label>.
Statistics and identity come from vendor/ (byte copies of tools/profiling/lib), hashed in the manifest.
"""
import argparse, fcntl, hashlib, json, math, os, re, shutil, signal, struct, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True          # no __pycache__ in the frozen, clean source tree
sys.path.insert(0, str(HERE / 'vendor'))
import stats  # noqa: E402  (vendored, hashed in the manifest)

TARGET_FRAC = 0.005
NULL_BLOCKS = 8
MAX_ATTEMPTS = 3
WINDOW_BUDGET_S = 45 * 60
PAYLOAD_TIMEOUT_S = 120
LABELS = ('main', 'fix', 'mainb')
PASS, UNRESOLVED, FAIL, INCOMPLETE = 'PASS', 'UNRESOLVED', 'FAIL', 'INCOMPLETE'
PAYLOAD_FAILURES = ('exit', 'timeout', 'product')
FROZEN_FILES = ('confirm_pairs.py', 'rule.txt', 'vendor/stats.py', 'vendor/identity.py')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- plan
def plan_window(n, windows):
    """Run order of one window (the same for every window of a workload). Null block j (1..K) follows
    comparison block ceil(j*B/K), so the last null block follows the last comparison block."""
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
    """3 accumulated-motion plots, 3 histograms when there are more than 3 micrographs
    (src/motioncorr_runner.cpp:1723-1745), then one shift plot per movie."""
    return 3 + (3 if n_movies > 3 else 0) + n_movies


def pdf_pages(path, timeout=60):
    try:
        r = subprocess.run(['gs', '-q', '-dNODISPLAY', '-dNOSAFER', '-c',
                            f'({path}) (r) file runpdfbegin pdfpagecount = quit'],
                           capture_output=True, text=True, timeout=max(timeout, 0.1))
        return int(r.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def product_problems(out, movies, timeout=60):
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
    elif sorted('/'.join(Path(v).parts[-2:]) for v in joint) != want:
        problems.append(f'joint STAR lists {len(joint)} micrographs, not the expected {len(want)}')
    pdf = out / 'logfile.pdf'
    pages = pdf_pages(pdf, timeout) if pdf.is_file() else None
    if pages != expected_pdf_pages(len(movies)):
        problems.append(f'logfile.pdf pages {pages}, expected {expected_pdf_pages(len(movies))}')
    return problems, pages


# ---------------------------------------------------------------- timing
def timed_payload(cmd, cwd, stdout, timeout, on_start=None):
    """Run one payload. Completion is a BLOCKING wait(); wall = monotonic(reap) - monotonic(spawn).
    The timeout is enforced by an independent watchdog that kills the process group, so it never
    quantises the measurement (Popen.wait(timeout=...) polls with sleeps of up to 50 ms)."""
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
    done, fired = threading.Event(), []

    def watchdog():
        if not done.wait(max(timeout, 0)):
            fired.append(True)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    wd = threading.Thread(target=watchdog, daemon=True); wd.start()
    if on_start:
        on_start(p)
    rc = p.wait()
    wall = time.monotonic() - t0
    done.set(); wd.join()
    return p, rc, wall, bool(fired)


# ---------------------------------------------------------------- bounded children
CHILDREN, CHILD_LOCK = set(), threading.Lock()
CLEANUP_MARGIN_S = 10            # declared: release completes within the deadline plus this margin


def run_child(cmd, timeout):
    """Run a child process in its own process group, registered so that Window.release() kills it,
    and killed here when `timeout` (the remaining window time) expires. Returns (rc, stdout)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    with CHILD_LOCK:
        CHILDREN.add(p)
    try:
        out, _ = p.communicate(timeout=max(timeout, 0.01))
        return p.returncode, out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        raise
    finally:
        with CHILD_LOCK:
            CHILDREN.discard(p)


def child_json(code, args, timeout):
    """Evaluate one expression of this module (or the vendored helpers) in a bounded child; JSON result."""
    rc, out = run_child([sys.executable, '-B', '-c', 'import sys, json; sys.path[:0] = [sys.argv[1], sys.argv[2]]; '
                         'import confirm_pairs as cp, identity; a = sys.argv[3:]; print(json.dumps(' + code + '))',
                         str(HERE), str(HERE / 'vendor')] + [str(x) for x in args], timeout)
    if rc != 0:
        raise RuntimeError(f'bounded check failed (exit {rc})')
    return json.loads(out)


# ---------------------------------------------------------------- resources
class Gpu:
    """Occupancy checks on one GPU by UUID. uuid None = dry run (no GPU checks; never a verdict)."""
    def __init__(self, uuid):
        self.uuid = uuid

    def pids(self, timeout=30):
        if self.uuid is None:
            return set()
        try:
            rc, out = run_child(['nvidia-smi', '-i', self.uuid, '--query-compute-apps=pid', '--format=csv,noheader'],
                                timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if rc != 0:
            return None
        return {int(x) for x in out.split() if x.strip().isdigit()}

    def local_cpus(self):
        r = subprocess.run(['nvidia-smi', '-i', self.uuid, '--query-gpu=pci.bus_id', '--format=csv,noheader'],
                           capture_output=True, text=True)
        bus = r.stdout.strip().lower()
        if r.returncode != 0 or not bus:
            raise RuntimeError(f'cannot resolve the PCI bus of {self.uuid}')
        return parse_cpus(Path(f'/sys/bus/pci/devices/{bus[-12:]}/local_cpulist').read_text().strip())


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
    """Every resource of one window; release() is idempotent, bounded, and runs on every exit path."""
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
                    time.sleep(min(5, max(self.remaining(), 0.1)))
            if os.stat(path).st_ino != os.fstat(fd).st_ino:
                raise RuntimeError(f'{path} was replaced while locked')

    def release(self):
        with CHILD_LOCK:
            queries = list(CHILDREN)                      # GPU queries, product/identity checks, deletions
        for p in self.children + self.samplers + queries:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                p.wait(timeout=5)                         # after SIGKILL, reaping is immediate
            except subprocess.TimeoutExpired:
                pass
        self.children, self.samplers = [], []
        for fd in self.fds:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
            except OSError:
                pass
        self.fds = []


def classify(timed_out, rc, sampler_alive, observed_mask, payload_mask, violations, budget):
    """(failure class, detail) of one finished payload before the product check, or None if valid.
    A payload without a successful CPU-mask observation, or whose sampler did not finish, is invalid."""
    if timed_out:
        return 'timeout', f'killed after {budget:.0f} s'
    if rc != 0:
        return 'exit', f'exit {rc}'
    if sampler_alive:
        return 'resource', 'sampler did not finish'
    if observed_mask is None:
        return 'resource', 'no CPU-mask observation'
    if observed_mask != payload_mask:
        return 'resource', f'payload mask {fmt_cpus(observed_mask)}'
    if violations:
        return 'resource', '; '.join(sorted(set(violations))[:5])
    return None


def completion_status(status, deadline_monotonic):
    """Never 'complete' once the deadline has passed (rule.txt "Deadline")."""
    return status if status != 'complete' or time.monotonic() <= deadline_monotonic else 'incomplete'


# ---------------------------------------------------------------- freeze / verify
def git(src, *a):
    return subprocess.run(['git', '-C', str(src)] + list(a), capture_output=True, text=True, check=True).stdout.strip()


def source_equivalence(src, build_sha, head):
    """Reused fix binary: src/ identical, CMakeLists.txt differing in comment lines only. Raises otherwise."""
    if build_sha == head:
        return 'binary built from the frozen head'
    if git(src, 'diff', '--name-only', build_sha, head, '--', 'src'):
        raise SystemExit(f'src/ differs between {build_sha} and {head}: rebuild from the head')
    changed = [l[1:].strip() for l in git(src, 'diff', '-U0', build_sha, head, '--', 'CMakeLists.txt').splitlines()
               if l[:1] in '+-' and not l.startswith(('+++', '---'))]
    if any(c and not c.startswith('#') for c in changed):
        raise SystemExit('CMakeLists.txt differs beyond comments: rebuild from the head')
    return f'binary built from {build_sha}; src/ identical to {head}; CMakeLists.txt differs in {len(changed)} comment line(s) only'


def freeze(o):
    src = Path(o.src)
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
    head = git(src, 'rev-parse', 'HEAD')
    if git(src, 'status', '--porcelain'):
        raise SystemExit('source tree not clean')
    if HERE != (src / 'docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft').resolve():
        raise SystemExit('the driver must run from the frozen source tree')
    payload, runner = parse_cpus(o.payload_cpus), parse_cpus(o.runner_cpus)
    if payload & runner or not o.lock:
        raise SystemExit('payload and runner masks must be disjoint, and at least one lock is required')
    m = {'status': 'frozen', 'venue': o.venue, 'gpu_uuid': o.gpu_uuid,
         'payload_cpus': fmt_cpus(payload), 'runner_cpus': fmt_cpus(runner), 'locks': o.lock,
         'frozen_files': {f: sha256(HERE / f) for f in FROZEN_FILES},
         'source_tree': str(src), 'source_head': head, 'main_sha': o.main_sha, 'fix_sha': head,
         'fix_build_sha': o.fix_build_sha, 'fix_build_equivalence': source_equivalence(src, o.fix_build_sha, head),
         'binaries': {'main': {'path': o.a, 'sha256': o.a_sha256}, 'fix': {'path': o.b, 'sha256': o.b_sha256}},
         'build_settings': o.build_settings, 'workloads': data,
         'budget_s': WINDOW_BUDGET_S, 'payload_timeout_s': PAYLOAD_TIMEOUT_S, 'max_attempts': MAX_ATTEMPTS}
    Path(o.manifest).write_text(json.dumps(m, indent=1))
    print(f'manifest {o.manifest} sha256 {sha256(o.manifest)}')


def verify(m, workload, check_inputs=True, check_source=True):
    """Everything frozen, checked before any resource. Raises SystemExit on any mismatch or git error."""
    bad = [f for f, h in m['frozen_files'].items() if not (HERE / f).is_file() or sha256(HERE / f) != h]
    for arm, b in m['binaries'].items():
        if not Path(b['path']).is_file() or sha256(b['path']) != b['sha256']:
            bad.append(f'{arm} binary')
    if check_source:
        try:
            src = Path(m['source_tree'])
            if git(src, 'rev-parse', 'HEAD') != m['source_head']:
                bad.append('source head')
            if git(src, 'status', '--porcelain'):
                bad.append('source tree not clean')
            if HERE != (src / 'docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft').resolve():
                bad.append('driver not in the frozen source tree')
            if source_equivalence(src, m['fix_build_sha'], m['source_head']) != m['fix_build_equivalence']:
                bad.append('build equivalence')
        except (subprocess.CalledProcessError, OSError, KeyError) as exc:
            raise SystemExit(f'provenance check failed: git/setup error: {exc}')
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
    dry = o.gpu_uuid is None or o.dry_run_inputs
    w = verify(m, o.workload, check_inputs=not o.dry_run_inputs, check_source=not o.dry_run_inputs)
    if not dry and o.gpu_uuid != m.get('gpu_uuid'):
        raise SystemExit('GPU differs from the manifest')
    out = Path(o.out) / o.workload / f'window{o.window}'
    if out.exists():
        raise SystemExit(f'{out} exists: a window runs once')
    (out / 'logs').mkdir(parents=True)
    gpu = Gpu(o.gpu_uuid)
    log = open(out / 'runs.jsonl', 'w')

    def emit(rec):
        log.write(json.dumps(rec) + '\n'); log.flush(); os.fsync(log.fileno())

    budget_s, payload_timeout_s = m['budget_s'], m['payload_timeout_s']
    t_start, wall_start = time.monotonic(), time.time()
    deadline = t_start + budget_s
    win = Window(deadline, m['locks'])
    status, reason = 'incomplete', 'not started'

    def on_signal(sig, frame):
        raise KeyboardInterrupt(f'signal {sig}')
    signal.signal(signal.SIGTERM, on_signal)
    bins = {'main': m['binaries']['main']['path'], 'fix': m['binaries']['fix']['path']}
    bins['mainb'] = bins['main']
    scratch = Path(o.scratch) / f'wd11c-{o.workload}-w{o.window}'
    kept = []

    def left():
        r = win.remaining()
        if r <= 0:
            raise TimeoutError('deadline reached')
        return r

    try:
        allowed = os.sched_getaffinity(0)
        payload, runner = parse_cpus(m['payload_cpus']), parse_cpus(m['runner_cpus'])
        gpu_cpus = gpu.local_cpus() if o.gpu_uuid else allowed
        if not (payload <= allowed & gpu_cpus) or not (runner <= allowed) or payload & runner:
            raise SystemExit(f'CPU masks invalid: payload {fmt_cpus(payload)}, runner {fmt_cpus(runner)}, '
                             f'allowed {fmt_cpus(allowed)}, GPU-local {fmt_cpus(gpu_cpus)}')
        os.sched_setaffinity(0, runner)
        emit({'header': {'manifest_sha256': sha256(o.manifest), 'workload': o.workload, 'window': o.window,
                         'venue': m['venue'], 'gpu_uuid': o.gpu_uuid, 'payload_cpus': fmt_cpus(payload),
                         'runner_cpus': fmt_cpus(runner), 'gpu_local_cpus': fmt_cpus(gpu_cpus),
                         'locks': m['locks'], 'dry_run': dry, 'start_epoch': wall_start,
                         'deadline_epoch': wall_start + budget_s}})
        t_lock = time.monotonic()
        win.acquire()
        emit({'locks_acquired_after_s': round(time.monotonic() - t_lock, 1)})
        while gpu.pids(timeout=min(30, left())) != set():
            time.sleep(min(10, left()))
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
            dst = scratch / tag
            dst.mkdir(parents=True)
            rec = {'seq': seq[0], 'phase': phase, 'label': label}
            before = gpu.pids(timeout=min(30, left()))
            if before is None or before:
                rec.update(failure='resource', detail=f'GPU occupied or query failed before the run: {before}')
                emit(rec); return rec, dst
            budget = min(payload_timeout_s, left())
            violations, mask = [], {}
            stop = threading.Event()

            def watch(p):
                # CPU mask first, before any slow GPU query: poll /proc until the payload image is in place.
                while not stop.is_set() and p.poll() is None and 'mask' not in mask:
                    try:
                        exe = Path(f'/proc/{p.pid}/exe').resolve()
                        argv = Path(f'/proc/{p.pid}/cmdline').read_bytes().split(b'\0')
                        if exe == Path(bins[label]).resolve() or bins[label].encode() in argv[:2]:
                            st = Path(f'/proc/{p.pid}/status').read_text()
                            mask['mask'] = parse_cpus(re.search(r'Cpus_allowed_list:\s*(\S+)', st).group(1))
                    except (OSError, AttributeError):
                        pass
                    time.sleep(0.002)
                while not stop.is_set() and p.poll() is None:
                    now = gpu.pids(timeout=10)
                    if now is None:
                        violations.append('GPU query failed during the run')
                    elif now - {p.pid}:
                        violations.append(f'foreign GPU process {sorted(now - {p.pid})}')
                    stop.wait(0.25)

            threads = []

            def started(p):
                win.children.append(p)
                th = threading.Thread(target=watch, args=(p,), daemon=True); th.start(); threads.append(th)

            with open(out / 'logs' / f'{tag}.txt', 'w') as so:
                p, rc, wall, timed_out = timed_payload(
                    ['taskset', '-c', fmt_cpus(payload), bins[label], '--i', 'movies.star', '--o', str(dst) + '/']
                    + w['args'], w['data'], so, budget, started)
            stop.set()
            for th in threads:
                th.join(timeout=min(15, max(win.remaining(), 0.1)))
            win.children.remove(p)
            sampler_alive = any(th.is_alive() for th in threads)
            rec.update(rc=rc, wall_s=round(wall, 6))
            verdict = classify(timed_out, rc, sampler_alive, mask.get('mask'), payload, violations, budget)
            if verdict:
                rec.update(failure=verdict[0], detail=verdict[1])
            else:
                problems, pages = child_json('cp.product_problems(a[0], a[1:])', [dst] + w['movies'], left())
                rec['pdf_pages'] = pages
                if problems:
                    rec.update(failure='product', detail='; '.join(problems[:5]))
            if 'mask' in mask:
                rec['observed_mask'] = fmt_cpus(mask['mask'])
            emit(rec)
            if not keep:
                run_child(['rm', '-rf', str(dst)], left())
            return rec, dst

        for label in ('main', 'fix'):                      # warm-ups: any failure ends the window
            r, _ = run('warmup', label)
            if 'failure' in r:
                raise RuntimeError(f'warm-up {label} failed: {r["failure"]} ({r.get("detail")})')
        plan = [tuple(x.split(',')) for x in w['plan']]
        for pos, (first, second, kind) in enumerate(plan, 1):
            keep = pos == 1
            for attempt in range(1, MAX_ATTEMPTS + 1):
                (r1, d1), (r2, d2) = run('timed', first, keep), run('timed', second, keep)
                ok = 'failure' not in r1 and 'failure' not in r2
                emit({'pair': kind, 'position': pos, 'order': f'{first},{second}', 'attempt': attempt,
                      'retained': ok, 'seqs': [r1['seq'], r2['seq']],
                      'walls': {first: r1.get('wall_s'), second: r2.get('wall_s')}})
                if keep and ok:
                    ident = child_json('identity.compare_trees(a[0], a[1])', [d1, d2], left())
                    emit({'identity': {'position': pos, 'identical': ident['identical'], 'problems': ident['problems'],
                                       'compared': ident['compared'], 'mrc_compared': ident['mrc_compared']}})
                    if not ident['identical']:
                        kept.extend([d1, d2])                 # copied to the evidence after release
                if keep and not (ok and kept):
                    run_child(['rm', '-rf', str(d1), str(d2)], left())
                if ok:
                    break
            else:
                raise RuntimeError(f'position {pos} ({kind}) failed {MAX_ATTEMPTS} attempts')
        status, reason = 'complete', ''
    except (TimeoutError, subprocess.TimeoutExpired, RuntimeError, KeyboardInterrupt, SystemExit, OSError,
            ValueError) as exc:
        status, reason = 'incomplete', f'{type(exc).__name__}: {exc}'
    finally:
        win.release()
        released_after_s, end_epoch, remaining = time.monotonic() - t_start, time.time(), win.remaining()
        final = completion_status(status, deadline)
        if final != status:
            reason = 'deadline passed before the completion marker'
        for d in kept:                                    # after release: identity-failure evidence
            shutil.copytree(d, out / 'identity-failure' / d.name, dirs_exist_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)
        marker = {'status': final, 'reason': reason, 'workload': o.workload, 'window': o.window,
                  'positions': len(w['plan']), 'manifest_sha256': sha256(o.manifest), 'budget_s': budget_s,
                  'start_epoch': wall_start, 'deadline_epoch': wall_start + budget_s, 'end_epoch': end_epoch,
                  'remaining_budget_s': round(remaining, 3), 'released_after_s': round(released_after_s, 3)}
        (out / ('complete.json' if final == 'complete' else 'incomplete.json')).write_text(json.dumps(marker, indent=1))
        subprocess.run(['gzip', '-rq', str(out / 'logs')], timeout=60)
        print(json.dumps(marker))
    return 0 if final == 'complete' else 1


# ---------------------------------------------------------------- combine
def validate_window(lines, m, w, plan, i, manifest_hash, reasons):
    """Strict chronological validation of one window's record stream: header, lock record, two
    successful warm-ups, then for each planned position its attempts (payload, payload, pair record),
    consecutive seq numbers, retained walls equal to their payload records, and one identity record
    after the first retained pair. Returns (retained [(kind, walls)], per-arm counts); appends defects."""
    pfx = f'window {i}: '
    recs = []
    for n, line in enumerate(lines, 1):
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            reasons.append(pfx + f'malformed record at line {n}'); return [], None, None
    it = iter(recs)
    nxt = lambda: next(it, None)
    h = nxt()
    hd = h.get('header') if isinstance(h, dict) else None
    need = ('manifest_sha256', 'workload', 'window', 'venue', 'gpu_uuid', 'payload_cpus', 'runner_cpus',
            'gpu_local_cpus', 'locks', 'dry_run', 'deadline_epoch')
    if not hd or any(k not in hd for k in need):
        reasons.append(pfx + 'missing or incomplete header'); return [], None, None
    if (hd['manifest_sha256'] != manifest_hash or hd['workload'] != w['_name'] or hd['window'] != i
            or hd['venue'] != m['venue'] or hd['gpu_uuid'] != m.get('gpu_uuid')
            or hd['payload_cpus'] != m['payload_cpus'] or hd['runner_cpus'] != m['runner_cpus']
            or hd['locks'] != m['locks'] or not m['locks']
            or parse_cpus(hd['payload_cpus']) & parse_cpus(hd['runner_cpus'])
            or abs(hd['deadline_epoch'] - hd.get('start_epoch', math.inf) - m['budget_s']) > 1e-3):
        reasons.append(pfx + 'header does not match the manifest (venue, GPU, masks, locks or budget)')
    if hd['dry_run'] is not False:
        reasons.append(pfx + 'dry run (no GPU checks or no input/source checks), never a verdict')
    if any(isinstance(r, dict) and 'header' in r for r in recs[1:]):
        reasons.append(pfx + 'more than one header')
    if 'locks_acquired_after_s' not in (nxt() or {}):
        reasons.append(pfx + 'lock record missing'); return [], None, None
    counts = {a: {'attempts': 0, **{k: 0 for k in PAYLOAD_FAILURES + ('resource',)}} for a in LABELS}
    seq = [0]

    def payload(phase, label):
        r = nxt()
        if not isinstance(r, dict) or r.get('phase') != phase or r.get('label') != label or r.get('seq') != seq[0] + 1:
            reasons.append(pfx + f'expected {phase} payload {label} seq {seq[0] + 1}, found {str(r)[:80]}')
            return None
        seq[0] += 1
        return r

    for label in ('main', 'fix'):
        r = payload('warmup', label)
        if r is None:
            return [], None, None
        if 'failure' in r or r.get('rc') != 0:
            reasons.append(pfx + f'warm-up {label} failed')
    retained, ident = [], []
    for pos, (first, second, kind) in enumerate(plan, 1):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            r1, r2 = payload('timed', first), payload('timed', second)
            pr = nxt()
            if r1 is None or r2 is None or not isinstance(pr, dict) or pr.get('position') != pos:
                reasons.append(pfx + f'position {pos}: records missing or out of order'); return retained, counts, hd
            for r in (r1, r2):
                counts[r['label']]['attempts'] += 1
                if 'failure' in r:
                    counts[r['label']][r['failure']] += 1
            ok = 'failure' not in r1 and 'failure' not in r2 and r1.get('rc') == 0 and r2.get('rc') == 0
            if (pr.get('order') != f'{first},{second}' or pr.get('pair') != kind or pr.get('attempt') != attempt
                    or pr.get('retained') is not ok or pr.get('seqs') != [r1['seq'], r2['seq']]):
                reasons.append(pfx + f'position {pos}: pair record contradicts its payloads'); return retained, counts, hd
            if ok and any(r.get('observed_mask') != m['payload_cpus'] or r.get('pdf_pages') != w['expected_pdf_pages']
                          for r in (r1, r2)):
                reasons.append(pfx + f'position {pos}: retained payload lacks its CPU-mask or product evidence')
                return retained, counts, hd
            if ok:
                ws = pr.get('walls') or {}
                if ws.get(first) != r1.get('wall_s') or ws.get(second) != r2.get('wall_s') or None in ws.values():
                    reasons.append(pfx + f'position {pos}: retained walls differ from the payload records')
                    return retained, counts, hd
                retained.append((kind, ws))
                if pos == 1:
                    ir = nxt()
                    if not isinstance(ir, dict) or 'identity' not in ir:
                        reasons.append(pfx + 'first-pair identity record missing'); return retained, counts, hd
                    ident.append(ir['identity'])
                break
        else:
            reasons.append(pfx + f'position {pos}: no retained attempt'); return retained, counts, hd
    if nxt() is not None:
        reasons.append(pfx + 'records after the last planned position')
    all_ident = [r['identity'] for r in recs if isinstance(r, dict) and 'identity' in r]
    if (len(all_ident) != 1 or len(ident) != 1 or ident[0].get('position') != 1 or ident[0].get('identical') is not True
            or ident[0].get('problems') != [] or not ident[0].get('compared', 0) >= 1
            or not ident[0].get('mrc_compared', 0) >= 1):
        reasons.append(pfx + 'product identity failed, missing or inconsistent')
    return retained, counts, hd


def combine(o):
    reasons, res = [], {'workload': o.workload, 'stats_sha256': sha256(HERE / 'vendor' / 'stats.py')}
    try:
        m = json.loads(Path(o.manifest).read_text())
        if m.get('frozen_files', {}).get('vendor/stats.py') != res['stats_sha256']:
            reasons.append('statistics helper differs from the manifest')
        mh = sha256(o.manifest)
        w = dict(m['workloads'][o.workload], _name=o.workload)
        plan = [tuple(x.split(',')) for x in w['plan']]
        comp, null, wa, wb, per_window = [], [], [], [], []
        counts = {a: {'attempts': 0, **{k: 0 for k in PAYLOAD_FAILURES + ('resource',)}} for a in LABELS}
        for i in range(1, w['windows'] + 1):
            wd = Path(o.out) / o.workload / f'window{i}'
            diag = {'window': i}
            per_window.append(diag)
            if not (wd / 'complete.json').is_file():
                inc = wd / 'incomplete.json'
                reasons.append(f'window {i}: no completion marker'
                               + (f' ({json.loads(inc.read_text()).get("reason")})' if inc.is_file() else ''))
                continue
            mk = json.loads((wd / 'complete.json').read_text())
            retained, c, hd = validate_window((wd / 'runs.jsonl').read_text().splitlines(), m, w, plan, i, mh, reasons)
            hd = hd or {}
            if (mk.get('status') != 'complete' or mk.get('manifest_sha256') != mh or mk.get('workload') != o.workload
                    or mk.get('window') != i or mk.get('positions') != len(plan) or mk.get('budget_s') != m['budget_s']
                    or mk.get('start_epoch') != hd.get('start_epoch') or mk.get('deadline_epoch') != hd.get('deadline_epoch')
                    or not isinstance(mk.get('remaining_budget_s'), (int, float)) or mk['remaining_budget_s'] < 0
                    or not mk.get('end_epoch', math.inf) <= mk.get('deadline_epoch', -math.inf)
                    or not 0 <= mk.get('released_after_s', math.inf) <= m['budget_s']):
                reasons.append(f'window {i}: completion marker inconsistent with the header or budget, or late')
            for kind, ws in retained:
                if kind == 'null':
                    null.append(ws['mainb'] - ws['main'])
                else:
                    comp.append({'order': kind, 'd': ws['fix'] - ws['main']}); wa.append(ws['main']); wb.append(ws['fix'])
            if c:
                for a in LABELS:
                    for k in counts[a]:
                        counts[a][k] += c[a][k]
            diag.update(retained_pairs=len(retained))
        n_ab = sum(c['order'] == 'AB' for c in comp); n_ba = len(comp) - n_ab
        if len(comp) != w['n'] or n_ab != n_ba:
            reasons.append(f'comparison pairs {len(comp)} ({n_ab} AB / {n_ba} BA), declared {w["n"]} balanced')
        if len(null) != 2 * NULL_BLOCKS:
            reasons.append(f'null pairs {len(null)}, declared {2 * NULL_BLOCKS}')
        payload_fail = {a: sum(counts[a][k] for k in PAYLOAD_FAILURES) for a in LABELS}
        systematic = []
        if sum(payload_fail.values()) >= 2:
            systematic.append(f'{sum(payload_fail.values())} payload failures (exit/timeout/product)')
        if payload_fail['fix'] >= 1 and payload_fail['main'] + payload_fail['mainb'] == 0:
            systematic.append('payload failures on the fix arm only (arm-dependent)')
        if systematic:
            reasons.append('systematic payload failures: ' + '; '.join(systematic))
        res.update(attempts_and_failures_by_arm=counts, systematic_failures=systematic, per_window=per_window,
                   pairs=len(comp), pairs_AB=n_ab, pairs_BA=n_ba, null_pairs=len(null))
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
    except Exception as exc:                              # never an exception instead of a verdict
        reasons.append(f'evidence unreadable: {type(exc).__name__}: {exc}')
    label = INCOMPLETE if reasons else res['statistical_label']
    res.update(label=label, incomplete_reasons=reasons)
    Path(o.result).write_text(json.dumps(res, indent=1))
    print(label, json.dumps({k: res.get(k) for k in ('workload', 'pairs', 'median_d_s', 'ci95_s',
                                                      'ci_pct_of_main_wall', 'incomplete_reasons')})[:2000])
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('freeze')
    for k in ('manifest', 'venue', 'gpu-uuid', 'src', 'main-sha', 'fix-build-sha', 'a', 'a-sha256', 'b', 'b-sha256',
              'build-settings', 'payload-cpus', 'runner-cpus'):
        f.add_argument('--' + k, required=True)
    f.add_argument('--lock', action='append', required=True, help='lock file held for each whole window')
    f.add_argument('--windows', type=int, default=2)
    f.add_argument('--workload', action='append', required=True, help='name:N:datadir:motioncorr args')
    r = sub.add_parser('run')
    for k in ('manifest', 'workload', 'out', 'scratch'):
        r.add_argument('--' + k, required=True)
    r.add_argument('--window', type=int, required=True)
    r.add_argument('--gpu-uuid', default=None, help='omit only for a dry run with a stub payload')
    r.add_argument('--samplers', action='store_true', help='mpstat and nvidia-smi every 10 s')
    r.add_argument('--dry-run-inputs', action='store_true', help='controls only: skip input and source checks')
    c = sub.add_parser('combine')
    for k in ('manifest', 'workload', 'out', 'result'):
        c.add_argument('--' + k, required=True)
    o = ap.parse_args()
    if o.cmd == 'freeze':
        return freeze(o)
    if o.cmd == 'run':
        return run_window(o)
    return combine(o)


if __name__ == '__main__':
    sys.exit(main())
