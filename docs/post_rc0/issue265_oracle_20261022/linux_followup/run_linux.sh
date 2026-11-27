#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# The single frozen launch of the #265 oracle follow-up on Linux (CPU only, CPU 16).
# Runs the original 11-fixture table and then the labelled subnormal follow-up table, sequentially,
# one execution each, no retry. Harness exit 0 only means the harness completed; it is not a verdict.
# usage: taskset -c 16 run_linux.sh <scratch-dir> <frozen-protocol-commit-sha>
set -u
W=$1; FROZEN_SHA=$2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C
R=$W/receipt; mkdir -p "$R"
[ -e "$R/launched" ] && { echo "already launched: no retry"; exit 95; }
exec 9>/tmp/motioncorr-star265-cpu16.lock
flock -n 9 || { echo "CPU16 LOCK CONTENTION: stop"; exit 91; }
date -u +%FT%TZ > "$R/launched"
echo "$FROZEN_SHA" > "$R/frozen_protocol_commit.txt"
{ echo "start $(date -u +%FT%TZ)"; hostname; uptime; echo "affinity: $(taskset -cp $$)"; grep Cpus_allowed_list /proc/self/status
  echo "locale: LC_ALL=$LC_ALL"; locale 2>&1 | head -3
  echo "--- processes whose last CPU is 16 (before):"; ps -eo user:12,pid,psr,pcpu,args | awk '$3==16' | cut -c1-160
  echo "--- GPU/motioncorr processes are not touched; nothing is queried from GPUs"; df -h /mnt/clathrin | tail -1; } > "$R/host_before.txt" 2>&1
# Frozen hash check: refuse to run on any mismatch (UNRUN, not a failure of the experiment).
sha256sum -c "$W/expected_hashes.txt" > "$R/hash_check.txt" 2>&1 || { echo "HASH MISMATCH: UNRUN"; echo 96 > "$R/exit_hashcheck"; exit 96; }
BIN=$W/bin/roundtrip_oracle_linux
{ echo "argv A: $BIN $W/inputs/fixtures.txt $W/out_main"; echo "argv B: $BIN $W/inputs/fixtures_followup_subnormal.txt $W/out_followup"; } > "$R/argv.txt"
"$BIN" "$W/inputs/fixtures.txt" "$W/out_main" > "$R/stdout_main.txt" 2> "$R/stderr_main.txt"; echo $? > "$R/exit_main.txt"
"$BIN" "$W/inputs/fixtures_followup_subnormal.txt" "$W/out_followup" > "$R/stdout_followup.txt" 2> "$R/stderr_followup.txt"; echo $? > "$R/exit_followup.txt"
{ echo "end $(date -u +%FT%TZ)"; echo "--- processes whose last CPU is 16 (after):"; ps -eo user:12,pid,psr,pcpu,args | awk '$3==16' | cut -c1-160; } > "$R/host_after.txt" 2>&1
sha256sum -c "$W/expected_hashes.txt" > "$R/hash_check_after.txt" 2>&1; echo $? > "$R/exit_hashcheck_after.txt"
du -sk "$W" > "$R/scratch_kib.txt"
touch "$R/done"
cat "$R/exit_main.txt" "$R/exit_followup.txt"
