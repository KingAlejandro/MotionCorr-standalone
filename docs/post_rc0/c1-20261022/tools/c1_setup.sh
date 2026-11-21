#!/bin/bash
# Fresh scratch + exact source checkout (real .git; CiFailClosedControls needs it) + hashed git archive.
# Inputs already copied to $C1_SCR/in/: thin.bundle (origin/main..C1), prs.bundle (PR heads, for the expected-union derivation).
set -eu
source "$(dirname "$0")/c1_env.sh"
cd "$C1_SCR"
[ -d src/.git ] && { echo "src exists; refusing to reuse"; exit 4; }
git init -q src
git -C src fetch -q --no-tags https://github.com/KingAlejandro/MotionCorr-standalone.git +refs/heads/main:refs/remotes/origin/main
git -C src cat-file -e 3691374061f782bc84531fd1c79d017ddcb5a7c2
git -C src fetch -q --no-tags "$C1_SCR/in/thin.bundle" +integration/c1-20261022:refs/heads/c1
git -C src checkout -q c1
[ "$(git -C src rev-parse HEAD)" = "$C1_SHA" ] || { echo "HEAD != C1_SHA"; exit 91; }
[ -z "$(git -C src status --porcelain)" ] || { echo "dirty"; exit 92; }
git -C src fetch -q --no-tags "$C1_SCR/in/prs.bundle" '+refs/c1/*:refs/c1/*'
git -C src archive --format=tar HEAD > source.tar
sha256sum source.tar > source.tar.sha256
(cd src && git ls-files -z | xargs -0 sha256sum) > source-files.sha256
wc -l source-files.sha256
{ echo "main=$(git -C src rev-parse origin/main)"; for r in $(git -C src for-each-ref --format='%(refname)' refs/c1); do echo "$r $(git -C src rev-parse $r)"; done; } > refs.txt
{ hostname; date -u; uname -a; gcc --version | head -1; nvcc --version | tail -2; cmake --version | head -1
  $C1_PY -c 'import sys,numpy;print(sys.version.split()[0],numpy.__version__)'; nvidia-smi --query-gpu=index,uuid,name,driver_version --format=csv,noheader
  sha256sum $C1_NVCOMP/lib/libnvcomp.so.5.3.0.16; cat /sys/kernel/mm/transparent_hugepage/enabled; ps -eo pid,etimes,args | grep -c '[c]c1plus'; } > toolchain.txt 2>&1
echo SETUP_OK
