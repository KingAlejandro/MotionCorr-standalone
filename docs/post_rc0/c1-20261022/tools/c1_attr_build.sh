#!/bin/bash
# Attribution-arm builds for T24 (CUDA+nvCOMP, Release, tests off, target motioncorr only). usage: c1_attr_build.sh N|only254|only260|only270
#   N        = C1 merges #267..#270 only (commit 21093fe9: numerics #254+#260+#270, no D2/D3, no independent fixes)
#   onlyNNN  = main + that PR head alone (tree already extracted by c1_expected_union.py under eu/prNNN/src)
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
arm=$1; A=$C1_SCR/attr/$arm
mkdir -p $A/src
case $arm in
  N) git -C $C1_SCR/src archive 21093fe9 | tar -x -C $A/src; echo "21093fe9" > $A/SOURCE;;
  only254|only260|only270) n=${arm#only}; cp -a $C1_SCR/eu/pr$n/src/. $A/src/; git -C $C1_SCR/src rev-parse refs/c1/pr$n > $A/SOURCE;;
  *) echo unknown; exit 2;;
esac
(cd $A/src && find . -type f -print0 | sort -z | xargs -0 sha256sum) > $A/source-files.sha256
CFG=nvcomp "$(dirname "$0")/c1_build.sh" $A/src $A/build motioncorr -DBUILD_TESTING=OFF
