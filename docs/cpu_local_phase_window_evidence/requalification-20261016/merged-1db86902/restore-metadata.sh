#!/bin/bash
set -eu
cd /home/ubuntu/fix183-20261016
for spec in candidate:e48b59ca2e6070ba6ac53e5fd4161e18b978219c base-178:1db869025507ac801845b4001b84e6bc0e77a645; do
 dir=${spec%%:*}; rev=${spec#*:}
 git -C "$dir" init
 git -C "$dir" fetch --depth=1 https://github.com/KingAlejandro/MotionCorr-standalone.git "$rev"
 git -C "$dir" reset --mixed FETCH_HEAD
 git -C "$dir" rev-parse HEAD
 git -C "$dir" status --short
 done
