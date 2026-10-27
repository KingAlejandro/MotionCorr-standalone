#!/bin/bash
set -u
W=/tmp/mc-capext-20261027-r2; M=$W/mut; rm -rf $M; mkdir -p $M
FL="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -Xpreprocessor -fopenmp -DMC_EXPERIMENT_CCF_DC -I/opt/homebrew/opt/libomp/include -isystem /opt/homebrew/Cellar/fftw/3.3.11/include -isystem /opt/homebrew/include"
LIBS="$W/build/libmotioncorr_core.a /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3.dylib /opt/homebrew/Cellar/fftw/3.3.11/lib/libfftw3f.dylib /opt/homebrew/opt/libomp/lib/libomp.dylib /opt/homebrew/lib/libtiff.dylib /opt/homebrew/lib/libpng.dylib /opt/homebrew/lib/libjpeg.dylib -lz"
H=$W/src/src/local_ccf_capture.h
run_unit() { # name, python-replace-old, python-replace-new
  name=$1; mkdir -p $M/$name/src
  python3 - "$H" "$M/$name/src/local_ccf_capture.h" "$2" "$3" <<'PY'
import sys
s=open(sys.argv[1]).read(); old,new=sys.argv[3],sys.argv[4]
assert s.count(old)==1,(old,s.count(old)); open(sys.argv[2],'w').write(s.replace(old,new))
PY
  [ $? -eq 0 ] || { echo "$name: MUTATION NOT APPLIED"; return; }
  c++ $FL -I$M/$name -I$W/src $W/src/tests/test_local_ccf_capture.cpp -o $M/$name/unit $LIBS 2> $M/$name/build.log || { echo "$name: BUILD FAILED"; return; }
  OMP_NUM_THREADS=2 $M/$name/unit > $M/$name/out.txt 2>&1; echo "$name: unit rc=$? :: $(tail -1 $M/$name/out.txt | cut -c1-140)"
}
echo "control (unmutated header through the same path):"
mkdir -p $M/ctl/src; cp $H $M/ctl/src/; c++ $FL -I$M/ctl -I$W/src $W/src/tests/test_local_ccf_capture.cpp -o $M/ctl/unit $LIBS 2>/dev/null && (OMP_NUM_THREADS=2 $M/ctl/unit | tail -1 | cut -c1-60; echo "ctl rc=${PIPESTATUS[0]}")
run_unit m2_select_wrong_coordinate '((cx == 104 && cy == 15) || (cx == 62 && cy == 79))' '((cx == 62 && cy == 47) || (cx == 62 && cy == 79))'
run_unit m3_no_duplicate_check 'LocalCcfDiagnostic::require(!was_seen,"duplicate selected patch");' ''
run_unit m4_no_weight_norm_check 'require(mode==Mode::Legacy||weight_x_norm==RFLOAT(nx),"full-width capture requires the full-width weight normalisation x_norm = pnx");' ''
run_unit m5_legacy_schema_changed 'local-ccf-capture/1' 'local-ccf-capture/9'
run_unit m6_no_missing_patch_check 'require(seen[0]&&seen[1]&&states.size()==2,"selected patch coverage missing");' 'require(states.size()>=1,"selected patch coverage missing");'
run_unit m7_no_centre_extent_check 'require(mode==Mode::Legacy||((xs+xe-1)/2==cx&&(ys+ye-1)/2==cy),"centre does not match patch extents");' ''
