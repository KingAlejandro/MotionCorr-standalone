# Sourced by every C1 qualification script on 4GPUs. Lane: GPU3 + CPUs 8-9 only.
# Required: C1_SCR (fresh scratch under /mnt/clathrin), C1_SHA (full source SHA).
: "${C1_SCR:?}" "${C1_SHA:?}"
case "$C1_SCR" in /mnt/clathrin/alex-motioncorr-c1-20261022-*) ;; *) echo "C1_SCR outside the assigned scratch" >&2; return 1 2>/dev/null || exit 1;; esac
export C1_CPUS=8-9
export C1_GPU_UUID=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d
export C1_GPU_LOCK=/tmp/motioncorr-gpu3-correctness.lock
export C1_BUILD_LOCK=/tmp/motioncorr-build.lock
export C1_PY=/home/alex/.mc-venv/bin/python3
export C1_NVCOMP=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
# pbzip2 is absent from the default PATH on 4GPUs. The #249 evidence pins one private copy (read in place, job PATH only, no installation).
export C1_PBZIP2_DIR=/mnt/clathrin/alex-motioncorr-214/tools/usr/bin
export C1_PBZIP2_SHA256=35410d199baebff55262e43cac9e8cdf9d14b540143c8e70ee53c6cf8ca9f21e
[ "$(sha256sum $C1_PBZIP2_DIR/pbzip2 | cut -c1-64)" = "$C1_PBZIP2_SHA256" ] || { echo "pbzip2 pin mismatch" >&2; return 1 2>/dev/null || exit 1; }
export PATH=$C1_PBZIP2_DIR:/usr/local/cuda-12.8/bin:/home/alex/.mc-venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$C1_NVCOMP/lib
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
# QF toolkit variables (docs/rc0/qf/tools): the C1 scratch plays the QF workspace.
export QF_W=$C1_SCR QF_SHA=$C1_SHA QF_CPUS=$C1_CPUS QF_GPU_UUID=$C1_GPU_UUID QF_GPU_LOCK=$C1_GPU_LOCK
export C1_FROZEN_RC0=/mnt/clathrin/alex-motioncorr-rc0/W-QF     # read-only: frozen F 6d68e2d6 builds and retained 24-movie products
export C1_TUTORIAL=/home/alex/motioncorr-validation-20261011-vm/tutorial-data   # read-only
export C1_KM_FIXTURES=/mnt/clathrin/alex-motioncorr-km-truth/fixtures            # read-only (#269 fixtures, receipts hash-checked)
