# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded local author controls; fresh fixture per exact/mutant case, no remote/native execution.
Run once: python3 -I -B test_regrade_v2_2.py --namespace NEW_UUID_DIRECTORY --source-commit FULL_SHA
Failed invocations must be retained. No retry/repair in place. Scratch cap 512 MiB.
"""
import argparse, ast, contextlib, datetime, fcntl, hashlib, importlib.util, io, json, os
import pathlib, platform, shutil, struct, subprocess, sys, traceback, uuid

HERE = pathlib.Path(__file__).resolve().parent
CAP = 512 << 20
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
sha = lambda b: hashlib.sha256(b).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main(a):
    lease = os.open('/tmp/motioncorr-guard264-v22-author.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if any(os.environ.get(k) != '1' for k in THREADS):
        raise ValueError('all numeric thread variables must equal 1')
    ns = pathlib.Path(a.namespace).absolute()
    if ns.parent.resolve() != ns.parent:
        raise ValueError('namespace parent must be canonical')
    ns.mkdir(exist_ok=False)
    results = []
    source = (HERE / 'regrade_v2_2.py').read_text()
    old = load('old', HERE / 'regrade_v2_1.py')
    suite = load('fixtures_only', HERE / 'test_regrade_v2_1.py')
    exact = load('v22', HERE / 'regrade_v2_2.py')
    driver = load('driver', HERE / 'remote_run_v2_2.py')
    runtime = {'invocation_uuid': str(uuid.uuid4()), 'argv': sys.argv, 'source_commit': a.source_commit,
               'python': sys.version, 'python_path': os.path.realpath(sys.executable), 'platform': platform.platform(),
               'python_sha256': sha(pathlib.Path(sys.executable).resolve().read_bytes()),
               'load': os.getloadavg(), 'free_bytes': shutil.disk_usage('/System/Volumes/Data').free,
               'numeric_threads': {k: os.environ[k] for k in THREADS}, 'affinity': 'UNAVAILABLE on macOS; no affinity claim',
               'gpu_uuid': 'UNRUN; no GPU query/native/build/SSH', 'lease': '/tmp/motioncorr-guard264-v22-author.lock',
               'sources': {p.name: sha(p.read_bytes()) for p in HERE.glob('*') if p.is_file()},
               'tar_path': suite.TAR, 'tar_sha256': sha(pathlib.Path(suite.TAR).read_bytes()),
               'predictions_sha256': sha(pathlib.Path(suite.PRED).read_bytes()),
               'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (ns / 'RUNTIME.json').write_text(json.dumps(runtime, indent=1) + '\n')
    ps = subprocess.run(['/bin/ps', '-Ao', 'pid,pcpu,comm', '-r'], capture_output=True, text=True)
    (ns / 'OCCUPANCY.txt').write_text('\n'.join(ps.stdout.splitlines()[:25]) + '\n')
    def bytes_used():
        return sum(p.stat().st_size for p in ns.rglob('*') if p.is_file() and not p.is_symlink())
    def record(name, ok, **kw):
        rec = dict(name=name, ok=bool(ok), **kw); results.append(rec)
        print(json.dumps(rec, default=str), flush=True)
        (ns / 'CONTROLS.json').write_text(json.dumps({'source_commit': a.source_commit,
             'grader_sha256': sha(source.encode()), 'suite_sha256': sha(pathlib.Path(__file__).read_bytes()),
             'results': results, 'all_ok': all(x['ok'] for x in results)}, indent=1) + '\n')
        if bytes_used() > CAP:
            raise ValueError('scratch cap exceeded')
    def new(name):
        d = ns / name; d.mkdir(exist_ok=False); return d
    def module(name, replacements=()):
        s = source
        for before, after in replacements:
            assert s.count(before) == 1, before
            s = s.replace(before, after)
        if replacements:
            d = new('mutant-' + name); path = d / 'regrade_v2_2.py'; path.write_text(s)
        else:
            path = HERE / 'regrade_v2_2.py'
        m = load(name, path)
        return m, sha(s.encode())
    def call(m, fn, args, d):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = getattr(m, fn)(argparse.Namespace(**args))
        (d / 'CALL.json').write_text(json.dumps({'function': fn, 'arguments': args, 'exit': rc,
          'stdout': out.getvalue(), 'stderr': err.getvalue(), 'grader_sha256': sha(pathlib.Path(m.__file__).read_bytes())}, indent=1) + '\n')
        return rc
    def inventory(root):
        return {str(p.relative_to(root)): {'sha256': sha(p.read_bytes()), 'stat': list(exact.stable_stat(p.stat()))}
                for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    def live(name, variant='pass', replacements=(), git_bin=None, instrument=None):
        d = new(name); root = d / 'scratch'; root.mkdir()
        expect = suite.live_fixture(str(root), variant)
        (d / 'EXPECT.json').write_text(json.dumps(expect)); (d / 'proc').mkdir()
        m, pin = module(name, replacements)
        if git_bin: m.GIT_BIN = git_bin
        before = inventory(root); observed = []
        real_run = m.subprocess.run
        def observe(cmd, **kw):
            env = kw.get('env', {})
            observed.append({'argv': cmd, 'env': env})
            return real_run(cmd, **kw)
        m.subprocess.run = observe
        original_git = m._git
        def git_hook(tree, private, *args):
            answer = original_git(tree, private, *args)
            if instrument == 'private_refresh' and args == ('status', '--porcelain'):
                # Simulate the optional index metadata refresh, but only on the selected index.
                p = pathlib.Path(private); st = p.stat(); os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
            if instrument == 'original_touch' and args == ('status', '--porcelain'):
                p = pathlib.Path(tree) / '.git/index'; st = p.stat(); os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
            return answer
        m._git = git_hook
        try:
            rc = call(m, 'cmd_precheck_live', dict(scratch_root=str(root), expect=str(d / 'EXPECT.json'),
                      proc_root=str(d / 'proc'), out=str(d / 'live.json')), d)
        finally:
            m.subprocess.run = real_run
        after = inventory(root); changed = [p for p in before if before[p] != after.get(p)]
        (d / 'IDENTITIES.json').write_text(json.dumps({'before': before, 'after': after, 'changed': changed,
                                                    'actual_git_calls': observed}, indent=1) + '\n')
        report = json.loads((d / 'live.json').read_bytes())
        valid_env = all(x['env'].get('GIT_OPTIONAL_LOCKS') == '0' and x['env'].get('GIT_INDEX_FILE')
                        and not x['env']['GIT_INDEX_FILE'].startswith(str(root) + '/') for x in observed)
        return rc, changed, report, observed, valid_env, pin
    try:
        # Numerical/parsing/row logic was copied exactly, including all gates and parity.
        defs = lambda p: {n.name: ast.dump(n) for n in ast.parse(p).body if isinstance(n, ast.FunctionDef)}
        olddefs, newdefs = defs((HERE / 'regrade_v2_1.py').read_text()), defs(source)
        unchanged = ('coefficients', 'global_rows', 'rows_equal', 'mrc_check', 'grade', 'snapshot', 'consumed')
        record('numerical_ast_unchanged', all(olddefs[n] == newdefs[n] for n in unchanged), functions=unchanged)
        # Original tar is used in place, not copied. CLI exact source receipt retained.
        d = new('real-tar')
        cmd = [sys.executable, '-I', '-B', str(HERE / 'regrade_v2_2.py'), 'grade', '--evidence-tar', suite.TAR,
               '--evidence-sha256', suite.TAR_SHA, '--predictions', suite.PRED, '--manifest', str(HERE / 'EVIDENCE_MANIFEST.json'), '--out', str(d / 'out')]
        p = subprocess.run(cmd, capture_output=True, text=True)
        (d / 'COMMAND.json').write_text(json.dumps({'argv': cmd, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}, indent=1) + '\n')
        rep = json.loads((d / 'out/REGRADE_V2_2.json').read_bytes())
        record('retained_tar', p.returncode == 2 and rep['star_layer_verdict'] == 'PASS' and rep['full_verdict'] == 'UNRUN'
               and not rep['row_parity_problems'] and rep['n4']['status'] == 'PASS', exit=p.returncode,
               consumed=len(rep['consumed']['files']), tar_sha256=runtime['tar_sha256'])
        # Tiny fresh growth and identity probes, each source/mutant owns its own input.
        stream_mutants = {
          'bound_removed': (("if n > cap:", "if False:"),),
          'identity_removed': (("if stable_stat(st) != stable_stat(end) or stable_stat(end) != stable_stat(named) or n != st.st_size:", "if False:"),),
          'both_removed': (("if n > cap:", "if False:"), ("if stable_stat(st) != stable_stat(end) or stable_stat(end) != stable_stat(named) or n != st.st_size:", "if False:"))}
        for mode, mutant, want in [('growth',None,1), ('growth','bound_removed',1), ('growth','both_removed',0),
                                    ('same_size',None,1), ('same_size','identity_removed',0),
                                    ('replace',None,1), ('replace','identity_removed',0), ('restored',None,0)]:
            name = 'stream-' + mode + '-' + (mutant or 'exact'); d = new(name); (d / 'bin').write_bytes(b'1234')
            m, pin = module(name, stream_mutants.get(mutant, ()))
            actual_read = m.os.read; triggered = False; sizes = []
            def read(fd, n):
                nonlocal triggered
                if not triggered:
                    triggered = True
                    if mode == 'growth':
                        with (d / 'bin').open('ab') as f: f.write(b'5678')
                    elif mode == 'same_size':
                        (d / 'bin').write_bytes(b'5678')
                    elif mode == 'replace':
                        (d / 'replacement').write_bytes(b'1234'); os.replace(d / 'replacement', d / 'bin')
                b = actual_read(fd, n); sizes.append(len(b)); return b
            m.os.read = read
            try:
                try: answer = m.DirReader(str(d)).hash_stream('bin', cap=4); rc, error = 0, None
                except m.Invalid as e: answer = None; rc, error = 1, str(e)
            finally: m.os.read = actual_read
            record(name, rc == want, exit=rc, expected=want, error=error, result=answer, bytes_read=sum(sizes),
                   grader_sha256=pin, detection='diagnostic-only; identity still rejects' if mutant == 'bound_removed' else 'acceptance-changing control')
        # Private-index positives use both locally installed Git implementations on fresh fixtures.
        for label, binary in [('apple','/usr/bin/git'), ('homebrew','/opt/homebrew/bin/git')]:
            for variant in ('pass', 'stale_index_stat'):
                name = 'private-' + label + '-' + variant
                rc, changed, rep, calls, env_ok, pin = live(name, variant, git_bin=binary)
                record(name, rc == 0 and not changed and len(calls) == 15 and env_ok,
                       exit=rc, changed=changed, actual_git_calls=len(calls), private_environment=env_ok,
                       problems=rep['problems'], git=binary, grader_sha256=pin)
        # Simulate a private metadata refresh; then remove redirection on a separate fixture.
        for mutant, want in [(False,0), (True,1)]:
            name = 'private-refresh-' + ('mutant' if mutant else 'exact')
            replacements = (("'GIT_INDEX_FILE': private_index,", "'GIT_INDEX_FILE': os.path.join(tree, '.git', 'index'),"),) if mutant else ()
            # Hook follows the actual selected index argument when redirection is removed.
            if mutant:
                replacements += (("answer = _git(tree, private, *args)", "answer = _git(tree, os.path.join(tree, '.git', 'index'), *args)"),)
            rc, changed, rep, calls, env_ok, pin = live(name, 'stale_index_stat', replacements, instrument='private_refresh')
            record(name, rc == want and (bool(changed) == mutant), exit=rc, changed=changed,
                   problems=rep['problems'], grader_sha256=pin, detection='procedure/index-isolation detection; mutant intentionally writes isolated original')
        # Index guard injection changes only the case-owned original index, never retained input.
        rc, changed, rep, calls, env_ok, pin = live('index-guard-injection', instrument='original_touch')
        record('index-guard-injection', rc == 1 and bool(changed) and 'index changed' in str(rep['problems']), exit=rc,
               changed=changed, problems=rep['problems'], instrumented=True)
        for variant in ('head_differs','untracked_file','runner_modified','binary_differs_from_receipt','binaries_not_distinct','symlink_component'):
            rc, changed, rep, calls, env_ok, pin = live('binding-' + variant, variant)
            record('binding-' + variant, rc == 1 and not changed, exit=rc, problems=rep['problems'])
        # Fake /proc only: no real /proc or SSH. Parent PID is deliberately used for writer.
        proc_cases = [('self',os.getpid(),'writer', 'self',False),
                      ('parent-writer',os.getppid(),'writer','descendant',True),
                      ('unrelated-writer',999999,'writer','option',True),
                      ('sibling',999998,'reader','sibling',False),
                      ('ssh-bootstrap-driver',os.getppid(),'sshd: alex@notty','launch',False),
                      ('cwd-writer',999997,'writer','cwd',True), ('fd-writer',999996,'writer','fd',True)]
        for name, pid, command, kind, want in proc_cases:
            d = new('proc-' + name); root = str(d / 'scratch'); pathlib.Path(root).mkdir()
            proc = d / 'proc'; p = proc / str(pid); p.mkdir(parents=True)
            arg = root + '/n3-cpu1' if kind in ('descendant','self') else '--input=' + root + '/file' if kind == 'option' else root + '-regrade-v2-2-output'
            if kind == 'launch':
                arg = 'exec /usr/bin/taskset -c 13 /usr/bin/python3 -I -B ' + root + '-regrade-v2-2-output/package/remote_run_v2_2.py --out ' + root + '-regrade-v2-2-output/run'
            (p / 'cmdline').write_bytes((command + '\0' + arg + '\0').encode())
            if kind == 'cwd': (p / 'cwd').symlink_to(root + '/n3-cpu1')
            if kind == 'fd': (p / 'fd').mkdir(); (p / 'fd/4').symlink_to(root + '/n3-cpu1/data')
            hits, unreadable = exact._scan_processes(str(proc), root)
            record('proc-' + name, bool(hits) == want and unreadable == 0, hits=hits, fake_proc=True)
            if name == 'parent-writer':
                m, pin = module('ancestor-exemption', (("skip = {os.getpid()}", "skip = {os.getpid(), os.getppid()}"),))
                mh, _ = m._scan_processes(str(proc), root)
                record('ancestor-exemption-mutant', not mh and bool(hits), exact_reject=bool(hits), mutant_reject=bool(mh),
                       grader_sha256=pin, detection='acceptance-changing process refusal')
        # MRC/snapshot regression: fresh directories per case, no tar corpus written.
        for name, mode, mutant, want in [('full-generated','full',False,0),('reread-exact','reread',False,1),
                                       ('reread-mutant','reread',True,0),('symlink','symlink',False,1),
                                       ('header-only','header',False,1)]:
            d = new(name); root = d / 'scratch'; root.mkdir()
            generated = suite.mrcs()
            if mode == 'header': generated = {k: v[:1024] for k,v in generated.items()}
            # reuse original tar read-only in memory, then write each fresh case once
            suite.safe_extract(suite.rebuild(add=generated), str(root))
            if mode == 'symlink':
                target = root / suite.MRC.format('ov-cand-cpu',suite.F_); target.rename(str(target) + '.real'); target.symlink_to(target.name + '.real')
            m, pin = module(name, (("if identity(files2, presence2) != ident: binding.append('input changed during grading')", "pass"),) if mutant else ())
            pre = d / 'pre.json'
            rcpre = call(m,'cmd_precheck_files',dict(scratch_root=str(root),manifest=str(HERE / 'EVIDENCE_MANIFEST.json'),out=str(pre)),d)
            if mode in ('symlink','header'):
                record(name,rcpre==1,exit=rcpre,generated_mrcs=True); continue
            original_grade = m.grade
            if mode == 'reread':
                def grade_and_change(*args):
                    result = original_grade(*args); target = root / suite.MRC.format('ov-cand-cpu',suite.F_)
                    b = bytearray(target.read_bytes()); b[-1] ^= 1; target.write_bytes(b); return result
                m.grade = grade_and_change
            rc = call(m,'cmd_grade',dict(scratch_root=str(root),evidence_tar=None,evidence_sha256=None,
                manifest=str(HERE / 'EVIDENCE_MANIFEST.json'),precheck=str(pre),predictions=suite.PRED,out=str(d / 'out')),d)
            rep = json.loads((d / 'out/REGRADE_V2_2.json').read_bytes())
            record(name,rcpre==0 and rc==want,exit=rc,expected=want,problems=rep['problems'],
                   grader_sha256=pin,generated_mrcs=True,instrumented=mode=='reread')
        # Narrow package built from committed source, measured; driver itself is never run.
        d = new('package')
        cmd = [sys.executable,'-I','-B',str(HERE / 'package_v2_2.py'),'--revision',a.source_commit,'--out',str(d / 'bundle')]
        p = subprocess.run(cmd,capture_output=True,text=True)
        (d / 'COMMAND.json').write_text(json.dumps({'argv':cmd,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=1)+'\n')
        if p.returncode != 0:
            record('package-build',False,exit=p.returncode,stderr=p.stderr); return 1
        receipt=json.loads((d / 'bundle/PACKAGE-RECEIPT.json').read_bytes())
        import tarfile
        package = d / 'unpacked'; package.mkdir()
        with tarfile.open(d / 'bundle/package.tar') as tar:
            for member in tar:
                assert member.isfile() and '/' not in member.name
                (package / member.name).write_bytes(tar.extractfile(member).read())
        verified=driver.verify_package(package,a.source_commit,receipt['package_manifest_sha256'])
        record('package-verified',receipt['package_bytes']<=1<<20 and verified['source_commit']==a.source_commit,
               package_bytes=receipt['package_bytes'],content_bytes=verified['content_bytes'],package_sha256=receipt['package_sha256'])
        # Fresh copy per tamper case, never repair a failing package in place.
        for kind in ('driver','manifest','source'):
            tampered = d / ('tampered-' + kind); shutil.copytree(package,tampered)
            manifest_pin=receipt['package_manifest_sha256']; commit=a.source_commit
            if kind=='driver': (tampered / 'remote_run_v2_2.py').write_bytes(b'tampered')
            if kind=='manifest': (tampered / 'PACKAGE.json').write_bytes(b'{}')
            if kind=='source': commit='0'*40
            try: driver.verify_package(tampered,commit,manifest_pin); rejected=False; error=None
            except ValueError as e: rejected=True; error=str(e)
            record('package-reject-'+kind,rejected,error=error)
        # Pure pre/post comparison controls; runtime Linux path is never entered.
        pre={'verdict':'PASS','scratch_root':'S','expect_sha256':'pin','binaries':{'a':'pin'},
             'trees':{'t':{'head':'h','index_after':{'sha256':'i'},'git_calls':[1]}}}
        post=json.loads(json.dumps(pre));post['trees']['t']['git_calls']=[2]
        driver.compare_live(pre,post);record('compare-private-paths-ignored',True)
        post['trees']['t']['index_after']['sha256']='changed'
        try: driver.compare_live(pre,post); rejected=False
        except ValueError: rejected=True
        record('compare-original-index-change',rejected)
        record('original-tar-unchanged',sha(pathlib.Path(suite.TAR).read_bytes())==runtime['tar_sha256'])
        record('source-restored', (HERE / 'regrade_v2_2.py').read_text()==source, source_sha256=sha(source.encode()))
        record('scratch-cap',bytes_used()<CAP,logical_bytes=bytes_used(),cap_bytes=CAP)
        return 0 if all(x['ok'] for x in results) else 1
    except Exception as exc:
        (ns / 'UNEXPECTED.json').write_text(json.dumps({'error':repr(exc),'traceback':traceback.format_exc()},indent=1)+'\n')
        raise
    finally:
        runtime['finish_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        runtime['final_bytes']=bytes_used()
        (ns / 'RUNTIME.json').write_text(json.dumps(runtime,indent=1)+'\n')
        os.close(lease)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--namespace',required=True);ap.add_argument('--source-commit',required=True)
    sys.exit(main(ap.parse_args()))
