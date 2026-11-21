#!/bin/bash
# Extract only the retained main-CPU `cpu-none` published sums (read-only source) and verify each against the retained sidecar's whole-file sha256.
# Output: $C1_SCR/census-ref-cpu/<movie>/cpu-none/output/movie.mrc. Exit 0 only when exactly 100 verified movies exist.
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
R=/mnt/clathrin/alex-motioncorr-km-truth/retained-cpu-products; D=$C1_SCR/census-ref-cpu
[ -e "$D" ] && { echo "$D exists; refusing to reuse"; exit 4; }
mkdir -p "$D" || exit 2
n=0
for f in "$R"/*.tar.zst; do
  m=$(basename "$f" .tar.zst); o=$D/$m/cpu-none/output; mkdir -p "$o" || exit 2
  zstd -dc "$f" | tar -x -C "$o" --wildcards "results/$m/cpu-none/output/movie.mrc" --strip-components=4 || { echo "extract failed $m"; exit 3; }
  [ -s "$o/movie.mrc" ] || { echo "missing $m"; exit 4; }
  want=$($C1_PY -c "import json,sys;print(json.load(open(sys.argv[1]))['files']['results/'+sys.argv[2]+'/cpu-none/output/movie.mrc'])" "$f.json" "$m") || exit 5
  got=$(sha256sum "$o/movie.mrc" | cut -c1-64)
  [ "$want" = "$got" ] || { echo "sidecar hash mismatch $m"; exit 6; }
  n=$((n+1))
done
echo "extracted and verified $n"
[ "$n" = 100 ] || exit 7
