#!/usr/bin/env bash
set -euo pipefail

# MotionCorr Synthetic CPU-versus-CUDA Regression Runner
# Usage:
#   ./tools/run_cuda_synthetic_regression.sh [OPTIONS]
# Environment overrides:
#   CPU_BIN     Path to single-thread CPU motioncorr binary
#   CUDA_BIN    Path to CUDA-enabled motioncorr binary
#   GPU_ID      CUDA device index (default: 0)
#   PYTHON      Python interpreter with numpy

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Detect python with numpy
PYTHON_CMD="${PYTHON:-}"
if [[ -z "${PYTHON_CMD}" ]]; then
    if python3 -c 'import numpy' 2>/dev/null; then
        PYTHON_CMD="python3"
    elif [[ -x "${HOME}/mc-env/bin/python3" ]]; then
        PYTHON_CMD="${HOME}/mc-env/bin/python3"
    elif [[ -x "${HOME}/miniforge3/envs/cil/bin/python3" ]]; then
        PYTHON_CMD="${HOME}/miniforge3/envs/cil/bin/python3"
    else
        PYTHON_CMD="python3"
    fi
fi

# Locate CPU binary
CPU_BINARY="${CPU_BIN:-}"
if [[ -z "${CPU_BINARY}" ]]; then
    if [[ -x "${REPO_ROOT}/build-cpu/motioncorr" ]]; then
        CPU_BINARY="${REPO_ROOT}/build-cpu/motioncorr"
    elif [[ -x "${REPO_ROOT}/build/motioncorr" ]]; then
        CPU_BINARY="${REPO_ROOT}/build/motioncorr"
    fi
fi

# Locate CUDA binary
CUDA_BINARY="${CUDA_BIN:-}"
if [[ -z "${CUDA_BINARY}" ]]; then
    if [[ -x "${REPO_ROOT}/build-cuda/motioncorr" ]]; then
        CUDA_BINARY="${REPO_ROOT}/build-cuda/motioncorr"
    elif [[ -x "${REPO_ROOT}/build/motioncorr" ]]; then
        CUDA_BINARY="${REPO_ROOT}/build/motioncorr"
    fi
fi

GPU_INDEX="${GPU_ID:-0}"

exec "${PYTHON_CMD}" "${SCRIPT_DIR}/run_cuda_synthetic_regression.py" \
    ${CPU_BINARY:+--cpu-bin "${CPU_BINARY}"} \
    ${CUDA_BINARY:+--cuda-bin "${CUDA_BINARY}"} \
    --gpu "${GPU_INDEX}" \
    --python "${PYTHON_CMD}" \
    "$@"
