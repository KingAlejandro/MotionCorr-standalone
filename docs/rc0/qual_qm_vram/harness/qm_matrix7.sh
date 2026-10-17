#!/bin/bash
cd /mnt/clathrin/alex-motioncorr-rc0/W-QM
PY=/home/alex/.mc-venv/bin/python3
flock /tmp/motioncorr-gpu1-correctness.lock $PY -I qm_bisect.py e10216 L auto completes 4 7
mkdir -p final
{
echo "source_sha=$(git -C src rev-parse HEAD)"
echo "binary_sha256=$(sha256sum build-nvcomp/motioncorr | cut -d' ' -f1)"
echo "balloon_sha256=$(sha256sum balloon | cut -d' ' -f1)"
nvidia-smi -i 1 --query-gpu=name,uuid,driver_version,memory.total --format=csv,noheader
nvcc_v=$(/usr/local/cuda-12.8/bin/nvcc --version | tail -1); echo "nvcc=$nvcc_v"
echo "nvcomp=5.3.0.16 cuda12 (~/nvcomp53)"
grep -E "CMAKE_BUILD_TYPE|USE_NVCOMP|CMAKE_CUDA_ARCHITECTURES|^CUDA:" build-nvcomp/CMakeCache.txt
uname -r; hostname
} > final/env.txt 2>&1
V=/home/alex/motioncorr-validation-20261011-vm
D=W-QM/dataroot
: > final/input_sha256.txt
for f in $V/corpus/data-https/EMPIAR-10441/data/frames/20May09_3A-3_109-21_0003.tif \
         $V/corpus/data-https/EMPIAR-10441/data/frames/200509_gain.mrc \
         "$V/corpus/data-https/EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer" \
         $V/corpus/data-https/EMPIAR-10361/data/PS_18_2_4/PS.18.2.4_CTEM_103-12_0007_Jan20_08.57.33.tif \
         $V/tutorial-data/Movies/20170629_00026_frameImage.tiff $V/tutorial-data/Movies/gain.mrc \
         /mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data/EMPIAR-10216/data/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc; do
  taskset -c 104-111 sha256sum "$f" >> final/input_sha256.txt
done
echo M7_DONE
