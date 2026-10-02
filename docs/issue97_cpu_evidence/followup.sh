#!/bin/bash
# Issue #97 follow-up measurements addressing review findings N1 and N3.
# Re-uses the retained arm outputs from the 85dd1f9 run: no rebuild, no re-run of
# motioncorr, no timing measurement. Read-only over existing products.
cd /home/ubuntu/mc-issue97-grok-opus || exit 1

ARMS="syn-base-off syn-base-on syn-fixed-off syn-fixed-on mov-base-off mov-base-on mov-fixed-off mov-fixed-on"

{
echo "### Issue #97 follow-up measurements (review findings N1, N3) -- $(date -Is)"
echo "### Re-uses retained arm outputs from the 85dd1f9 validation run."
echo "### No rebuild, no motioncorr re-run, no timing measurement."
echo
echo "--- placement (held identical to the original run) ---"
grep Cpus_allowed_list /proc/self/status
grep Mems_allowed_list /proc/self/status
numactl --show | grep -E "^policy|^nodebind|^membind|^physcpubind"
echo "--- load at this follow-up ---"
cat /proc/loadavg
echo "--- concurrent users of cores 32-63 ---"
ps -eo pid,user,pcpu,psr,comm --sort=-pcpu | awk 'NR==1 || ($4>=32 && $4<=63 && $3>1.0)'
echo

echo "--- N3: was the recenter block actually reached? ---"
echo "    do_local requires patch_x > 2 AND patch_y > 2. Read from the NESTED per-movie"
echo "    logfile, which the original run_validation.sh grep ('\$out'/*.log) never matched."
for a in $ARMS; do
    f=$(find "out/$a" -name '*.log' ! -name stdout.log ! -name time.log | head -1)
    printf "%-14s %-20s %-24s patch_blocks=%-4s too_few_patches=%s\n" \
        "$a" "$(grep -m1 '^Patches:' "$f")" "$(grep -m1 '^interpolate_shifts' "$f")" \
        "$(grep -c '^Patch (' "$f")" "$(grep -c 'Too few patches' "$f")"
done
echo

echo "--- N1: rlnAccumMotion Total/Early/Late (values the previous filter discarded) ---"
echo "    Columns: opticsGroup AccumMotionTotal AccumMotionEarly AccumMotionLate"
for a in $ARMS; do
    printf "%-14s %s\n" "$a" "$(awk '/\.mrc /{print $3, $4, $5, $6}' "out/$a/corrected_micrographs.star" | tail -1)"
done
echo

echo "--- corrected comparator: path TOKENS normalised, so data rows are compared ---"
python3 compare3.py out
echo "compare exit=$?"
} > followup_measurements.log 2>&1

tail -30 followup_measurements.log
