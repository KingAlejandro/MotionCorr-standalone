#!/bin/bash
#SBATCH -p scarf
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J mcio
#SBATCH -o /home/vol05/scarf1415/mc-io/slurm-%j.out
export TMPDIR=/tmp
bash $HOME/mc-io/iojob.sh
