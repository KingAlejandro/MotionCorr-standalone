#!/usr/bin/env bash
# New attempt; never overwrites the 13 October failed SCARF campaign.
set -euo pipefail
R=/home/alex/motioncorr-validation-20261011-vm
T=$R/timing-20261016
O=$T/run-4
mkdir "$O"
exec > "$O/launcher.log" 2>&1
exec 9>/tmp/motioncorr-bench.lock
flock -n 9 || { echo 'BLOCKED: advisory benchmark mutex occupied'; exit 75; }
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
export LD_LIBRARY_PATH=/home/alex/motioncorr-nvtiff-native-v2-20261006/private-sdk/unpacked/nvidia/nvtiff/lib:/usr/local/cuda-12.8/lib64:${LD_LIBRARY_PATH:-}
P=$R/nvtiff-env39/bin/python
[[ -x "$P" ]] || P=/home/alex/.mc-venv/bin/python
finish() {
 rc=$?
 trap - EXIT
 nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv > "$O/compute-after.csv" 2>&1 || true
 ps -eo pid,ppid,sid,stat,comm,args > "$O/processes-after.txt"
 date -u +%FT%TZ > "$O/end.utc"
 printf '%s\n' "$rc" > "$O/exit.txt"
 exit "$rc"
}
trap finish EXIT
date -u +%FT%TZ > "$O/start.utc"
hostname > "$O/hostname.txt"
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE > "$O/topology.txt"
numactl --show > "$O/memory-policy.txt" 2>&1
cat /proc/self/status > "$O/launcher-status.txt"
cat /sys/kernel/mm/transparent_hugepage/enabled > "$O/thp.txt"
nvidia-smi --query-gpu=uuid,name,memory.total,memory.used,utilization.gpu,driver_version --format=csv > "$O/devices.csv"
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv > "$O/compute-before.csv"
ps -eo pid,ppid,sid,stat,comm,args > "$O/processes-before.txt"
"$P" - "$O" <<'PY'
import pathlib,os,subprocess,time,json
out=pathlib.Path(__import__('sys').argv[1]);checks=[]
# Fail closed: neither a deleted-inode flock nor unrelated GPU/build work is safe.
for p in pathlib.Path('/proc').glob('[0-9]*'):
 try:
  for fd in (p/'fd').iterdir():
   try:target=os.readlink(fd)
   except OSError:continue
   if 'motioncorr-bench.lock' in target and '(deleted)' in target:raise RuntimeError('deleted-inode benchmark lock holder '+str(p))
 except (PermissionError,FileNotFoundError,ProcessLookupError):pass
for attempt in range(61):
 apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid','--format=csv,noheader'],text=True).strip()
 compilers=[]
 for name in ('cc1plus','nvcc','cicc','ptxas'):
  r=subprocess.run(['pgrep','-x',name],capture_output=True,text=True)
  if r.returncode==0:compilers.append([name,r.stdout.strip()])
 load=os.getloadavg()[0];checks.append({'monotonic_s':time.monotonic(),'apps':apps,'compilers':compilers,'load1':load})
 (out/'settle.json').write_text(json.dumps(checks,indent=2)+'\n')
 if not apps and not compilers and load<2.:break
 if attempt==60:raise RuntimeError('No box-wide GPU/build/load quiet window after 300s; unrelated work left alone')
 time.sleep(5)
if sorted(os.sched_getaffinity(0))!=list(range(96,104)):raise RuntimeError('top-level eight-CPU cap absent')
PY
export NVTIFF_SHARED_ROOT=$R/nvtiff-shared OWNED_CPU_ROOT=$T
cd "$T"
"$P" -m unittest -v test_paired test_capture_accounted > "$O/controls-normal.log" 2>&1
"$P" -O -m unittest -v test_paired test_capture_accounted > "$O/controls-optimized.log" 2>&1
"$P" test_owned_task_lifecycle.py --owned "$T/owned_cpu.py" --out "$O/lifecycle-normal.json" > "$O/lifecycle-normal.log" 2>&1
"$P" -O test_owned_task_lifecycle.py --owned "$T/owned_cpu.py" --out "$O/lifecycle-optimized.json" > "$O/lifecycle-optimized.log" 2>&1
"$P" verify_capture_accounted_linux.py --shared "$R/nvtiff-shared" --owned-root "$T" --kit "$R/kit-eacf5013" --cpus 96,97,98,99,100,101,102,103 --out "$O/actual-counters" > "$O/actual-counters.log" 2>&1
"$P" paired.py --shared "$R/nvtiff-shared" --owned-cpu "$T/owned_cpu.py" --kit "$R/kit-eacf5013" --kit-manifest "$R/nvtiff-kit-manifest.json" --binary "$R/nvtiff-build-v1/ingest_bench" --build-manifest "$R/nvtiff-build-v1/build-manifest.json" --input-manifest "$R/nvtiff-shared/inputs.json" --corpus-root "$R/corpus/data-https" --native-summary "$R/nvtiff-acceptance-v1/summary.json" --native-identities "$R/nvtiff-acceptance-v1/identities.json" --release "$T/timing-release.json" --venue vm --cpus 96,97,98,99,100,101,102,103 --uuid "$CUDA_VISIBLE_DEVICES" --out "$O/pairs"
