#!/usr/bin/env python3
"""Derive lane-adapted copies of two committed drivers with asserted replacements (the originals are not edited; diffs are kept).

c1_census_runner.py  from tools/run_realistic_motion_census.py: --j 8/OMP_NUM_THREADS=8 -> 2 (2-CPU lane) and GPU selection forced to GPU3 only
                     (the stock helper walks GPUs 2,3,1,0) with the lease released only by the caller after its final health check.
c1_run_v2_cases.py   from docs/post_rc0/s1/synth_combined/run_v2_cases.py: --j 8/OMP_NUM_THREADS=8 -> 2.
Command lines are otherwise identical, so results compare with the retained runs; thread counts do not enter the algorithms.
"""
import difflib, re
from pathlib import Path
here = Path(__file__).resolve().parent; repo = here.parents[3]

def derive(src, dst, edits):
    orig = (repo / src).read_text(); s = orig
    for a, b, *rx in edits:
        if rx:
            s, n = re.subn(a, b, s, flags=re.S); assert n == 1, (a, n)
        else:
            assert s.count(a) == 1, (a, s.count(a)); s = s.replace(a, b)
    (here / dst).write_text(s)
    (here / (dst[:-3] + '.diff')).write_text(''.join(difflib.unified_diff(orig.splitlines(True), s.splitlines(True), src, dst)))

derive('tools/run_realistic_motion_census.py', 'c1_census_runner.py', [
    ("env['OMP_NUM_THREADS']='8'", "env['OMP_NUM_THREADS']='2'   # C1: 2-CPU lane"),
    ("'--use_own','--j','8',", "'--use_own','--j','2',"),
    (r"def lock_gpu\(\):.*?\n\n\ndef run_seed", '''def lock_gpu():
    # C1: GPU3 only, nonblocking canonical lease; the caller verifies lane health afterwards.
    uuid=os.environ['C1_GPU_UUID']
    if uuid in subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines(): return None
    if os.environ.get('C1_LEASE_HELD')=='1': return open(os.devnull),3,uuid   # c1_gpu_run.sh holds the lease across the whole campaign
    f=open(os.environ['C1_GPU_LOCK'],'a')
    try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: f.close(); return None
    return f,3,uuid


def run_seed''', 1)])
derive('docs/post_rc0/s1/synth_combined/run_v2_cases.py', 'c1_run_v2_cases.py', [
    ("'--use_own','--j','8',", "'--use_own','--j','2',"),
    ("env['OMP_NUM_THREADS']='8'", "env['OMP_NUM_THREADS']='2'   # C1: 2-CPU lane")])
print('ok')
