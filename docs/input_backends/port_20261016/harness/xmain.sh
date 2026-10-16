#!/bin/bash
# main (1db86902) vs port (977a9cef lineage) with default --ingest auto, per input set.
# usage: xmain.sh <input-set> <manifest> [movies-star-for-input-check] ; both arms run on GPU3/CPUs 72-79
set -u
wait_bench() { while ! flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held by another session; waiting 60 s ($(date -u +%FT%TZ))" >&2; sleep 60; done; }
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
PY=/home/alex/mc-env/bin/python3
GPUUUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
LOCK=/tmp/motioncorr-gpu3-correctness.lock
RES=$D/results/xmain; mkdir -p $RES $D/out
ALLOW=(--allow-added-log-line "nvCOMP ingestion" --allow-added-log-line "Staging this movie as native unsigned"
       --allow-added-log-line "Released native uint" --allow-added-log-line "Materialized native uint")
v=$1; MAN=$2
for arm in main port; do
  [ $arm = main ] && BIN=$D/build-main-nvcomp/motioncorr || BIN=$D/build-port-nvcomp/motioncorr
  out=$D/out/xmain__${v}__$arm
  wait_bench
  ( flock -w 7200 9
    CUDA_VISIBLE_DEVICES=$GPUUUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c 72-79 \
      bash $D/source/docs/input_backends/harness/run_matrix.sh $BIN $D/inputs/$v $out 0 --ingest auto
  ) 9>$LOCK > $RES/${v}__$arm.run 2>&1
  cp $out.witness $RES/${v}__$arm.witness; cp $out.time $RES/${v}__$arm.time
  echo "RUN $v $arm: $(head -1 $RES/${v}__$arm.run) routes=[$(awk '{print $2}' $out.witness | sort | uniq -c | tr '\n' ' ')] $(grep -E 'Elapsed' $out.time | cut -c1-70)"
done
o=$($PY $D/source/docs/issue85_laneC/compare_output_trees.py $D/out/xmain__${v}__main $D/out/xmain__${v}__port --manifest $MAN "${ALLOW[@]}" --json-out $RES/cmp__$v.json 2>&1); rc=$?
[ $rc -eq 0 ] && echo "CMP $v main-vs-port PASS $(echo "$o" | grep -o 'Validated.*pixels per arm')" || { echo "CMP $v main-vs-port FAIL rc=$rc"; echo "$o" | tail -4; }
if [ "${KEEP:-0}" != 1 ]; then rm -rf $D/out/xmain__${v}__*; fi
