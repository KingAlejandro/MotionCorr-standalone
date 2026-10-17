#!/bin/bash
D=/mnt/clathrin/alex-motioncorr-rc0/W-TIFF
while ! flock -n /tmp/motioncorr-bench.lock true; do echo "bench lock held; waiting 60 s $(date -u +%FT%TZ)"; sleep 60; done
export PATH=/home/alex/mc-env/bin:/usr/local/cuda-12.8/bin:$PATH
rm -rf $D/build-mut-rowoffset
cmake -S $D/mut-rowoffset -B $D/build-mut-rowoffset -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/home/alex/mc-env/bin/python3 -DCUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc -DCUDAToolkit_ROOT=/usr/local/cuda-12.8 -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON -DNVCOMP_ROOT=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive > $D/configure-mut.log 2>&1; echo "configure rc=$?" > $D/build-mut.rc
cmake --build $D/build-mut-rowoffset -j8 --target motioncorr > $D/build-mut.log 2>&1; echo "build rc=$?" >> $D/build-mut.rc
