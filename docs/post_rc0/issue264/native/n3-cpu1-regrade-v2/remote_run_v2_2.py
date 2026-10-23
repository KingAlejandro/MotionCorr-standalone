# SPDX-License-Identifier: GPL-2.0-or-later
"""Prospective Linux CPU13 driver. NOT execution authorization. No input root argument.
Launch only after fresh independent review and parent scheduling, per REMOTE-PLAN-v2.2.md.
"""
import argparse, contextlib, datetime, hashlib, importlib.util, io, json, os, pathlib, platform
import resource, subprocess, sys, time, traceback

ROOT = '/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1'
LEASE = '/tmp/motioncorr-guard264-cpu13-regrade.lock'
CAP = 20 << 20
FILE_CAP = 1 << 20
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
sha = lambda b: hashlib.sha256(b).hexdigest()
utc = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()


def verify_package(directory, commit, manifest_sha):
    p = pathlib.Path(directory)
    if p.resolve() != p or p.is_symlink():
        raise ValueError('package directory must be canonical')
    if (p / 'PACKAGE.json').is_symlink() or (p / 'PACKAGE.json').stat().st_size > FILE_CAP:
        raise ValueError('package manifest is not bounded/regular')
    raw = (p / 'PACKAGE.json').read_bytes()
    if len(raw) > FILE_CAP or sha(raw) != manifest_sha:
        raise ValueError('package manifest hash mismatch')
    m = json.loads(raw)
    if m['source_commit'] != commit or len(commit) != 40:
        raise ValueError('package source revision mismatch')
    required = {'regrade_v2_2.py', 'remote_run_v2_2.py', 'CONTRACT.md', 'AMENDMENT-1.md',
                'AMENDMENT-2.md', 'EXPECT_LIVE.json', 'EVIDENCE_MANIFEST.json',
                'REMOTE-PLAN-v2.2.md', 'predictions_iter2.json'}
    if set(m['files']) != required or {x.name for x in p.iterdir()} != required | {'PACKAGE.json'}:
        raise ValueError('package member set mismatch')
    total = len(raw)
    for name, pin in m['files'].items():
        f = p / name
        if f.is_symlink() or not f.is_file() or f.stat().st_size > FILE_CAP:
            raise ValueError('package member is not a bounded regular file: ' + name)
        b = f.read_bytes(); total += len(b)
        blob = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
        if len(b) != pin['size'] or sha(b) != pin['sha256'] or blob != pin['git_blob']:
            raise ValueError('package member identity mismatch: ' + name)
    if total > FILE_CAP or sum(x['size'] for x in m['files'].values()) != m['content_bytes']:
        raise ValueError('package content cap/size mismatch')
    return m


def cpu13_sample():
    with open('/proc/stat') as f:
        values = next(l for l in f if l.startswith('cpu13 ')).split()[1:]
    v = list(map(int, values))[:8]  # guest/guest_nice are already included in user/nice
    return sum(v), v[3] + v[4]


def compare_live(pre, post):
    # Private-index paths differ; compare every original index and source/binary descriptor.
    def stable(x):
        return {'scratch_root': x['scratch_root'], 'expect_sha256': x['expect_sha256'],
                'binaries': x['binaries'], 'trees': {n: {k: v for k, v in t.items() if k != 'git_calls'}
                                                for n, t in x['trees'].items()}}
    if pre['verdict'] != 'PASS' or post['verdict'] != 'PASS' or stable(pre) != stable(post):
        raise ValueError('live pre/post identity mismatch')


def compare_files(pre, post):
    if pre['verdict'] != 'PASS' or post['verdict'] != 'PASS' or pre != post:
        raise ValueError('file pre/post identity mismatch')


def operation_bytes(namespace):
    return sum(p.stat().st_size for p in pathlib.Path(namespace).rglob('*') if p.is_file() and not p.is_symlink())


def run(a):
    if sys.platform != 'linux' or sys.version_info < (3, 8):
        raise ValueError('requires Linux Python >=3.8; local execution is forbidden')
    import fcntl
    package = pathlib.Path(__file__).resolve().parent
    manifest = verify_package(package, a.source_commit, a.package_manifest_sha256)
    if any(os.environ.get(k) != '1' for k in THREADS):
        raise ValueError('all five numeric thread environment variables must equal 1')
    if os.sched_getaffinity(0) != {13}:
        raise ValueError('affinity must be exactly CPU13')
    if pathlib.Path.cwd().resolve() == pathlib.Path(ROOT) or pathlib.Path(ROOT) in pathlib.Path.cwd().resolve().parents:
        raise ValueError('launch cwd is inside input root')
    # Lock path is shared by protocol; O_NOFOLLOW prevents following a replacement symlink.
    fd = os.open(LEASE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # contention terminates, no wait/retry
        out = pathlib.Path(a.out).absolute()
        namespace = package.parent
        if out.parent != namespace or out.exists() or out.parent.resolve() != out.parent:
            raise ValueError('output must be a new sibling of package in the new namespace')
        if pathlib.Path(ROOT) == namespace or pathlib.Path(ROOT) in namespace.parents:
            raise ValueError('namespace is inside input root')
        if operation_bytes(namespace) > 2 * FILE_CAP:
            raise ValueError('namespace already exceeds 2 MiB before operation')
        out.mkdir()
        # Enforce a hard maximum per newly written file; fixed call graph writes <=10 reports/logs.
        resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_CAP, FILE_CAP))
        rec = {'kind': 'prospective cpu1 regrade v2.2 operation', 'start_utc': utc(),
               'source_commit': a.source_commit, 'package_manifest_sha256': a.package_manifest_sha256,
               'package': manifest, 'argv': sys.argv, 'pid': os.getpid(), 'uid': os.getuid(),
               'lease': LEASE, 'affinity': sorted(os.sched_getaffinity(0)), 'python': sys.version,
               'python_executable': os.path.realpath(sys.executable), 'platform': platform.platform(),
               'numeric_threads': {k: os.environ[k] for k in THREADS}, 'steps': [], 'status': 'FAIL'}
        def save():
            target = out / 'OPERATION.json'
            tmp = out / 'OPERATION.json.partial'
            tmp.write_text(json.dumps(rec, indent=1) + '\n'); os.replace(tmp, target)
        save()
        try:
            for name, cmd in [('python-version', [sys.executable, '--version']),
                              ('git-version', ['/usr/bin/git', '--version']),
                              ('taskset-witness', ['/usr/bin/taskset', '-pc', str(os.getpid())])]:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                rec[name] = {'argv': cmd, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
                if p.returncode:
                    raise ValueError(name + ' failed')
            for name, path in [('python_sha256', os.path.realpath(sys.executable)), ('git_sha256', '/usr/bin/git')]:
                h = hashlib.sha256()
                with open(path, 'rb') as f:
                    for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
                rec[name] = h.hexdigest()
            pre = cpu13_sample(); time.sleep(3); post = cpu13_sample()
            total, idle = post[0] - pre[0], post[1] - pre[1]
            busy = (total - idle) / total if total > 0 else 1
            rec['cpu13_sample'] = {'pre': pre, 'post': post, 'busy_fraction': busy}
            if busy > 0.5:
                raise ValueError('CPU13 is busy (>50%)')
            spec = importlib.util.spec_from_file_location('regrade_v2_2', package / 'regrade_v2_2.py')
            g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
            def step(name, function, **kw):
                start = utc(); buf = io.StringIO(); error = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(error):
                    rc = function(argparse.Namespace(**kw))
                rec['steps'].append({'name': name, 'start_utc': start, 'finish_utc': utc(), 'exit': rc,
                                     'arguments': kw, 'stdout': buf.getvalue(), 'stderr': error.getvalue()})
                save()
                if operation_bytes(namespace) > CAP:
                    raise ValueError('operation exceeded 20 MiB')
                if rc != 0:
                    raise ValueError(name + ' failed; no retry')
            for phase in ('pre', 'post'):
                step('live-' + phase, g.cmd_precheck_live, scratch_root=ROOT,
                     expect=str(package / 'EXPECT_LIVE.json'), proc_root='/proc', out=str(out / ('live-' + phase + '.json')))
                step('files-' + phase, g.cmd_precheck_files, scratch_root=ROOT,
                     manifest=str(package / 'EVIDENCE_MANIFEST.json'), out=str(out / ('files-' + phase + '.json')))
                if phase == 'pre':
                    step('grade', g.cmd_grade, scratch_root=ROOT, evidence_tar=None, evidence_sha256=None,
                         manifest=str(package / 'EVIDENCE_MANIFEST.json'), precheck=str(out / 'files-pre.json'),
                         predictions=str(package / 'predictions_iter2.json'), out=str(out / 'grade'))
            load = lambda n: json.loads((out / n).read_bytes())
            compare_live(load('live-pre.json'), load('live-post.json'))
            compare_files(load('files-pre.json'), load('files-post.json'))
            verify_package(package, a.source_commit, a.package_manifest_sha256)
            rec['status'] = 'PASS'
        except Exception as e:
            rec['error'] = repr(e); rec['traceback'] = traceback.format_exc()
        finally:
            rec['finish_utc'] = utc(); rec['operation_bytes'] = operation_bytes(namespace); save()
        return 0 if rec['status'] == 'PASS' else 1
    finally:
        os.close(fd)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--source-commit', required=True)
    ap.add_argument('--package-manifest-sha256', required=True); ap.add_argument('--out', required=True)
    args = ap.parse_args()
    try: sys.exit(run(args))
    except Exception as exc: print('refused:', exc, file=sys.stderr); sys.exit(1)
