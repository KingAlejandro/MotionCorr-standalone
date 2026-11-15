#!/bin/bash
# usage (on cpu64, after the build): record_binaries.sh NAME [BUILD_DIR ...]
# Recomputes the staged-file manifest (must equal stage_records/NAME.json's staged_manifest_sha256, else the tree changed between staging and build)
# and records the sha256 of each binary plus the CMake build type and compile flags: $DS_SC/stage-NAME-binaries.json
set -u
NAME=$1; shift; SC=/tmp/motioncorr-damping-a1c78adc1d0f
MAN=$(cd $SC/src-$NAME && find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
{
  echo "{\"name\": \"$NAME\", \"manifest_recomputed_after_build_sha256\": \"$MAN\", \"binaries\": ["
  first=1
  for b in "$@"; do
    [ $first -eq 1 ] || echo ","; first=0
    echo "{\"build_dir\": \"$b\", \"motioncorr_sha256\": \"$(sha256sum $SC/$b/motioncorr | cut -d' ' -f1)\", \"build_type\": \"$(grep -h CMAKE_BUILD_TYPE: $SC/$b/CMakeCache.txt | cut -d= -f2)\", \"hook\": \"$(grep -h MC_EXPERIMENT_CCF_DC: $SC/$b/CMakeCache.txt | cut -d= -f2)\", \"flags\": \"$(grep -h -- '-O3' $SC/$b/CMakeFiles/motioncorr.dir/flags.make | head -1 | sed 's/\"/\x27/g')\"}"
  done
  echo "]}"
} > $SC/stage-$NAME-binaries.json
cat $SC/stage-$NAME-binaries.json
