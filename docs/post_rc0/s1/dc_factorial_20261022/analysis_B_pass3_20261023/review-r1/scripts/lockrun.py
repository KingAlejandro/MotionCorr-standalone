import fcntl, os, sys, runpy
fd = os.open('/tmp/motioncorr-dc-B-pass3-analysis-review-r1-20261023-sonnet/.numeric.lock', os.O_CREAT|os.O_RDWR, 0o644)
try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
except OSError: sys.exit('lock busy')
script = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
