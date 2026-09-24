#!/usr/bin/env bash
set -euo pipefail

# MotionCorr Synthetic CPU-versus-Metal Regression Runner
# Usage:
#   ./tools/run_metal_synthetic_regression.sh [OPTIONS]
# Environment overrides:
#   CPU_BIN       Path to single-thread CPU motioncorr binary
#   METAL_BIN     Path to Metal-enabled motioncorr binary
#   METAL_DEVICE  Metal device index or name (default: auto-detected)
#   PYTHON        Python interpreter with numpy

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Detect python with numpy
PYTHON_CMD="${PYTHON:-}"
if [[ -z "${PYTHON_CMD}" ]]; then
    if python3 -c 'import numpy' 2>/dev/null; then
        PYTHON_CMD="python3"
    elif [[ -x "/opt/homebrew/bin/python3" ]]; then
        PYTHON_CMD="/opt/homebrew/bin/python3"
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

# Locate Metal binary
METAL_BINARY="${METAL_BIN:-}"
if [[ -z "${METAL_BINARY}" ]]; then
    if [[ -x "${REPO_ROOT}/build-metal/motioncorr" ]]; then
        METAL_BINARY="${REPO_ROOT}/build-metal/motioncorr"
    elif [[ -x "${REPO_ROOT}/build/motioncorr" ]]; then
        METAL_BINARY="${REPO_ROOT}/build/motioncorr"
    fi
fi

EXTRA_ARGS=()
if [[ -n "${METAL_DEVICE:-}" ]]; then
    EXTRA_ARGS+=(--device "${METAL_DEVICE}")
fi

exec "${PYTHON_CMD}" "${SCRIPT_DIR}/run_metal_synthetic_regression.py" \
    ${CPU_BINARY:+--cpu-bin "${CPU_BINARY}"} \
    ${METAL_BINARY:+--metal-bin "${METAL_BINARY}"} \
    --python "${PYTHON_CMD}" \
    "${EXTRA_ARGS[@]}" \
    "$@"
