#!/bin/bash
# Attempt 2: attempt 1 failed only because ctest was not on PATH (rc 127); its logs are kept. Runs under lane.py.
set -u
NS=/tmp/motioncorr-lfw-v5-20261026; R=$NS/receipts
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
ulimit -v 12582912
occ(){ echo "=== OCCUPANCY $1 $(date -u +%FT%TZ)"; uptime; free -m | head -2; df -h /tmp | tail -1; du -sh $NS | tail -1; taskset -pc $$; ps -eo pid,psr,pcpu,user,args --sort=-pcpu | head -8 | cut -c1-150
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
 [ $? -eq 0 ] || { echo "STOP: foreign compute"; exit 3; }; }
occ before-ctest2 | tee $R/occupancy-before-ctest2.txt || exit 3
cd $NS/build && env -u MC_EXPERIMENT_CCF_DC_ARM /usr/bin/time -v -o $R/ctest2.time /home/ubuntu/.mc-venv/bin/ctest -R '^(LocalFullWidthWeight|IsotropicWeight|GlobalHalfGain|CoupledPeak|PatchRetryState|ExperimentalFlagsCli|LocalCcfCaptureCli|CcfDcHook)$' -V > $R/ctest2.log 2>&1; echo ctest2_rc=$? | tee $R/ctest2.rc
occ after-ctest2 | tee $R/occupancy-after-ctest2.txt
