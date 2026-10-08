#!/bin/bash
# Movie I/O cost breakdown for MotionCorr, all arms on one exclusive node.
set -u
B=$HOME/mc-io
SRC=$B/src
R=$B/results; mkdir -p "$R"
LOG=$R/io.txt
T=$HOME/i53-scarf/relion30_tutorial/Movies
RUNROOT=$HOME/i53-scarf/runroot
say(){ echo "$@" | tee -a "$LOG"; }

say "=== START $(date -Is) node=$(hostname) job=${SLURM_JOB_ID:-na} cpus=$(nproc) ==="
say "home_fs=$(stat -f -c %T $HOME)  tmp_fs=$(stat -f -c %T /tmp)"

# ---------------------------------------------------------------- build
cd "$SRC"
rm -rf build-cpu
cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DTIMING=ON -DBUILD_TESTING=OFF \
  > $R/conf.log 2>&1 || { say "CONFIGURE FAILED"; tail -25 $R/conf.log | tee -a "$LOG"; exit 1; }
grep -h "^CXX_FLAGS" build-cpu/CMakeFiles/motioncorr_core.dir/flags.make | tee -a "$LOG"
cmake --build build-cpu --parallel 32 > $R/build.log 2>&1 \
  || { say "BUILD FAILED"; tail -30 $R/build.log | tee -a "$LOG"; exit 1; }
BIN=$SRC/build-cpu/motioncorr
say "binary=$(sha256sum $BIN | cut -d' ' -f1)"

g++ -O3 -fopenmp -o $B/tiffbench  $B/tiffbench.cpp  -ltiff -lz 2>&1 | tee -a "$LOG"
g++ -O3 -o $B/writebench $B/writebench.cpp 2>&1 | tee -a "$LOG"
say "microbenchmarks built"

# ---------------------------------------------------------------- stage
STAGE=/tmp/mcio.$$
mkdir -p $STAGE/Movies $STAGE/out
say "staging 24 movies + gain to $STAGE ..."
S0=$(date +%s.%N)
cp $T/*.tiff $T/gain.mrc $STAGE/Movies/
say "stage_copy_s=$(echo "$(date +%s.%N) - $S0" | bc)  size=$(du -sh $STAGE/Movies | cut -f1)"
sed "s|^Movies/|$STAGE/Movies/|" $RUNROOT/movies.star > $STAGE/movies.star
sed "s|^Movies/|$T/|"             $RUNROOT/movies.star > $B/movies_panfs.star

OPT="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --seed 1"

# --------------------------------------------------- A: real 24-movie runs
run24(){ # tag star gainref outdir threads
  local TAG=$1 STAR=$2 GAIN=$3 OUT=$4 J=$5
  rm -rf "$OUT"; mkdir -p "$OUT"
  local S=$(date +%s.%N)
  /usr/bin/time -v $BIN --i "$STAR" --o "$OUT/" --j $J --gainref "$GAIN" $OPT \
     > $R/run_$TAG.log 2> $R/time_$TAG.txt
  local rc=$?
  local W=$(echo "$(date +%s.%N) - $S" | bc)
  local RSS=$(grep -oP 'Maximum resident set size \(kbytes\): \K[0-9]+' $R/time_$TAG.txt)
  say "RUN $TAG rc=$rc j=$J wall=${W}s peakRSS=$((RSS/1024))MiB mrc=$(ls $OUT/*.mrc 2>/dev/null | grep -vc '_PS\|gain')"
}

say "--- A: end-to-end, input+output on PanFS \$HOME ---"
for i in 1 2 3; do run24 panfs_j8_r$i $B/movies_panfs.star $T/gain.mrc $B/out_panfs 8; done
say "--- A: end-to-end, input+output on local /tmp ---"
for i in 1 2 3; do run24 tmp_j8_r$i $STAGE/movies.star $STAGE/Movies/gain.mrc $STAGE/out 8; done
say "--- A: thread sweep on /tmp ---"
for J in 1 4 16 32; do run24 tmp_j${J} $STAGE/movies.star $STAGE/Movies/gain.mrc $STAGE/out $J; done

# --------------------------------------------------- B: decode microbenchmark
say "--- B: TIFF decode modes (A=current, B=reuse handle+fused flip, C=strip-parallel) ---"
for J in 1 8 16 32 64; do
  for M in A B C; do
    $B/tiffbench $M $J $STAGE/Movies/*.tiff 2>>$R/tiffbench.err | tee -a "$LOG"
  done
done

# --------------------------------------------------- C: write microbenchmark
say "--- C: MRC write modes, 24 files of 3710x3838 float ---"
for D in "$B/out_panfs" "$STAGE/out"; do
  mkdir -p "$D"
  for M in cur nolock direct; do $B/writebench $M "$D" 24 3710 3838 | tee -a "$LOG"; done
done

say "--- D: ghostscript PDF step ---"
EPS=$(ls $B/out_panfs/*.eps 2>/dev/null | head -24 | tr '\n' ' ')
if [ -n "$EPS" ]; then
  S=$(date +%s.%N)
  gs -sDEVICE=pdfwrite -dNOPAUSE -dBATCH -dSAFER -dDEVICEWIDTHPOINTS=800 \
     -dDEVICEHEIGHTPOINTS=800 -sOutputFile=/tmp/gsbench.pdf $EPS > /dev/null 2>&1
  say "gs_24eps_s=$(echo "$(date +%s.%N) - $S" | bc)"
else
  say "gs: no eps found"
fi

rm -rf $STAGE
say "=== DONE $(date -Is) ==="
