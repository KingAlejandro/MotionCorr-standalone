#!/bin/bash
# K269 CUDA census (100 movies, arm none) on the tested CUDA build, GPU3 under the nonblocking lease (c1_gpu_run.sh), lane-adapted derivative runner
# (c1_census_runner.py: --j 2, GPU3 only; the stock runner walks GPUs 2,3,1,0 and --j 8, so it does not fit the single-GPU3 rule). usage: c1_census_cuda.sh
set -u
D=$(dirname "$0"); source "$D/c1_env.sh" || exit 1
export QF_W=$C1_SCR; cd $C1_SCR
mkdir -p census; for t in truth-4096x4096.npy truth-5760x4092.npy; do [ -e census/$t ] || ln -s $C1_BUILDS_SRC/census/$t census/$t; done
exec "$D/c1_gpu_run.sh" census-cuda taskset -c $C1_CPUS $C1_PY $D/c1_census.py run cuda $C1_BUILDS_SRC/build-cuda/motioncorr results-c1-cuda
