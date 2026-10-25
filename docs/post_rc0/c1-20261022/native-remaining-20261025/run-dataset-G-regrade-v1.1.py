import datetime,hashlib,json,pathlib,subprocess,shlex
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
src=pathlib.Path('/tmp/motioncorr-20261025-c1-dataset-grade/c1_ds_archive_regrade.py')
sha=hashlib.sha256(src.read_bytes()).hexdigest()
assert sha=='291475e9cac66f3c5b4c41658d3a2448fdf085d152ae88dab9aa4566eb171dd2'
sc='/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb'
ns=sc+'/dataset-G-archive-regrade-v1.1-20261025'
remote='''set -euo pipefail
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
NS="$SC/dataset-G-archive-regrade-v1.1-20261025"
export C1_SCR="$SC" C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f C1_T24_DIR=t24-i6-20261025 C1_TOOLS="$SC/tools-v2.4-run" PYTHONDONTWRITEBYTECODE=1
source "$C1_TOOLS/c1_env.sh"
exec 8>>/tmp/motioncorr-c1-cpu8-9.lock
flock -n 8
test ! -e "$NS"
mkdir "$NS"
cat > "$NS/c1_ds_archive_regrade.py"
echo '291475e9cac66f3c5b4c41658d3a2448fdf085d152ae88dab9aa4566eb171dd2  '"$NS/c1_ds_archive_regrade.py" | sha256sum -c -
taskset -c 8-9 "$C1_PY" -I -B -c 'import os,pathlib,time,resource; assert os.sched_getaffinity(0)=={8,9}; m=pathlib.Path("/proc/meminfo").read_text(); assert int(m.split("MemAvailable:")[1].split()[0])>8388608; v=os.statvfs("/mnt/clathrin"); assert v.f_bavail*v.f_frsize>1073741824; print("ADMISSION CPU8-9 RAM>8GiB SCRATCH>1GiB, read-only, no native/GPU")'
(cd "$C1_TOOLS"; sha256sum -c ../tools-v2.4-run.sha256) > "$NS/tools-check.log"
set +e
taskset -c 8-9 /usr/bin/timeout --signal=TERM --kill-after=5s 120s "$C1_PY" -I -B "$NS/c1_ds_archive_regrade.py" "$SC/t24-i6-20261025/c1-ds-G" --out-dir "$NS/grade" > "$NS/stdout" 2> "$NS/stderr"
rc=$?
set -e
echo "$rc" > "$NS/exit"
cat "$NS/stdout" "$NS/stderr"
if [ -f "$NS/grade/REGRADE.json" ]; then cat "$NS/grade/REGRADE.json"; fi
exit "$rc"
'''
argv=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','4GPUs','bash -c '+shlex.quote(remote)]
r=subprocess.run(argv,input=src.read_bytes(),capture_output=True,timeout=180)
rec={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'read-only versioned G grade; original FAIL and v1 import failure retained','namespace':ns,'helper_sha256':sha,'new_native_jobs':0,'exit':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode(),'argv':argv}
(P/'c1-dataset-G-regrade-v1.1-execution.json').write_text(json.dumps(rec,indent=2)+'\n')
print(json.dumps({k:v for k,v in rec.items() if k not in ('argv','stdout','stderr')},indent=2)); print(r.stdout.decode()[:1800]);print(r.stderr.decode()[:1800])
