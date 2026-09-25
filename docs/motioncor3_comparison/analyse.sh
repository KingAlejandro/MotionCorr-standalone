#!/bin/bash
# Post-run analysis. NOT a measurement: runs unlocked and niced so it cannot
# contend with anyone else's timed series.
set -uo pipefail
ROOT=/home/alex/mc3-compare
W="$ROOT/work"
PY="$ROOT/venv/bin/python3"

echo "### matched arm (-Bft 150 150)"
nice -n 15 taskset -c 96-103 "$PY" "$ROOT/compare_mc3_vs_motioncorr.py" \
  --motioncorr-dir "$W/out-motioncorr" --mc3-dir "$W/out-mc3" \
  --mc3-logdir "$W/log-mc3" --movies "$W/movie_bases.txt" \
  --angpix 0.885 --crop 2048 --json-out "$W/compare_matched.json" | tail -60

echo; echo "### B-factor sensitivity arm (MotionCor3 default -Bft 500 100)"
nice -n 15 taskset -c 96-103 "$PY" "$ROOT/compare_mc3_vs_motioncorr.py" \
  --motioncorr-dir "$W/out-motioncorr" --mc3-dir "$W/out-mc3-bftdef" \
  --mc3-logdir "$W/log-mc3-bftdef" --movies "$W/movie_bases.txt" \
  --angpix 0.885 --crop 2048 --json-out "$W/compare_bftdefault.json" | tail -40

echo; echo "### log scrape (fallbacks that would invalidate the comparison)"
nice -n 15 "$PY" "$ROOT/scrape_logs.py" "$W/out-motioncorr" "$W/log-mc3" "$W/scrape.json"

echo; echo "### output manifest"
{
  echo "# MotionCorr arm"
  ( cd "$W/out-motioncorr" && find . -type f | sort | while read -r f; do
      printf "%s  %s  %s\n" "$(sha256sum "$f" | cut -c1-16)" "$(stat -c%s "$f")" "$f"; done )
  echo "# MotionCor3 arm"
  ( cd "$W/out-mc3" && find . -type f | sort | while read -r f; do
      printf "%s  %s  %s\n" "$(sha256sum "$f" | cut -c1-16)" "$(stat -c%s "$f")" "$f"; done )
  echo "# MotionCor3 logs"
  ( cd "$W/log-mc3" && find . -type f | sort | while read -r f; do
      printf "%s  %s  %s\n" "$(sha256sum "$f" | cut -c1-16)" "$(stat -c%s "$f")" "$f"; done )
} > "$W/output_manifest.txt"
wc -l < "$W/output_manifest.txt"
