#!/bin/bash
# Item 5 wrapper: take the four GPU correctness locks in ascending order, then the bench lock
# last; wait until no foreign compute process is on any GPU; run the driver pinned to
# CPUs 104-111 + 64-71; release everything on exit. Usage: multigpu_step.sh [driver args]
set -u
W=/mnt/clathrin/alex-motioncorr-rc0/W-QUAL
exec 9>/tmp/motioncorr-gpu0-correctness.lock;  flock 9
exec 8>/tmp/motioncorr-gpu1-correctness.lock;  flock 8
exec 7>/tmp/motioncorr-gpu2-correctness.lock;  flock 7
exec 6>/tmp/motioncorr-gpu3-correctness.lock;  flock 6
exec 5>/tmp/motioncorr-bench.lock;             flock 5
echo "locks held $(date -u +%FT%TZ)"
while [ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do echo "foreign GPU process present, waiting"; nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name --format=csv,noheader; sleep 10; done
export PATH=/home/alex/.mc-venv/bin:/usr/local/cuda-12.8/bin:$PATH
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
taskset -c 64-71,104-111 /home/alex/.mc-venv/bin/python3 $W/tools/multigpu_publication.py "$@"
rc=$?
echo "driver rc=$rc locks released $(date -u +%FT%TZ)"
exit $rc
