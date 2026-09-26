#!/bin/bash
# Follow-up: which affinity setting should actually be recommended?
# spread pushes threads maximally apart, which at j=2 on a 2-socket box means
# cross-socket. close packs them. OMP_PLACES alone enables binding with libgomp's
# default policy. Test all three against unbound.
set -u
cd /home/ubuntu/mc-issue26
R=results; mkdir -p $R
BT=/home/ubuntu/mc-issue26/src-3e3a19679337d3de61327c02eef1a2947cf13517/build-timing/motioncorr
say(){ echo; echo "################ $* ################"; date -u +%FT%TZ; }

say "ARM L: OMP_PROC_BIND=close OMP_PLACES=cores"
export OMP_PROC_BIND=close OMP_PLACES=cores
python3 bench26.py --binary $BT --patch 5 --threads 2,4,8,16 --reps 2 \
  --label L_patch5x5_close --out $R/L_patch5x5_close.json --max-load 4.2 --settle-timeout 120
unset OMP_PROC_BIND OMP_PLACES

say "ARM M: OMP_PLACES=cores only (libgomp default policy)"
export OMP_PLACES=cores
python3 bench26.py --binary $BT --patch 5 --threads 2,4,8,16 --reps 2 \
  --label M_patch5x5_placesonly --out $R/M_patch5x5_placesonly.json --max-load 4.2 --settle-timeout 120
unset OMP_PLACES

say "ARM N: unbound j=4 x 10 - characterise the placement lottery"
python3 bench26.py --binary $BT --patch 5 --threads 4 --reps 10 \
  --label N_j4_unbound_x10 --out $R/N_j4_unbound_x10.json --max-load 4.2 --settle-timeout 120

say "ARM O: spread j=4 x 10 - same, bound"
export OMP_PROC_BIND=spread OMP_PLACES=cores
python3 bench26.py --binary $BT --patch 5 --threads 4 --reps 10 \
  --label O_j4_spread_x10 --out $R/O_j4_spread_x10.json --max-load 4.2 --settle-timeout 120
unset OMP_PROC_BIND OMP_PLACES

say "AFFINITY SERIES COMPLETE"
