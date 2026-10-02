set -u
W=/home/alex/mc-release-20261002; DATA=/home/alex/mc-unified-20260930/data
UUID=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54; MASK=64-71
NSYS=/usr/local/cuda/bin/nsys
OPTS="--i movies.star --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 6 --max_io_threads 6 --ingest nvcomp"
P=$W/prof; mkdir -p $P; cd $P

cap() { # tag arm traceargs...
  tag="$1"; arm="$2"; shift 2
  occ=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader); [ -n "$occ" ] && { echo "OCCUPIED, abort: $occ"; return 1; }
  rm -rf $P/$tag; mkdir -p $P/$tag/output
  ( cd $DATA && sudo -n env CUDA_VISIBLE_DEVICES=$UUID OMP_NUM_THREADS=6 PATH=$PATH \
      taskset -c $MASK $NSYS profile --output=$P/$tag/prof --force-overwrite=true --stats=false "$@" \
      $W/bld-nvtx-$arm/motioncorr $OPTS --o $P/$tag/output/ --ingest_witness $P/$tag/ingest.witness ) \
      > $P/$tag/capture.log 2>&1
  rc=$?
  sudo -n chown -R "$USER" $P/$tag
  echo "$tag rc=$rc rep=$(ls -la $P/$tag/prof.nsys-rep 2>/dev/null | awk '{print $5}')"
  [ $rc -ne 0 ] && { tail -5 $P/$tag/capture.log; return 1; }
  $NSYS export --type sqlite --force-overwrite true --output $P/$tag/prof.sqlite $P/$tag/prof.nsys-rep > $P/$tag/export.log 2>&1
  echo "  export rc=$? sqlite=$(du -h $P/$tag/prof.sqlite 2>/dev/null | cut -f1)"
  # grade the profiled run too, so an instrumented run that silently degraded is visible
  all=$(cat $P/$tag/capture.log $(find $P/$tag/output -name '*.log') 2>/dev/null)
  echo "  witnesses: global=$(grep -c '\[CUDA Global Alignment\] completed' <<<"$all") patch=$(grep -c '\[CUDA Patch Alignment\] completed' <<<"$all") dw=$(grep -c 'Dose-Weighted Reconstruction Profile' <<<"$all") warn=$(grep -c 'WARNING:' <<<"$all") products=$(find $P/$tag/output -type f | wc -l)"
}

for arm in a1_base a6_final; do
  cap gpu-$arm   $arm --trace=cuda,nvtx
  cap host-$arm  $arm --trace=nvtx,osrt
  cap flame-$arm $arm --trace=cuda,nvtx --sample=process-tree --backtrace=fp --sampling-period=250000
done
echo "CAPTURES-DONE $(date -u +%FT%TZ)"
