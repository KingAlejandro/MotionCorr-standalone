#!/bin/bash
# Read-only identity records on cpu64 for the pinned build, tools, interpreter, baseline and fixtures. Creates nothing under the baseline or fixture trees.
set -u
R=/tmp/motioncorr-lfw-capture-20261027; B=$R/build
echo "utc $(date -u +%FT%TZ) host $(hostname)"
echo "--- binaries"; sha256sum $B/motioncorr $B/local_ccf_capture $B/local_b2_fit $B/ccf_dc_hook $B/patch_retry_state $B/global_half_gain $B/coupled_peak $B/local_full_width_weight $R/receipts/weight_control/weight_control; ls -l $B/motioncorr
echo "--- shared libraries of motioncorr"; ldd $B/motioncorr | awk '{print $3}' | grep '^/' | sort -u | while read l; do r=$(readlink -f "$l"); printf '%s -> %s  ' "$l" "$r"; sha256sum "$r" | cut -c1-64; done
echo "--- loader"; ls -l /lib64/ld-linux-x86-64.so.2; sha256sum $(readlink -f /lib64/ld-linux-x86-64.so.2) | cut -c1-64
echo "--- toolchain"; g++ --version | head -1; /home/ubuntu/.mc-venv/bin/cmake --version | head -1; /home/ubuntu/.mc-venv/bin/python3 -c "import sys,numpy,hashlib;print('python',sys.version.split()[0],sys.executable,'numpy',numpy.__version__);print('numpy/__init__.py',hashlib.sha256(open(numpy.__file__,'rb').read()).hexdigest())"
readlink -f /home/ubuntu/.mc-venv/bin/python3; sha256sum $(readlink -f /home/ubuntu/.mc-venv/bin/python3) | cut -c1-64; cat /home/ubuntu/.mc-venv/bin/cmake | head -5; sha256sum /home/ubuntu/.mc-venv/bin/cmake | cut -c1-64
echo "--- cmake cache and flags"; sha256sum $B/CMakeCache.txt; grep -E 'CMAKE_BUILD_TYPE|CMAKE_CXX_COMPILER:|MC_EXPERIMENT_CCF_DC:|CUDA:|CMAKE_HOME_DIRECTORY|BUILD_TESTING|CMAKE_CXX_FLAGS_RELEASE' $B/CMakeCache.txt
cat $B/CMakeFiles/motioncorr_core.dir/flags.make | sed -n 3,9p; cat $B/CMakeFiles/motioncorr.dir/link.txt | cut -c1-500
echo "--- compiled objects"; grep -c 'Building CXX object' $R/receipts/build.log; grep 'Building CXX object' $R/receipts/build.log | sed 's/.*Building CXX object //' | sort | sha256sum
echo "--- source identity"; python3 -B $R/prep/verify_source.py $R/source $R/prep/source.blobs
echo "--- comparator (new tree vs the tree of the sealed pilot)"; sha256sum $R/source/docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py /tmp/motioncorr-lfw-v5-20261026/source/docs/post_rc0/s1/global_damping_20261026/scripts/compare_products.py
echo "--- sealed baseline noisy ON (original root, read-only)"; BD=/tmp/motioncorr-lfw-v5-20261026/evidence/noisy/ON
find $BD -type l | wc -l; (cd $BD && find . -type f | sort | xargs sha256sum); stat -c '%A %U %n' $BD $BD/output $BD/input
echo "--- fixture sources"; sha256sum /tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures/noisy.star /tmp/motioncorr-damping-a1c78adc1d0f/v2/v2fixtures/noisy.mrcs /tmp/motioncorr-local-ccf-20261026/native-input/noisy.star /tmp/motioncorr-local-ccf-20261026/native-input/noisy.mrcs
echo "--- baseline input dir symlinks"; find $BD/input -type l | wc -l
echo "--- no capture or output dirs exist for the future jobs"; ls -d $R/evidence $R/native-input 2>&1 | head
