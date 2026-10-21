#!/bin/bash
# Run on 4GPUs (setsid). Streams hash-verified fixtures to cpu64 under an in-flight cap; originals untouched.
G=/mnt/clathrin/alex-motioncorr-km-truth/fixtures; D=ubuntu@130.246.81.24; R=/home/ubuntu/mc-synth-combined
CONDS="pedestal32 dose1 dose05 dose2 dose4 outmodel nonsquare pedestal0 contrast025 contrast4"
for c in $CONDS; do for s in 0 1 2 3 4 5 6 7 8 9; do
  n=$(printf '%s-s%02d' $c $s)
  while :; do
    k=$(ssh -o BatchMode=yes $D "ls $R/fixtures/*/movie.mrcs 2>/dev/null | wc -l"); free=$(ssh -o BatchMode=yes $D "df --output=avail -BG /home/ubuntu | tail -n 1 | tr -dc 0-9")
    [ "${k:-99}" -lt 10 ] && [ "${free:-0}" -gt 30 ] && break; sleep 20
  done
  ssh -o BatchMode=yes $D "test -f $R/fixtures/$n/RECEIPT.json" && continue
  ssh -o BatchMode=yes $D "rm -rf $R/fixtures/$n.partial; mkdir $R/fixtures/$n.partial"
  tar -C $G/$n -cf - input.star movie.mrcs RECEIPT.json | ssh -o BatchMode=yes $D "tar -C $R/fixtures/$n.partial -xf -" || { echo FAIL $n; continue; }
  want=$(grep -o '"movie.mrcs": "[0-9a-f]*"' $G/$n/RECEIPT.json | cut -d'"' -f4)
  got=$(ssh -o BatchMode=yes $D "sha256sum $R/fixtures/$n.partial/movie.mrcs" | cut -d' ' -f1)
  if [ "$want" = "$got" ]; then ssh -o BatchMode=yes $D "mv $R/fixtures/$n.partial $R/fixtures/$n"; echo ok $n; else echo HASHMISMATCH $n; fi
done; done
echo pushed-all
