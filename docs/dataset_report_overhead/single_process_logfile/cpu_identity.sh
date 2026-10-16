#!/bin/bash
# CPU-path product identity, 12 movies, base vs candidate. Run under:
#   flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash cpu_identity.sh
# No --gpu: both arms run the CPU alignment path of the CUDA build. Same as-run-path scheme as correct.sh.
set -u
W=/home/alex/mc-small/lfe; D=/home/alex/mc-small/data96; EV=$W/ev
BIN_base=$W/build-base/motioncorr; BIN_cand=$W/build-cand/motioncorr
CMP=$W/src-cand/docs/perf_integration/identity/cmp_trees.py; PY=/home/alex/.mc-venv/bin/python
R=$W/runs/cpu; rm -rf $R; mkdir -p $R
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --even_odd_split --save_noDW)
fix() { find $2 \( -name '*.star' -o -name '*.lst' \) -exec sed -i "s#$1#$2#g" {} +; }
echo "start $(date -Is)"; cd $D
for arm in base cand; do
  AS=$R/as_run; rm -rf $AS; mkdir -p $AS; B=BIN_$arm; t0=$SECONDS
  GSLOG=$R/$arm.gs.log PATH=$EV/proxy:$PATH taskset -c 96-103 ${!B} --i movies12_fixed116.star --o $AS/ "${OPTS[@]}" > $R/$arm.stdout 2>&1
  echo "cpu $arm rc=$? mrc=$(find $AS -name '*.mrc' | wc -l) wall=$((SECONDS-t0))s"
  mv $AS $R/$arm; fix $AS $R/$arm
done
echo "== cpu: products (cmp_trees.py)"; $PY $CMP $R/base $R/cand
echo "== cpu: logfile.pdf pages"; $PY $EV/pagecmp.py cmp $R/base/logfile.pdf $R/cand/logfile.pdf
for arm in base cand; do echo "-- $arm gs calls writing logfile.pdf"; grep -o -e '-sOutputFile=[^ ]*logfile.pdf[^ ]*' -e '-sOUTPUTFILE=[^ ]*logfile.pdf[^ ]*' $R/$arm.gs.log | sed "s#$R/as_run#<out>#"; done
echo "-- inventory"; diff <(cd $R/base && find . -type f | sort) <(cd $R/cand && find . -type f | sort) && echo "inventory identical"
cp -r $R/cand $R/ctl_flip; f=$(find $R/ctl_flip -name '*.mrc' | head -1)
$PY - "$f" <<'PYEOF'
import sys; p=sys.argv[1]; b=bytearray(open(p,'rb').read()); b[len(b)//2]^=1; open(p,'wb').write(b)
PYEOF
echo "-- cmp_trees payload-flip control (expect DIFFERENT)"; $PY $CMP $R/base $R/ctl_flip
echo "end $(date -Is)"
