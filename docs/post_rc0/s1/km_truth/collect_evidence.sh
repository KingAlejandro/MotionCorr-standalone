#!/usr/bin/env bash
# Run on the corresponding host after its 100 per-seed completion markers exist.
set -euo pipefail
backend=${1:?cpu or cuda}
if [[ "$backend" == cpu ]]; then
  cd /home/ubuntu/mc-km-truth-20261021
  test "$(find results -name cpu.done.json | wc -l)" -eq 100
  tar czf cpu-evidence.tar.gz \
    --exclude='*.mrc' --exclude='*.mrcs' --exclude='*.tif' --exclude='*.tiff' \
    --exclude='*.npy' --exclude='*.lock' \
    results fixtures controls stage-control expectations/*.json \
    interrupted-generation/RECORD.json generation-environment.json \
    cpu-build.log cpu-build.exit diag-build.log diag-build.exit capture-build.log capture-build.exit \
    generation.log generation-parallel.log prefetch-pedestal.log transfer-direct.log transfer-zstd.log \
    product-retention.log census-cpu-*.log \
    generate_campaign.py generate_campaign_parallel.py prefetch_pedestal.py run_realistic_motion_census.py \
    transfer_direct.py transfer_direct_zstd.py retain_cpu_products.py stage_control.py orientation_controls.py analyze_live.py \
    v2/test-data/generate_realistic_motion.py v2/tools/check_realistic_motion.py
else
  test "$backend" = cuda
  cd /mnt/clathrin/alex-motioncorr-km-truth
  test "$(find results -name cuda.done.json | wc -l)" -eq 100
  tar czf cuda-evidence.tar.gz \
    --exclude='*.mrc' --exclude='*.mrcs' --exclude='*.lock' \
    results fixtures/*/TRANSFER_VERIFIED.json \
    cuda-build.log cuda-build.exit diag-build.log diag-build.exit capture-build.log capture-build.exit census-cuda.log
fi
