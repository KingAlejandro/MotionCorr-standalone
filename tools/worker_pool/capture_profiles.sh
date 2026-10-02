#!/bin/bash
# One nsys capture per arm, with CUDA allocation events, then export to SQLite.
# Profiled runs are attribution, never a timing claim.
set -u
W=/home/alex/mc-worker-20261002
D=$W/data
R=$W/prof
UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
export PATH=/usr/local/cuda-12.8/bin:$PATH
OPTS="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --max_io_threads 8 --ingest nvcomp"
mkdir -p $R
for ARM in A0 A1 B C D E; do
  # refuse to profile with a co-tenant on ANY device: a UUID check cannot see
  # another process on the same card, so compare the compute-app PID list.
  OTHER=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l)
  if [ "$OTHER" != "0" ]; then echo "ARM=$ARM SKIPPED: $OTHER compute app(s) present"; continue; fi
  OUT=$R/out-$ARM; rm -rf $OUT; mkdir -p $OUT
  ( cd $D && env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=8 taskset -c 0-7 \
      nsys profile -t cuda --cuda-memory-usage=true --sample=none --cpuctxsw=none \
        -f true -o $R/$ARM \
        $W/parms/b-$ARM/motioncorr --i movies.star --o $OUT/ $OPTS ) > $R/$ARM-run.log 2>&1
  rc=$?
  H=$(for f in $(ls $OUT/Movies/*.mrc 2>/dev/null|sort); do tail -c +1025 "$f"; done | sha256sum | cut -c1-16)
  N=$(ls $OUT/Movies/*.mrc 2>/dev/null|wc -l)
  P=$(grep -o 'CUDA worker pool: retained.*' $R/$ARM-run.log | tail -1)
  echo "ARM=$ARM rc=$rc n_mrc=$N mrc=$H"
  echo "   pool: ${P:-<none>}"
  rm -rf $OUT
  nsys export --type sqlite --force-export true -o $R/$ARM.sqlite $R/$ARM.nsys-rep > $R/$ARM-export.log 2>&1
  echo "   export_rc=$? size=$(du -h $R/$ARM.sqlite 2>/dev/null | cut -f1)"
done
echo CAPTURE_DONE
