#!/bin/bash
# usage (on the laptop, repo root): stage_tree.sh NAME COMMIT [HOST]
# Stages `git archive COMMIT` into $SC/src-NAME on HOST (default cpu64), initialises a git repo over it AFTER recording the tree manifest
# (the fail-closed CTest controls need git metadata), and writes stage_records/NAME.json with: commit, git tree sha, sha256 of the archive stream,
# sha256 of the staged-file manifest (sorted sha256sum lines, .git excluded). Review finding F6: every binary used from now on is tied to such a record
# by record_binaries.sh, which recomputes the manifest right after the build.
set -eu
NAME=$1; COMMIT=$2; HOST=${3:-cpu64}; SC=/tmp/motioncorr-damping-a1c78adc1d0f
DIR=$(cd "$(dirname "$0")" && pwd); REC=$DIR/../stage_records; mkdir -p "$REC"
FULL=$(git rev-parse "$COMMIT"); TREE=$(git rev-parse "$COMMIT^{tree}")
ssh "$HOST" "rm -rf $SC/src-$NAME; mkdir -p $SC/src-$NAME"
TMPA=$(mktemp); git archive "$COMMIT" > "$TMPA"
ARCH=$(shasum -a 256 "$TMPA" | cut -d' ' -f1)
ssh "$HOST" "tar -x -C $SC/src-$NAME" < "$TMPA"; rm -f "$TMPA"
MAN=$(ssh "$HOST" "cd $SC/src-$NAME && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1; find . -type f | wc -l")
MANSHA=$(echo "$MAN" | sed -n 1p); NFILES=$(echo "$MAN" | sed -n 2p)
ssh "$HOST" "cd $SC/src-$NAME && git init -q . && git add -A && git -c user.name=stage -c user.email=stage@invalid commit -q -m 'staged $FULL' && git status --porcelain | wc -l" > /dev/null
cat > "$REC/$NAME.json" <<JSON
{"name": "$NAME", "commit": "$FULL", "git_tree": "$TREE", "git_archive_stream_sha256": "$ARCH", "staged_manifest_sha256": "$MANSHA", "staged_files": $NFILES, "host": "$HOST", "staged_dir": "$SC/src-$NAME", "staged_at_utc": "$(date -u +%FT%TZ)"}
JSON
cat "$REC/$NAME.json"
