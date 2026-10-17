#!/bin/bash
#SBATCH -p gpu-devel
#SBATCH --nodelist=gn0005
#SBATCH --exclusive
#SBATCH --gres=gpu:4
#SBATCH -t 02:00:00
#SBATCH -J mcwarm-ab
#SBATCH -o /home/vol05/scarf1415/mc-warmup-20261014/ab-%j.out
D=/home/vol05/scarf1415/mc-warmup-20261014
CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVR=/home/vol05/scarf1415/nvcomp-sdk
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVR/lib:${LD_LIBRARY_PATH:-}"
export TMPDIR=/tmp
cd $D
echo "=== VENUE ==="; date -Is; hostname; grep Cpus_allowed_list /proc/self/status; cat /sys/kernel/mm/transparent_hugepage/enabled
nvidia-smi --query-gpu=index,uuid,name,persistence_mode --format=csv,noheader
echo "gs $(gs --version)"; sha256sum build-base/motioncorr build-cand/motioncorr
bash copy.sh && bash stage.sh
python3 warmab.py ${REPS:-12}
echo BENCH_DONE
