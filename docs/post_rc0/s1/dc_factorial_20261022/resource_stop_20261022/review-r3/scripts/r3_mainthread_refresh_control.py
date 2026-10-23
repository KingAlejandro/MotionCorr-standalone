# R3 review-only control R3-K25: ownership refresh fails in the worker's MAIN thread only (observer and
# sampler threads unaffected) after the job starts; job times out. Expectation for a fail-closed worker:
# CLEANUP_FAILED RUN.json + CLEANUP_FAILED_LEASE_HELD receipt + lease held, within a bounded time.
# Reuses the frozen harness (exported 0751c2f3) machinery: Fixture, single(), identity-checked Registry.
import importlib.util, json, os, signal, sys, tempfile, time
HARNESS, WORKER, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location('h', HARNESS)
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
tail = "sys.exit(m.main(sys.argv[2:]))\n"
assert h.FAULT_ENTRY.count(tail) == 1
h.FAULT_ENTRY = h.FAULT_ENTRY.replace(tail, '''if 'main_refresh_after_flag' in faults:
    import threading
    orig_m = m.ProcessOwnership.refresh
    def refresh_m(self):
        if threading.current_thread() is threading.main_thread() and os.path.exists(os.environ['FAKE_FAULT_FLAG']):
            raise RuntimeError('injected main-thread ownership refresh failure')
        return orig_m(self)
    m.ProcessOwnership.refresh = refresh_m
''' + tail)
def held(f, p, d):
    d['receipt_seen'] = False
    deadline = time.time() + 40
    while time.time() < deadline and not d['receipt_seen']:
        d['receipt_seen'] = bool(f.receipts('CLEANUP_FAILED_LEASE_HELD')); time.sleep(0.1)
    d['seconds_waited'] = round(40 - max(0, deadline - time.time()), 1)
    f.refresh_registry()
    own = [json.loads(x) for x in (f.t / 'own.txt').read_text().splitlines()] if (f.t / 'own.txt').exists() else []
    d['job_root_alive_at_check'] = [i['pid'] for i in own if f.reg.alive(i)]
    d['lease_held_while_alive'] = not f.lease_free()
    d['worker_alive'] = bool(f.worker_ident and f.reg.alive(f.worker_ident))
    r = f.run('J0-flag_tree') or {}
    d['run_status'] = r.get('status'); d['cleanup'] = r.get('cleanup')
    d['kill_worker'] = f.reg.kill(f.worker_ident) if f.worker_ident else None
chk = lambda f, c, d: (d['receipt_seen'] and d['lease_held_while_alive'] and d['worker_alive']
                       and d['run_status'] == 'CLEANUP_FAILED' and not (f.runs / 'J1-ok').exists())
with tempfile.TemporaryDirectory() as t:
    ok, detail = h.single(t, WORKER, ('flag_tree', 'ok'), {}, chk, fault='main_refresh_after_flag',
                          over=dict(job_timeout=2), during=held)
res = dict(control='R3-K25 main-thread-only refresh failure during timeout cleanup', result='PASS' if ok else 'FAIL',
           worker=WORKER, worker_sha256=h.sha(WORKER), harness_sha256=h.sha(HARNESS), detail=detail)
open(OUT, 'w').write(json.dumps(res, indent=1, default=str) + '\n')
print(res['result'], 'receipt_seen', detail.get('receipt_seen'), 'run_status', detail.get('run_status'),
      'root_alive', detail.get('job_root_alive_at_check'), 'signals', (detail.get('cleanup') or {}).get('signals'),
      'leftovers', detail.get('leftovers'), 'sentinel', repr(detail.get('sentinel')))
sys.exit(0 if ok else 1)
