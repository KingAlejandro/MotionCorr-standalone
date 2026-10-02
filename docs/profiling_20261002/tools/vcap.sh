set -u
W=/home/alex/mc-release-20261002; DATA=/home/alex/mc-unified-20260930/data
UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54; MASK=64-71; NSYS=/usr/local/cuda/bin/nsys
OPTS="--i movies.star --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 6 --max_io_threads 6 --ingest nvcomp"
P=$W/vprof; mkdir -p $P
echo "owner=single-gpu-release scope=nsys-vram-captures start=$(date -u +%FT%TZ)" > /tmp/motioncorr-bench.lock
for a in a0_main a1_base a2_gain a3_premask a4_globalpool a5_patchpool a6_final; do
  occ=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader)
  w=0; while [ -n "$occ" ] && [ $w -lt 300 ]; do sleep 10; w=$((w+10)); occ=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader); done
  [ -n "$occ" ] && { echo "SKIP $a: GPU busy"; continue; }
  rm -rf $P/$a; mkdir -p $P/$a/output
  ( cd $DATA && sudo -n env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=6 PATH=$PATH \
      taskset -c $MASK $NSYS profile --output=$P/$a/v --force-overwrite=true --stats=false \
      --trace=cuda --cuda-memory-usage=true \
      $W/bld-$a/motioncorr $OPTS --o $P/$a/output/ --ingest_witness $P/$a/ingest.witness ) > $P/$a/cap.log 2>&1
  rc=$?; sudo -n chown -R "$USER" $P/$a
  all=$(cat $P/$a/cap.log $(find $P/$a/output -name '*.log') 2>/dev/null)
  echo "$a rc=$rc global=$(grep -c '\[CUDA Global Alignment\] completed' <<<"$all") dw=$(grep -c 'Dose-Weighted Reconstruction Profile' <<<"$all") warn=$(grep -c 'WARNING:' <<<"$all") products=$(find $P/$a/output -type f|wc -l)"
  [ $rc -ne 0 ] && { tail -4 $P/$a/cap.log; continue; }
  $NSYS export --type sqlite --force-overwrite true --output $P/$a/v.sqlite $P/$a/v.nsys-rep > $P/$a/exp.log 2>&1
  echo "  export rc=$? $(du -h $P/$a/v.sqlite 2>/dev/null|cut -f1)  memevents=$(/home/alex/mc-env/bin/python3 -c "
import sqlite3,sys
c=sqlite3.connect('$P/$a/v.sqlite')
try: print(c.execute('select count(*) from CUDA_GPU_MEMORY_USAGE_EVENTS').fetchone()[0])
except Exception as e: print('ABSENT')")"
  rm -rf $P/$a/output
done
rm -f /tmp/motioncorr-bench.lock
echo "VCAP-DONE $(date -u +%FT%TZ)"
