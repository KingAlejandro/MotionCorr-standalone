#!/bin/bash
set -eu
cd /home/ubuntu/fix183-20261016
for spec in candidate:7c453e5ef54816f0eacdbdf532f133e284e49ac1 base:d7171b810dc97003784339d7bad1c279903f3bba; do
 dir=${spec%%:*}; rev=${spec#*:}
 git -C "$dir" init
 git -C "$dir" fetch --depth=1 https://github.com/KingAlejandro/MotionCorr-standalone.git "$rev"
 git -C "$dir" reset --mixed FETCH_HEAD
 git -C "$dir" rev-parse HEAD
 git -C "$dir" status --short
 done
