#!/bin/bash
# Two legs, strictly in sequence, because the second is a benchmark.
#
#  1. 24-movie same-backend A/B at --j 4. PR #90 touches gain-reference caching,
#     which is shared across worker threads, so the thread count is a real
#     surface and not a formality.
#  2. Interleaved paired timing, 3 blocks. This runs alone: nothing else of
#     mine is on the machine while it does.
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-io-evidence
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
echo "=== provenance ==="; date -Is; hostname; uptime
md5sum $R/harness/compare_outputs.py $R/harness/timing_blocks.py

echo "=== A/B at --j 4 ==="
rm -rf $R/ab-j4
taskset -c 56-63 python3 $R/harness/compare_outputs.py --repo $R/src-pr90 \
  --ref-binary $R/src-main/build-cpu/motioncorr --ref-label main \
  --test-binary $R/src-pr90/build-cpu/motioncorr --test-label pr90 \
  --tutorial $HOME/mc51/tutorial --threads 4 \
  --work $R/ab-j4 --json $R/evidence/pr90_outputs_j4.json
echo "ab j4 exit=$?"
echo "=== AB J4 DONE ==="; date -Is

# The timing leg is a benchmark, so it does not start while any other leg of
# mine is still on the machine. By this point the j4 A/B's own comparator has
# exited, so a match here means somebody else's leg, not this script's child.
echo "=== waiting for my other legs to finish ==="
while pgrep -f "damaged_matrix.py|resume_matrix.py|compare_outputs.py" >/dev/null; do
  sleep 30
done
echo "machine free of my work"; date -Is; uptime

echo "=== interleaved paired timing, 3 blocks, --j 8, alone ==="
rm -rf $R/timing
taskset -c 56-63 python3 $R/harness/timing_blocks.py \
  --ref-binary $R/src-main/build-cpu/motioncorr --ref-label main \
  --test-binary $R/src-pr90/build-cpu/motioncorr --test-label pr90 \
  --tutorial $HOME/mc51/tutorial --threads 8 --blocks 3 --taskset 56-63 \
  --work $R/timing --json $R/evidence/pr90_timing_blocks.json
echo "timing exit=$?"
echo "=== TIMING DONE ==="; date -Is
