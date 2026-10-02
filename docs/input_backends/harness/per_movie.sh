#!/bin/bash
# Per-movie wall from the runner's own log, separated from process startup.
# A 6-movie run on this geometry is startup-dominated: the CUDA context and
# first-use module loading land inside movie 1, so a process wall divided by
# six is not a per-movie cost.
set -u
W=/home/alex/mc-inputs-20261002
printf '%-6s %-24s %8s %8s %8s %8s\n' arm variant first_s rest_med rest_min rest_max
for d in "$@"; do
  arm=$(basename "$d" | sed -E 's/^p4_([a-z]+)__.*/\1/')
  var=$(basename "$d" | sed -E 's/^p4_[a-z]+__//')
  ts=$(grep -h "Full movie wall time" "$d"/Movies/*.log 2>/dev/null | grep -oP '[0-9.]+(?= s)')
  [ -z "$ts" ] && continue
  first=$(echo "$ts" | head -1)
  rest=$(echo "$ts" | tail -n +2 | sort -n)
  n=$(echo "$rest" | wc -l)
  med=$(echo "$rest" | awk -v n=$n 'NR==int((n+1)/2)')
  printf '%-6s %-24s %8s %8s %8s %8s\n' "$arm" "$var" "$first" "$med" \
    "$(echo "$rest" | head -1)" "$(echo "$rest" | tail -1)"
done
