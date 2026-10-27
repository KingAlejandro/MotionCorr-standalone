#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r2; mkdir -p $W/san
FL="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -std=gnu++17 -arch arm64 -Xpreprocessor -fopenmp -DMC_EXPERIMENT_CCF_DC -I/opt/homebrew/opt/libomp/include -I$W/src -isystem /opt/homebrew/Cellar/fftw/3.3.11/include -isystem /opt/homebrew/include"
LIBS="$W/build/libmotioncorr_core.a /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3.dylib /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3f.dylib /opt/homebrew/opt/libomp/lib/libomp.dylib /opt/homebrew/lib/libtiff.dylib /opt/homebrew/lib/libpng.dylib /opt/homebrew/lib/libjpeg.dylib -lz"
c++ $FL $W/src/tests/test_local_ccf_capture.cpp -o $W/san/unit_san $LIBS 2> $W/san/build.log; echo san_build_rc=$?
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=print_stacktrace=1 OMP_NUM_THREADS=2 $W/san/unit_san > $W/san/run.out 2>&1; echo san_run_rc=$?; tail -2 $W/san/run.out | cut -c1-200
