#!/bin/bash
# Runs under lane.py (all overlapping CPU32-47 leases + canonical bench lock held, taskset 32-47). Owned namespace only. No GPU, no movie.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; R=$NS/receipts; H=d1c498b87123b324c027c2d8957736b9954e6326
CM=/home/ubuntu/.mc-venv/bin/cmake; PYV=/home/ubuntu/.mc-venv/bin/python3
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
ulimit -v 12582912
occ(){ echo "=== OCCUPANCY $1 $(date -u +%FT%TZ)"; uptime; free -m | head -2; df -h /tmp | tail -1; du -sh $NS 2>/dev/null | tail -1; taskset -pc $$; ps -eo pid,psr,pcpu,user,args --sort=-pcpu | head -8 | cut -c1-150
 python3 - <<'PY'
import time
def snap():
    d={}
    for l in open('/proc/stat'):
        if l.startswith('cpu') and l[3].isdigit():
            f=l.split(); n=int(f[0][3:])
            if 32<=n<=47: v=list(map(int,f[1:])); d[n]=(sum(v),v[3]+v[4])
    return d
a=snap();time.sleep(2);b=snap()
busy=sum((b[n][0]-a[n][0]-(b[n][1]-a[n][1]))/max(1,b[n][0]-a[n][0]) for n in a)
print('cpu32-47 busy cores over 2s: %.2f'%busy)
raise SystemExit(3 if busy>1.5 else 0)
PY
 rc=$?; [ $rc -eq 0 ] || { echo "STOP: foreign compute on CPUs 32-47 (busy>1.5 cores)"; exit 3; }; }
occ before-configure | tee $R/occupancy-before-configure.txt || exit 3
echo "=== CONFIGURE"; /usr/bin/time -v -o $R/configure.time $CM -S $NS/source -B $NS/build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DMC_EXPERIMENT_CCF_DC=ON -DPython3_EXECUTABLE=$PYV > $R/configure.log 2>&1; echo configure_rc=$? | tee $R/configure.rc; [ "$(cat $R/configure.rc)" = configure_rc=0 ] || exit 4
occ before-build | tee $R/occupancy-before-build.txt || exit 3
echo "=== BUILD"; /usr/bin/time -v -o $R/build.time $CM --build $NS/build -j2 --target motioncorr local_full_width_weight isotropic_weight global_half_gain coupled_peak patch_retry_state ccf_dc_hook > $R/build.log 2>&1; echo build_rc=$? | tee $R/build.rc; [ "$(cat $R/build.rc)" = build_rc=0 ] || exit 5
occ before-ctest | tee $R/occupancy-before-ctest.txt || exit 3
echo "=== CTEST"; cd $NS/build && env -u MC_EXPERIMENT_CCF_DC_ARM /usr/bin/time -v -o $R/ctest.time ctest -R '^(LocalFullWidthWeight|IsotropicWeight|GlobalHalfGain|CoupledPeak|PatchRetryState|ExperimentalFlagsCli|LocalCcfCaptureCli|CcfDcHook)$' -V > $R/ctest.log 2>&1; echo ctest_rc=$? | tee $R/ctest.rc
echo "=== RECEIPT"; BIN=$NS/build/motioncorr
python3 - <<PY
import hashlib,json,subprocess,os
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
ns='$NS'; b='$BIN'
ldd=subprocess.run(['ldd',b],capture_output=True,text=True).stdout
libs={}
for l in ldd.splitlines():
    if '=>' in l and '(0x' in l:
        p=l.split('=>')[1].split('(')[0].strip()
        if p and os.path.exists(p): libs[p]={'realpath':os.path.realpath(p),'sha256':sha(os.path.realpath(p))}
cc=subprocess.run(['g++','--version'],capture_output=True,text=True).stdout.splitlines()[0]
cm=subprocess.run(['$CM','--version'],capture_output=True,text=True).stdout.splitlines()[0]
cache=open(ns+'/build/CMakeCache.txt').read()
def cv(k):
    for l in cache.splitlines():
        if l.startswith(k+':'): return l.split('=',1)[1]
rec={'source_archive':{'path':ns+'/archive/source-$H.tar','sha256':sha(ns+'/archive/source-$H.tar'),'commit':'$H','tree':'033794b433e928723dbe7e4359b9e02651478fb6'},
 'binary':{'path':b,'sha256':sha(b),'bytes':os.path.getsize(b)},
 'tests':{n:{'path':ns+'/build/'+n,'sha256':sha(ns+'/build/'+n)} for n in ['local_full_width_weight','isotropic_weight','global_half_gain','coupled_peak','patch_retry_state','ccf_dc_hook']},
 'compiler':cc,'cmake':cm,'cmake_args':{'CMAKE_BUILD_TYPE':cv('CMAKE_BUILD_TYPE'),'CUDA':cv('CUDA'),'MC_EXPERIMENT_CCF_DC':cv('MC_EXPERIMENT_CCF_DC'),'Python3_EXECUTABLE':cv('Python3_EXECUTABLE'),'CMAKE_CXX_COMPILER':cv('CMAKE_CXX_COMPILER'),'CMAKE_CXX_FLAGS_RELEASE':cv('CMAKE_CXX_FLAGS_RELEASE')},
 'shared_libraries':libs,'env':{'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},'jobs':2,'cpus':'32-47','lane_sha256':sha(ns+'/lane.py')}
open(ns+'/receipts/build_receipt.json','w').write(json.dumps(rec,indent=1)+'\n')
print('receipt written; binary',rec['binary']['sha256'])
PY
occ after | tee $R/occupancy-after.txt
echo done
