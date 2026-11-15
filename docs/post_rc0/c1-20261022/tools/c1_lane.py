"""Lane policy for the vendored QF library (docs/rc0/qf/tools/qual_lib.py), applied without editing it.

#198 policy: correctness runs stay on their own lane and do not wait for the bench lock (only timed windows use it). qual_lib.run_case waits up to
6 h for the bench lock; here the lock is only probed and the probe is recorded in the run record. GPU3 lease handling and the foreign-process
wait on the lane GPU are unchanged.
"""
import fcntl


def _probe(*args, **kwargs):
    with open('/tmp/motioncorr-bench.lock', 'a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); free = True
        except BlockingIOError:
            free = False
    return {'policy': '#198: correctness does not wait for the bench lock', 'probe_free': free, 'waited_s': 0}


def install():
    import qual_lib
    qual_lib.wait_bench_free = _probe
