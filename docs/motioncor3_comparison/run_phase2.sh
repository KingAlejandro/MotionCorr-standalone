#!/bin/bash
# Controls + paired timed series. Under taskset -c 96-103, holding the bench flock.
#   $1 = timed pairs (phase 2)   $2 = reps (phase 3)
set -uo pipefail
ROOT=/home/alex/mc3-compare; W="$ROOT/work"
MC="$ROOT/MotionCorr-306bc67/build-mc3cmp/motioncorr"
MC3="$ROOT/MotionCor3-stock/MotionCor3"
MC3O3="$ROOT/MotionCor3-o3/MotionCor3"
NP="${1:-6}"; NR="${2:-4}"; GPU=0; EXPECT=24
cd "$W"; mkdir -p logs

echo "=== $(date -u +%FT%TZ) affinity=$(taskset -cp $$ 2>&1|sed 's/.*: //') nproc=$(nproc)"

mc3_serial() {  # $1=indir $2=outdir $3=logdir $4=stdout $5=bft $6=binary
  local i="$1" o="$2" g="$3" lf="$4" bft="${5:-150 150}" bin="${6:-$MC3}"
  case "$o$g" in *.mrc*|*.st*|*.tif*|*.eer*) echo "FATAL path trigger"; echo 99; return;; esac
  rm -rf "$o" "$g"; mkdir -p "$o" "$g"
  /usr/bin/time -v "$bin" -InTiff "$i/" -InSuffix .tiff -Serial 1 \
    -OutMrc "$o/" -LogDir "$g/" \
    -Gain Movies/gain.mrc -RotGain 0 -FlipGain 0 -InvGain 0 \
    -PixSize 0.885 -kV 200 -FmDose 1.277 -InitDose 0 \
    -Patch 5 5 0 -Bft $bft -Group 1 1 -FmRef 1 \
    -FtBin 1 -Align 1 -SumRange 0 0 -Throw 0 -Trunc 0 \
    -Cs 0 -InFmMotion 0 -SplitSum 0 -Gpu "$GPU" > "$lf" 2>&1
  echo $?
}
run_mc() {  # $1=outdir $2=stdout $3=extra
  local o="$1" lf="$2" x="${3:-}"
  rm -rf "$o"; mkdir -p "$o"
  /usr/bin/time -v "$MC" --i movies.star --o "$o/" --use_own --gpu "$GPU" --j 8 \
    --dose_weighting --dose_per_frame 1.277 --preexposure 0 \
    --patch_x 5 --patch_y 5 --bfactor 150 \
    --gainref Movies/gain.mrc --gain_rot 0 --gain_flip 0 \
    --group_frames 1 --bin_factor 1 --max_iter 5 --seed 1 --save_noDW $x > "$lf" 2>&1
  echo $?
}
# Sets globals rather than returning the pid through $( ). A backgrounded subshell
# inside a command substitution inherits bash's saved copy of the substitution pipe on
# fd 10, so the parent never sees EOF and blocks forever -- observed here as a stalled
# run holding the bench lock with no worker process alive.
SPID=""; SFILE=""
start_s(){ SFILE="$1"; ( while :; do ps -eo user:24,pcpu --no-headers | awk '$1!="alex"{s+=$2} END{printf "%.1f\n",s+0}'; sleep 1; done ) > "$1" 2>/dev/null & SPID=$!; }
stop_s(){ kill "$SPID" 2>/dev/null; wait "$SPID" 2>/dev/null
  FL=$(awk '{s+=$1; if($1>m)m=$1; n++} END{if(n)printf "%.1f/%.1f/%d",s/n,m,n; else printf "na/na/0"}' "$SFILE"); }
emit(){ local e c r f ok=INVALID
  e=$(grep -m1 "Elapsed (wall clock)" "$2"|awk '{print $NF}'); c=$(grep -m1 "Percent of CPU" "$2"|awk '{print $NF}')
  r=$(grep -m1 "Maximum resident set" "$2"|awk '{print $NF}'); f=$(grep -m1 "File system inputs" "$2"|awk '{print $NF}')
  [ "$3" -eq 0 ] && [ "$4" -eq "$EXPECT" ] && ok=OK
  echo "RESULT,$1,$e,$c,$r,$f,rc=$3,outputs=$4,$ok,foreign=${5:-na}"; }

# ---------------------------------------------------------------- CONTROLS
# The alone-vs-batch control failed: patch trajectories differed while the GLOBAL
# trajectory was byte-identical. But single-movie mode and serial mode use different
# save/correct paths, so that test cannot tell "batch composition matters" apart from
# "the two modes differ". These two controls separate them, both in serial mode.
if [ "${SKIP_CONTROLS:-0}" = 1 ]; then echo "=== CONTROLS skipped (already recorded)"; else
echo "=== CONTROL A: determinism (same 24-movie serial batch, run twice)"
rc=$(mc3_serial Movies "$W/ctlA" "$W/ctlA-log" "$W/logs/ctlA.log")
echo "ctlA rc=$rc outputs=$(ls "$W"/ctlA/*_DW.mrc 2>/dev/null|wc -l)"

echo "=== CONTROL B: batch composition (2-movie serial batch vs 24-movie serial batch)"
rm -rf "$W/sub2"; mkdir -p "$W/sub2"
M1=$(sed -n 1p movie_bases.txt); M2=$(sed -n 2p movie_bases.txt)
ln -sf "$W/Movies/$M1.tiff" "$W/sub2/$M1.tiff"; ln -sf "$W/Movies/$M2.tiff" "$W/sub2/$M2.tiff"
ln -sf "$W/Movies/gain.mrc" "$W/sub2/gain.mrc"
rc=$(mc3_serial "$W/sub2" "$W/ctlB" "$W/ctlB-log" "$W/logs/ctlB.log")
echo "ctlB rc=$rc outputs=$(ls "$W"/ctlB/*_DW.mrc 2>/dev/null|wc -l)"

for pair in "ctlA:determinism_24v24" "ctlB:composition_2v24"; do
  d=${pair%%:*}; lab=${pair##*:}
  for suf in ".mrc" "_DW.mrc"; do
    a="$W/$d/$M1$suf"; b="$W/out-mc3/$M1$suf"
    if [ -f "$a" ] && [ -f "$b" ]; then
      cmp -s <(tail -c +1025 "$a") <(tail -c +1025 "$b") && v=PIXEL_IDENTICAL || v=DIFFERS
      echo "CONTROL,$lab,$M1$suf,$v"
    else echo "CONTROL,$lab,$M1$suf,MISSING"; fi
  done
  for lg in Patch-Full Patch-Patch; do
    a="$W/$d-log/$M1-$lg.log"; b="$W/log-mc3/$M1-$lg.log"
    if [ -f "$a" ] && [ -f "$b" ]; then
      cmp -s "$a" "$b" && v=IDENTICAL || v=DIFFERS
      echo "CONTROL,$lab,$lg,$v"
    else echo "CONTROL,$lab,$lg,MISSING"; fi
  done
done

fi
# ------------------------------------------------------------- settle gate
waited=0
while :; do
  n=$({ pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; pgrep -x cc1; } | wc -l)
  l=$(awk '{print $1}' /proc/loadavg)
  q=$(awk -v l="$l" 'BEGIN{print (l<2.0)?1:0}')
  { [ "$n" -eq 0 ] && [ "$q" -eq 1 ]; } && break
  [ "$waited" -ge 600 ] && { echo "GUARD TIMEOUT ${waited}s compilers=$n load1=$l"; break; }
  sleep 5; waited=$((waited+5))
done
echo "settle wait: ${waited}s (compilers=$n load1=$l)"

# --------------------------------------------------------- PHASE 2 paired
# Effects here are large (tens of seconds on runs of 40-80 s), so n=6 paired is
# ample. The n>=40 requirement documented for this host applies to ~40 ms effects
# on a ~2 s process, which is four orders of magnitude finer than this contrast.
echo "=== PHASE 2 paired n=$NP"
for i in $(seq 1 "$NP"); do
  if [ $((i%2)) -eq 1 ]; then ord=MC_first; arms="mc mc3"; else ord=MC3_first; arms="mc3 mc"; fi
  for a in $arms; do
    if [ "$a" = mc ]; then
      start_s "$W/logs/f-mc.$i"; rc=$(run_mc "$W/t-mc" "$W/logs/t-mc.$i.log")
      stop_s; fl=$FL; p=$(ls "$W"/t-mc/Movies/*_noDW.mrc 2>/dev/null|wc -l)
      emit "pair$i,$ord,motioncorr" "$W/logs/t-mc.$i.log" "$rc" "$p" "$fl"
    else
      start_s "$W/logs/f-mc3.$i"; rc=$(mc3_serial Movies "$W/t-mc3" "$W/t-mc3-log" "$W/logs/t-mc3.$i.log")
      stop_s; fl=$FL; p=$(ls "$W"/t-mc3/*_DW.mrc 2>/dev/null|wc -l)
      emit "pair$i,$ord,motioncor3_stock" "$W/logs/t-mc3.$i.log" "$rc" "$p" "$fl"
    fi
  done
done

# ------------------------------------------------------- PHASE 3 variants
echo "=== PHASE 3 variants n=$NR"
for i in $(seq 1 "$NR"); do
  start_s "$W/logs/f-mcns.$i"; rc=$(run_mc "$W/t-mcns" "$W/logs/t-mcns.$i.log" --skip_logfile)
  stop_s; fl=$FL; p=$(ls "$W"/t-mcns/Movies/*_noDW.mrc 2>/dev/null|wc -l)
  emit "rep$i,motioncorr_skip_logfile" "$W/logs/t-mcns.$i.log" "$rc" "$p" "$fl"
  start_s "$W/logs/f-o3.$i"; rc=$(mc3_serial Movies "$W/t-o3" "$W/t-o3-log" "$W/logs/t-o3.$i.log" "150 150" "$MC3O3")
  stop_s; fl=$FL; p=$(ls "$W"/t-o3/*_DW.mrc 2>/dev/null|wc -l)
  emit "rep$i,motioncor3_o3host" "$W/logs/t-o3.$i.log" "$rc" "$p" "$fl"
done
echo "=== DONE $(date -u +%FT%TZ) load=$(cat /proc/loadavg)"
