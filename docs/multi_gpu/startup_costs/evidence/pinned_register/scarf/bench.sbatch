#!/bin/bash
#SBATCH -p gpu-devel
#SBATCH --nodelist=gn0002
#SBATCH --exclusive
#SBATCH --gres=gpu:4
#SBATCH -t 02:00:00
#SBATCH -J mcpin-ab
#SBATCH -o /home/vol05/scarf1415/mc-pinreg-20261016/ab-%j.out
D=/home/vol05/scarf1415/mc-pinreg-20261016
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}"
export TMPDIR=/tmp
cd $D
echo "=== VENUE ==="; date -Is; hostname; uname -r; grep Cpus_allowed_list /proc/self/status; lscpu | grep -E "Model name|NUMA node"; nvidia-smi topo -m
for f in enabled defrag khugepaged/defrag; do echo "thp/$f: $(cat /sys/kernel/mm/transparent_hugepage/$f)"; done
nvidia-smi --query-gpu=index,uuid,name,persistence_mode,driver_version --format=csv,noheader
sha256sum build-base/motioncorr build-cand/motioncorr
echo "=== PROBES (GPU0, lane 0-7) ==="
export CUDA_VISIBLE_DEVICES=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
taskset -c 0-7 ./fork_probe 3 > probe-fork.txt 2>&1; cat probe-fork.txt
: > probe-pin.jsonl; for rep in $(seq 1 10); do for m in hostalloc reg_huge reg_4k; do taskset -c 0-7 ./pin_probe $m >> probe-pin.jsonl 2>&1; done; done
unset CUDA_VISIBLE_DEVICES
echo "=== A/B ==="
bash copy.sh && bash stage.sh
python3 warmab.py ${REPS:-12}
echo "=== PRODUCTS (kept 1x8 warm-up trees) ==="
python3 src-cand/docs/perf_integration/identity/cmp_trees.py keep/base keep/cand | head -5
echo BENCH_DONE
