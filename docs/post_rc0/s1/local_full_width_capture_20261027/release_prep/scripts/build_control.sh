#!/bin/bash
# Compile and run the weight control against the pinned build (flags and libraries taken from the existing local_full_width_weight target).
set -eu
root=/tmp/motioncorr-lfw-capture-20261027; b=$root/build; mkdir -p $root/receipts/weight_control
cd $b
flags=$(sed -n 's/^CXX_FLAGS = //p' CMakeFiles/local_full_width_weight.dir/flags.make); defs=$(sed -n 's/^CXX_DEFINES = //p' CMakeFiles/local_full_width_weight.dir/flags.make); incs=$(sed -n 's/^CXX_INCLUDES = //p' CMakeFiles/local_full_width_weight.dir/flags.make)
g++ $defs $incs $flags -c $root/prep/weight_control.cpp -o $root/receipts/weight_control/weight_control.o
link=$(cat CMakeFiles/local_full_width_weight.dir/link.txt | sed "s#CMakeFiles/local_full_width_weight.dir/tests/test_local_full_width_weight.cpp.o#$root/receipts/weight_control/weight_control.o#; s#-o local_full_width_weight#-o $root/receipts/weight_control/weight_control#")
eval "$link"
rm -f $root/receipts/weight_control/native_weight_x*.f32
$root/receipts/weight_control/weight_control $root/receipts/weight_control
/home/ubuntu/.mc-venv/bin/python3 -B - <<PY
import sys, numpy as np
sys.path.insert(0, '$root/prep'); import weight_oracle as W
for xn in (42, 22):
    n = np.fromfile('$root/receipts/weight_control/native_weight_x%d.f32' % xn, dtype='<f4').reshape(32, 22); o = W.weight_map(xn)
    print('x_norm', xn, 'oracle equals native ccfWeightAt exactly:', bool(np.array_equal(n, o)), 'max abs diff', float(np.abs(n.astype('f8') - o).max()))
a = np.fromfile('$root/receipts/weight_control/native_weight_x42.f32', dtype='<f4'); b = np.fromfile('$root/receipts/weight_control/native_weight_x22.f32', dtype='<f4')
print('x42 map differs from x22 map in', int((a != b).sum()), 'of', a.size, 'bins')
PY
