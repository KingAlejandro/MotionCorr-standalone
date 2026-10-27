#!/bin/bash
# Local: stream the exact git archive of the pinned commit to a fresh cpu64 namespace and verify every file against the git blob list. Refuses an existing namespace.
set -eu
SRC=f473fbc9c380c7bb8cc1533f19461fbf70dde485; ROOT=/tmp/motioncorr-lfw-capture-20261027
REPO=/Users/alex.konstantinov/.t3/worktrees/MotionCorr/experiment-local-full-width-weight-20261026; PREP=$REPO/docs/post_rc0/s1/local_full_width_capture_20261027/release_prep/scripts
SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes cpu64"
$SSH "test ! -e $ROOT && mkdir $ROOT && mkdir $ROOT/receipts $ROOT/prep"
cd $REPO; git ls-tree -r $SRC > /tmp/source.blobs; shasum -a 256 /tmp/source.blobs
git archive --prefix=source/ $SRC | $SSH "tar -x -C $ROOT"
git archive $SRC --format=tar | shasum -a 256 | sed 's/-$/git-archive-tar-no-prefix/'
cat /tmp/source.blobs | $SSH "cat > $ROOT/prep/source.blobs"
(cd $PREP && tar -c --no-xattrs --no-mac-metadata -f - lane.py guard.py verify_source.py build_fw.sh tests_fw.sh weight_oracle.py weight_control.cpp build_control.sh 2>/dev/null || COPYFILE_DISABLE=1 tar -c -f - lane.py guard.py verify_source.py build_fw.sh tests_fw.sh weight_oracle.py weight_control.cpp build_control.sh) | $SSH "tar -x -C $ROOT/prep"
$SSH "cd $ROOT && find prep -name '._*' | wc -l && python3 -B prep/verify_source.py source prep/source.blobs && sha256sum prep/* | tee receipts/prep_sha256.txt | cut -c1-80"
