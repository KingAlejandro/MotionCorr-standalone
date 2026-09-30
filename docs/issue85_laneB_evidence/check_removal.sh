#!/bin/bash
# Verify the lane B removal recipe: after the deletions and reverts in the
# design note, the tree must be byte-identical to origin/main. A "removable
# experiment" whose removal leaves a permanent refactor behind is not one.
set -eu
REPO=${1:-$(git rev-parse --show-toplevel)}
BASE=${2:-origin/main}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$REPO" archive HEAD | (mkdir -p "$TMP/after" && tar -x -C "$TMP/after")
git -C "$REPO" archive "$BASE" | (mkdir -p "$TMP/base" && tar -x -C "$TMP/base")

cd "$TMP/after"
rm -f src/tiff_movie_reader.h src/tiff_movie_reader.cpp src/rwTIFF_layout.h \
      src/apps/tiff_reader_bench.cpp tests/test_tiff_persistent_reader.cpp \
      agents/designs/issue_85_laneB_persistent_tiff_readers.md
rm -rf docs/issue85_laneB_evidence
for f in src/rwTIFF.h src/image.h CMakeLists.txt src/motioncorr_runner.cpp src/motioncorr_runner.h; do
    git -C "$REPO" show "$BASE:$f" > "$f"
done

if diff -rq "$TMP/base" "$TMP/after"; then
    echo "REMOVAL CLEAN: byte-identical to $BASE"
else
    echo "REMOVAL INCOMPLETE: the differences above survive the recipe"
    exit 1
fi
