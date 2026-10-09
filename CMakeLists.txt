cmake_minimum_required(VERSION 3.21)
project(MotionCorr LANGUAGES C CXX)

set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FFTW_DOUBLE REQUIRED IMPORTED_TARGET fftw3)
pkg_check_modules(FFTW_FLOAT REQUIRED IMPORTED_TARGET fftw3f)
if(APPLE AND CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
    find_path(LIBOMP_INCLUDE_DIR omp.h
        PATHS /opt/homebrew/opt/libomp/include /usr/local/opt/libomp/include)
    find_library(LIBOMP_LIBRARY omp
        PATHS /opt/homebrew/opt/libomp/lib /usr/local/opt/libomp/lib)
    if(NOT LIBOMP_INCLUDE_DIR OR NOT LIBOMP_LIBRARY)
        message(FATAL_ERROR "Install libomp to build with AppleClang")
    endif()
    add_library(motioncorr_openmp INTERFACE)
    target_compile_options(motioncorr_openmp INTERFACE -Xpreprocessor -fopenmp)
    target_include_directories(motioncorr_openmp INTERFACE "${LIBOMP_INCLUDE_DIR}")
    target_link_libraries(motioncorr_openmp INTERFACE "${LIBOMP_LIBRARY}")
else()
    find_package(OpenMP REQUIRED COMPONENTS CXX)
    add_library(motioncorr_openmp INTERFACE)
    target_link_libraries(motioncorr_openmp INTERFACE OpenMP::OpenMP_CXX)
endif()
find_package(TIFF REQUIRED)
find_package(PNG REQUIRED)
find_package(JPEG REQUIRED)
find_package(ZLIB REQUIRED)

# Which DEFLATE implementation LibTIFF uses is fixed when LibTIFF itself is
# built (libdeflate has been an option since 4.2) and is invisible from a
# version number, yet it governs most of the movie-read cost: the tutorial
# movies are Adobe Deflate with RowsPerStrip=1, so one movie is 92,112
# whole-strip decompressions. Probe the library that will actually be linked,
# by asking it to select the libdeflate subcodec -- only a LibTIFF built with
# libdeflate accepts that. The probe writes and removes one small TIFF, under
# an explicit path in the build tree: try_run leaves the working directory as
# the one cmake was invoked from, which may not be writable, and a probe that
# cannot create its file would report a false "zlib only".
if(CMAKE_CROSSCOMPILING)
    set(TIFF_DEFLATE_SUBCODEC "not probed (cross-compiling)")
else()
    include(CheckCSourceRuns)
    set(_mc_saved_required_libraries "${CMAKE_REQUIRED_LIBRARIES}")
    set(_mc_saved_required_definitions "${CMAKE_REQUIRED_DEFINITIONS}")
    set(CMAKE_REQUIRED_LIBRARIES TIFF::TIFF)
    set(CMAKE_REQUIRED_DEFINITIONS
        "-DMC_PROBE_TIFF=\"${CMAKE_CURRENT_BINARY_DIR}/mc_deflate_subcodec_probe.tif\"")
    check_c_source_runs("
#include <stdio.h>
#include <tiffio.h>
int main(void)
{
    TIFF *tif;
    int ok = 0;
    TIFFSetErrorHandler(0);
    TIFFSetWarningHandler(0);
    tif = TIFFOpen(MC_PROBE_TIFF, \"w\");
    if (tif) {
        if (TIFFSetField(tif, TIFFTAG_COMPRESSION, COMPRESSION_ADOBE_DEFLATE) == 1)
            ok = TIFFSetField(tif, TIFFTAG_DEFLATE_SUBCODEC,
                              DEFLATE_SUBCODEC_LIBDEFLATE) == 1;
        TIFFClose(tif);
        remove(MC_PROBE_TIFF);
    }
    return ok ? 0 : 1;
}
" TIFF_HAS_LIBDEFLATE)
    set(CMAKE_REQUIRED_LIBRARIES "${_mc_saved_required_libraries}")
    set(CMAKE_REQUIRED_DEFINITIONS "${_mc_saved_required_definitions}")
    if(TIFF_HAS_LIBDEFLATE)
        set(TIFF_DEFLATE_SUBCODEC "libdeflate")
    else()
        set(TIFF_DEFLATE_SUBCODEC "zlib only")
    endif()
endif()
message(STATUS "LibTIFF Deflate subcodec: ${TIFF_DEFLATE_SUBCODEC}")
if(TIFF_DEFLATE_SUBCODEC STREQUAL "zlib only")
    message(STATUS "  Deflate movie reads use zlib here. A LibTIFF built with "
                   "libdeflate decodes the same bytes faster; see README, "
                   "\"LibTIFF Deflate backend\". Results are unaffected.")
endif()

set(RELION_VERSION_SUFFIX "-motioncorr-standalone")
configure_file(src/macros.cpp.in ${CMAKE_CURRENT_BINARY_DIR}/macros.cpp @ONLY)

file(GLOB_RECURSE MOTIONCORR_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/*.c")
list(REMOVE_ITEM MOTIONCORR_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/src/apps/run_motioncorr.cpp")

add_library(motioncorr_core STATIC ${MOTIONCORR_SOURCES}
    "${CMAKE_CURRENT_BINARY_DIR}/macros.cpp")
target_include_directories(motioncorr_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_definitions(motioncorr_core PRIVATE HAVE_TIFF HAVE_PNG HAVE_JPEG)
target_link_libraries(motioncorr_core PUBLIC
    PkgConfig::FFTW_DOUBLE PkgConfig::FFTW_FLOAT
    motioncorr_openmp TIFF::TIFF PNG::PNG JPEG::JPEG ZLIB::ZLIB)

option(TIMING "Enable internal timing" OFF)
if(TIMING)
    add_compile_definitions(TIMING)
endif()

option(CUDA "Build with CUDA acceleration" OFF)
if(CUDA)
    # Establish the project default before enable_language(CUDA), which has
    # cached nvcc's own default architecture since CMake 3.18 and so would leave
    # any later fallback unreachable. sm80 is the architecture this project
    # builds and validates on: a deliberate default, not a claim of support for
    # every device. $ENV{CUDAARCHS} keeps its usual meaning, so stand down for it
    # on the same non-empty test CMakeDetermineCUDACompiler itself applies.
    if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES AND "$ENV{CUDAARCHS}" STREQUAL "")
        set(CMAKE_CUDA_ARCHITECTURES 80 CACHE STRING "CUDA architectures")
    endif()
    enable_language(CUDA)
    # motioncorr_core is created above, before CUDA is enabled, and CMake copies
    # CUDA_ARCHITECTURES from the variable only at target creation, so the
    # target would otherwise keep an unset property and generation would fail.
    set_property(TARGET motioncorr_core PROPERTY
                 CUDA_ARCHITECTURES "${CMAKE_CUDA_ARCHITECTURES}")
    message(STATUS "motioncorr_core CUDA architectures: ${CMAKE_CUDA_ARCHITECTURES}")
    set(CMAKE_CUDA_STANDARD 17)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)
    find_package(CUDAToolkit REQUIRED)
    target_compile_definitions(motioncorr_core PUBLIC _CUDA_ENABLED)
    target_compile_options(motioncorr_core PRIVATE $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler -fopenmp>)
    target_sources(motioncorr_core PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_alignpatch.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_realspace_dw.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_fft_prep.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_movie_session.cu")
    target_link_libraries(motioncorr_core PUBLIC CUDA::toolkit CUDA::cudart CUDA::cufft)

    option(USE_NVCOMP "Enable GPU Deflate decompression via NVIDIA nvCOMP" OFF)
    if(USE_NVCOMP)
        find_path(NVCOMP_INCLUDE_DIR nvcomp/deflate.h
            HINTS ${NVCOMP_ROOT}/include $ENV{NVCOMP_ROOT}/include)
        find_library(NVCOMP_LIB nvcomp
            HINTS ${NVCOMP_ROOT}/lib $ENV{NVCOMP_ROOT}/lib64)
        if(NVCOMP_INCLUDE_DIR AND NVCOMP_LIB)
            target_include_directories(motioncorr_core PUBLIC ${NVCOMP_INCLUDE_DIR})
            target_link_libraries(motioncorr_core PUBLIC ${NVCOMP_LIB})
            target_compile_definitions(motioncorr_core PUBLIC _NVCOMP_ENABLED)
            message(STATUS "Found nvCOMP: ${NVCOMP_LIB}")
        else()
            message(FATAL_ERROR "USE_NVCOMP=ON requested but nvcomp headers or library not found. Set NVCOMP_ROOT.")
        endif()
    endif()
endif()

add_executable(motioncorr src/apps/run_motioncorr.cpp)
target_link_libraries(motioncorr PRIVATE motioncorr_core)
install(TARGETS motioncorr RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
    add_executable(runner_numerics tests/test_runner_numerics.cpp)
    target_link_libraries(runner_numerics PRIVATE motioncorr_core)
    # Device-free control for the issue #69 patch-retry shift-state contract.
    add_executable(patch_retry_state tests/test_patch_retry_state.cpp)
    target_link_libraries(patch_retry_state PRIVATE motioncorr_core)
    add_test(NAME PatchRetryState COMMAND patch_retry_state)
    add_executable(defect_parser tests/test_defect_parser.cpp)
    target_link_libraries(defect_parser PRIVATE motioncorr_core)
    # Pure C++ arithmetic regression (issue #97). Registered above the
    # find_package(Python3 ... REQUIRED) line because it needs no interpreter.
    add_test(NAME RunnerInterpolateRecenter
        COMMAND $<TARGET_FILE:runner_numerics> interpolate_recenter)
    add_test(NAME MrcHeaderStats
        COMMAND $<TARGET_FILE:runner_numerics> mrc_stats)
    add_executable(pdf_concat tests/test_pdf_concat.cpp)
    target_link_libraries(pdf_concat PRIVATE motioncorr_core)
    add_test(NAME PdfConcat COMMAND pdf_concat)
    add_test(NAME DefectParser COMMAND defect_parser)
    # Device-free control for the nvCOMP ingestion staging layout. Deliberately not
    # under if(CUDA): the alignment rule and the zlib wrapper checks are integer and
    # byte logic, and a successful A100 decode cannot observe either of them.
    # Header-only and deliberately not linked against motioncorr_core: these
    # contracts must be checkable in a build with no CUDA and no nvCOMP.
    add_executable(deflate_layout tests/test_deflate_layout.cpp)
    target_include_directories(deflate_layout PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    add_test(NAME DeflateLayout COMMAND deflate_layout)
    add_executable(adler32_arithmetic tests/test_adler32.cpp)
    target_include_directories(adler32_arithmetic PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    add_test(NAME Adler32Arithmetic COMMAND adler32_arithmetic)
    set_tests_properties(Adler32Arithmetic PROPERTIES TIMEOUT 120)
    add_executable(adler32_kernel_host tests/test_adler32_kernel_host.cpp)
    target_include_directories(adler32_kernel_host PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/adler32_host_mock" "${CMAKE_CURRENT_SOURCE_DIR}")
    add_test(NAME Adler32KernelHost COMMAND adler32_kernel_host)
    # Links motioncorr_core for StageProfile and REPORT_ERROR; motioncorr_core
    # already carries the OpenMP/pthread link.
    add_executable(stage_profile_threads tests/test_stage_profile_threads.cpp)
    target_link_libraries(stage_profile_threads PRIVATE motioncorr_core)
    add_test(NAME StageProfileThreads COMMAND stage_profile_threads)
    add_executable(frame_buffer_pool tests/test_frame_buffer_pool.cpp)
    target_link_libraries(frame_buffer_pool PRIVATE motioncorr_core)
    add_test(NAME FrameBufferPool COMMAND frame_buffer_pool)
    add_executable(scratch_arena tests/test_scratch_arena.cpp)
    target_include_directories(scratch_arena PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    add_test(NAME ScratchArena COMMAND scratch_arena)
    add_executable(defect_neighbours tests/test_defect_neighbours.cpp)
    target_include_directories(defect_neighbours PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    add_test(NAME DefectNeighbours COMMAND defect_neighbours)
    # Compiled negative controls for the merged hot-pixel bad list: each mutant
    # header must make DefectNeighbours fail. A missing or repeated target line
    # stops the configure step rather than building an unmutated control.
    function(add_defect_merge_mutant _mutant _from _to)
        file(READ "${CMAKE_CURRENT_SOURCE_DIR}/src/defect_neighbours.h" _header)
        string(FIND "${_header}" "${_from}" _first)
        string(FIND "${_header}" "${_from}" _last REVERSE)
        if(_first EQUAL -1 OR NOT _first EQUAL _last)
            message(FATAL_ERROR "defect merge mutant ${_mutant}: target missing or not unique")
        endif()
        string(REPLACE "${_from}" "${_to}" _header "${_header}")
        set(_dir "${CMAKE_CURRENT_BINARY_DIR}/mutants/defect_merge_${_mutant}")
        file(WRITE "${_dir}/src/defect_neighbours.h" "${_header}")
        add_executable(defect_neighbours_${_mutant} tests/test_defect_neighbours.cpp)
        target_include_directories(defect_neighbours_${_mutant} PRIVATE "${_dir}")
        add_test(NAME DefectMergeMutant_${_mutant} COMMAND defect_neighbours_${_mutant} --expect-fail)
    endfunction()
    add_defect_merge_mutant(append_only
        "(j == b.size() || (i < a.size() && a[i] < b[j]))" "(i < a.size())")
    add_defect_merge_mutant(no_order_check
        "if ((long)v <= prev) return false;" "if (false) return false;")
    add_defect_merge_mutant(swap_xy "xs.push_back(v % nx);" "xs.push_back(v / nx);")
    # The malformed-input cases hang the pre-#98 parser; bound them so a
    # regression fails the suite instead of stalling it.
    set_tests_properties(DefectParser PROPERTIES TIMEOUT 120)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    add_test(NAME NvcompAcceptanceDiagnostics
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_nvcomp_acceptance_diagnostics.py)
    add_test(NAME GainCacheOwnership
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_gain_cache_host.py
            --cxx ${CMAKE_CXX_COMPILER})
    set_tests_properties(GainCacheOwnership PROPERTIES TIMEOUT 120)
    # Declaration/definition agreement on the _NVCOMP_ENABLED guard. Device-free
    # and deliberately outside if(CUDA): the whole point is a configuration this
    # suite does not link, so no compiled test can observe it.
    add_test(NAME NvcompGuards
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/check_nvcomp_guards.py)
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c "import numpy"
        RESULT_VARIABLE _NUMPY_CHECK
        OUTPUT_QUIET ERROR_QUIET
    )
    if(NOT _NUMPY_CHECK EQUAL 0)
        message(FATAL_ERROR "BUILD_TESTING=ON requires Python 3 with 'numpy' installed.")
    endif()
        add_test(NAME SyntheticRegression
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_synthetic_regression.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME HotPixelRngDeterminism
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_hotpixel_rng_determinism.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME RunnerExposure
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --case exposure)
        foreach(case failure invalid resume tomography)
            add_test(NAME Runner_${case}
                COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                    --binary $<TARGET_FILE:motioncorr> --case ${case})
        endforeach()
        add_test(NAME RunnerLateBin
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:runner_numerics> --case late_bin)
        add_test(NAME RunnerExportedUnits
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:runner_numerics> --case exported_units)
        add_test(NAME GainCache
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_gain_cache.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME TiffRead
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_tiff_read.py
                --helper $<TARGET_FILE:runner_numerics>)
        add_test(NAME DamagedMovie
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_damaged_movie.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME CompressedMovieSequence
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_compressed_movie_sequence.py
                --binary $<TARGET_FILE:motioncorr>)
        set_tests_properties(CompressedMovieSequence PROPERTIES TIMEOUT 120)
        add_test(NAME GlobalIfftElision
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_global_ifft_elision.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME HostBufferReuse
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_host_buffer_reuse.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME StageProfile
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_stage_profile.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME RunnerModelParser
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:runner_numerics> --case model_parser)
        add_test(NAME MicrographModelBounds
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_micrograph_model_bounds.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:runner_numerics>)
        set_tests_properties(MicrographModelBounds PROPERTIES TIMEOUT 120)
        add_test(NAME RunnerInterpolateShifts
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --case interpolate_shifts)
        add_test(NAME WriteFaults
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_write_faults.py
                --binary $<TARGET_FILE:motioncorr>)
        # The same three-phase fail-closed sequence with the background output
        # writer turned off. WriteFaults above exercises the deferred path, where
        # the write fails on the worker thread and the failure is collected after
        # the fact; this one exercises the inline path, where it propagates on the
        # spot. --sync_output is a measurement control, so it must not be a way to
        # get weaker failure semantics.
        add_test(NAME WriteFaultsSync
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_write_faults.py
                --binary $<TARGET_FILE:motioncorr> --runner-arg=--sync_output)
        # Several MRC products for one movie, so the rule under test is not merely
        # "the image write failed" but "the first failed product cancels the rest
        # of that movie's group, the per-movie STAR among them". With one product
        # per movie the ordering requirement is unobservable.
        add_test(NAME WriteFaultsMultiProduct
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_write_faults.py
                --binary $<TARGET_FILE:motioncorr> --runner-arg=--save_noDW
                --runner-arg=--even_odd_split)
        # #127 Ghostscript overlap: a throw from the main-thread batch.pdf pass
        # must fail the job, not unwind through a joinable std::thread. Needs no
        # GPU, so it runs in every configuration.
        add_test(NAME OutputStageFaults
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_output_stage_faults.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME CiFailClosedControls
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/test_ci_fail_closed.py)
        add_test(NAME CudaValidationParser
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/test_cuda_patch_validation_parser.py)
        add_test(NAME OutputTreeComparator
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_compare_output_trees.py)
        set_tests_properties(OutputTreeComparator PROPERTIES TIMEOUT 120)
    # Injects short and deferred write failures with setrlimit(RLIMIT_FSIZE),
    # so it needs POSIX resource limits and an ignorable SIGXFSZ.
    if(UNIX)
        add_executable(observation_model_save tests/test_observation_model_save.cpp)
        target_link_libraries(observation_model_save PRIVATE motioncorr_core)
        add_test(NAME JointStarPublication
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_joint_star_publication.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:observation_model_save>)

        add_executable(image_write_faults tests/test_image_write_faults.cpp)
        target_link_libraries(image_write_faults PRIVATE motioncorr_core)
        add_test(NAME ImageWriteFaults COMMAND image_write_faults)

        # Issue #95: the native uint16 staging ownership contract. Device-free:
        # it checks that the frames alias one mapping, that Image::read's
        # coreAllocateReuse() keeps that slice, and that release() returns the
        # payload to the operating system. The last assertion needs /proc and
        # reports a skip elsewhere; CI runs on Linux.
        add_executable(native_movie_staging tests/test_native_movie_staging.cpp)
        target_link_libraries(native_movie_staging PRIVATE motioncorr_core)
        add_test(NAME NativeMovieStaging COMMAND native_movie_staging)
        # Exit 77 when the resident-set arm could not run, so ctest reports NOTRUN
        # rather than a Passed that hides a skipped assertion.
        set_tests_properties(NativeMovieStaging PROPERTIES SKIP_RETURN_CODE 77)
    endif()
endif()
if(BUILD_TESTING AND CUDA)
    if(Python3_Interpreter_FOUND)
        add_test(NAME RunnerInterpolateShiftsCuda
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --case interpolate_shifts --gpu 0)
        set_tests_properties(RunnerInterpolateShiftsCuda PROPERTIES LABELS "cuda;hardware")
        add_test(NAME StageProfileDeviceTiming
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_stage_profile.py
                --binary $<TARGET_FILE:motioncorr> --gpu 0)
        set_tests_properties(StageProfileDeviceTiming PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
    endif()
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        # Issue #85 lane C: uint16 staging must reproduce the float path's device
        # state exactly, including the no-gain case where the float path never
        # writes d_Iframes. Needs a real device.
        add_executable(cuda_u16_staging_equivalence tests/cuda_u16_staging_equivalence.cpp)
        target_link_libraries(cuda_u16_staging_equivalence PRIVATE motioncorr_core)
        add_test(NAME CudaU16StagingEquivalence COMMAND cuda_u16_staging_equivalence)
        set_tests_properties(CudaU16StagingEquivalence PROPERTIES LABELS "cuda;hardware")

        add_executable(cuda_wrapper_upload_failure tests/cuda_wrapper_upload_failure.cpp)
        target_link_libraries(cuda_wrapper_upload_failure PRIVATE motioncorr_core)
        target_link_options(cuda_wrapper_upload_failure PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree" "LINKER:--wrap=cudaMemcpy")
        add_test(NAME CudaWrapperUploadFailure COMMAND cuda_wrapper_upload_failure)
        set_tests_properties(CudaWrapperUploadFailure PROPERTIES LABELS "cuda;hardware")
        add_executable(cuda_fault_matrix tests/cuda_fault_matrix.cpp)
        target_link_libraries(cuda_fault_matrix PRIVATE motioncorr_core)
        target_link_options(cuda_fault_matrix PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cudaMemcpy" "LINKER:--wrap=cudaMemset"
            "LINKER:--wrap=cudaDeviceSynchronize"
            "LINKER:--wrap=cudaEventCreate" "LINKER:--wrap=cudaEventDestroy"
            "LINKER:--wrap=cufftCreate" "LINKER:--wrap=cufftDestroy"
            "LINKER:--wrap=cufftMakePlanMany" "LINKER:--wrap=cufftSetWorkArea"
            "LINKER:--wrap=cufftPlanMany" "LINKER:--wrap=cufftExecR2C"
            "LINKER:--wrap=cufftExecC2R"
            "LINKER:--wrap=cudaGetDeviceCount")
        add_test(NAME CudaFaultMatrix COMMAND cuda_fault_matrix)
        set_tests_properties(CudaFaultMatrix PROPERTIES LABELS "cuda;hardware")
        add_executable(cuda_patch_workspace tests/cuda_patch_workspace.cpp)
        target_link_libraries(cuda_patch_workspace PRIVATE motioncorr_core)
        target_link_options(cuda_patch_workspace PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cudaEventCreate" "LINKER:--wrap=cudaEventDestroy"
            "LINKER:--wrap=cufftCreate" "LINKER:--wrap=cufftMakePlanMany"
            "LINKER:--wrap=cufftDestroy")
        add_test(NAME CudaPatchWorkspace COMMAND cuda_patch_workspace)
        set_tests_properties(CudaPatchWorkspace PROPERTIES LABELS "cuda;hardware" TIMEOUT 120)
        # Batched local patch alignment: exactness against the per-patch path and
        # fault controls (docs/batched_patch_alignment.md).
        set(PATCH_BATCH_WRAPS
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cudaEventCreate" "LINKER:--wrap=cufftCreate"
            "LINKER:--wrap=cufftMakePlanMany" "LINKER:--wrap=cufftExecR2C"
            "LINKER:--wrap=cufftExecC2R")
        add_executable(cuda_patch_batch tests/cuda_patch_batch.cpp)
        target_link_libraries(cuda_patch_batch PRIVATE motioncorr_core)
        target_link_options(cuda_patch_batch PRIVATE ${PATCH_BATCH_WRAPS})
        add_test(NAME CudaPatchBatch COMMAND cuda_patch_batch)
        # Measurement only (low-VRAM Tier 2 decision, docs/perf_vram_tier1/report.md):
        # is the patch R2C bit-identical when not run as one batch-n plan? Not a test.
        add_executable(cuda_patch_fft_batch_probe tests/cuda_patch_fft_batch_probe.cpp)
        target_link_libraries(cuda_patch_fft_batch_probe PRIVATE CUDA::cudart CUDA::cufft)
        set_tests_properties(CudaPatchBatch PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        add_executable(cuda_vram_alias tests/cuda_vram_alias.cpp)
        target_link_libraries(cuda_vram_alias PRIVATE motioncorr_core)
        target_link_options(cuda_vram_alias PRIVATE "LINKER:--wrap=cudaMalloc")
        add_test(NAME CudaVramAlias COMMAND cuda_vram_alias)
        set_tests_properties(CudaVramAlias PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        # Compiled negative controls: a copy of one CUDA source with one line
        # rewritten, linked ahead of motioncorr_core so it replaces the original
        # object. Each must make the named test's exactness checks fail. A target
        # line that is missing or not unique stops the configure step, so a mutant
        # cannot silently become identical to the original.
        function(mc_cuda_mutant test_prefix test_source source_file mutant from to)
            set(_cu "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/${source_file}.cu")
            set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_cu}")
            file(READ "${_cu}" _source)
            string(FIND "${_source}" "${from}" _first)
            string(FIND "${_source}" "${from}" _last REVERSE)
            if(_first EQUAL -1 OR NOT _first EQUAL _last)
                message(FATAL_ERROR "mutant ${mutant}: target line missing or not unique in ${source_file}.cu")
            endif()
            string(REPLACE "${from}" "${to}" _mutant_source "${_source}")
            set(_mutant_cu "${CMAKE_CURRENT_BINARY_DIR}/mutants/${source_file}_${mutant}.cu")
            file(WRITE "${_mutant_cu}" "${_mutant_source}")
            get_filename_component(_exe "${test_source}" NAME_WE)
            add_executable(${_exe}_${mutant} ${test_source} "${_mutant_cu}")
            target_link_libraries(${_exe}_${mutant} PRIVATE motioncorr_core)
            target_link_options(${_exe}_${mutant} PRIVATE ${ARGN})
            add_test(NAME ${test_prefix}_${mutant} COMMAND ${_exe}_${mutant} --expect-mismatch)
            set_tests_properties(${test_prefix}_${mutant} PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        endfunction()
        # shift_retired: retired patches keep receiving phase shifts.
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch shift_retired
            "for (int j = 0; j < (int)active.size(); ++j) { const int p = active[j];"
            "for (int j = 0; j < n_patches; ++j) { const int p = j;" ${PATCH_BATCH_WRAPS})
        # never_retire: converged patches keep iterating.
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch never_retire
            "[&](int p) { return logs[p].converged; }"
            "[&](int p) { return logs[p].converged && false; }" ${PATCH_BATCH_WRAPS})
        # extract_no_remap: the window takes the first ccf_ny spectrum rows, not
        # the negative frequencies from the end.
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch extract_no_remap
            "int fy = (y > win_nfy_half) ? (y - win_nfy + nfy) : y;"
            "int fy = y;" ${PATCH_BATCH_WRAPS})
        # scale_divide: the extraction scale rounds differently from scaleComplexKernel.
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch scale_divide
            "make_float2(v.x * scale, v.y * scale)"
            "make_float2(v.x / (1.0f / scale), v.y / (1.0f / scale))" ${PATCH_BATCH_WRAPS})
        # shift_wrong_half / perpatch_wrong_half: the shift kernel wraps window
        # rows with the full spectrum's half height (batched / per-patch).
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch shift_wrong_half
            "ccf_nfx, ccf_nfy, ccf_nfy_half, n_frames);"
            "ccf_nfx, ccf_nfy, pny / 2, n_frames);" ${PATCH_BATCH_WRAPS})
        mc_cuda_mutant(CudaPatchBatchMutant tests/cuda_patch_batch.cpp cuda_alignpatch perpatch_wrong_half
            "const int data_nfy_half = data_nfy / 2;"
            "const int data_nfy_half = nfy / 2;" ${PATCH_BATCH_WRAPS})
        # arena_overlap: every carved buffer starts at the arena base.
        mc_cuda_mutant(CudaVramAliasMutant tests/cuda_vram_alias.cpp cuda_alignpatch arena_overlap
            "char *p = cursor; cursor += align_up(bytes); return p;"
            "char *p = cursor; cursor += 0 * align_up(bytes); return p;" "LINKER:--wrap=cudaMalloc")
        # arena_work_over_buffers: the cuFFT work area overlaps the carved buffers.
        mc_cuda_mutant(CudaVramAliasMutant tests/cuda_vram_alias.cpp cuda_alignpatch arena_work_over_buffers
            "work = arena_base + arena_need;"
            "work = arena_base;" "LINKER:--wrap=cudaMalloc")
        # refusal_off: readers of the borrowed real-space movie proceed.
        mc_cuda_mutant(CudaVramAliasMutant tests/cuda_vram_alias.cpp cuda_movie_session refusal_off
            "if (!real_frames_invalid_reason) return false;"
            "if (operation) return false;" "LINKER:--wrap=cudaMalloc")
        # dw_scratch_over_fourier: the dose-weighting scratch is carved from a
        # live buffer (the spectra it reads) instead of the dead real-space movie.
        mc_cuda_mutant(CudaVramAliasMutant tests/cuda_vram_alias.cpp cuda_movie_session dw_scratch_over_fourier
            "scratch.block = reinterpret_cast<char*>(d_Iframes);"
            "scratch.block = reinterpret_cast<char*>(d_Fframes);" "LINKER:--wrap=cudaMalloc")
        # Worker-lifetime device gain retention: the produced sum is the oracle,
        # so a wrongly reused or wrongly retired buffer changes pixels.
        add_executable(cuda_device_gain_pool tests/cuda_device_gain_pool.cpp)
        target_link_libraries(cuda_device_gain_pool PRIVATE motioncorr_core)
        target_link_options(cuda_device_gain_pool PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cudaMemcpy" "LINKER:--wrap=cudaSetDevice"
            "LINKER:--wrap=cudaGetDevice")
        add_test(NAME CudaDeviceGainPool COMMAND cuda_device_gain_pool)
        set_tests_properties(CudaDeviceGainPool PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        # Cleanup-origin fatal retirement is sticky; isolate this transition
        # from the other selector's earlier fatal retirement in its own process.
        add_test(NAME CudaDeviceGainCleanupFatal COMMAND cuda_device_gain_pool --case cleanup-fatal)
        set_tests_properties(CudaDeviceGainCleanupFatal PROPERTIES LABELS "cuda;hardware" TIMEOUT 120)
        # Worker-retained movie geometry: products identical fresh/retained/poisoned,
        # and the ledger shows the entry was taken, never aliased, never handed on
        # by a failed session.
        set(GEOMETRY_RETENTION_WRAPS "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cufftCreate")
        add_executable(cuda_geometry_retention tests/cuda_geometry_retention.cpp)
        target_link_libraries(cuda_geometry_retention PRIVATE motioncorr_core)
        target_link_options(cuda_geometry_retention PRIVATE ${GEOMETRY_RETENTION_WRAPS})
        add_test(NAME CudaGeometryRetention COMMAND cuda_geometry_retention)
        set_tests_properties(CudaGeometryRetention PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        # no_take: every movie allocates its own geometry (the predecessor behaviour).
        mc_cuda_mutant(CudaGeometryRetentionMutant tests/cuda_geometry_retention.cpp cuda_movie_session no_take
            "geometry.matches(device_id, nx, ny, n_frames);"
            "false && geometry.matches(device_id, nx, ny, n_frames);" ${GEOMETRY_RETENTION_WRAPS})
        # return_failed: a session with a recorded failure still returns its geometry.
        mc_cuda_mutant(CudaGeometryRetentionMutant tests/cuda_geometry_retention.cpp cuda_movie_session return_failed
            "if (is_initialized && !failure_state.hasFailed() &&"
            "if (is_initialized &&" ${GEOMETRY_RETENTION_WRAPS})
        # keep_taken_alias: a taken entry keeps its frame buffer in the pool slot.
        mc_cuda_mutant(CudaGeometryRetentionMutant tests/cuda_geometry_retention.cpp cuda_movie_session keep_taken_alias
            "        geometry.iframes = nullptr;"
            "        (void)0;" ${GEOMETRY_RETENTION_WRAPS})
        # Independent predecessor arithmetic and actual reconstruction ownership
        # for the experimental dose-denominator plane. Needs a real device.
        set_source_files_properties(tests/cuda_dose_normalization.cpp PROPERTIES LANGUAGE CUDA)
        add_executable(cuda_dose_normalization tests/cuda_dose_normalization.cpp)
        target_link_libraries(cuda_dose_normalization PRIVATE motioncorr_core)
        target_link_options(cuda_dose_normalization PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree"
            "LINKER:--wrap=cudaGetLastError" "LINKER:--wrap=cudaEventSynchronize"
            "LINKER:--wrap=cudaMemcpy" "LINKER:--wrap=cufftExecC2R"
            "LINKER:--wrap=cudaDeviceSynchronize" "LINKER:--wrap=cufftExecR2C"
            "LINKER:--wrap=cudaEventCreate" "LINKER:--wrap=cudaEventDestroy"
            "LINKER:--wrap=cufftCreate" "LINKER:--wrap=cufftDestroy")
        add_test(NAME CudaDoseNormalization COMMAND cuda_dose_normalization)
        set_tests_properties(CudaDoseNormalization PROPERTIES LABELS "cuda;hardware" TIMEOUT 900)
        add_test(NAME CudaDoseSessionPlan COMMAND cuda_dose_normalization --case borrowed)
        set_tests_properties(CudaDoseSessionPlan PROPERTIES LABELS "cuda;hardware" TIMEOUT 120)
        add_executable(motioncorr_retry_caller
            src/apps/run_motioncorr.cpp tests/cuda_retry_caller_shim.cpp)
        target_link_libraries(motioncorr_retry_caller PRIVATE motioncorr_core)
        target_link_options(motioncorr_retry_caller PRIVATE
            "LINKER:--wrap=_Z20cudaAlignPatchDeviceP6float2iiidRSt6vectorIdSaIdEES4_idiRSob"
            "LINKER:--wrap=_Z33cudaAlignPatchDeviceWithWorkspaceR23PatchAlignmentWorkspaceP6float2iiidRSt6vectorIdSaIdEES6_idiRSob"
            "LINKER:--wrap=_Z25cudaAlignPatchBatchDeviceR30BatchedPatchAlignmentWorkspaceiiiidPSt6vectorIdSaIdEES4_idiP13PatchBatchLog"
            "LINKER:--wrap=_Z14cudaAlignPatchRSt6vectorI13MultidimArrayI8tComplexIfEESaIS3_EEiidRS_IdSaIdEES9_idiRSob")
        # Issue #69 P1c: the REAL motioncorr binary with an interposed cudaMalloc, so
        # the fallback cudaPreparePatch boundary and the runner's post-prep enforcement
        # are exercised in production code rather than simulated by a predicate test.
        # The shim is linked only here; src/ contains no fault switch.
        add_executable(motioncorr_faultinject
            src/apps/run_motioncorr.cpp tests/cuda_fault_inject_shim.cpp)
        target_link_libraries(motioncorr_faultinject PRIVATE motioncorr_core)
        target_link_libraries(motioncorr_faultinject PRIVATE ${CMAKE_DL_LIBS})
        target_link_options(motioncorr_faultinject PRIVATE
            "-rdynamic"
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaMemcpy"
            "LINKER:--wrap=cudaFree" "LINKER:--wrap=cudaGetLastError"
            "LINKER:--wrap=cudaDeviceSynchronize" "LINKER:--wrap=cudaGetDeviceCount"
            # cudaStreamSynchronize reaches the ingest scratch teardown, which runs
            # after the worker has already chosen its return value; TIFFOpen reaches
            # the multi-threaded strip reader, where some threads holding a handle
            # and some not is the state that used to deadlock the OpenMP team.
            "LINKER:--wrap=cudaStreamSynchronize" "LINKER:--wrap=TIFFOpen")
        add_test(NAME CudaPreprocessingFailurePaths
            COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_preprocessing_failure_controls.py
                --binary $<TARGET_FILE:motioncorr_faultinject>)
        set_tests_properties(CudaPreprocessingFailurePaths PROPERTIES
            LABELS "cuda;hardware" TIMEOUT 900)
        # The same two reconstruction-cleanup controls on the nvCOMP ingest arm.
        # run_preprocessing_failure_controls.py builds its fixture with
        # TIFFTAG_COMPRESSION = 1, so the fast path declines it and
        # unweighted-release-fatal / dw-release-fatal have only ever run on the
        # compact-U16 arm, which keeps a host movie. The nvCOMP arm keeps none,
        # and the reconstruction fallback is exactly where that was a
        # std::terminate before this branch, so this is a different test rather
        # than a repetition. Writes its own Adobe Deflate RowsPerStrip=1 fixture
        # and pins --ingest nvcomp, so an ineligible fixture fails the run
        # instead of quietly falling back to the arm it is meant to replace.
        #
        # Not in DEFAULT_REQUIRED_TESTS, for the same reason
        # CudaPreprocessingFailurePaths is not: it needs a GPU and a USE_NVCOMP
        # build, and a CPU-only configuration would fail the collection gate on
        # a test it cannot run.
        if(USE_NVCOMP)
            set_source_files_properties(tests/cuda_adler32.cpp PROPERTIES LANGUAGE CUDA)
            add_executable(cuda_adler32 tests/cuda_adler32.cpp)
            target_link_libraries(cuda_adler32 PRIVATE motioncorr_core)
            add_test(NAME CudaAdler32 COMMAND cuda_adler32)
            set_tests_properties(CudaAdler32 PROPERTIES LABELS "cuda;hardware" TIMEOUT 120)
            add_executable(motioncorr_nvcomp_acceptance
                src/apps/run_motioncorr.cpp tests/cuda_nvcomp_acceptance_shim.cpp)
            target_link_libraries(motioncorr_nvcomp_acceptance PRIVATE motioncorr_core ${CMAKE_DL_LIBS})
            target_link_options(motioncorr_nvcomp_acceptance PRIVATE
                "-rdynamic" "LINKER:--wrap=cudaMemcpyAsync" "LINKER:--wrap=cudaLaunchKernel")
            add_test(NAME CudaNvcompAcceptanceFailures
                COMMAND ${Python3_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_nvcomp_acceptance_controls.py
                    --binary $<TARGET_FILE:motioncorr_nvcomp_acceptance>)
            set_tests_properties(CudaNvcompAcceptanceFailures PROPERTIES
                LABELS "cuda;hardware" TIMEOUT 600)
            add_test(NAME CudaNvcompReconstructionFailures
                COMMAND ${Python3_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_nvcomp_reconstruction_controls.py
                    --binary $<TARGET_FILE:motioncorr_faultinject>)
            set_tests_properties(CudaNvcompReconstructionFailures PROPERTIES
                LABELS "cuda;hardware" TIMEOUT 900)
        endif()
        # Dose-weighting scratch alias (docs/vram_live_ranges.md). The mutant runner
        # carves the scratch from the real-space movie even when --save_noDW or
        # --even_odd_split still needs it; its products stay correct, so the
        # per-movie borrow line is the only witness and the control checks it.
        set(_runner "${CMAKE_CURRENT_SOURCE_DIR}/src/motioncorr_runner.cpp")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_runner}")
        file(READ "${_runner}" _runner_source)
        set(_from "poly_model, !pre_dw_sum_needed);")
        string(FIND "${_runner_source}" "${_from}" _first)
        string(FIND "${_runner_source}" "${_from}" _last REVERSE)
        if(_first EQUAL -1 OR NOT _first EQUAL _last)
            message(FATAL_ERROR "dw alias mutant: target line missing or not unique in motioncorr_runner.cpp")
        endif()
        string(REPLACE "${_from}" "poly_model, true);" _runner_source "${_runner_source}")
        file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/mutants/motioncorr_runner_dw_alias.cpp" "${_runner_source}")
        # The mutant object defines every symbol of the archive's runner object, so
        # the linker never pulls the original from motioncorr_core.
        add_executable(motioncorr_dw_alias_mutant src/apps/run_motioncorr.cpp
            "${CMAKE_CURRENT_BINARY_DIR}/mutants/motioncorr_runner_dw_alias.cpp")
        target_compile_definitions(motioncorr_dw_alias_mutant PRIVATE HAVE_TIFF HAVE_PNG HAVE_JPEG)
        target_link_libraries(motioncorr_dw_alias_mutant PRIVATE motioncorr_core)
        add_test(NAME CudaDoseWeightAlias
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_dw_alias_controls.py
                --binary $<TARGET_FILE:motioncorr>
                --mutant-binary $<TARGET_FILE:motioncorr_dw_alias_mutant>)
        set_tests_properties(CudaDoseWeightAlias PROPERTIES LABELS "cuda;hardware" TIMEOUT 300)
        # Driven by tests/run_fallback_boundary_control.sh, which needs a device and a
        # movie, so it is not registered as a bare ctest case.
        # Optional Issue #85 lane C native failure matrix. Supplying the known
        # uint16 TIFF fixture opts into this hardware test; ordinary CI and CPU-only
        # CTest collection do not require the external data.
        set(MOTIONCORR_U16_TEST_MOVIE "" CACHE FILEPATH
            "Optional uint16 TIFF fixture for the native lane-C failure matrix")
        set(MOTIONCORR_U16_TEST_STAGE_BYTES "28477960" CACHE STRING
            "Bytes in one uint16 frame for MOTIONCORR_U16_TEST_MOVIE")
        if(MOTIONCORR_U16_TEST_MOVIE)
            if(NOT EXISTS "${MOTIONCORR_U16_TEST_MOVIE}")
                message(FATAL_ERROR "MOTIONCORR_U16_TEST_MOVIE does not exist: ${MOTIONCORR_U16_TEST_MOVIE}")
            endif()
            find_program(BASH_EXECUTABLE bash REQUIRED)
            add_test(NAME CudaU16FailurePaths
                COMMAND ${BASH_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tests/run_u16_failure_controls.sh
                    $<TARGET_FILE:motioncorr_faultinject>
                    ${MOTIONCORR_U16_TEST_MOVIE} ${MOTIONCORR_U16_TEST_STAGE_BYTES}
                    ${CMAKE_CURRENT_SOURCE_DIR}/docs/issue85_laneC/compare_output_trees.py)
            set_tests_properties(CudaU16FailurePaths PROPERTIES
                LABELS "cuda;hardware" TIMEOUT 900)
        endif()
        # Issue #69. Pure predicate over cudaError_t plus the host-only failure state:
        # needs the CUDA headers, needs no device.
        add_executable(cuda_error_class tests/cuda_error_class.cpp)
        target_link_libraries(cuda_error_class PRIVATE motioncorr_core)
        add_test(NAME CudaErrorClass COMMAND cuda_error_class)
        set_tests_properties(CudaErrorClass PROPERTIES LABELS "cuda")
    endif()
endif()
