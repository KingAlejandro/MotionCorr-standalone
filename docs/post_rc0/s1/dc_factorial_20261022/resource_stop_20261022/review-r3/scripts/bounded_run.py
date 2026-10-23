# Run one command in its own session, bounded; identity-checked TERM/KILL of that session leader only.
import json, os, signal, subprocess, sys, time
sys.path.insert(0, sys.argv[1]); from process_ownership import ProcessTable
rec_path, bound, cmd = sys.argv[2], float(sys.argv[3]), sys.argv[4:]
env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
t = ProcessTable(); t0 = time.time()
p = subprocess.Popen(cmd, start_new_session=True, env=env)
b = t.read(p.pid); rec = dict(pid=p.pid, start=b['start'], uid=os.getuid(), argv=cmd, start_utc=time.strftime('%FT%TZ', time.gmtime()), load=os.getloadavg())
try: rec['exit'] = p.wait(timeout=bound)
except subprocess.TimeoutExpired:
    rec['fallback'] = []
    for s in (signal.SIGTERM, signal.SIGKILL):
        cur = t.read(p.pid)
        if cur and cur['start'] == b['start'] and os.getsid(p.pid) == p.pid:
            os.kill(p.pid, s); rec['fallback'].append(int(s))
        try: rec['exit'] = p.wait(timeout=60); break
        except subprocess.TimeoutExpired: rec['exit'] = None
rec.update(end_utc=time.strftime('%FT%TZ', time.gmtime()), seconds=round(time.time() - t0, 1))
open(rec_path, 'w').write(json.dumps(rec, indent=1) + '\n'); print('bounded_run', json.dumps(rec))
