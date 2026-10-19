# SCARF environment for the QF tools (sourced inside the Slurm job step)
export QF_W=/home/vol05/scarf1415/mc-rc0-scarfF
export QF_SHA=6d68e2d6ec45c37b75fd0f4aaff8272f192b7029
export QF_CPUS=$(awk '/^Cpus_allowed_list/{print $2}' /proc/self/status)
export QF_GPU_UUID=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)
export QF_GPU_LOCK=/tmp/motioncorr-wscarf-gpu-correctness.lock
CU=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
export PATH=$QF_W/venv/bin:$CU/bin:/usr/bin:/bin:/usr/sbin:/home/vol05/scarf1415/bin
unset LD_LIBRARY_PATH PYTHONPATH
