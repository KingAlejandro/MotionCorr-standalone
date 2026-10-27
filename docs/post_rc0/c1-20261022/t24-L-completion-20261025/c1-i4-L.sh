#!/bin/bash
# Prepared 25 Oct; execute once only after parent harvest, independent reuse review and fresh admission.
# Exact tested source/unchanged tools. Fresh F control + two missing arms; four explicitly reused i3 arms.
set -euo pipefail
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f C1_T24_DIR=t24-i4-20261025 PYTHONDONTWRITEBYTECODE=1
V=$SC/tools-v2.3-run; PY=/home/alex/.mc-venv/bin/python3; T=$SC/$C1_T24_DIR; F=/mnt/clathrin/alex-motioncorr-rc0/W-QF
source "$V/c1_env.sh"
cd "$SC"
exec 8>>/tmp/motioncorr-c1-cpu8-9.lock
flock -n 8 || { echo 'CPU8-9 lease contended: no launch'; exit 5; }
$PY -c 'import os; assert os.sched_getaffinity(0)=={8,9}, os.sched_getaffinity(0)'
# Fresh namespace is the invocation reservation. No retry or overwrite.
mkdir "$T"
trap 'rc=$?; date -u +%FT%TZ > "$T/finished"; echo "$rc" > "$T/chain.exit"' EXIT
date -u +%FT%TZ > "$T/started"
sha256sum "$0" > "$T/chain.sha256"
(cd "$V"; sha256sum -c ../tools-v2.3-run.sha256) > "$T/tools-check.log"
sha256sum -c build-nvcomp.binaries.sha256 > "$T/c1-binary-check.log"
# The parent freezes/rechecks imported product hashes in addition to this manifest, before/after.
$PY - "$T" <<'PY'
import hashlib,json,pathlib,sys,time
p=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb');t=pathlib.Path(sys.argv[1]);out={}
pinfile=p/'c1-i4-20261025-pins.json'
assert hashlib.sha256(pinfile.read_bytes()).hexdigest()=='60563c87ed04a660f5c85adc32f913b19b5bcf42002f6c9c69a30698fbd23fd1'
pins=json.loads(pinfile.read_text());sha=lambda f:hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()
for a,pin in pins['attr'].items():
 d=p/'attr'/a;assert (d/'SOURCE').read_text().strip()==pin['source']
 assert sha(d/'source-files.sha256')==pin['source_manifest_sha256']
 assert sha(d/'build.binaries.sha256')==pin['build_receipt_sha256']
 assert sha(d/'build/motioncorr')==pin['binary_sha256']
 assert sha(p/'t24-i3'/f'{a}-G'/'RUN.json')==pin['g_run_sha256']
 for name,h in pin['checked_source_files']:assert sha(d/'src'/name)==h,(a,name)
for name,h in pins['baseline'].items():assert sha(name)==h,name
(t/'PINS.json').write_bytes(pinfile.read_bytes())
for a in ('F-fresh','c1','N','only254'):
 d=p/'t24-i3'/f'{a}-L';r=json.loads((d/'RUN.json').read_text());assert r['rc']==0
 assert r['cpu_mask']=='8-9'
 assert r['health_pre']['rc']==0 and r['health_post']['rc']==0
 assert r['gpu_witness']['on_lane_gpu_only'] is True
 assert not r['cleanup']['members_before'] and not r['cleanup']['remaining']
 assert hashlib.sha256(pathlib.Path(r['binary']).read_bytes()).hexdigest()==r['binary_sha256']
 assert hashlib.sha256(pathlib.Path('/home/alex/motioncorr-validation-20261011-vm/tutorial-data/movies.star').read_bytes()).hexdigest()==r['input_star_sha256']
 w=d/'ingest-witness.txt';assert sha(w)=='6e6fe100f370219f602a9c922094adb427423426f689f61ce3cc3985b03cb7d0'
 assert w.read_text().splitlines()==r['ingest_witness'] and len(r['ingest_witness'])==24
 assert all(x.endswith(' nvcomp') for x in r['ingest_witness'])
 files=sorted(list((d/'out').glob('Movies/*.mrc'))+list((d/'out').glob('Movies/*.star'))+list((d/'out').glob('corrected_micrographs.star')))
 assert len(files)==49,(a,len(files))
 hashes={str(f.relative_to(d)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 out[a]={'state':'REUSED_EXISTING_EXECUTION_NOT_RERUN','original_directory':str(d),'run_sha256':hashlib.sha256((d/'RUN.json').read_bytes()).hexdigest(),'binary_sha256':r['binary_sha256'],'products_sha256':hashes,'witness_sha256':sha(w)}
(t/'IMPORTED-EVIDENCE.json').write_text(json.dumps(out,indent=2)+'\n')
PY
for a in F-fresh c1 N only254; do ln -s "$SC/t24-i3/$a-L" "$T/$a-L"; done
go() { local n=$1 ok=$2; shift 2; set +e; bash "$V/c1_stage.sh" "$n" "$@"; local rc=$?; set -e
  case " $ok " in *" $rc "*) return 0;; esac
  echo "stage $n exited $rc (allowed $ok)" > "$T/STOP"; exit 1; }
go i4-20261025-lane-L 0 "$PY" "$V/c1_tutorial24.py" lane-hash L "$F/multigpu/L/s0" "$F/multigpu/L/cmp-w1_vs_s0-products.json" "$T/F-fresh-L/out" F-fresh_vs_F-retained-L
# Fresh cross-date control is strict IDENTICAL, outside unchanged attribute()'s label set.
go i4-20261025-run-F-current-L 0 "$PY" "$V/c1_tutorial24.py" run F-current "$F/build-nvcomp/motioncorr" L
go i4-20261025-cmp-F-current-L 0 "$PY" "$V/c1_tutorial24.py" compare "$T/F-fresh-L/out" "$T/F-current-L/out" F-fresh_vs_F-current-L
"$PY" - "$T" <<'PY'
import json,pathlib,sys,hashlib
p=pathlib.Path(sys.argv[1]);r=json.loads((p/'F-current-L/RUN.json').read_text())
assert r['rc']==0 and r['health_pre']['rc']==0 and r['health_post']['rc']==0
assert r['gpu_witness']['on_lane_gpu_only'] is True and not r['cleanup']['members_before'] and not r['cleanup']['remaining']
w=p/'F-current-L/ingest-witness.txt';assert hashlib.sha256(w.read_bytes()).hexdigest()=='6e6fe100f370219f602a9c922094adb427423426f689f61ce3cc3985b03cb7d0'
assert len(r['ingest_witness'])==24 and r['ingest_witness']==w.read_text().splitlines()
assert r['binary_sha256']==json.loads((p/'F-fresh-L/RUN.json').read_text())['binary_sha256']
PY
for a in only260 only270; do
 go i4-20261025-run-$a-L 0 "$PY" "$V/c1_tutorial24.py" run "$a" "$SC/attr/$a/build/motioncorr" L
 "$PY" - "$T" "$a" <<'PY'
import json,pathlib,sys,hashlib
p=pathlib.Path(sys.argv[1]);a=sys.argv[2];d=p/f'{a}-L'
r=json.loads((d/'RUN.json').read_text());pins=json.loads((p/'PINS.json').read_text())
assert r['rc']==0 and r['binary_sha256']==pins['attr'][a]['binary_sha256']
assert r['health_pre']['rc']==0 and r['health_post']['rc']==0 and r['gpu_witness']['on_lane_gpu_only'] is True
assert not r['cleanup']['members_before'] and not r['cleanup']['remaining']
w=d/'ingest-witness.txt';assert hashlib.sha256(w.read_bytes()).hexdigest()=='6e6fe100f370219f602a9c922094adb427423426f689f61ce3cc3985b03cb7d0'
assert len(r['ingest_witness'])==24 and r['ingest_witness']==w.read_text().splitlines()
PY
done
for a in c1 N only254 only260 only270; do
 go i4-20261025-cmp-F-$a-L '0 1' "$PY" "$V/c1_tutorial24.py" compare "$T/F-fresh-L/out" "$T/$a-L/out" F-fresh_vs_$a-L
done
go i4-20261025-cmp-N-c1-L 0 "$PY" "$V/c1_tutorial24.py" compare "$T/N-L/out" "$T/c1-L/out" N_vs_c1-L
for a in only254 only260 only270; do
 go i4-20261025-cmp-$a-c1-L '0 1' "$PY" "$V/c1_tutorial24.py" compare "$T/$a-L/out" "$T/c1-L/out" ${a}_vs_c1-L
done
go i4-20261025-attribute-L 0 "$PY" "$V/c1_tutorial24.py" attribute L
$PY - "$T" <<'PY'
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);before=json.loads((p/'IMPORTED-EVIDENCE.json').read_text())
pins=json.loads((p/'PINS.json').read_text())
for a in ('only260','only270'):
 d=p/f'{a}-L';r=json.loads((d/'RUN.json').read_text());assert r['rc']==0
 assert r['binary_sha256']==pins['attr'][a]['binary_sha256']
 assert r['health_pre']['rc']==0 and r['health_post']['rc']==0 and r['gpu_witness']['on_lane_gpu_only'] is True
 assert not r['cleanup']['members_before'] and not r['cleanup']['remaining']
 w=d/'ingest-witness.txt';assert hashlib.sha256(w.read_bytes()).hexdigest()=='6e6fe100f370219f602a9c922094adb427423426f689f61ce3cc3985b03cb7d0'
 assert len(r['ingest_witness'])==24 and r['ingest_witness']==w.read_text().splitlines()
for a,r in before.items():
 d=pathlib.Path(r['original_directory']);assert hashlib.sha256((d/'RUN.json').read_bytes()).hexdigest()==r['run_sha256']
 for n,h in r['products_sha256'].items():assert hashlib.sha256((d/n).read_bytes()).hexdigest()==h,(a,n)
 assert hashlib.sha256((d/'ingest-witness.txt').read_bytes()).hexdigest()==r['witness_sha256']
for name,h in pins['baseline'].items():assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==h,name
(p/'IMPORTED-EVIDENCE-UNCHANGED').write_text('PASS: original receipts/products unchanged\n')
PY
echo 'bounded L attribution completed; no aggregate C1/science/performance PASS' > "$T/DONE"
