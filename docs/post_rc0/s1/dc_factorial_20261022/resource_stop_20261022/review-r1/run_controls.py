import json, os, subprocess, sys, time
R = '/tmp/motioncorr-dc-gpu-worker-review-r1-20261022'
T = 'docs/post_rc0/s1/dc_factorial_20261022/tools/test_gpu_worker_v2.py'
env = dict(os.environ, TMPDIR=R + '/tmp', OMP_NUM_THREADS='1')
env.pop('GPU_WORKER_V2_UNDER_TEST', None)
t0 = time.time()
p = subprocess.Popen([sys.executable, '-B', T, '--json', R + '/controls-review.json'], env=env,
                     stdout=open(R + '/controls-review.out', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
ident = subprocess.run(['ps', '-o', 'pid=,uid=,pgid=,lstart=', '-p', str(p.pid)], capture_output=True, text=True).stdout.strip()
rec = dict(pid=p.pid, uid=os.getuid(), session_leader=True, ps=ident, start=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)))
try:
    rc = p.wait(timeout=420); rec['timed_out'] = False
except subprocess.TimeoutExpired:
    rec['timed_out'] = True
    now = subprocess.run(['ps', '-o', 'pid=,uid=,pgid=,lstart=', '-p', str(p.pid)], capture_output=True, text=True).stdout.strip()
    if now == ident:  # same PID, UID, group and start time as recorded at launch
        os.killpg(p.pid, 15); rec['signalled_pgid'] = p.pid
    rc = p.wait(timeout=30)
rec.update(exit=rc, wall_s=round(time.time() - t0, 1))
json.dump(rec, open(R + '/controls-review-launch.json', 'w'), indent=1)
print(json.dumps(rec))
