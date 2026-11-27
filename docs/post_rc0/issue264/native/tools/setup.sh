#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# One-time source setup from a git bundle: candidate, base and three TEST-ONLY overlay trees.
# usage: G_SCR=... G_SHA=... setup.sh BUNDLE BUNDLE_SHA256    (refuses an existing tree)
set -u
source "$(dirname "$0")/lane.sh" || exit 1
bundle=$1; want=$2
[ "$(sha256sum "$bundle" | cut -c1-64)" = "$want" ] || { echo "bundle hash mismatch"; exit 2; }
cd "$G_SCR" || exit 2
for t in src-cand src-base src-ov-base src-ov-cand src-ov-mut; do [ -e $t ] && { echo "$t exists"; exit 4; }; done
clone() { git clone -q --no-checkout "$bundle" "$1" && git -C "$1" checkout -q --detach "$2" && [ "$(git -C "$1" rev-parse HEAD)" = "$2" ]; }
clone src-cand $G_SHA && clone src-base $G_BASE && clone src-ov-base $G_BASE && clone src-ov-cand $G_SHA && clone src-ov-mut $G_SHA || exit 3
P=$G_SCR/src-cand/docs/post_rc0/issue264/native/n3_observation_overlay.patch
# Deliberate N4 mutant: the uncentred domain (same replacement as verify_host.py), then the overlay.
python3 - "$G_SCR/src-ov-mut/src/local_motion_guard.h" <<'PY' || exit 3
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text(); assert s.count(' - Real(0.5)') == 4; p.write_text(s.replace(' - Real(0.5)', ''))
PY
for t in src-ov-base src-ov-cand src-ov-mut; do (cd $t && patch -p1 --no-backup-if-mismatch < "$P") || exit 3; done
for t in src-cand src-base src-ov-base src-ov-cand src-ov-mut; do
  echo "$t HEAD=$(git -C $t rev-parse HEAD) diff_sha256=$(git -C $t diff | sha256sum | cut -c1-64) status_lines=$(git -C $t status --porcelain | wc -l)" \
    "runner=$(sha256sum $t/src/motioncorr_runner.cpp | cut -c1-64) helper=$( [ -e $t/src/local_motion_guard.h ] && sha256sum $t/src/local_motion_guard.h | cut -c1-64 || echo absent)"
done | tee "$G_SCR/SOURCES.txt"
