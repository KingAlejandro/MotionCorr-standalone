#!/usr/bin/env bash
#SBATCH --job-name=mc-nvtiff-matched
#SBATCH --partition=gpu-devel
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --exclusive
#SBATCH --mem=64G
#SBATCH --time=00:45:00
#SBATCH --exclude=gn0001
#SBATCH --output=/work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff/logs/timing-20261016-%j.out
#SBATCH --error=/work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff/logs/timing-20261016-%j.err
set -euo pipefail
touch /work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff/logs/.probe-$SLURM_JOB_ID || exit 97
NV_ROOT=/work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff
KIT_ROOT=/work4/scd/scarf1415/motioncorr/validation-20261011-scarf/kit-eacf5013
KIT_MANIFEST=/work4/scd/scarf1415/motioncorr/validation-20261011-scarf/harness/kit-manifest.json
TIMING_ROOT=$NV_ROOT/timing-20261016
JOB_ROOT=$NV_ROOT/timing-20261016-job-$SLURM_JOB_ID
CUDA_ROOT=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
PYTHON=$NV_ROOT/oracle-venv/bin/python
mkdir "$JOB_ROOT"
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1
"$PYTHON" - "$JOB_ROOT" <<'SELECT_CPU'
import json,os,pathlib,sys
out=pathlib.Path(sys.argv[1]);allowed=sorted(os.sched_getaffinity(0));groups=[]
def expand(s):
 r=[]
 for part in s.strip().split(','):
  lo,_,hi=part.partition('-');r.extend(range(int(lo),int(hi or lo)+1))
 return r
for cpu in allowed:
 siblings=tuple(c for c in expand(pathlib.Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list').read_text()) if c in allowed)
 if len(siblings)==2 and siblings not in groups:groups.append(siblings)
if len(groups)<4:raise RuntimeError('four physical cores with both SMT threads are required')
cpus=sorted(c for g in groups[:4] for c in g)
(out/'cpus.txt').write_text(','.join(map(str,cpus)))
(out/'reserved-cpu-mask.json').write_text(json.dumps({'initial_reserved_affinity':allowed,'used_logical_cpus':cpus,'used_physical_core_siblings':groups[:4],'scope':'Allocation can reserve more; timed controller, payload and subsequently spawned helpers are bound to eight logical CPUs'},indent=2)+'\n')
SELECT_CPU
CPUS=$(cat "$JOB_ROOT/cpus.txt")
# This is the current owned batch shell; subsequent tee/NVML/oracle helpers
# inherit its eight-thread mask. No unrelated process affinity is changed.
taskset -pc "$CPUS" "$$" > "$JOB_ROOT/launcher-binding.txt"
exec > >(tee "$JOB_ROOT/job.log") 2>&1
export LD_LIBRARY_PATH=$NV_ROOT/sdk-0.8.0.82/nvidia/nvtiff/lib:$CUDA_ROOT/lib64:${LD_LIBRARY_PATH:-}
date -u +%FT%TZ > "$JOB_ROOT/started.utc"
hostname -f > "$JOB_ROOT/hostname.txt"
scontrol show job "$SLURM_JOB_ID" > "$JOB_ROOT/slurm-job.txt"
lscpu -e=CPU,NODE,SOCKET,CORE,ONLINE > "$JOB_ROOT/cpu-topology.txt"
numactl --show > "$JOB_ROOT/memory-policy.txt" 2>&1
cat /proc/self/status > "$JOB_ROOT/launcher-status.txt"
df -Pk "$NV_ROOT" > "$JOB_ROOT/scratch-filesystem.txt"
df -Pk /scratch/scarf1415/motioncorr-empiar-corpus-v1-20261002/data > "$JOB_ROOT/input-filesystem.txt"
findmnt -T "$NV_ROOT" > "$JOB_ROOT/work4-mount.txt"
findmnt -T /scratch/scarf1415/motioncorr-empiar-corpus-v1-20261002/data > "$JOB_ROOT/input-mount.txt"
export TMPDIR=${SLURM_TMPDIR:-/tmp}
df -Pk "$TMPDIR" > "$JOB_ROOT/local-scratch-filesystem.txt"
findmnt -T "$TMPDIR" > "$JOB_ROOT/local-scratch-mount.txt"
set +e
quota -v -u scarf1415 > "$JOB_ROOT/quota.txt" 2>&1
QUOTA_RC=$?
set -e
printf '%s\n' "$QUOTA_RC" > "$JOB_ROOT/quota-status.txt"
nvidia-smi --query-gpu=index,uuid,name,memory.total,driver_version --format=csv > "$JOB_ROOT/devices.csv"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader > "$JOB_ROOT/compute-apps-start.csv"
"$PYTHON" - "$NV_ROOT" "$JOB_ROOT" <<'PY'
import csv,hashlib,json,os,pathlib,sys
r,out=map(pathlib.Path,sys.argv[1:]); approval=r/'native-approval.json'
if hashlib.sha256(approval.read_bytes()).hexdigest()!='ad765f278a24cb7b58792fe00de9fd8d5a8ac4a6922759437308dbfa9e924fff':raise RuntimeError('root approval moved')
a=json.loads(approval.read_text())
if a.get('correctness_release') is not True or a.get('timing_release') is not False:raise RuntimeError('wrong release scope')
for rel,want in a['files'].items():
    p=r/'harness'/pathlib.Path(rel).name
    if hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise RuntimeError('accepted source moved: '+rel)
cpus=sorted(os.sched_getaffinity(0))
if len(cpus)!=8:raise RuntimeError('exact eight logical CPUs required: '+str(cpus))
allocated=os.environ.get('SLURM_JOB_GPUS','').split(',')
if not allocated or any(not x.isdigit() for x in allocated):raise RuntimeError('allocated physical GPU set unavailable')
devices=[{k.strip():v.strip() for k,v in d.items()} for d in csv.DictReader((out/'devices.csv').open())]
# SCARF cgroups can expose one allocated physical GPU as visible index zero;
# SLURM_JOB_GPUS remains the node index. Never guess a second device.
if len(devices)==1:device=devices[0]
else:
    matches=[d for d in devices if d['index'] in allocated]
    if len(matches)!=len(allocated):raise RuntimeError('reserved physical GPUs cannot be resolved')
    device=min(matches,key=lambda d:int(d['index']))
uuid=device['uuid']
for row in csv.reader((out/'compute-apps-start.csv').open()):
    if row:raise RuntimeError('exclusive host has GPU compute; leave unrelated processes untouched')
if os.statvfs(r).f_bavail*os.statvfs(r).f_frsize < (40<<30):raise RuntimeError('less than 40GiB filesystem scratch available')
receipt={'pid':os.getpid(),'cpus':cpus,'uuid':uuid,'slurm_reserved_gpu_indices':allocated,'visible_devices':devices,'used_gpu_count':1,'used_device':device,'device_binding':'single cgroup-visible UUID' if len(devices)==1 else 'first explicitly reserved node-index UUID','slurm_job_id':os.environ['SLURM_JOB_ID'],'approval_sha256':hashlib.sha256(approval.read_bytes()).hexdigest(),'scope':'same-allocation untimed qualification followed by separately released matched default-allocator batch1 endpoint pairs','storage_scope':'Immutable source movies on shared PanFS scratch; samples and receipts on quota-safe work4. Filesystem capacity/standard quota visibility recorded, no claim of globally dedicated storage','quota_visibility':'quota utility status and output retained; empty output is not a verified per-user quota'}
(out/'resources.json').write_text(json.dumps(receipt,indent=2)+'\n')
(out/'cpus.txt').write_text(','.join(map(str,cpus)))
(out/'uuid.txt').write_text(uuid)
PY
CPUS=$(cat "$JOB_ROOT/cpus.txt")
UUID=$(cat "$JOB_ROOT/uuid.txt")
: "${NVTIFF_TIMING_RELEASE_SHA:?exact root timing release hash required}"
"$PYTHON" - "$NV_ROOT" <<'CHECK_RELEASE'
import hashlib,json,os,pathlib,sys
r=pathlib.Path(sys.argv[1]);p=r/'timing-20261016/timing-release.json'
if hashlib.sha256(p.read_bytes()).hexdigest()!=os.environ['NVTIFF_TIMING_RELEASE_SHA']:raise RuntimeError('root timing release identity differs')
a=json.loads(p.read_text())
if a.get('timing_release') is not True:raise RuntimeError('root controller timing release absent')
for directory,key in ((r/'harness','shared_files'),(r/'timing-20261016','timing_files')):
 for name,want in a[key].items():
  if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=want:raise RuntimeError('timing released source moved: '+name)
if hashlib.sha256((r/'timing-20261016/owned_cpu.py').read_bytes()).hexdigest()!=a['owned_cpu_sha256']:raise RuntimeError('timing accounting moved')
CHECK_RELEASE
export CUDA_VISIBLE_DEVICES=$UUID
export NVTIFF_SHARED_ROOT=$NV_ROOT/harness OWNED_CPU_ROOT=$TIMING_ROOT
cd "$TIMING_ROOT"
"$PYTHON" -m unittest -v test_paired test_capture_accounted > "$JOB_ROOT/controls-normal.log" 2>&1
"$PYTHON" -O -m unittest -v test_paired test_capture_accounted > "$JOB_ROOT/controls-optimized.log" 2>&1
"$PYTHON" test_owned_task_lifecycle.py --owned "$TIMING_ROOT/owned_cpu.py" --out "$JOB_ROOT/lifecycle-normal.json" > "$JOB_ROOT/lifecycle-normal.log" 2>&1
"$PYTHON" -O test_owned_task_lifecycle.py --owned "$TIMING_ROOT/owned_cpu.py" --out "$JOB_ROOT/lifecycle-optimized.json" > "$JOB_ROOT/lifecycle-optimized.log" 2>&1
"$PYTHON" verify_capture_accounted_linux.py --shared "$NV_ROOT/harness" --owned-root "$TIMING_ROOT" --kit "$KIT_ROOT" --cpus "$CPUS" --out "$JOB_ROOT/actual-counters" > "$JOB_ROOT/actual-counters.log" 2>&1
set +e
"$PYTHON" "$NV_ROOT/harness/acceptance.py" \
  --binary "$NV_ROOT/build-v2/ingest_bench" \
  --kit "$KIT_ROOT" --kit-manifest "$KIT_MANIFEST" \
  --input-manifest "$NV_ROOT/harness/inputs.json" \
  --build-manifest "$NV_ROOT/build-v2/build-manifest.json" \
  --corpus-root /scratch/scarf1415/motioncorr-empiar-corpus-v1-20261002/data \
  --out "$JOB_ROOT/native" --cpus "$CPUS" --uuid "$UUID"
ACCEPTANCE_RC=$?
set -e
printf '%s\n' "$ACCEPTANCE_RC" > "$JOB_ROOT/acceptance-exit.txt"
TIMING_RC=1
if [[ "$ACCEPTANCE_RC" == 0 ]]; then
  set +e
  "$PYTHON" "$TIMING_ROOT/paired.py" \
    --shared "$NV_ROOT/harness" --owned-cpu "$TIMING_ROOT/owned_cpu.py" \
    --kit "$KIT_ROOT" --kit-manifest "$KIT_MANIFEST" \
    --binary "$NV_ROOT/build-v2/ingest_bench" --build-manifest "$NV_ROOT/build-v2/build-manifest.json" \
    --input-manifest "$NV_ROOT/harness/inputs.json" --corpus-root /scratch/scarf1415/motioncorr-empiar-corpus-v1-20261002/data \
    --native-summary "$JOB_ROOT/native/summary.json" --native-identities "$JOB_ROOT/native/identities.json" \
    --release "$TIMING_ROOT/timing-release.json" --venue scarf --cpus "$CPUS" --uuid "$UUID" --out "$JOB_ROOT/pairs"
  TIMING_RC=$?
  set -e
else
  printf '%s\n' 'Timing UNRUN because same-allocation native oracle/memory qualification failed' > "$JOB_ROOT/timing-unrun.txt"
fi
printf '%s\n' "$TIMING_RC" > "$JOB_ROOT/timing-exit.txt"
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader > "$JOB_ROOT/compute-apps-end.csv"
"$PYTHON" - "$NV_ROOT" "$JOB_ROOT" <<'PY'
import csv,hashlib,json,pathlib,sys
r,out=map(pathlib.Path,sys.argv[1:]);a=json.loads((r/'native-approval.json').read_text());uuid=(out/'uuid.txt').read_text()
for rel,want in a['files'].items():
    if hashlib.sha256((r/'harness'/pathlib.Path(rel).name).read_bytes()).hexdigest()!=want:raise RuntimeError('accepted source changed during native acceptance: '+rel)
for row in csv.reader((out/'compute-apps-end.csv').open()):
    if row:raise RuntimeError('exclusive host still has GPU compute process; release unproven')
(out/'release.json').write_text(json.dumps({'allocated_uuid':uuid,'compute_apps_empty_on_owned_device':True,'source_pins_unchanged':True,'unrelated_processes_untouched':True},indent=2)+'\n')
PY
date -u +%FT%TZ > "$JOB_ROOT/ended.utc"
if [[ "$ACCEPTANCE_RC" != 0 ]]; then exit "$ACCEPTANCE_RC"; fi
exit "$TIMING_RC"
