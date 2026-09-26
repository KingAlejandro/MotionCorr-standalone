#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:4
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J i53final
#SBATCH -o /home/vol05/scarf1415/i53-scarf/slurm-%j.out
export TMPDIR=/tmp
bash $HOME/final.sh
