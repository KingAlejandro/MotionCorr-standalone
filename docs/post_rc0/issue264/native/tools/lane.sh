# SPDX-License-Identifier: GPL-2.0-or-later
# Sourced by every #264 native script on 4GPUs. Lane: GPU1 (by UUID) + CPUs 14-15 only.
# Required: G_SCR (fresh scratch under /mnt/clathrin), G_SHA (full candidate SHA).
: "${G_SCR:?}" "${G_SHA:?}"
case "$G_SCR" in /mnt/clathrin/alex-motioncorr-guard264-20261022-*) ;; *) echo "G_SCR outside the assigned scratch" >&2; return 1 2>/dev/null || exit 1;; esac
export G_BASE=3691374061f782bc84531fd1c79d017ddcb5a7c2
export G_CPUS=14-15
export G_GPU_UUID=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d
export G_GPU_LOCK=/tmp/motioncorr-gpu1-correctness.lock
export G_BUILD_LOCK=/tmp/motioncorr-build.lock
export G_CPU_LOCK=/tmp/motioncorr-guard264-cpu14-15.lock
export G_PY=/home/alex/.mc-venv/bin/python3
export G_NVCOMP=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
# Private pbzip2 (read in place, job PATH only); pin from the parent registry, re-verified on every source.
export G_PBZIP2_DIR=/mnt/clathrin/alex-motioncorr-214/tools/usr/bin
export G_PBZIP2_SHA256=35410d199baebff55262e43cac9e8cdf9d14b540143c8e70ee53c6cf8ca9f21e
[ "$(sha256sum $G_PBZIP2_DIR/pbzip2 | cut -c1-64)" = "$G_PBZIP2_SHA256" ] || { echo "pbzip2 pin mismatch" >&2; return 1 2>/dev/null || exit 1; }
export PATH=$G_PBZIP2_DIR:/usr/local/cuda-12.8/bin:/home/alex/.mc-venv/bin:/usr/bin:/bin
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$G_NVCOMP/lib
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES CUDA_VISIBLE_DEVICES
export G_TUTORIAL=/home/alex/motioncorr-validation-20261011-vm/tutorial-data          # read-only
export G_FROZEN_L=/mnt/clathrin/alex-motioncorr-rc0/W-QF/multigpu/L                    # read-only manifest
export G_KM_MOVIE=/mnt/clathrin/alex-motioncorr-peakfit/known-motion-cpu-fixtures/km_local_nonsquare.mrcs   # read-only
export G_KM_SHA256=644274e0d869d3c468db873ab2af48fc064cbf78c02f5c080d6e669907493fb3
