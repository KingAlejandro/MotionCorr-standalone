#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Stage C loader preflight (prepared for the parent's admission; NOT run by the driver, NOT run in the draft). For each given
# binary (the three motioncorr builds and the two oracles) print `ldd` under the exact environment the Stage C driver passes to
# its children (the allowlist PATH, HOME, LANG, LC_ALL, LC_CTYPE, TMPDIR, USER, LOGNAME; everything else, including
# LD_LIBRARY_PATH and LD_PRELOAD, dropped) and under the full inherited environment (what Stage B and the retained producer
# calls used), with the sha256 of every resolved library, and say whether the two resolutions match.
# Usage: stageC_ldd_preflight.sh BINARY...      Exit: 0 all match; 14 ldd failed; 15 an unresolved library; 17 the resolutions differ.
set -u -o pipefail
[ "$#" -ge 1 ] || { echo "usage: $0 BINARY..." >&2; exit 14; }
tmp=$(mktemp -d) || exit 14
trap 'rm -rf "$tmp"' EXIT
scrub() {  # same variable set as ENV_ALLOW in ccf_dc_stagec_driver.py
  local out=() v
  for v in PATH HOME LANG LC_ALL LC_CTYPE TMPDIR USER LOGNAME; do
    [ -n "${!v+x}" ] && out+=("$v=${!v}")
  done
  env -i "${out[@]}" "$@"
}
norm() { sed -E 's/ \(0x[0-9a-f]+\)$//' "$1" | LC_ALL=C sort; }
rc=0
for b in "$@"; do
  echo "== $b"
  [ -f "$b" ] || { echo "STOP: not a file"; exit 14; }
  scrub ldd "$b" > "$tmp/scrub.raw" 2> "$tmp/scrub.err" || { echo "STOP: ldd failed under the scrubbed environment: $(cat "$tmp/scrub.err")"; exit 14; }
  ldd "$b" > "$tmp/full.raw" 2> "$tmp/full.err" || { echo "STOP: ldd failed under the full environment: $(cat "$tmp/full.err")"; exit 14; }
  grep -q 'not found' "$tmp/scrub.raw" "$tmp/full.raw" && { echo "STOP: unresolved library"; grep 'not found' "$tmp/scrub.raw" "$tmp/full.raw"; exit 15; }
  norm "$tmp/scrub.raw" > "$tmp/scrub.n"; norm "$tmp/full.raw" > "$tmp/full.n"
  echo "-- scrubbed environment:"; cat "$tmp/scrub.n"
  echo "-- full environment:"; cat "$tmp/full.n"
  echo "-- sha256 of the libraries resolved under the scrubbed environment:"
  awk '/=>/ && $3 ~ /^\// {print $3}' "$tmp/scrub.n" | while read -r lib; do sha256sum "$lib"; done
  if cmp -s "$tmp/scrub.n" "$tmp/full.n"; then echo "LDD_MATCH $b"; else echo "LDD_DIFFERS $b"; diff "$tmp/scrub.n" "$tmp/full.n"; rc=17; fi
done
exit $rc
