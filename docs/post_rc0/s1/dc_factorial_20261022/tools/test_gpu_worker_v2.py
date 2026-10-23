#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Harmless host controls for gpu_worker_v2.py: fake nvidia-smi, mock jobs, no GPU.

Every job is a short Python mock; the only processes signalled are mock
descendants created by the worker under test. An independent sentinel process
of the same user must survive untouched. Writes a JSON receipt to --json.
"""
import argparse, fcntl, hashlib, json, os, signal, subprocess, sys, tempfile, textwrap, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKER = Path(os.environ.get('GPU_WORKER_V2_UNDER_TEST', HERE / 'gpu_worker_v2.py'))  # mutants only
UUID = 'GPU-00000000-test-test-test-000000000002'

FAKE_SMI = textwrap.dedent('''\
    import json, os, sys
    def alive(p):
        try: os.kill(p, 0); return True
        except OSError: return False
    st = json.load(open(os.environ['FAKE_SMI_STATE']))
    if st.get('fail'): sys.exit(9)
    uuid = os.environ['FAKE_UUID']
    if 'query-gpu' in ' '.join(sys.argv[1:]):
        print('0, GPU-other-0, 1 MiB, 0 %, 0')
        print('%d, %s, 1 MiB, 0 %%, %d' % (st.get('index', 2), uuid, st.get('ecc', 0)))
    else:
        own = [int(x) for x in open(st['own_file']).read().split()] if os.path.exists(st['own_file']) else []
        for pid in st.get('foreign', []) + [p for p in own if alive(p)]:
            print('%s, %d, 10 MiB' % (uuid, pid))
''')

MOCK_JOB = textwrap.dedent('''\
    import json, os, subprocess, sys, time
    mode, out = sys.argv[1], sys.argv[2]
    state = os.environ['FAKE_SMI_STATE']
    st = json.load(open(state))
    with open(st['own_file'], 'a') as f: f.write('%d\\n' % os.getpid())
    if mode == 'ok':
        time.sleep(0.4); open(out + '/product.txt', 'w').write('ok\\n'); sys.exit(0)
    if mode == 'foreign_after':
        time.sleep(0.4); st['foreign'] = [999999]; json.dump(st, open(state, 'w'))
        time.sleep(0.6); open(out + '/product.txt', 'w').write('ok\\n'); sys.exit(0)
    if mode == 'tree':
        # child in our group, a grandchild in its own new session, then outlive the timeout
        kids = [subprocess.Popen(['sleep', '300']),
                subprocess.Popen([sys.executable, '-c', 'import os,sys,time,subprocess;os.setsid();g=subprocess.Popen(["sleep","300"]);open(sys.argv[1],"w").write(str(g.pid));time.sleep(300)', out + '/grandchild.pid'])]
        while not os.path.exists(out + '/grandchild.pid'): time.sleep(0.02)
        time.sleep(0.1)
        open(out + '/tree.json', 'w').write(json.dumps([k.pid for k in kids] + [int(open(out + '/grandchild.pid').read())]))
        time.sleep(300)
''')

SENTINEL = textwrap.dedent('''\
    import signal, sys, time
    log = sys.argv[1]
    def h(s, f): open(log, 'a').write('signal %d\\n' % s)
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(s, h)
    open(log, 'a').write('ready\\n')
    time.sleep(120)
''')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except PermissionError: return True


def setup(tmp, modes, state):
    tmp = Path(tmp)
    (tmp / 'root').mkdir(); (tmp / 'root/runs').mkdir()
    (tmp / 'root/SOURCE_SHA').write_text('mock-source\n')
    (tmp / 'smi.py').write_text(FAKE_SMI)
    smi = tmp / 'nvidia-smi'
    smi.write_text(f'#!/bin/sh\nexec {sys.executable} {tmp / "smi.py"} "$@"\n'); smi.chmod(0o755)
    job = tmp / 'mock_job'
    job.write_text(f'#!{sys.executable}\n' + MOCK_JOB); job.chmod(0o755)
    (tmp / 'binaries.json').write_text(json.dumps({'cuda-exp': dict(path=str(job), sha256=sha(job))}))
    q = [dict(id=f'J{i}-{m}', tier='T', backend='cuda', arm='both', build='cuda-exp', group='g', cwd=str(tmp),
              args=[m, '{OUT}'], inputs={}, model=False) for i, m in enumerate(modes)]
    (tmp / 'queue.json').write_text(json.dumps(q))
    state.setdefault('own_file', str(tmp / 'own.txt'))
    (tmp / 'state.json').write_text(json.dumps(state))
    return tmp


def worker(tmp, timeout=30, extra_env=None, background=False):
    env = dict(os.environ, FAKE_SMI_STATE=str(tmp / 'state.json'), FAKE_UUID=UUID, **(extra_env or {}))
    cmd = [sys.executable, '-B', str(WORKER), '--root', str(tmp / 'root'), '--queue', str(tmp / 'queue.json'),
           '--runs-dir', str(tmp / 'root/runs-v2'), '--binaries', str(tmp / 'binaries.json'), '--cpu', '0',
           '--uuid', UUID, '--gpu-index', '2', '--lock', str(tmp / 'gpu.lock'), '--job-timeout', str(timeout),
           '--smi', str(tmp / 'nvidia-smi'), '--prefix', '']
    if background:
        return subprocess.Popen(cmd, env=env, stdout=open(tmp / 'w.out', 'w'), stderr=subprocess.STDOUT)
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def receipts(tmp, kind):
    return sorted((tmp / 'root/runs-v2').glob(kind + '-*.json'))


def lease_free(tmp):
    with open(tmp / 'gpu.lock', 'a') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); return True
        except BlockingIOError: return False


def run_record(tmp, jid):
    p = tmp / 'root/runs-v2' / jid / 'RUN.json'
    return json.loads(p.read_text()) if p.exists() else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--json', required=True); a = ap.parse_args()
    results = []
    def check(name, ok, **detail):
        results.append(dict(control=name, result='PASS' if ok else 'FAIL', **detail))
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)

    with tempfile.TemporaryDirectory() as t:  # C1 contention at admission
        tmp = setup(t, ['ok', 'ok'], dict(foreign=[424242]))
        r = worker(tmp)
        stop = [json.loads(p.read_text()) for p in receipts(tmp, 'STOP')]
        check('C1 foreign process before first launch: no launch', r.returncode == 75 and not list((tmp / 'root/runs-v2').glob('J*'))
              and stop and 'foreign' in json.dumps(stop) and lease_free(tmp), exit=r.returncode, stop=stop)

    with tempfile.TemporaryDirectory() as t:  # C2 ECC and C3 unreadable query
        tmp = setup(t, ['ok'], dict(ecc=1)); r = worker(tmp)
        check('C2 nonzero ECC: no launch', r.returncode == 75 and not (tmp / 'root/runs-v2/J0-ok').exists(), exit=r.returncode)
    with tempfile.TemporaryDirectory() as t:
        tmp = setup(t, ['ok'], dict(fail=True)); r = worker(tmp)
        check('C3 failed nvidia-smi query: no launch', r.returncode == 75 and not (tmp / 'root/runs-v2/J0-ok').exists(), exit=r.returncode)
    with tempfile.TemporaryDirectory() as t:
        tmp = setup(t, ['ok'], dict(index=1)); r = worker(tmp)
        check('C3b UUID at wrong index: no launch', r.returncode == 75 and not (tmp / 'root/runs-v2/J0-ok').exists(), exit=r.returncode)

    with tempfile.TemporaryDirectory() as t:  # C4 normal queue, own process visible on GPU is not foreign
        tmp = setup(t, ['ok', 'ok'], {}); r = worker(tmp)
        recs = [run_record(tmp, j) for j in ('J0-ok', 'J1-ok')]
        check('C4 clean queue: both jobs recorded, own GPU process not foreign', r.returncode == 0 and all(
              x and x['status'] == 'EXITED' and x['exit'] == 0 and not x['resource']['foreign_on_target_during'] for x in recs)
              and lease_free(tmp), exit=r.returncode, stderr=r.stderr[-400:])

    with tempfile.TemporaryDirectory() as t:  # C5 foreign appears during job 1
        tmp = setup(t, ['foreign_after', 'ok'], {}); r = worker(tmp)
        rec = run_record(tmp, 'J0-foreign_after')
        check('C5 foreign appears mid-job: job recorded with foreign, stop before next launch',
              r.returncode == 75 and rec and rec['exit'] == 0 and '999999' in json.dumps(rec['resource'])
              and not (tmp / 'root/runs-v2/J1-ok').exists() and lease_free(tmp), exit=r.returncode, resource=rec and rec['resource'])

    with tempfile.TemporaryDirectory() as t:  # C6 existing directory preserved
        tmp = setup(t, ['ok', 'ok'], {})
        old = tmp / 'root/runs-v2/J0-ok'; old.mkdir(parents=True); (old / 'partial.log').write_text('incomplete\n')
        before = {p.name: sha(p) for p in old.iterdir()}
        r = worker(tmp)
        after = {p.name: sha(p) for p in old.iterdir()}
        final = [json.loads(p.read_text()) for p in receipts(tmp, 'FINAL')]
        check('C6 existing incomplete directory untouched and skipped', r.returncode == 0 and before == after
              and not (old / 'RUN.json').exists() and run_record(tmp, 'J1-ok') and final and final[0]['preserved_existing'] == ['J0-ok'],
              exit=r.returncode, before=before, after=after)

    for name, how in (('C7 timeout', 'timeout'), ('C8 cancellation (SIGTERM to worker)', 'cancel')):
        with tempfile.TemporaryDirectory() as t:
            tmp = setup(t, ['tree', 'ok'], {})
            sent_log = tmp / 'sentinel.log'
            sentinel = subprocess.Popen([sys.executable, '-c', SENTINEL, str(sent_log)], start_new_session=True)
            while not sent_log.exists(): time.sleep(0.05)
            w = worker(tmp, timeout=3 if how == 'timeout' else 600, background=True)
            tree = tmp / 'root/runs-v2/J0-tree/tree.json'
            deadline = time.time() + 20
            while not tree.exists() and time.time() < deadline: time.sleep(0.05)
            time.sleep(0.5)
            if how == 'cancel': w.send_signal(signal.SIGTERM)
            kids = json.loads(tree.read_text()) if tree.exists() else []
            try: code = w.wait(timeout=60)
            except subprocess.TimeoutExpired:
                # A worker that cannot reap holds its lease by design. Record FAIL, then remove only
                # this control's own processes by exact PID: worker, mock root and recorded tree.
                own = [int(x) for x in (tmp / 'own.txt').read_text().split()] if (tmp / 'own.txt').exists() else []
                held = not lease_free(tmp)
                for pid in [w.pid] + own + kids:
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                w.wait(); sentinel.kill(); sentinel.wait()
                check(f'{name}: owned descendants reaped, record kept, no foreign signal, lease released', False,
                      reason='worker did not finish within 60 s (lease held: %s)' % held,
                      receipts=[p.name for p in (tmp / 'root/runs-v2').glob('*.json')])
                continue
            rec = run_record(tmp, 'J0-tree')
            # The setsid grandchild's own sleep is found through the recorded identities.
            leftovers = [k for k in kids if alive(k)]
            sent_alive = alive(sentinel.pid); sentinel.kill(); sentinel.wait()
            check(f'{name}: owned descendants reaped, record kept, no foreign signal, lease released',
                  rec and rec['status'] == ('TIMEOUT' if how == 'timeout' else 'CANCELLED') and not leftovers
                  and not rec['cleanup']['owned_live_after'] and sent_alive and 'signal' not in sent_log.read_text()
                  and not (tmp / 'root/runs-v2/J1-ok').exists() and lease_free(tmp) and code in (75, 4),
                  exit=code, status=rec and rec['status'], signals=rec and rec['cleanup']['signals'],
                  cleanup_errors=rec and rec['cleanup']['errors'], leftovers=leftovers, sentinel_log=sent_log.read_text())

    receipt = dict(schema='gpu-worker-v2-host-controls/1', python=sys.version, platform=sys.platform,
                   worker_sha256=sha(WORKER), test_sha256=sha(__file__), results=results,
                   limits='Host mock controls with a fake nvidia-smi; no GPU, no motioncorr. On macOS the '
                          'ownership helper runs in observed-descendants polling mode; Linux child-subreaper '
                          'adoption is not exercised here.')
    Path(a.json).write_text(json.dumps(receipt, indent=1) + '\n')
    sys.exit(0 if all(r['result'] == 'PASS' for r in results) else 1)


if __name__ == '__main__':
    main()
