set -u
W=/home/alex/mc-fft; K=$W/kmns; PY=/home/alex/.mc-venv/bin/python; GPU3=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
L=$K/kmns.txt; uptime > $L
for c in km_local_hisnr_ns km_local_realscale_ns; do $PY $K/gen.py --case $c --include-heavy --outdir $K/fixtures >> $K/gen.log 2>&1; echo "gen $c rc=$?" >> $L; done
for arm in default fast mut; do
  b=$W/build/motioncorr; [ $arm = fast ] && b=$W/val/motioncorr_fast; [ $arm = mut ] && b=$W/val/motioncorr_mut
  rm -rf $K/out_$arm
  ( cd $W/src && flock /tmp/motioncorr-gpu3-correctness.lock env CUDA_VISIBLE_DEVICES=$GPU3 taskset -c 80-87 \
      $PY tools/run_known_motion_gates.py --binary $b --python $PY --gpu 0 --outdir $K/out_$arm \
      --fixtures $K/fixtures --include-heavy --no-regenerate --json $K/km_$arm.json > $K/km_$arm.txt 2>&1 )
  echo "known-motion-ns $arm rc=$?" >> $L
done
echo KMNS-DONE >> $L
