#!/bin/bash
# usage: run_nc_all.sh   (on cpu64) Render the movies, run the 128 native runs, score. Fresh scratch $DS_SC/nc each time.
set -u
D=$(dirname "$(readlink -f "$0")"); source "$D/env.sh" || exit 1
NC=$DS_SC/nc; S=$DS_SC/src-h5; BIN=$DS_SC/build-h5on/motioncorr
{ echo "date $(date -u +%FT%TZ) host $(hostname)"; echo "h5 $DS_CAND_SHA"; sha256sum $BIN; lane grep Cpus_allowed_list /proc/self/status
  ps -eo psr,pcpu,pid,comm --no-headers | awk '$1>=48 && $1<=55 && $2>5' | sed 's/^/busy-before: /'; } > $DS_SC/nc-env.txt 2>&1
mkdir -p $NC
lane $DS_PY $D/render_ncontrols.py $NC/movies $S > $DS_SC/nc-render.out 2>&1; echo "render rc=$?"
lane $DS_PY -I $D/run_ncontrols.py $NC $BIN $DS_CPUS > $DS_SC/nc-run.out 2>&1; echo "run rc=$?"
lane $DS_PY -I $D/score_ncontrols.py $NC $S $DS_SC/w6.json $DS_SC/nc-scores > $DS_SC/nc-score.out 2>&1; echo "score rc=$?"
