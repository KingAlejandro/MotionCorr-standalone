#!/bin/bash
# run_dataset.py endpoint, 4 movies, one worker, base vs candidate. Output only; no timing claim.
# Run under: flock -w 7200 /tmp/motioncorr-bench.lock taskset -c 96-103 bash dataset.sh
# Both arms use the same --out path (shifts EPS draw their own path), then the tree is moved and
# .star/.lst/.json are rewritten to the new root, as in correct.sh.
set -u
W=/home/alex/mc-small/lfe; D=/home/alex/mc-small/data96; EV=$W/ev
CMP=$W/src-cand/docs/perf_integration/identity/cmp_trees.py; PY=/home/alex/.mc-venv/bin/python
U=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54
R=$W/runs/dataset2; rm -rf $R; mkdir -p $R
OPTS=(--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8)
{ grep -v 'tiff 1$' $D/movies12_fixed116.star; grep 'tiff 1$' $D/movies12_fixed116.star | head -4; } > $R/movies4.star
cd $D
for arm in base cand; do
  AS=$R/as_run; rm -rf $AS
  taskset -c 96-103 $PY $W/src-$arm/tools/multi_gpu/run_dataset.py --binary $W/build-$arm/motioncorr --star $R/movies4.star \
    --out $AS --required-products .mrc,.star --launcher-args="--devices $U --cpus 96-103" -- "${OPTS[@]}" --ingest nvcomp > $R/$arm.console 2>&1
  echo "dataset $arm rc=$? $(grep -o '"verdict": "[A-Z]*"' $AS/status.json 2>/dev/null | head -1)"
  mv $AS $R/$arm
  find $R/$arm \( -name '*.star' -o -name '*.lst' -o -name '*.json' \) -exec sed -i "s#$AS#$R/$arm#g" {} +
done
echo "-- merged products (cmp_trees.py)"; $PY $CMP $R/base/merged $R/cand/merged
echo "-- merged inventory"; diff <(cd $R/base/merged && find . -type f | sort) <(cd $R/cand/merged && find . -type f | sort) && echo "inventory identical"
echo "-- merged logfile.pdf pages"; $PY $EV/pagecmp.py cmp $R/base/merged/logfile.pdf $R/cand/merged/logfile.pdf
echo "-- worker trees: any logfile.pdf rendered by workers?"; for arm in base cand; do echo "$arm: $(find $R/$arm/workers -name logfile.pdf | wc -l) worker logfile.pdf, $(find $R/$arm/workers -name 'all_batches.pdf' | wc -l) all_batches.pdf"; done
echo "end $(date -Is)"
