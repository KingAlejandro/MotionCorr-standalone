#!/bin/bash
# Stage an isolated working directory so neither arm writes into the shared
# tutorial tree that other sessions are using. Movies/ is a symlink, so both
# arms read the identical bytes through the identical page cache.
set -euo pipefail

ROOT=/home/alex/mc3-compare
TUT=/home/alex/MotionCorr-standalone/relion30_tutorial
WORK="$ROOT/work"

mkdir -p "$WORK/logs"
ln -sfn "$TUT/Movies" "$WORK/Movies"
cp -f "$TUT/movies.star" "$WORK/movies.star"

cd "$WORK"
echo "== inputs"
sha256sum movies.star
sha256sum Movies/gain.mrc
ls Movies/*.tiff | wc -l
( cd Movies && sha256sum --ignore-missing -c SHA256SUMS.txt 2>&1 | grep -c ': OK$' ) || true
ls Movies/*.tiff | sed 's#.*/##; s#\.tiff$##' > "$WORK/movie_bases.txt"
wc -l < "$WORK/movie_bases.txt"
echo "== ghostscript: $(which gs || echo absent)"
