#!/bin/bash
# Missing bounded C1 rows only. No CPU campaign, no broad CUDA census, no benchmarks.
set -euo pipefail
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f C1_T24_DIR=t24-i6-20261025 PYTHONDONTWRITEBYTECODE=1
V=$SC/tools-v2.4-run; PY=/home/alex/.mc-venv/bin/python3
source "$V/c1_env.sh"
cd "$SC"
exec 8>>/tmp/motioncorr-c1-cpu8-9.lock; flock -n 8 || exit 5
OP=$SC/remaining-i6-20261025; mkdir "$OP"
trap 'rc=$?; echo "$rc" > "$OP/chain.exit"; date -u +%FT%TZ > "$OP/finished"' EXIT
$PY - "$SC" <<'PY'
import pathlib,os,json,subprocess,time,hashlib,sys
p=pathlib.Path(sys.argv[1]);assert os.sched_getaffinity(0)=={8,9}
for n in ['matrix-cuda','matrix-nvcomp','matrix-cuda.json','matrix-nvcomp.json','a249-i6-20261025','t24-i6-20261025','v2/cuda-unset']:
 assert not (p/n).exists(),n
def sample():
 d={}
 for l in pathlib.Path('/proc/stat').read_text().splitlines():
  if l.startswith(('cpu8 ','cpu9 ')):
   a=l.split();v=list(map(int,a[1:]))[:8];d[a[0]]=(sum(v),v[3]+v[4])
 return d
a=sample();time.sleep(3);b=sample();busy={k:1-(b[k][1]-v[1])/(b[k][0]-v[0]) for k,v in a.items()};assert max(busy.values())<.5
m=dict((l.split(':')[0],l.split(':')[1].strip()) for l in pathlib.Path('/proc/meminfo').read_text().splitlines());assert int(m['MemAvailable'].split()[0])>64*1024*1024
st=os.statvfs(p);assert st.f_bavail*st.f_frsize>16<<30
q=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],capture_output=True,text=True,check=True);assert 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d' not in q.stdout
(p/'remaining-i6-20261025/ADMISSION.json').write_text(json.dumps({'cpus':sorted(os.sched_getaffinity(0)),'busy':busy,'memory_available':m['MemAvailable'],'scratch_free_bytes':st.f_bavail*st.f_frsize,'gpu_apps':q.stdout,'timing_claim':False},indent=2)+'\n')
PY
(cd "$V"; sha256sum -c ../tools-v2.4-run.sha256) > "$OP/tools-check.log"
sha256sum -c build-cuda.binaries.sha256 build-nvcomp.binaries.sha256 > "$OP/binaries-check.log"
sha256sum "$0" > "$OP/chain.sha256"
go() { local n=$1; shift; set +e; bash "$V/c1_stage.sh" "$n" "$@"; local rc=$?; set -e
 if [ "$rc" -ne 0 ]; then echo "$n exited $rc; remaining stages UNRUN" > "$OP/STOP"; exit "$rc"; fi; }
go i6-20261025-r9-cuda bash "$V/c1_item.sh" 9cuda
go i6-20261025-r9-nvcomp bash "$V/c1_item.sh" 9nvcomp
for b in cuda nvcomp; do for c in bz2 xz zst; do
 go i6-20261025-a249-$b-$c bash "$V/c1_gpu_run.sh" i6-a249-$b-$c taskset -c 8-9 "$PY" "$SC/src/tests/test_compressed_mrc_status.py" --binary "$SC/build-$b/motioncorr" --codec "$c" --gpu 0 --work "$SC/a249-i6-20261025/$b-$c"
done; done
mkdir "$SC/$C1_T24_DIR"
for c in G L; do
 ln -s "$SC/t24-i3/c1-$c" "$SC/$C1_T24_DIR/c1-$c"
 go i6-20261025-dataset-$c bash "$V/c1_gpu_run.sh" i6-ds-$c "$PY" "$V/c1_tutorial24.py" dataset c1 "$SC/build-nvcomp/motioncorr" "$c"
done
go i6-20261025-k267-cuda bash "$V/c1_v2.sh" cuda
printf 'completed named stages; no aggregate C1 or truth PASS inferred\n' > "$OP/DONE"
