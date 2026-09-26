# Stabilization evidence, 26 September 2026

Tracking #66. These are separate pinned investigations, not a universal release or performance result.

## CPU shared-runner fixes

[CPU commands, negative controls and limitations](cpu/README.md); [provenance](cpu/provenance.json).
Source `2c27c7b`, Release, CUDA=OFF on cpu64, affinity 48–55, maximum 8 build jobs. 10/10 CTests pass, preserving historical exact j1/j4 outputs. Base-failing regressions establish the fixed faults. Later review identified a missing-coefficient-row parser hole; its follow-up and final evidence remain in PR #78. These artifacts do not silently cover later commits.

## Native CUDA cleanup and tie ablation

Base source `0c7d68f`, current PR #51. CUDA 12.8, sm80, Release, TIMING=ON. Dedicated SCARF gn3000/A100 allocation, one movie-processing process, 8 threads, all 24 tutorial movies, gain, 5x5 patches, dose/frame 1.277, seed 1. Full command and process evidence are in the job logs and time files; executable hashes are in each binaries.sha256.

| Candidate | Job | Result vs base |
|---|---|---|
| bcc3899 including tie-rule change |3509025|22/24 exact;00023 and00035 differ|
| cc65001 removing only tie-rule change and its test registration |3509040|24/24 exact|

Raw comparator reports are in [with-ties/exact24](cuda/with-ties/exact24) and [without-ties/exact24](cuda/without-ties/exact24). Each result was checked for top-level PASS, complete coverage, corrected pixel identity, trajectory PASS and STAR PASS; a summary count alone was not accepted. The old aggregation summary contains null convenience fields for RMSE/STAR differences due to mismatched key names; use the per-movie reports for those metrics.

The ablation attributes the two changed movies to CPU-raster tie selection. A direct common-CCF control confirms the new rule matches CPU ordering for 5 cases over 20 repeats, but it changes iterative alignment on real data. The tie change stays separate under #70. Six injected-upload cases pass cleanup/error checks. No performance speedup or measured whole-process peak-memory reduction is claimed. Static storage reduction is gain+sum arrays, approximately 108.6 MiB with gain at 3710x3838; it is not a measured peak reduction.

These are CUDA-to-CUDA comparisons. They neither pass nor change historical CPU/RELION Gate 2. Shared-runner integration and repaired CPU/CUDA truth checks are separate candidate evidence.

## Recovered completed T3 multi-GPU experiment

T3's Multi-GPU Movie Scheduling task completed a later experiment than the previously inspected failed-cold-cache phase10. [Raw final log](scarf-t3/final.txt), [exact script](scarf-t3/final.sh), [Slurm allocation](scarf-t3/pf.sbatch). Source for ours `0c7d68f`. Job 3508552, gn3000, scarf23, 4 A100s, 16 logical CPU mask 0–15; four processes share this mask. Ours uses j=8 per process; MC3 uses one GPU per process. Tools interleaved. These are batch wall times including input/output.

| Four-process configuration | Verified cold median, n=2 | Warm median, n=5 |
|---|---:|---:|
| MotionCorr nativeCUDA |15.0425s|13.5703s|
| MotionCor3 stock |13.3434s|11.5633s|

The final log records page residency dropping to 0 MiB before each cold arm. This corrects the earlier absence of valid cold evidence; it does not rehabilitate phase10's failed eviction. Timed output files were removed by the historical script, so counts and timings alone cannot establish numerical equivalence of each timed arm.

A separate retained serial-vs-sharded comparison in results9 has 24 complete per-movie exact PASS reports; see [gatec](scarf-t3/gatec). It is evidence for that configuration, not proof of every cache/repeat/GPU arm. It was independently re-aggregated from raw checks. MotionCor3 repeat variability remains a separate limitation; do not attribute every process-sharding difference to a scheduler or claim cross-backend pixel equality.

The prior gn0004 results had a different performance ranking. No GPU-model/cache/NUMA explanation is asserted without a controlled experiment. The present work did not rerun those historical performance comparisons.
