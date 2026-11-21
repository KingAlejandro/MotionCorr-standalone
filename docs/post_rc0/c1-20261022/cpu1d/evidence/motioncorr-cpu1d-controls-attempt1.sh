#!/bin/bash
set -euo pipefail
set -C
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
P=$SC/cpu1d-startup-freeze1
E=$SC/cpu1d-startup-operation1
mkdir "$E"
exec > "$E/operation.out" 2>&1
date -u +%FT%TZ
hostname
id
uptime
df -B1 /mnt/clathrin
cat /proc/self/stat > "$E/runner.proc-stat"
cat /proc/self/status > "$E/runner.proc-status"
cat /proc/self/cmdline > "$E/runner.argv.nul"
ps -eo pid,ppid,uid,sid,psr,etime,comm,args | awk 'NR==1 || /motioncorr|cpu1c|cpu1d/'
lslocks -o PID,COMMAND,TYPE,MODE,PATH | awk 'NR==1 || /motioncorr/'
for pid in 3308367 3308375; do [ ! -e "/proc/$pid" ] || { echo "old PID unexpectedly exists: $pid"; exit 6; }; done
for path in t24-cpu1d census census-ref-cpu v2/cpu-unset v2/cpuF-unset logs/launch-cpu1d-attempt1 logs/chain-cpu1d.go; do [ ! -e "$SC/$path" ] || { echo "unexpected existing path: $path"; exit 6; }; done
# No native command is used. All control processes inherit CPUs 8-9.
exec 9>>/tmp/motioncorr-c1-cpu8-9.lock
flock -n 9 || { echo contention; exit 7; }
date -u +%FT%TZ > "$E/lease.acquired"
trap 'rc=$?; echo "$rc" > "$E/operation.exit"; date -u +%FT%TZ > "$E/operation.finished"' EXIT
(cd "$P" && sha256sum -c packet.sha256) > "$E/packet.verify"
[ -z "$(find "$P" -name '._*' -print -quit)" ]
mkdir "$SC/tools-cpu1d-run"
cp "$P"/tools/* "$SC/tools-cpu1d-run/"
for name in chain-cpu1d.sh cpu1d-launch-wrapper.sh cpu1d-tools-expected.sha256; do cat "$P/$name" > "$SC/$name"; done
(cd "$SC/tools-cpu1d-run" && sha256sum -c "$SC/cpu1d-tools-expected.sha256") > "$E/deployed.verify"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/home/alex/.mc-venv/bin/python3 -B "$P/test_startup.py" "$P" "$P/old" "$SC/cpu1d-startup-controls-attempt1" > "$E/controls.out" 2>&1
# Direct read-only prerequisite DRYRUN: no stage, no reservation, no chain GO.
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f
set +e
taskset -c 8-9 /home/alex/.mc-venv/bin/python3 -B "$SC/tools-cpu1d-run/cpu1d_prereq.py" "$SC/chain-cpu1d.sh" "$SC/cpu1c-identities.json" "$SC/cpu1d-tools-expected.sha256" "$SC/cpu1c-pins" "$E/cpu1d-prereq-dryrun.json" > "$E/cpu1d-prereq-dryrun.out" 2>&1
rc=$?
set -e
echo "$rc" > "$E/cpu1d-prereq-dryrun.exit"
[ "$rc" = 0 ]
[ -z "$(find "$SC/logs" -maxdepth 1 -name 'cpu1d-*' -print -quit)" ]
[ ! -e "$SC/logs/launch-cpu1d-attempt1" ]
[ ! -e "$SC/logs/chain-cpu1d.go" ]
for path in t24-cpu1d census census-ref-cpu v2/cpu-unset v2/cpuF-unset; do [ ! -e "$SC/$path" ]; done
# Fresh metadata after controls: no native qualification or GPU launch.
lslocks -o PID,COMMAND,TYPE,MODE,PATH > "$E/locks.final"
du -sb "$P" "$SC/tools-cpu1d-run" "$SC/cpu1d-startup-controls-attempt1" "$E"
date -u +%FT%TZ
