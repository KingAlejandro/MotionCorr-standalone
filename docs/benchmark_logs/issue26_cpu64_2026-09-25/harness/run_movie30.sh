#!/bin/bash
set -u
cd /home/ubuntu/mc-issue26
R=results; mkdir -p $R
BT=/home/ubuntu/mc-issue26/src-3e3a19679337d3de61327c02eef1a2947cf13517/build-timing/motioncorr
say(){ echo; echo "################ $* ################"; date -u +%FT%TZ; }

say "ARM P: movie 00030, 5x5, unbound - does the 00021 scaling curve generalise?"
unset OMP_PROC_BIND OMP_PLACES
python3 bench26.py --binary $BT --star movies_m30.star --patch 5 --threads 1,4,16 --reps 2 \
  --label P_m30_unbound --out $R/P_m30_unbound.json --max-load 4.2 --settle-timeout 120

say "ARM Q: movie 00030, 5x5, spread"
export OMP_PROC_BIND=spread OMP_PLACES=cores
python3 bench26.py --binary $BT --star movies_m30.star --patch 5 --threads 1,4,16 --reps 2 \
  --label Q_m30_spread --out $R/Q_m30_spread.json --max-load 4.2 --settle-timeout 120
unset OMP_PROC_BIND OMP_PLACES

say "MOVIE30 SERIES COMPLETE"
