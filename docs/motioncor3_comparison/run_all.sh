#!/bin/bash
# Matched 24-movie comparison: MotionCorr-standalone 306bc67 vs upstream MotionCor3 1.2.4.
# Invoked under taskset -c 96-103 while holding /tmp/motioncorr-bench.lock.
#   $1 = number of timed pairs (0 = metrics run only)
set -uo pipefail

ROOT=/home/alex/mc3-compare
WORK="$ROOT/work"
MC="$ROOT/MotionCorr-306bc67/build-mc3cmp/motioncorr"
MC3_STOCK="$ROOT/MotionCor3-stock/MotionCor3"
MC3_O3="$ROOT/MotionCor3-o3/MotionCor3"
NPAIRS="${1:-10}"
GPU=0
EXPECT=24

cd "$WORK"; mkdir -p logs

echo "=== PROVENANCE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "host=$(hostname) affinity=$(taskset -cp $$ 2>&1 | sed 's/.*: //') nproc=$(nproc)"
for b in "$MC" "$MC3_STOCK" "$MC3_O3"; do sha256sum "$b"; done
sha256sum movies.star Movies/gain.mrc
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader

# --- settle guard -----------------------------------------------------------
# The flock serialises ownership but not the previous holder's decay tail, and it
# does not cover compiles at all. pgrep -x (exact name), never -f: -f self-matches.
# Only measurements need a quiet box. A metrics-only pass (NPAIRS=0) produces no
# timing number, so gating it on quiescence would hold the mutex for up to 15 minutes
# and block other sessions for no benefit.
waited=0; n=0; l=0
while [ "$NPAIRS" -gt 0 ]; do
  n=$({ pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; pgrep -x cc1; } | wc -l)
  l=$(awk '{print $1}' /proc/loadavg)
  q=$(awk -v l="$l" 'BEGIN{print (l<2.0)?1:0}')
  { [ "$n" -eq 0 ] && [ "$q" -eq 1 ]; } && break
  [ "$waited" -ge 900 ] && { echo "GUARD TIMEOUT ${waited}s compilers=$n load1=$l"; break; }
  sleep 10; waited=$((waited+10))
done
if [ "$NPAIRS" -gt 0 ]; then
  echo "settle wait: ${waited}s (compilers=$n load1=$l)"
else
  # Do not print "load1=0": the gate never ran, so those are initialisers, not
  # observations. A log line that looks like a measurement but is not is exactly
  # the failure mode this whole protocol exists to avoid.
  echo "settle gate: SKIPPED (metrics-only run, produces no timing)"
fi

# --- arms -------------------------------------------------------------------
run_motioncorr() {   # $1=outdir  $2=logfile  $3="" | "--skip_logfile"
  local o="$1" lf="$2" extra="${3:-}"
  rm -rf "$o"; mkdir -p "$o"
  /usr/bin/time -v "$MC" \
    --i movies.star --o "$o/" \
    --use_own --gpu "$GPU" --j 8 \
    --dose_weighting --dose_per_frame 1.277 --preexposure 0 \
    --patch_x 5 --patch_y 5 --bfactor 150 \
    --gainref Movies/gain.mrc --gain_rot 0 --gain_flip 0 \
    --group_frames 1 --bin_factor 1 --max_iter 5 --seed 1 \
    --save_noDW $extra > "$lf" 2>&1
  echo $?
}

run_mc3() {          # $1=binary $2=outdir $3=logdir $4=logfile [$5=bft pair]
  local bin="$1" o="$2" g="$3" lf="$4" bft="${5:-150 150}"
  # sGenOutputName truncates the -OutMrc prefix at the first ".mrc"/".st" substring,
  # and CAlignMain does the same to -LogDir for ".mrc"/".tif"/".eer". A path
  # containing any of those silently redirects every output.
  case "$o$g" in *.mrc*|*.st*|*.tif*|*.eer*)
    echo "FATAL: output path contains a MotionCor3 truncation trigger: $o $g" >&2
    echo 99; return;; esac
  rm -rf "$o" "$g"; mkdir -p "$o" "$g"     # MotionCor3 does not create them
  /usr/bin/time -v "$bin" \
    -InTiff Movies/ -InSuffix .tiff -Serial 1 \
    -OutMrc "$o/" -LogDir "$g/" \
    -Gain Movies/gain.mrc -RotGain 0 -FlipGain 0 -InvGain 0 \
    -PixSize 0.885 -kV 200 -FmDose 1.277 -InitDose 0 \
    -Patch 5 5 0 -Bft $bft -Group 1 1 -FmRef 1 \
    -FtBin 1 -Align 1 -SumRange 0 0 -Throw 0 -Trunc 0 \
    -Cs 0 -InFmMotion 0 -SplitSum 0 \
    -Gpu "$GPU" > "$lf" 2>&1
  echo $?
}

# Foreign load is NOT covered by the flock: another user's JAX job (ryz18496,
# "balla-sweep") lives on this box and has been measured at ~101% CPU. A quiet box
# is therefore unobtainable, and a point-in-time probe before the run would race
# with it ramping up. Sample continuously for the duration of each timed run and
# report mean/max, so a run that was actually contended is visible as data rather
# than absorbed into the arm's mean.
start_sampler() {   # $1=outfile -> echoes sampler pid
  ( while :; do
      ps -eo user:24,pcpu --no-headers | awk '$1!="alex"{s+=$2} END{printf "%.1f\n", s+0}'
      sleep 1
    done > "$1" ) & echo $!
}
stop_sampler() {    # $1=pid $2=file -> "mean/max/n"
  kill "$1" 2>/dev/null; wait "$1" 2>/dev/null
  awk '{s+=$1; if($1>m)m=$1; n++} END{if(n)printf "%.1f/%.1f/%d", s/n, m, n; else printf "na/na/0"}' "$2"
}

# A crashed run is fast. Never time a run without confirming it produced 24 outputs.
emit() {  # $1=tag $2=logfile $3=rc $4=produced
  local e c r f
  e=$(grep -m1 "Elapsed (wall clock)" "$2" | awk '{print $NF}')
  c=$(grep -m1 "Percent of CPU"       "$2" | awk '{print $NF}')
  r=$(grep -m1 "Maximum resident set" "$2" | awk '{print $NF}')
  f=$(grep -m1 "File system inputs"   "$2" | awk '{print $NF}')
  local ok=INVALID; [ "$3" -eq 0 ] && [ "$4" -eq "$EXPECT" ] && ok=OK
  echo "RESULT,$1,$e,$c,$r,$f,rc=$3,outputs=$4,$ok,foreign_cpu_mean/max/n=${5:-na}"
}

# --- phase 1: metrics run (outputs kept) ------------------------------------
echo "=== PHASE 1 metrics run"
rc=$(run_motioncorr "$WORK/out-motioncorr" "$WORK/logs/motioncorr.metrics.log")
p=$(ls "$WORK"/out-motioncorr/Movies/*_noDW.mrc 2>/dev/null | wc -l)
emit motioncorr_metrics "$WORK/logs/motioncorr.metrics.log" "$rc" "$p"
rc=$(run_mc3 "$MC3_STOCK" "$WORK/out-mc3" "$WORK/log-mc3" "$WORK/logs/mc3.metrics.log")
p=$(ls "$WORK"/out-mc3/*_DW.mrc 2>/dev/null | wc -l)
emit motioncor3_metrics "$WORK/logs/mc3.metrics.log" "$rc" "$p"
echo "--- mc3 output inventory ---"; ls "$WORK/out-mc3" | sed 's/[0-9]\{8\}_[0-9]\{5\}_frameImage//' | sort | uniq -c
echo "--- mc3 log inventory ---";    ls "$WORK/log-mc3" | sed 's/[0-9]\{8\}_[0-9]\{5\}_frameImage//' | sort | uniq -c


# --- phase 1b: B-factor sensitivity -----------------------------------------
# -Bft 150 150 matches RELION's NOMINAL --bfactor 150, but the two filters are not
# the same function: RELION applies exp(-2B(ky^2/nfy^2+kx^2/nfx^2)) on the full grid
# while MotionCor3 applies exp(-0.25B(kx^2+ky^2)/((cmpX-1)cmpY)) on an internally
# ~1.81x binned grid. Run MotionCor3 at its own default too, so the report can show
# how much of any disagreement is attributable to this one unmatchable knob.
echo "=== PHASE 1b MotionCor3 at upstream default -Bft 500 100"
rc=$(run_mc3 "$MC3_STOCK" "$WORK/out-mc3-bftdef" "$WORK/log-mc3-bftdef" "$WORK/logs/mc3.bftdef.log" "500 100")
p=$(ls "$WORK"/out-mc3-bftdef/*_DW.mrc 2>/dev/null | wc -l)
emit motioncor3_bft_default "$WORK/logs/mc3.bftdef.log" "$rc" "$p"

# --- phase 1c: batch-position control ---------------------------------------
# Reading the source says MotionCor3's defect correction is a deterministic function
# of pixel index, with no RNG state. That shows there is no SEED; it does not show
# there is no other per-movie carried state (buffer reuse, async save interleaving,
# patch rejection). Test it instead of arguing it: one movie alone vs the same movie
# inside the 24-movie batch, compared byte-for-byte on pixels.
echo "=== PHASE 1c batch-position control"
CTLM=$(head -1 "$WORK/movie_bases.txt")
rm -rf "$WORK/ctl-mc3" "$WORK/ctl-mc3-log"; mkdir -p "$WORK/ctl-mc3" "$WORK/ctl-mc3-log"
"$MC3_STOCK" -InTiff "Movies/$CTLM.tiff" -OutMrc "$WORK/ctl-mc3/$CTLM.mrc" \
  -LogDir "$WORK/ctl-mc3-log/" \
  -Gain Movies/gain.mrc -RotGain 0 -FlipGain 0 -InvGain 0 \
  -PixSize 0.885 -kV 200 -FmDose 1.277 -InitDose 0 \
  -Patch 5 5 0 -Bft 150 150 -Group 1 1 -FmRef 1 \
  -FtBin 1 -Align 1 -SumRange 0 0 -Throw 0 -Trunc 0 \
  -Cs 0 -InFmMotion 0 -SplitSum 0 -Gpu "$GPU" > "$WORK/logs/mc3.ctl.log" 2>&1
echo "ctl rc=$? movie=$CTLM"
for f in "$CTLM.mrc" "${CTLM}_DW.mrc"; do
  if [ -f "$WORK/ctl-mc3/$f" ] && [ -f "$WORK/out-mc3/$f" ]; then
    # compare PIXELS only (bytes 1024+): MRC headers carry run-dependent fields
    a=$(tail -c +1025 "$WORK/ctl-mc3/$f" | sha256sum | cut -d" " -f1)
    b=$(tail -c +1025 "$WORK/out-mc3/$f" | sha256sum | cut -d" " -f1)
    [ "$a" = "$b" ] && v=IDENTICAL || v=DIFFERS
    echo "CONTROL,motioncor3,$f,alone_vs_batch=$v"
  else
    echo "CONTROL,motioncor3,$f,MISSING"
  fi
done
grep -h "" "$WORK/ctl-mc3-log/$CTLM-Patch-Full.log" 2>/dev/null | md5sum | sed "s|^|CONTROL,mc3_traj_alone_md5,|"
grep -h "" "$WORK/log-mc3/$CTLM-Patch-Full.log"     2>/dev/null | md5sum | sed "s|^|CONTROL,mc3_traj_batch_md5,|"

[ "$NPAIRS" -eq 0 ] && { echo "=== metrics-only, done $(date -u +%H:%M:%SZ)"; exit 0; }

# --- phase 2: paired timed series, arm order alternating within each pair ----
echo "=== PHASE 2 paired series n=$NPAIRS (order alternates; label kept per pair)"
for i in $(seq 1 "$NPAIRS"); do
  if [ $((i % 2)) -eq 1 ]; then order=MC_first; arms="mc mc3"; else order=MC3_first; arms="mc3 mc"; fi
  for arm in $arms; do
    if [ "$arm" = mc ]; then
      sp=$(start_sampler "$WORK/logs/fl-mc.$i")
      rc=$(run_motioncorr "$WORK/t-mc" "$WORK/logs/t-mc.$i.log")
      fl=$(stop_sampler "$sp" "$WORK/logs/fl-mc.$i")
      p=$(ls "$WORK"/t-mc/Movies/*_noDW.mrc 2>/dev/null | wc -l)
      emit "pair$i,$order,motioncorr" "$WORK/logs/t-mc.$i.log" "$rc" "$p" "$fl"
    else
      sp=$(start_sampler "$WORK/logs/fl-mc3.$i")
      rc=$(run_mc3 "$MC3_STOCK" "$WORK/t-mc3" "$WORK/t-mc3-log" "$WORK/logs/t-mc3.$i.log")
      fl=$(stop_sampler "$sp" "$WORK/logs/fl-mc3.$i")
      p=$(ls "$WORK"/t-mc3/*_DW.mrc 2>/dev/null | wc -l)
      emit "pair$i,$order,motioncor3_stock" "$WORK/logs/t-mc3.$i.log" "$rc" "$p" "$fl"
    fi
  done
done

# --- phase 3: the two single-arm variants -----------------------------------
echo "=== PHASE 3 variants n=$NPAIRS"
for i in $(seq 1 "$NPAIRS"); do
  sp=$(start_sampler "$WORK/logs/fl-mcns.$i")
  rc=$(run_motioncorr "$WORK/t-mcns" "$WORK/logs/t-mcns.$i.log" --skip_logfile)
  fl=$(stop_sampler "$sp" "$WORK/logs/fl-mcns.$i")
  p=$(ls "$WORK"/t-mcns/Movies/*_noDW.mrc 2>/dev/null | wc -l)
  emit "rep$i,motioncorr_skip_logfile" "$WORK/logs/t-mcns.$i.log" "$rc" "$p" "$fl"
  sp=$(start_sampler "$WORK/logs/fl-mc3o3.$i")
  rc=$(run_mc3 "$MC3_O3" "$WORK/t-mc3o3" "$WORK/t-mc3o3-log" "$WORK/logs/t-mc3o3.$i.log")
  fl=$(stop_sampler "$sp" "$WORK/logs/fl-mc3o3.$i")
  p=$(ls "$WORK"/t-mc3o3/*_DW.mrc 2>/dev/null | wc -l)
  emit "rep$i,motioncor3_o3" "$WORK/logs/t-mc3o3.$i.log" "$rc" "$p" "$fl"
done

echo "=== load at end: $(cat /proc/loadavg)"
echo "=== DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
