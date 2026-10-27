#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r2; cd $W/dump
FL="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -Xpreprocessor -fopenmp -DMC_EXPERIMENT_CCF_DC -I/opt/homebrew/opt/libomp/include -isystem /opt/homebrew/Cellar/fftw/3.3.11/include -isystem /opt/homebrew/include"
LIBS="$W/build/libmotioncorr_core.a /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3.dylib /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3f.dylib /opt/homebrew/opt/libomp/lib/libomp.dylib /opt/homebrew/lib/libtiff.dylib /opt/homebrew/lib/libpng.dylib /opt/homebrew/lib/libjpeg.dylib -lz"
c++ $FL -I$W/oldinc -I$W/src dump_legacy.cpp -o dump_old $LIBS 2>old_build.log; echo old_build_rc=$?
c++ $FL -I$W/src dump_legacy.cpp -o dump_new $LIBS 2>new_build.log; echo new_build_rc=$?
rm -rf out_old out_new; export OMP_NUM_THREADS=2
./dump_old $W/dump/out_old; echo run_old_rc=$?; ./dump_new $W/dump/out_new; echo run_new_rc=$?
echo files_old=$(find out_old -type f | wc -l) files_new=$(find out_new -type f | wc -l)
diff -r out_old out_new && echo LEGACY_BYTES_IDENTICAL
