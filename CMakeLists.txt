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
    enable_language(CUDA)
    if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
        set(CMAKE_CUDA_ARCHITECTURES 80)
    endif()
    set(CMAKE_CUDA_STANDARD 17)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)
    find_package(CUDAToolkit REQUIRED)
    target_compile_definitions(motioncorr_core PUBLIC _CUDA_ENABLED)
    target_sources(motioncorr_core PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_alignpatch.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_realspace_dw.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_fft_prep.cu"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/acc/cuda/cuda_movie_session.cu")
    target_link_libraries(motioncorr_core PUBLIC CUDA::toolkit CUDA::cudart CUDA::cufft)
endif()

add_executable(motioncorr src/apps/run_motioncorr.cpp)
target_link_libraries(motioncorr PRIVATE motioncorr_core)
install(TARGETS motioncorr RUNTIME DESTINATION bin)

include(CTest)
if(BUILD_TESTING)
    add_executable(runner_numerics tests/test_runner_numerics.cpp)
    target_link_libraries(runner_numerics PRIVATE motioncorr_core)
    add_executable(defect_parser tests/test_defect_parser.cpp)
    target_link_libraries(defect_parser PRIVATE motioncorr_core)
    add_test(NAME DefectParser COMMAND defect_parser)
    # The malformed-input cases hang the pre-#98 parser; bound them so a
    # regression fails the suite instead of stalling it.
    set_tests_properties(DefectParser PROPERTIES TIMEOUT 120)
    # Pure C++ regression (issue #97); registered here beside the other native test,
    # ahead of the Python/numpy probe, since it needs neither.
    add_test(NAME RunnerInterpolateRecenter
        COMMAND $<TARGET_FILE:runner_numerics> interpolate_recenter)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
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
        add_test(NAME GlobalIfftElision
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_global_ifft_elision.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME RunnerModelParser
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runner_contract.py
                --binary $<TARGET_FILE:motioncorr> --helper $<TARGET_FILE:runner_numerics> --case model_parser)
        add_test(NAME WriteFaults
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_write_faults.py
                --binary $<TARGET_FILE:motioncorr>)
        add_test(NAME CiFailClosedControls
            COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/test_ci_fail_closed.py)
    # Injects short and deferred write failures with setrlimit(RLIMIT_FSIZE),
    # so it needs POSIX resource limits and an ignorable SIGXFSZ.
    if(UNIX)
        add_executable(image_write_faults tests/test_image_write_faults.cpp)
        target_link_libraries(image_write_faults PRIVATE motioncorr_core)
        add_test(NAME ImageWriteFaults COMMAND image_write_faults)
    endif()
endif()
if(BUILD_TESTING AND CUDA)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_executable(cuda_wrapper_upload_failure tests/cuda_wrapper_upload_failure.cpp)
        target_link_libraries(cuda_wrapper_upload_failure PRIVATE motioncorr_core)
        target_link_options(cuda_wrapper_upload_failure PRIVATE
            "LINKER:--wrap=cudaMalloc" "LINKER:--wrap=cudaFree" "LINKER:--wrap=cudaMemcpy")
        add_test(NAME CudaWrapperUploadFailure COMMAND cuda_wrapper_upload_failure)
        set_tests_properties(CudaWrapperUploadFailure PROPERTIES LABELS "cuda;hardware")
    endif()
endif()
