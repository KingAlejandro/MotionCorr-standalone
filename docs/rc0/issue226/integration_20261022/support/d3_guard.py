#!/home/alex/.mc-venv/bin/python3
import fcntl,sys
from health import snapshot, settle
phase,prefix=sys.argv[1:]
def bench():
    with open('/tmp/motioncorr-bench.lock','w') as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
if phase=='post': settle(prefix.replace('/','_'))
else:
    bench(); snapshot(prefix.replace('/','_')+'-pre',idle=True); bench()
