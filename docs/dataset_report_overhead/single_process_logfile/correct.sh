#!/bin/bash
# Correctness matrix, base 116eb04a vs candidate. Run under:
#   flock -w 3600 /tmp/motioncorr-bench.lock taskset -c 96-103 bash correct.sh
# Both arms of a configuration write to the SAME as-run path (each shifts EPS draws its own
# absolute path onto the page), then the tree is moved and .star/.lst are rewritten to the new
# root so cmp_trees.py's root normalisation applies. EPS files are left alone.
set -u
W=/home/alex/mc-small/lfe; D=/home/alex/mc-small/data96; EV=$W/ev
BIN_base=$W/build-base/motioncorr; BIN_cand=$W/build-cand/motioncorr
CMP=$W/src-cand/docs/perf_integration/identity/cmp_trees.py
PY=/home/alex/.mc-venv/bin/python
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
R=$W/runs/correct; rm -rf $R; mkdir -p $R
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8)
GPU=(--gpu 0 --ingest nvcomp)
export CUDA_VISIBLE_DEVICES=$U CUDA_DEVICE_ORDER=PCI_BUS_ID
echo "start $(date -Is) gs=$(gs --version) base=$(sha256sum $BIN_base | cut -c1-16) cand=$(sha256sum $BIN_cand | cut -c1-16)"
cd $D
star_n() { { grep -v 'tiff 1$' $1; grep 'tiff 1$' $1 | head -$2; } ; }
star_n movies12_fixed116.star 6 > $R/movies6.star
star_n movies12_fixed116.star 2 > $R/movies2.star
star_n movies12_fixed116.star 4 > $R/movies4.star
fix() { find $2 \( -name '*.star' -o -name '*.lst' \) -exec sed -i "s#$1#$2#g" {} +; }

for cfg in default eo; do
  extra=(); [ $cfg = eo ] && extra=(--even_odd_split)
  mkdir -p $R/$cfg
  for arm in base cand; do
    AS=$R/$cfg/as_run; rm -rf $AS; mkdir -p $AS; B=BIN_$arm
    GSLOG=$R/$cfg/$arm.gs.log PATH=$EV/proxy:$PATH \
      taskset -c 96-103 ${!B} --i movies12_fixed116.star --o $AS/ "${OPTS[@]}" "${GPU[@]}" "${extra[@]}" > $R/$cfg/$arm.stdout 2>&1
    echo "$cfg $arm rc=$? movies_mrc=$(find $AS -name '*.mrc' | wc -l)"
    mv $AS $R/$cfg/$arm; fix $AS $R/$cfg/$arm
  done
  echo "== $cfg: products (cmp_trees.py)"; $PY $CMP $R/$cfg/base $R/$cfg/cand
  echo "== $cfg: logfile.pdf pages"; $PY $EV/pagecmp.py cmp $R/$cfg/base/logfile.pdf $R/$cfg/cand/logfile.pdf
  echo "== $cfg: gs calls that write logfile.pdf"
  for arm in base cand; do echo "-- $arm"; grep -c . $R/$cfg/$arm.gs.log; grep -o -e '-sOutputFile=[^ ]*logfile.pdf[^ ]*' -e '-sOUTPUTFILE=[^ ]*logfile.pdf[^ ]*' $R/$cfg/$arm.gs.log | sed "s#$R/$cfg/as_run#<out>#"; done
  echo "== $cfg: inventory (names only)"; diff <(cd $R/$cfg/base && find . -type f | sort) <(cd $R/$cfg/cand && find . -type f | sort) && echo "inventory identical"
done

echo "== comparator controls"
cp -r $R/default/cand $R/ctl_flip; f=$(find $R/ctl_flip -name '*.mrc' | head -1)
$PY - "$f" <<'PYEOF'
import sys; p=sys.argv[1]; b=bytearray(open(p,'rb').read()); b[len(b)//2]^=1; open(p,'wb').write(b)
PYEOF
echo "-- cmp_trees payload-flip control (expect DIFFERENT)"; $PY $CMP $R/default/base $R/ctl_flip
echo "-- cmp_trees eo vs default (expect DIFFERENT)"; $PY $CMP $R/default/base $R/eo/base
echo "-- pagecmp controls on default/base EPS lists"; $PY $EV/pagecmp.py controls $R/default/base
echo "-- pagecmp eo-vs-default logfile (different content, expect DIFFERENT)"; $PY $EV/pagecmp.py cmp $R/default/base/logfile.pdf $R/eo/base/logfile.pdf

echo "== incremental: 6 movies, then --only_do_unfinished over 12"
mkdir -p $R/incr
for arm in base cand; do
  AS=$R/incr/as_run; rm -rf $AS; mkdir -p $AS; B=BIN_$arm
  for step in 1 2; do
    s=$R/movies6.star; ex=(); [ $step = 2 ] && s=movies12_fixed116.star && ex=(--only_do_unfinished)
    GSLOG=$R/incr/$arm.gs$step.log PATH=$EV/proxy:$PATH \
      taskset -c 96-103 ${!B} --i $s --o $AS/ "${OPTS[@]}" "${GPU[@]}" "${ex[@]}" > $R/incr/$arm.stdout$step 2>&1
    echo "incr $arm step$step rc=$?"
    cp $AS/logfile.pdf $R/incr/$arm.logfile$step.pdf
  done
  mv $AS $R/incr/$arm; fix $AS $R/incr/$arm
done
for step in 1 2; do
  echo "-- step$step logfile.pdf pages base vs cand"; $PY $EV/pagecmp.py cmp $R/incr/base.logfile$step.pdf $R/incr/cand.logfile$step.pdf
  for arm in base cand; do echo "-- $arm step$step gs calls writing logfile.pdf (-sOutputFile = EPS list, -sOUTPUTFILE = concatenation)"
    grep -o -e '-sOutputFile=[^ ]*logfile.pdf[^ ]*' -e '-sOUTPUTFILE=[^ ]*logfile.pdf[^ ]*' $R/incr/$arm.gs$step.log | sed "s#$R/incr/as_run#<out>#"; done
done
echo "-- incr products"; $PY $CMP $R/incr/base $R/incr/cand
echo "-- incr: step1 vs step2 logfile (control: must differ)"; $PY $EV/pagecmp.py cmp $R/incr/cand.logfile1.pdf $R/incr/cand.logfile2.pdf

echo "== failure cases, 2 movies"
mkdir -p $R/fail $R/fakegs_fail $R/fakegs_hang
printf '#!/bin/sh\nexit 1\n' > $R/fakegs_fail/gs; printf '#!/bin/sh\nsleep 1\nexit 1\n' > $R/fakegs_hang/gs; chmod +x $R/fakegs_*/gs
for case in fail hang dir; do
  for arm in base cand; do
    AS=$R/fail/as_run; rm -rf $AS; mkdir -p $AS; B=BIN_$arm
    pre=$R/fakegs_$case; [ $case = dir ] && { pre=/usr/bin; mkdir $AS/logfile.pdf; }
    t0=$(date +%s.%N)
    PATH=$pre:$PATH taskset -c 96-103 ${!B} --i $R/movies2.star --o $AS/ "${OPTS[@]}" "${GPU[@]}" > $R/fail/$arm.$case.out 2>&1
    echo "fail-case=$case arm=$arm rc=$? wall=$(echo "$(date +%s.%N)-$t0" | bc | cut -c1-5)s mrc=$(find $AS -name '*.mrc' | wc -l)"
    sed -i "s#$AS#<out>#g" $R/fail/$arm.$case.out
    (cd $AS && ls -l --time-style=+ header.pdf batch.pdf all_batches.pdf logfile.pdf logfile.pdf.lst 2>&1 | awk '{print $1,$5,$6,$7}') > $R/fail/$arm.$case.ls
    rm -rf $AS
  done
  echo "-- $case: console output diff (base < > cand), after normalising the output root"
  diff $R/fail/base.$case.out $R/fail/cand.$case.out && echo "console identical"
  echo "-- $case: output files (ls)"; diff $R/fail/base.$case.ls $R/fail/cand.$case.ls && echo "listing identical"
done

echo "== dataset endpoint, 4 movies, one worker (output only, no timing claim)"
mkdir -p $R/dataset
for arm in base cand; do
  AS=$R/dataset/$arm; rm -rf $AS
  taskset -c 96-103 $PY $W/src-$arm/tools/multi_gpu/run_dataset.py --binary $W/build-$arm/motioncorr --star $R/movies4.star \
    --out $AS --required-products .mrc,.star --launcher-args="--devices $U --cpus 96-103" -- "${OPTS[@]}" --ingest nvcomp > $R/dataset/$arm.console 2>&1
  echo "dataset $arm rc=$? $(grep -o '"verdict": "[A-Z]*"' $AS/status.json 2>/dev/null | head -1)"
done
$PY $CMP $R/dataset/base/merged $R/dataset/cand/merged
echo "-- merged inventory"; diff <(cd $R/dataset/base/merged && find . -type f | sort) <(cd $R/dataset/cand/merged && find . -type f | sort) && echo "inventory identical"
echo "-- merged logfile.pdf pages"; $PY $EV/pagecmp.py cmp $R/dataset/base/merged/logfile.pdf $R/dataset/cand/merged/logfile.pdf
echo "end $(date -Is)"
