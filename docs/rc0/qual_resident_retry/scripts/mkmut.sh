#!/bin/bash
# usage: mkmut.sh <m3|m4>   builds target motioncorr of src-mut with one mutation of downloadPatchSpectra
S=/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q
cd $S
until flock -n /tmp/motioncorr-bench.lock true; do echo "$(date -u +%T) bench held" >> mut-wait.log; sleep 60; done
if [ ! -d src-mut ]; then mkdir src-mut && tar -xf src-1db86902.tar -C src-mut; fi
cp src-1db86902/src/acc/cuda/cuda_movie_session.cu src-mut/src/acc/cuda/cuda_movie_session.cu
python3 - $1 <<'PY'
import sys
p='/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/src-mut/src/acc/cuda/cuda_movie_session.cu'
s=open(p).read()
if sys.argv[1]=='m3':
    old='d_fpatches + (size_t)igroup * patch_h * patch_nfx, sz_patch_comp,'
    new='d_fpatches, sz_patch_comp,'
else:
    old='''    bool ok = preparePatchInVram(x_start, y_start, patch_w, patch_h, n_groups,
                                 group_start, group_size, d_fpatches);'''
    new='''    std::vector<int> equal_size(n_groups, group_size[0]);
    bool ok = preparePatchInVram(x_start, y_start, patch_w, patch_h, n_groups,
                                 group_start, equal_size.data(), d_fpatches);'''
assert s.count(old)==1, 'mutation target missing/not unique'
open(p,'w').write(s.replace(old,new))
PY
[ $? = 0 ] || exit 3
if [ ! -d build/cuda-mut ]; then
  taskset -c 80-87 cmake -S src-mut -B build/cuda-mut -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/home/alex/mc-env/bin/python3 -DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive > build/cuda-mut.configure.log 2>&1
fi
taskset -c 80-87 cmake --build build/cuda-mut -j8 --target motioncorr > build/cuda-mut-$1.build.log 2>&1
echo "build $1 rc=$?" >> build/cuda-mut.status
cp build/cuda-mut/motioncorr build/motioncorr-mut-$1
sha256sum build/motioncorr-mut-$1 >> build/cuda-mut.status
