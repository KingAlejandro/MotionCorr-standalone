#!/bin/bash
# Witness the route an MRC movie takes. The code says float -- the compact gate
# requires a "tif" file format and the nvCOMP gate opens the file with
# TIFFOpen -- and this is that statement checked at runtime rather than read.
set -u
W=/home/alex/mc-inputs-20261002
S=$W/src-u8b/test-data/synthetic
GPU=$1
out=$W/results/mrc_route
rm -rf "$out"; mkdir -p "$out"
cd "$S" || exit 1
taskset -c 96-103 $W/bld-u8c/motioncorr --i synthetic_fallback.star --o "$out/" \
  --use_own --patch_x 1 --patch_y 1 --j 4 --gpu "$GPU" \
  --ingest_witness "$out.witness" > "$out.stdout" 2>&1
echo "MRCROUTE rc=$? witness=[$(cat "$out.witness" 2>/dev/null | tr '\n' ' ')]"
rm -rf "$out" "$out.stdout" "$out.witness"
