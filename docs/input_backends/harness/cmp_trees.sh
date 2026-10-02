#!/bin/bash
# Compare two product trees, declaring the log lines a route change is allowed
# to add. Those prefixes are dropped from BOTH arms, so the allowance cannot
# hide a product difference -- only a line whose presence is the route itself.
set -u
W=/home/alex/mc-inputs-20261002
PY=$HOME/.mc-venv/bin/python
ALLOW=(--allow-added-log-line "nvCOMP ingestion"
       --allow-added-log-line "Staging this movie as native unsigned"
       --allow-added-log-line "Released native uint"
       --allow-added-log-line "Materialized native uint")
LABEL=$1; A=$2; B=$3; MANIFEST=$4; STAR=$5
out=$($PY $W/tools/compare_output_trees.py "$A" "$B" --manifest "$MANIFEST" \
        --input-star "$STAR" "${ALLOW[@]}" 2>&1); rc=$?
if [ $rc -eq 0 ]; then
  echo "CMP $LABEL PASS  $(echo "$out" | grep -o 'Validated.*pixels per arm')"
else
  echo "CMP $LABEL FAIL"; echo "$out" | tail -8 | sed 's/^/      /'
fi
