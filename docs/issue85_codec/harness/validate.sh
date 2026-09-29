#!/bin/bash
# Issue #85 codec arms: build the final source, prove the configure probe
# against runtime ground truth, run the required suite under both LibTIFF
# builds, and compare every product across arms.
set -u
WD=/home/ubuntu/mc-i85-codec-20260929
export PATH=/home/ubuntu/.mc-venv/bin:$PATH
CM=/home/ubuntu/.mc-venv/bin/cmake
PY=/home/ubuntu/.mc-venv/bin/python3
V="$WD/validation"; mkdir -p "$V"
BASE_BIN_SHA=d884fb5d2e45824849734447779b58934bfff83c84cd127dd9a9622d7101f1f5

echo "### 1. apply final source and rebuild in place"
cd "$WD/src" && patch -p1 --forward < "$WD/mc85.patch" > "$V/patch.log" 2>&1; echo "patch_rc=$?"
cd "$WD"
taskset -c 32-47 $CM -S src -B build-sys -DCMAKE_BUILD_TYPE=Release -DTIMING=ON \
    -DPython3_EXECUTABLE=$PY > "$V/configure_final.log" 2>&1; echo "configure_rc=$?"
grep -E "Deflate subcodec|TIFF_HAS_LIBDEFLATE" "$V/configure_final.log"
taskset -c 32-47 $CM --build build-sys -j 16 > "$V/build_final.log" 2>&1; echo "build_rc=$?"
NEW=$(sha256sum build-sys/motioncorr | cut -d' ' -f1)
echo "motioncorr_sha256=$NEW"
[ "$NEW" = "$BASE_BIN_SHA" ] && echo "BINARY_IDENTICAL_TO_MEASURED=yes" || echo "BINARY_IDENTICAL_TO_MEASURED=no"

echo "### 2. configure probe negative control (zlib-only LibTIFF)"
rm -rf "$WD/build-probe-zlib"
taskset -c 32-47 $CM -S src -B "$WD/build-probe-zlib" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$WD/tiff-zlib" -DBUILD_TESTING=OFF > "$V/configure_zlibarm.log" 2>&1
echo "configure_rc=$?"
grep -E "Deflate subcodec|Performing Test TIFF_HAS_LIBDEFLATE|zlib here" "$V/configure_zlibarm.log"
grep -m1 "TIFF_INCLUDE_DIR\|TIFF_LIBRARY:" "$WD/build-probe-zlib/CMakeCache.txt"

echo "### 3. runtime codec witness on the final binary, both arms"
cd "$WD/run"
for arm in ld zlib; do
  export MC_CODEC_WITNESS_OUT="$V/witness_final_$arm.json"
  rm -rf "$V/wit_$arm"
  taskset -c 32-39 env LD_LIBRARY_PATH="$WD/tiff-$arm/lib" LD_PRELOAD="$WD/witness/codec_witness.so" \
    "$WD/build-sys/motioncorr" --i movies1.star --o "$V/wit_$arm" --use_own --j 4 --seed 1 \
    --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 \
    --gainref Movies/gain.mrc > "$V/wit_$arm.log" 2>&1
  echo "$arm rc=$? $(cat $MC_CODEC_WITNESS_OUT)"
done
unset MC_CODEC_WITNESS_OUT

echo "### 4. exact ordered decoded samples, real movie, cross-arm"
for arm in ld zlib; do
  taskset -c 32-39 env LD_LIBRARY_PATH="$WD/tiff-$arm/lib" \
    "$WD/build-sys/runner_numerics" read_tiff_raw \
    Movies/20170629_00021_frameImage.tiff "$V/raw_$arm.bin" > "$V/raw_$arm.log" 2>&1
  echo "$arm dump_rc=$? $(sha256sum $V/raw_$arm.bin)"
done
cmp "$V/raw_ld.bin" "$V/raw_zlib.bin" && echo "RAW_SAMPLES_IDENTICAL=yes" || echo "RAW_SAMPLES_IDENTICAL=no"
# Negative control: one flipped sample must break the same comparison.
cp "$V/raw_zlib.bin" "$V/raw_mut.bin"
$PY - "$V/raw_mut.bin" <<'PYX'
import struct, sys
p = sys.argv[1]
with open(p, "r+b") as f:
    f.seek(24 + 4 * 1000)
    v = struct.unpack("<f", f.read(4))[0]
    f.seek(24 + 4 * 1000)
    f.write(struct.pack("<f", v + 1.0))
PYX
cmp -s "$V/raw_ld.bin" "$V/raw_mut.bin" && echo "RAW_NEGATIVE_CONTROL=FAILED_TO_DETECT" || echo "RAW_NEGATIVE_CONTROL=detected"
rm -f "$V/raw_ld.bin" "$V/raw_zlib.bin" "$V/raw_mut.bin"

echo "### 5. required test suite under both LibTIFF arms"
for arm in ld zlib; do
  echo "--- ctest arm=$arm ---"
  ( cd "$WD/build-sys" && taskset -c 32-47 env LD_LIBRARY_PATH="$WD/tiff-$arm/lib" \
      ctest --output-on-failure -j 8 > "$V/ctest_$arm.log" 2>&1 )
  echo "ctest_rc=$?"
  tail -3 "$V/ctest_$arm.log"
done

echo "### 6. cross-arm product identity"
CT="$WD/src/tools/compare_motioncorr.py"
for mode in gain nogain; do
  $PY "$WD/run/parity.py" --ref "$WD/results/${mode}_ld_rep1" --test "$WD/results/${mode}_zlib_rep1" \
     --compare-tool "$CT" --json-out "$V/parity_${mode}_ld_vs_zlib.json"
  echo "  ${mode}_cross_arm_rc=$?"
done
$PY "$WD/run/parity.py" --ref "$WD/results/gain_ld_rep1" --test "$WD/results/gain_ld_rep2" \
   --compare-tool "$CT" --json-out "$V/parity_gain_ld_rerun.json"
echo "  same_arm_rerun_control_rc=$?"
$PY "$WD/run/parity.py" --ref "$WD/results/gain_ld_rep1" --test "$WD/results/gain_zlib_rep1" \
   --compare-tool "$CT" --json-out "$V/parity_gain_negative_control.json" --mutate
echo "  negative_control_rc=$? (0 = the gate correctly turned red)"
echo VALIDATE_DONE
