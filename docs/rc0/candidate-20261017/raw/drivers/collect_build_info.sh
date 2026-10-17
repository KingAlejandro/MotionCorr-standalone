#!/bin/bash
# Candidate build provenance (host side). Read-only: inspects the workspace, builds and host.
set -u
W=${QF_W:?}
cd "$W"
{
echo "collected $(date -u +%FT%TZ)"
echo "host $(hostname) kernel $(uname -r)"
grep PRETTY_NAME /etc/os-release
lscpu | grep -E "Model name|NUMA node[0-9]"
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv,noheader
/usr/local/cuda-12.8/bin/nvcc --version | tail -2
g++ --version | head -1
cmake --version | head -1
ldd --version | head -1
/home/alex/.mc-venv/bin/python3 -c "import sys,numpy;print('python',sys.version.split()[0],'numpy',numpy.__version__)"
echo "ghostscript $(gs --version)"
echo "THP enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
echo "GLIBC_TUNABLES=${GLIBC_TUNABLES:-<unset>}"
echo "decoders: xz=$(command -v xz) bzip2=$(command -v bzip2) zstd=$(command -v zstd) pbzip2=$(command -v pbzip2 || echo ABSENT)"
echo "--- dpkg"
dpkg-query -W -f='${Package} ${Version}\n' 'libfftw3*' 'libtiff*' 'libdeflate*' 'zlib1g*' 'libpng16*' 'libjpeg*' 'libgomp1' 'libstdc++6' 'libzstd1' 'liblzma5' 'libjbig0' 'libwebp7' 'liblerc4' 2>/dev/null | grep -v '^\S* $'
echo "--- nvCOMP"
NVC=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
grep -hE "#define NVCOMP_VER_(MAJOR|MINOR|PATCH|BUILD)" $NVC/include/nvcomp/version.h 2>/dev/null
ls $NVC/lib | head
echo "--- source"
echo "src HEAD $(git -C src rev-parse HEAD) branch $(git -C src rev-parse --abbrev-ref HEAD) modified=$(git -C src status --porcelain | wc -l)"
echo "QF_SHA ${QF_SHA:-<unset>}"
echo "--- binaries"
for b in cpu cuda nvcomp; do
  for e in motioncorr motioncorr_faultinject motioncorr_resident_retry_fault; do
    [ -f build-$b/$e ] && sha256sum build-$b/$e
  done
done
echo "--- flags (motioncorr target and core library)"
for b in cpu cuda nvcomp; do
  for t in motioncorr motioncorr_core; do
    f=build-$b/CMakeFiles/$t.dir/flags.make
    [ -f $f ] && grep -E "^(CXX_FLAGS|CUDA_FLAGS|CXX_DEFINES|CUDA_DEFINES) " $f | sed "s#^#$b/$t: #"
  done
done
echo "--- cache"
for b in cpu cuda nvcomp; do
  grep -E "^(CMAKE_BUILD_TYPE|CMAKE_CXX_COMPILER|CMAKE_CUDA_COMPILER|CMAKE_CUDA_ARCHITECTURES|CUDA|USE_NVCOMP|NVCOMP_ROOT|MOTIONCORR_CPU_DOSE_SYMMETRY|MC_REQUIRE_ALL_DECODERS|MC_REAL_CUTDOWN_DIR|BUILD_TESTING|CMAKE_HOME_DIRECTORY):" build-$b/CMakeCache.txt | sed "s#^#$b: #"
done
echo "--- configure status lines"
for b in cpu cuda nvcomp; do
  grep -E "dose weighting|Deflate subcodec|not found|Found (fftw|TIFF|ZLIB|PNG|JPEG|OpenMP|CUDAToolkit|Python3)|nvCOMP|fftw3" logs/configure-$b.log | sed "s#^#$b: #"
done
echo "--- linked libraries"
for b in cpu cuda nvcomp; do
  echo "[$b]"; LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$NVC/lib ldd build-$b/motioncorr | sed 's/ (0x[0-9a-f]*)//'
done
echo "--- ctest -N"
for b in cpu cuda nvcomp; do echo "$b: $(ctest --test-dir build-$b -N | tail -1)"; done
} > logs/build-info.txt 2>&1
echo written logs/build-info.txt
