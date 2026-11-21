#!/bin/bash
# CPU startup only; launch once after the parent creates chain-cpu1d.go.
# Overrides are for retained harmless controls. Real launch uses these defaults.
set -euo pipefail
set -C
SC=${CPU1D_SC:-/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb}
L=${CPU1D_LAUNCH_DIR:-$SC/logs/launch-cpu1d-attempt1}
LOCK=${CPU1D_LOCK:-/tmp/motioncorr-c1-cpu8-9.lock}
CHAIN=${CPU1D_CHAIN:-$SC/chain-cpu1d.sh}
OUT=${CPU1D_CHAIN_OUT:-$SC/logs/chain-cpu1d.out}
# Atomic invocation reservation comes first; never reuse even a failed attempt.
mkdir "$L" || { echo "invocation already reserved or cannot reserve: $L" >&2; exit 4; }
finish() {
  rc=$?
  trap - EXIT
  if [ -n "${child:-}" ] && [ ! -e "$L/chain.exit" ]; then
    # On a receipt failure before release, the handshake self-expires in 5 s.
    set +e
    wait "$child"
    child_rc=$?
    printf '%s\n' "$child_rc" > "$L/chain.exit"
    date -u +%FT%TZ > "$L/chain.reaped"
  fi
  printf '%s\n' "$rc" > "$L/wrapper.exit"
  date -u +%FT%TZ > "$L/wrapper.finished"
  exit "$rc"
}
trap finish EXIT
identity() {
  local pid=$1 dest=$2
  printf '%s\n' "$pid" > "$dest.pid"
  date -u +%FT%TZ > "$dest.started"
  cat "/proc/$pid/stat" > "$dest.proc-stat"
  cat "/proc/$pid/status" > "$dest.proc-status"
  cat "/proc/$pid/cmdline" > "$dest.argv.nul"
  awk '/^Uid:/{print $2}' "/proc/$pid/status" > "$dest.uid"
  awk '/^Cpus_allowed_list:/{print $2}' "/proc/$pid/status" > "$dest.cpus"
}
identity $$ "$L/wrapper"
printf '%q ' "$0" "$@" > "$L/wrapper.argv"
printf '\n' >> "$L/wrapper.argv"
printf 'SC=%q\nLOCK=%q\nCHAIN=%q\nOUT=%q\n' "$SC" "$LOCK" "$CHAIN" "$OUT" > "$L/config"
[ "$(cat "$L/wrapper.cpus")" = 8-9 ] || { echo "affinity must be 8-9" > "$L/affinity.error"; exit 8; }
# Append-open works on an existing lease under noclobber. Distinguish open errors.
exec 9>>"$LOCK" || { echo "cannot open lease" > "$L/lease.error"; exit 8; }
if ! flock -n 9; then echo "CPU lease contended" > "$L/lease.contended"; exit 7; fi
date -u +%FT%TZ > "$L/lease.acquired"
[ -f "$SC/logs/chain-cpu1d.go" ] || { echo "parent GO file absent" > "$L/go.absent"; exit 9; }
# Child waits behind a private handshake so /proc identity is captured before exec.
# FD 9 is inherited; lease remains held until the entire synchronous chain reaps.
bash -c 'for ((i=0;i<100;i++)); do if [ -f "$1/child.release" ]; then exec bash "$2"; fi; sleep 0.05; done; exit 8' _ "$L" "$CHAIN" > "$OUT" 2>&1 &
child=$!
identity "$child" "$L/chain"
printf '%q ' bash "$CHAIN" > "$L/chain.argv"
printf '\n' >> "$L/chain.argv"
date -u +%FT%TZ > "$L/child.release"
set +e
wait "$child"
rc=$?
set -e
printf '%s\n' "$rc" > "$L/chain.exit"
date -u +%FT%TZ > "$L/chain.reaped"
exit "$rc"
