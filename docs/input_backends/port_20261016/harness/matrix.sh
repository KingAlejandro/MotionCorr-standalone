#!/bin/bash
# W-TIFF route matrix on the 4GPUs lane (GPU3, CPUs 72-79).
# usage: matrix.sh <tag> <binary> <variant>...
# For each variant: the pinned routes nvcomp, compact, float, plus auto, each as its own
# run (flock on the gpu3 lock per run, taskset 72-79). Products are compared for strict
# identity with docs/issue85_laneC/compare_output_trees.py against the 2-movie manifest.
set -u
wait_bench() { while ! flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held by another session; waiting 60 s ($(date -u +%FT%TZ))" >&2; sleep 60; done; }
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
TAG=$1; BIN=$2; shift 2
SRC=${SRC:-$D/source}
PY=/home/alex/mc-env/bin/python3
CMP="$PY $SRC/docs/issue85_laneC/compare_output_trees.py"
MAN=$SRC/docs/input_backends/two_movie_manifest.json
GPUUUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
LOCK=/tmp/motioncorr-gpu3-correctness.lock
RES=$D/results/$TAG; mkdir -p $RES
ALLOW=(--allow-added-log-line "nvCOMP ingestion"
       --allow-added-log-line "Staging this movie as native unsigned"
       --allow-added-log-line "Released native uint"
       --allow-added-log-line "Materialized native uint")
run_route() { # variant route
  wait_bench
  local v=$1 r=$2 out=$D/out/${TAG}__${1}__${2}
  mkdir -p $D/out
  ( flock -w 7200 9
    if [ -n "$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | grep $GPUUUID)" ]; then echo "FOREIGN PROCESS ON GPU3 BEFORE RUN $v $r" >&2; fi
    CUDA_VISIBLE_DEVICES=$GPUUUID CUDA_DEVICE_ORDER=PCI_BUS_ID taskset -c 72-79 \
      bash $SRC/docs/input_backends/harness/run_matrix.sh $BIN $D/inputs/$v $out 0 --ingest $r
  ) 9>$LOCK > $RES/${v}__${r}.run 2>&1
  cp $out.witness $RES/${v}__${r}.witness 2>/dev/null
  cp $out.time $RES/${v}__${r}.time 2>/dev/null
  tail -3 $out.stdout > $RES/${v}__${r}.stdout.tail 2>/dev/null
}
compare() { # label a b
  local out rc
  out=$($CMP "$2" "$3" --manifest $MAN --input-star $D/inputs/$4/movies.star "${ALLOW[@]}" --json-out $RES/cmp__$1.json 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo "CMP $1 PASS $(echo "$out" | grep -o 'Validated.*pixels per arm')"; else echo "CMP $1 FAIL rc=$rc"; echo "$out" | tail -4 | sed 's/^/    /'; fi
}
for v in "$@"; do
  for r in nvcomp compact float auto; do run_route $v $r; done
  for r in nvcomp compact float auto; do
    echo "RUN $v $r: $(head -1 $RES/${v}__${r}.run) routes=[$(awk '{print $2}' $RES/${v}__${r}.witness 2>/dev/null | sort | uniq -c | tr '\n' ' ')] products=$(grep PRODUCTS $RES/${v}__${r}.run)"
  done
  O=$D/out/${TAG}__$v
  if [ "${DECLINE:-0}" = 1 ]; then
    echo "DECLINE $v: pinned nvcomp refusal text: $(grep -h -m1 -i 'declined\|cannot use\|nvcomp' ${O}__nvcomp.stdout ${O}__nvcomp/*.log 2>/dev/null | head -1 | cut -c1-200)"
    compare "$v:auto-vs-compact"   ${O}__auto    ${O}__compact $v
    compare "$v:compact-vs-float"  ${O}__compact ${O}__float   $v
  else
    compare "$v:nvcomp-vs-compact" ${O}__nvcomp ${O}__compact $v
    compare "$v:nvcomp-vs-float"   ${O}__nvcomp ${O}__float   $v
    compare "$v:auto-vs-nvcomp"    ${O}__auto   ${O}__nvcomp  $v
    compare "$v:compact-vs-float"  ${O}__compact ${O}__float  $v
    if [ -n "${REFKEEP:-}" ] && [ "$v" != "$REFKEEP" ]; then compare "$v:nvcomp-vs-ref($REFKEEP)" ${O}__nvcomp $D/out/${TAG}__${REFKEEP}__nvcomp $v; fi
  fi
  # keep the first widened arm's tree for the cross-variant gate; drop the rest
  if [ "$v" != "${REFKEEP:-}" ]; then rm -rf ${O}__* ; else rm -rf ${O}__compact ${O}__float ${O}__auto; fi
done
