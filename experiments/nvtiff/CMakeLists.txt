# SPDX-License-Identifier: GPL-2.0-or-later
# Also buildable alone: cmake -S experiments/nvtiff -B build-nvtiff ...
cmake_minimum_required(VERSION 3.21)
project(MotionCorrNvTiffExperiment LANGUAGES CXX)

find_package(CUDAToolkit 12 REQUIRED)
find_path(NVTIFF_INCLUDE_DIR nvtiff.h
    HINTS "${NVTIFF_ROOT}/include" "$ENV{NVTIFF_ROOT}/include")
find_library(NVTIFF_LIBRARY NAMES nvtiff libnvtiff.so.0
    HINTS "${NVTIFF_ROOT}/lib" "${NVTIFF_ROOT}/lib64"
          "$ENV{NVTIFF_ROOT}/lib" "$ENV{NVTIFF_ROOT}/lib64")
if(NOT NVTIFF_INCLUDE_DIR OR NOT NVTIFF_LIBRARY)
    message(FATAL_ERROR "nvTIFF experiment requires a separately installed nvTIFF 0.8 SDK. Set NVTIFF_ROOT.")
endif()

add_executable(motioncorr_nvtiff_probe nvtiff_probe.cpp)
target_compile_features(motioncorr_nvtiff_probe PRIVATE cxx_std_17)
target_include_directories(motioncorr_nvtiff_probe PRIVATE "${NVTIFF_INCLUDE_DIR}")
target_link_libraries(motioncorr_nvtiff_probe PRIVATE CUDA::cudart "${NVTIFF_LIBRARY}")
# Deliberately no install() or link into motioncorr_core: dependency/licensing,
# native sample identity and application benefit must be reviewed before promotion.
