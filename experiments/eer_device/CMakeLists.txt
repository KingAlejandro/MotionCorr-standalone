# Standalone build of the device-EER feasibility experiment (#193 option 2).
# Not referenced by the top-level CMakeLists.txt and not built by the main build.
#   cmake -S experiments/eer_device -B <build> -DCMAKE_BUILD_TYPE=Release
# The host reference is src/renderEER.cpp compiled from the same tree, linked unmodified.
cmake_minimum_required(VERSION 3.21)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    # An unqualified build is -O0 and inflates every host-side number.
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()
project(eer_device_experiment LANGUAGES C CXX CUDA)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_C_STANDARD 99)
if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
    set(CMAKE_CUDA_ARCHITECTURES 80)
endif()
get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FFTW_DOUBLE REQUIRED IMPORTED_TARGET fftw3)
pkg_check_modules(FFTW_FLOAT REQUIRED IMPORTED_TARGET fftw3f)
find_package(OpenMP REQUIRED COMPONENTS CXX)
find_package(TIFF REQUIRED)
find_package(PNG REQUIRED)
find_package(JPEG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(CUDAToolkit REQUIRED)

set(RELION_VERSION_SUFFIX "-motioncorr-standalone")
configure_file("${REPO_ROOT}/src/macros.cpp.in" "${CMAKE_CURRENT_BINARY_DIR}/macros.cpp" @ONLY)
file(GLOB_RECURSE HOST_SOURCES CONFIGURE_DEPENDS
    "${REPO_ROOT}/src/*.cpp" "${REPO_ROOT}/src/*.cc" "${REPO_ROOT}/src/*.c")
list(REMOVE_ITEM HOST_SOURCES "${REPO_ROOT}/src/apps/run_motioncorr.cpp")
add_library(eer_host_core STATIC ${HOST_SOURCES} "${CMAKE_CURRENT_BINARY_DIR}/macros.cpp")
target_include_directories(eer_host_core PUBLIC "${REPO_ROOT}")
target_compile_definitions(eer_host_core PRIVATE HAVE_TIFF HAVE_PNG HAVE_JPEG)
target_link_libraries(eer_host_core PUBLIC PkgConfig::FFTW_DOUBLE PkgConfig::FFTW_FLOAT
    OpenMP::OpenMP_CXX TIFF::TIFF PNG::PNG JPEG::JPEG ZLIB::ZLIB)

add_library(eerdev STATIC eer_device.cu)
target_link_libraries(eerdev PUBLIC CUDA::cudart)

add_executable(eer_device_exp eer_exp.cpp eer_fixture.cpp)
target_compile_definitions(eer_device_exp PRIVATE HAVE_TIFF)
target_link_libraries(eer_device_exp PRIVATE eerdev eer_host_core CUDA::cudart)

# Host-weakness probe: the same renderEER.cpp, instrumented with AddressSanitizer.
# Other sources come from eer_host_core; this object comes first on the link line.
add_executable(eer_device_exp_asan eer_exp.cpp eer_fixture.cpp "${REPO_ROOT}/src/renderEER.cpp")
target_compile_definitions(eer_device_exp_asan PRIVATE HAVE_TIFF)
target_compile_options(eer_device_exp_asan PRIVATE -fsanitize=address -fno-omit-frame-pointer -g)
target_link_options(eer_device_exp_asan PRIVATE -fsanitize=address)
target_link_libraries(eer_device_exp_asan PRIVATE eerdev eer_host_core CUDA::cudart)
