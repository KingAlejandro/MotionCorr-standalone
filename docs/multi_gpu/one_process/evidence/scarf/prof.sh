#!/bin/bash
# nsys trace of the n4 workload, both arms (diagnostic, untimed).
set -uo pipefail
C=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$C/bin:$PATH" LD_LIBRARY_PATH="$C/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}" TMPDIR=/tmp OMP_NUM_THREADS=8
B=/home/vol05/scarf1415/mc-mdev-20261013
BIN=$B/build-cand/motioncorr
P=/tmp/mdev-prof; rm -rf $P; mkdir -p $P
cd /tmp/bench-data
W="--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --ingest nvcomp --skip_logfile"
mapfile -t G < <(nvidia-smi --query-gpu=uuid --format=csv,noheader)
NS="nsys profile --trace=cuda,osrt,nvtx --sample=none --cpuctxsw=none --force-overwrite=true"
cat > $P/parm.sh <<EOS
#!/bin/bash
L=(0-7 8-15 16-23 24-31); G=(${G[*]})
for k in 0 1 2 3; do CUDA_VISIBLE_DEVICES=\${G[\$k]} taskset -c \${L[\$k]} $BIN --i /tmp/mdev-shards-4/shard_4way_\$k.star --o $P/outP/w\$k/ --gpu 0 --j 8 $W > /dev/null & done
wait
EOS
chmod +x $P/parm.sh
for rep in 1 2; do
  /usr/bin/time -f "T wall %e" $NS -o $P/T$rep taskset -c 0-31 $BIN --i movies4.star --o $P/outT/ --gpu 0,1,2,3 --j 32 $W > $P/T$rep.console 2>&1; tail -1 $P/T$rep.console
  /usr/bin/time -f "P wall %e" $NS -o $P/P$rep $P/parm.sh > $P/P$rep.console 2>&1; tail -1 $P/P$rep.console
  rm -rf $P/outT $P/outP
done
for a in T2 P2; do grep -q ERROR $P/$a.console && echo "ERR in $a";
  nsys stats -q --format csv --report cuda_api_sum,osrt_sum -o $P/$a $P/$a.nsys-rep > /dev/null 2>&1
  nsys export -q --type sqlite -o $P/$a.sqlite $P/$a.nsys-rep > /dev/null 2>&1
done
ls -la $P
echo PROF_DONE
