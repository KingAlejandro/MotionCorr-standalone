#!/bin/bash
# One missing L dataset and one eight-case CUDA characterization; no reruns/census.
set -euo pipefail
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
V=$SC/tools-v2.4-run
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f C1_T24_DIR=t24-i6-20261025 C1_TOOLS=$V PYTHONDONTWRITEBYTECODE=1
source "$V/c1_env.sh"
exec 8>>/tmp/motioncorr-c1-cpu8-9.lock; flock -n 8
OP=$SC/remaining-i7-20261025
mkdir "$OP"
trap 'rc=$?; echo "$rc" > "$OP/chain.exit"; date -u +%FT%TZ > "$OP/finished"' EXIT
"$C1_PY" -I -B - "$SC" "$OP" <<'PY'
import os,pathlib,time,json,subprocess,sys,hashlib
s,o=map(pathlib.Path,sys.argv[1:]); assert os.sched_getaffinity(0)=={8,9}
for n in ['t24-i6-20261025/c1-ds-L','t24-i6-20261025/c1-L','v2/cuda-unset','v2/cuda-unset.eval.json']: assert not (s/n).exists(),n
def sample():
 d={}
 for l in pathlib.Path('/proc/stat').read_text().splitlines():
  if l.startswith(('cpu8 ','cpu9 ')):
   a=l.split();v=list(map(int,a[1:]))[:8];d[a[0]]=(sum(v),v[3]+v[4])
 return d
a=sample();time.sleep(3);b=sample();busy={k:1-(b[k][1]-v[1])/(b[k][0]-v[0]) for k,v in a.items()}; assert max(busy.values())<.5
m=pathlib.Path('/proc/meminfo').read_text();mem=int(m.split('MemAvailable:')[1].split()[0]);assert mem>64*1024*1024
v=os.statvfs(s);free=v.f_bavail*v.f_frsize;assert free>16<<30
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],text=True); assert 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d' not in apps
g=json.loads((s/'dataset-G-archive-regrade-v1.1-20261025/grade/REGRADE.json').read_text()); assert g['state']=='IDENTICAL' and g['verdict']=='PASS'
assert hashlib.sha256((s/'dataset-G-archive-regrade-v1.1-20261025/c1_ds_archive_regrade.py').read_bytes()).hexdigest()=='291475e9cac66f3c5b4c41658d3a2448fdf085d152ae88dab9aa4566eb171dd2'
r=json.loads((s/'t24-i3/c1-L/RUN.json').read_text()); assert r['rc']==0 and r['health_pre']['rc']==0 and r['health_post']['rc']==0 and r['gpu_witness']['on_lane_gpu_only']
assert r['binary_sha256']==hashlib.sha256((s/'build-nvcomp/motioncorr').read_bytes()).hexdigest()
wit=(s/'t24-i3/c1-L/ingest-witness.txt').read_bytes();assert hashlib.sha256(wit).hexdigest()=='6e6fe100f370219f602a9c922094adb427423426f689f61ce3cc3985b03cb7d0'
assert r['ingest_witness']==wit.decode().splitlines() and len(r['ingest_witness'])==24
(o/'ADMISSION.json').write_text(json.dumps({'cpus':[8,9],'busy':busy,'mem_available_kib':mem,'scratch_free_bytes':free,'gpu_apps':apps,'claims':'correctness characterization only, no performance','plan':'L native once; old strict archive INVALID retained; independently verified v1.1 archive/product grade must PASS; only then K267 CUDA once'},indent=2)+'\n')
PY
(cd "$V"; sha256sum -c ../tools-v2.4-run.sha256) > "$OP/tools-check.log"
(cd "$SC"; sha256sum -c build-nvcomp.binaries.sha256) > "$OP/binaries-check.log"
ln -s "$SC/t24-i3/c1-L" "$SC/$C1_T24_DIR/c1-L"
set +e
bash "$V/c1_stage.sh" i7-20261025-dataset-L bash "$V/c1_gpu_run.sh" i7-ds-L "$C1_PY" "$V/c1_tutorial24.py" dataset c1 "$SC/build-nvcomp/motioncorr" L
raw=$?
set -e
echo "$raw" > "$OP/dataset-L-original-stage.exit"
# The helper refuses any failure besides the exact archive inventory issue, and
# binds worker exit digests before the unchanged strict canonical comparison.
"$C1_PY" -I -B "$SC/dataset-G-archive-regrade-v1.1-20261025/c1_ds_archive_regrade.py" "$SC/$C1_T24_DIR/c1-ds-L" --out-dir "$OP/L-grade" > "$OP/L-grade.stdout" 2> "$OP/L-grade.stderr"
test "$raw" -eq 1
bash "$V/c1_stage.sh" i7-20261025-k267-cuda bash "$V/c1_v2.sh" cuda
printf 'L exact archive/product grade and K267 evaluator completed; inner scientific states require grading\n' > "$OP/DONE"
