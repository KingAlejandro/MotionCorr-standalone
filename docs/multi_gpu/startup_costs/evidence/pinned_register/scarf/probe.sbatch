#!/bin/bash
#SBATCH -p gpu
#SBATCH --nodelist=gn0002
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH -t 00:15:00
#SBATCH -J mcpin-probe
#SBATCH -o /home/vol05/scarf1415/mc-pinreg-20261016/probe-%j.out
C=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export LD_LIBRARY_PATH="$C/lib64:${LD_LIBRARY_PATH:-}"
cd /home/vol05/scarf1415/mc-pinreg-20261016
date -Is; hostname; uname -r; nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | head -1
./fork_probe_fixed 3 > probe-fork.txt 2>&1; echo "fork_probe rc=$?"; cat probe-fork.txt
