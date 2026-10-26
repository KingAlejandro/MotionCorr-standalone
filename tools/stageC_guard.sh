#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Stage C resource guard (amendment 1: fails closed). The Stage A/B guard rules, with every required read made mandatory:
# a command that fails, or output that is empty, malformed or non-finite, ends the guard with a non-zero code; it never
# passes on missing data. Usage: stageC_guard.sh LABEL NEED_GPU(0|1)
# Environment (required): STAGEC_GPU2 (exact UUID), STAGEC_FOREIGN_PID, STAGEC_SCRATCH. Real runs also set STAGEC_REAL=1.
# Exit: 0 pass; 11 other compute app on the granted GPU; 12 its utilisation > 50 %; 13 a core of 80-87 > 50 % busy;
#       14 a required command failed; 15 empty, malformed or non-finite data; 16 scratch accounting failure or above the
#       frozen 20 GiB cap; 20 a test hook is present where it is not allowed.
# Test hooks exist only with STAGEC_TEST_MODE=1: STAGEC_TEST_PROC_STAT_1/2 (fixtures replacing /proc/stat) and
# STAGEC_TEST_NO_SLEEP=1; command shims are ordinary PATH entries. With STAGEC_REAL=1 any STAGEC_TEST_* variable stops it.
set -u -o pipefail
CAP=21474836480                                   # frozen 20 GiB scratch cap
die() { echo "STOP guard: $2 ($(date -u +%FT%TZ))"; exit "$1"; }

label=${1:-}; need_gpu=${2:-}
case "$need_gpu" in 0|1) ;; *) die 15 "NEED_GPU must be 0 or 1";; esac
[ -n "$label" ] || die 15 "empty label"
if [ "${STAGEC_REAL:-0}" = 1 ] && env | grep -q '^STAGEC_TEST_'; then die 20 "test hook present in a real run"; fi
if [ "${STAGEC_TEST_MODE:-0}" != 1 ] && env | grep -q '^STAGEC_TEST_'; then die 20 "test hook without STAGEC_TEST_MODE=1"; fi
GPU2=${STAGEC_GPU2:-}; FOREIGN_PID=${STAGEC_FOREIGN_PID:-}; S=${STAGEC_SCRATCH:-}
echo "$GPU2" | grep -Eq '^GPU-[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$' || die 15 "STAGEC_GPU2 is not an exact GPU UUID"
echo "$FOREIGN_PID" | grep -Eq '^[0-9]+$' || die 15 "STAGEC_FOREIGN_PID is not numeric"
[ -d "$S" ] || die 16 "scratch directory missing"

tmp=$(mktemp -d) || die 14 "mktemp failed"
trap 'rm -rf "$tmp"' EXIT
run() {  # name command... : stdout and stderr kept; any failure stops with 14
  local name=$1; shift
  "$@" >"$tmp/$name.out" 2>"$tmp/$name.err" || die 14 "required command failed: $* (rc $?)"
}
numeric() { echo "$1" | grep -Eq '^[0-9]+$'; }

echo "== guard $label $(date -u +%FT%TZ)"

# --- GPU table: exact UUID exactly once, numeric memory and utilisation
run gpus nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits
[ -s "$tmp/gpus.out" ] || die 15 "empty GPU table"
awk -F', *' 'NF != 5 {bad = 1} END {exit bad}' "$tmp/gpus.out" || die 15 "malformed GPU table row"
row=$(awk -F', *' -v g="$GPU2" '$2 == g {n++; print $3, $4} END {if (n != 1) print "BAD"}' "$tmp/gpus.out" | tr '\n' ' ')
case "$row" in *BAD*|"") die 15 "granted GPU UUID not present exactly once";; esac
set -- $row; gmem=${1:-}; gutil=${2:-}
numeric "$gmem" && numeric "$gutil" && [ "$gutil" -le 100 ] || die 15 "granted GPU memory or utilisation is not a valid number"
cat "$tmp/gpus.out"

# --- compute apps: command must succeed; every line well formed (empty is a valid answer)
run apps nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory,process_name --format=csv,noheader
awk -F', ' 'NF > 0 && $0 != "" { if (NF < 4 || $1 !~ /^[0-9]+$/ || $2 !~ /^GPU-/ || $3 !~ /^[0-9]+ MiB$/) bad = 1 } END {exit bad}' "$tmp/apps.out" || die 15 "malformed compute-app line"
cat "$tmp/apps.out"

# --- CPU: two /proc/stat samples; cores 80-87 all present with valid fields and a positive delta
src1=/proc/stat; src2=/proc/stat
if [ "${STAGEC_TEST_MODE:-0}" = 1 ]; then src1=${STAGEC_TEST_PROC_STAT_1:-/proc/stat}; src2=${STAGEC_TEST_PROC_STAT_2:-/proc/stat}; fi
grep '^cpu[0-9]' "$src1" > "$tmp/stat1" 2>/dev/null || die 15 "no per-core rows in the first /proc/stat sample"
[ "${STAGEC_TEST_NO_SLEEP:-0}" = 1 ] || sleep 3
grep '^cpu[0-9]' "$src2" > "$tmp/stat2" 2>/dev/null || die 15 "no per-core rows in the second /proc/stat sample"
awk '
  NR == FNR { if (NF >= 9) {s1[$1] = 1; for (i = 2; i <= 9; i++) a[$1, i] = $i}; next }
  { if (NF >= 9) {s2[$1] = 1; for (i = 2; i <= 9; i++) b[$1, i] = $i} }
  END {
    for (n = 80; n <= 87; n++) {
      c = "cpu" n
      if (!(c in s1) || !(c in s2)) { print c, "MISSING"; continue }
      valid = 1
      for (i = 2; i <= 9; i++) if (a[c, i] !~ /^[0-9]+$/ || b[c, i] !~ /^[0-9]+$/) valid = 0
      if (!valid) { print c, "MALFORMED"; continue }
      u1 = a[c,2] + a[c,3] + a[c,4] + a[c,7] + a[c,8]; t1 = u1 + a[c,5] + a[c,6]
      u2 = b[c,2] + b[c,3] + b[c,4] + b[c,7] + b[c,8]; t2 = u2 + b[c,5] + b[c,6]
      dt = t2 - t1; du = u2 - u1
      if (dt <= 0 || du < 0) { print c, "BADDELTA"; continue }
      printf "%s %.0f\n", c, 100 * du / dt
    }
  }' "$tmp/stat1" "$tmp/stat2" > "$tmp/busy" || die 15 "CPU delta computation failed"
[ "$(wc -l < "$tmp/busy" | tr -d ' ')" = 8 ] || die 15 "expected eight cores 80-87"
awk '$2 !~ /^[0-9]+$/ {bad = 1} END {exit bad}' "$tmp/busy" || die 15 "a core of 80-87 has no valid sample: $(grep -E 'MISSING|MALFORMED|BADDELTA' "$tmp/busy" | tr '\n' ' ')"
echo "cpu80-87 busy%: $(tr '\n' ' ' < "$tmp/busy")"
maxbusy=$(awk '{if ($2 > m) m = $2} END {print m + 0}' "$tmp/busy")

# --- processes, scratch, memory
run ps ps -eo psr,stat,pcpu,user,pid,args --no-headers
[ -s "$tmp/ps.out" ] || die 15 "empty process list"
echo "processes currently running on cpu80-87:"; awk '$1 >= 80 && $1 <= 87 && $2 ~ /^R/' "$tmp/ps.out" | cut -c1-140
run df df -P -B1 "$S"
avail=$(awk 'NR == 2 {print $4}' "$tmp/df.out"); numeric "$avail" && [ "$avail" -gt 0 ] || die 16 "df available bytes missing or not numeric"
run du du -sb "$S"
used=$(awk 'NR == 1 {print $1}' "$tmp/du.out"); numeric "$used" || die 16 "scratch usage not numeric"
[ "$used" -le "$CAP" ] || die 16 "scratch use $used above the frozen 20 GiB cap"
[ "$avail" -ge $((CAP - used)) ] || die 16 "df available $avail below the room left under the 20 GiB cap"
run free free -b
mt=$(awk '$1 == "Mem:" {print $2}' "$tmp/free.out"); ma=$(awk '$1 == "Mem:" {print $7}' "$tmp/free.out")
numeric "$mt" && numeric "$ma" && [ "$ma" -gt 0 ] && [ "$ma" -le "$mt" ] || die 15 "memory total or available missing, not numeric or inconsistent"
echo "scratch used $used bytes of cap $CAP; df available $avail; memory total $mt available $ma"

# --- stop rules (thresholds unchanged)
[ "$maxbusy" -gt 50 ] && die 13 "a core in 80-87 is >50% busy ($maxbusy%)"
if [ "$need_gpu" = 1 ]; then
  others=$(awk -F', ' -v g="$GPU2" -v f="$FOREIGN_PID" '$2 == g && $1 != f {print $1}' "$tmp/apps.out")
  [ -n "$others" ] && die 11 "other compute app on GPU2: $others"
  [ "$gutil" -gt 50 ] && die 12 "GPU2 utilisation $gutil% > 50%"
fi
echo "guard $label passed"
