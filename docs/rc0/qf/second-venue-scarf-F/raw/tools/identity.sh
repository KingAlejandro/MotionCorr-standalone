#!/bin/bash
# host, GPU, toolchain identity (no timing)
source /home/vol05/scarf1415/mc-rc0-scarfF/tools/env.sh
set +e
echo "date $(date -u +%FT%TZ) host $(hostname) slurm_job ${SLURM_JOB_ID:-} step ${SLURM_STEP_ID:-}"
echo "QF_CPUS=$QF_CPUS QF_GPU_UUID=$QF_GPU_UUID QF_GPU_LOCK=$QF_GPU_LOCK"
echo "CUDA_VISIBLE_DEVICES(slurm)=${CUDA_VISIBLE_DEVICES:-unset}"
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total,pci.bus_id --format=csv,noheader
echo "compute-apps: [$(nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader)]"
nvidia-smi -q | grep -E 'CUDA Version|Driver Version'
echo "THP enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled) defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag)"
lscpu | grep -E 'Model name|^CPU\(s\)|Thread|Socket|NUMA node\(s\)'
echo "kernel $(uname -r); $(cat /etc/redhat-release 2>/dev/null)"
g++ --version | sed -n 1p
nvcc --version | tail -2
cmake --version | sed -n 1p
python3 -c 'import sys,numpy;print("python",sys.version.split()[0],"numpy",numpy.__version__,sys.executable)'
python3 -c 'import PIL' 2>/dev/null && echo "PIL present" || echo "PIL absent"
echo "nvcomp: $(ls /home/vol05/scarf1415/nvcomp-sdk/lib/libnvcomp.so.*.*)"; grep -h 'define NVCOMP_VER' /home/vol05/scarf1415/nvcomp-sdk/include/nvcomp/*.h 2>/dev/null
echo "gs $(gs --version)  pbzip2 $(command -v pbzip2)  zstd $(command -v zstd)  xz $(command -v xz)"
echo "src HEAD $(git -C $QF_W/src rev-parse HEAD) porcelain=$(git -C $QF_W/src status --porcelain | wc -l) appledouble=$(find $QF_W/src -name '._*' | wc -l)"
df -h /tmp $QF_W | tail -2
