#!/bin/sh
# Malformed-input campaign: device (memcheck + plain, run twice) and host (release + ASan, one process per fraction).
# usage: run_malformed.sh <build-dir> <fixture-dir> <out-dir>
set -u
B=${1:?}; FX=${2:?}; OUT=${3:?}
HERE=$(cd "$(dirname "$0")" && pwd)
L=$HERE/run_lane.sh
CS=${COMPUTE_SANITIZER:-/usr/local/cuda/bin/compute-sanitizer}
mkdir -p "$OUT"
export ASAN_OPTIONS=detect_leaks=0:abort_on_error=0
# ---- device: every fixture, upsampling 1 and 2 (and -1 on the mutated one), memcheck and plain, twice
for fx in base48 mut48 trunc_last trunc_file empty_strip; do
  for u in 1 2 -1; do
    $L $B/eer_device_exp dev-frames --eer $FX/$fx.eer --upsampling $u > $OUT/dev.$fx.u$u.run1.jsonl 2> $OUT/dev.$fx.u$u.run1.err; echo $? > $OUT/dev.$fx.u$u.run1.rc
    $L $B/eer_device_exp dev-frames --eer $FX/$fx.eer --upsampling $u > $OUT/dev.$fx.u$u.run2.jsonl 2> $OUT/dev.$fx.u$u.run2.err
    cmp -s $OUT/dev.$fx.u$u.run1.jsonl $OUT/dev.$fx.u$u.run2.jsonl && echo deterministic > $OUT/dev.$fx.u$u.determinism || echo DIFFERENT > $OUT/dev.$fx.u$u.determinism
    $L $CS --tool memcheck --error-exitcode 99 --leak-check full $B/eer_device_exp dev-frames --eer $FX/$fx.eer --upsampling $u > $OUT/dev.$fx.u$u.memcheck.jsonl 2> $OUT/dev.$fx.u$u.memcheck.log; echo $? > $OUT/dev.$fx.u$u.memcheck.rc
    cmp -s $OUT/dev.$fx.u$u.run1.jsonl $OUT/dev.$fx.u$u.memcheck.jsonl && echo same >> $OUT/dev.$fx.u$u.determinism || echo "memcheck-output-differs" >> $OUT/dev.$fx.u$u.determinism
  done
done
# guard hook: halve the allowed pixel index, valid data must be refused without writing beyond it
for u in 1 2; do
  $L $CS --tool memcheck --error-exitcode 99 $B/eer_device_exp dev-frames --eer $FX/base48.eer --upsampling $u --clamp_div 2 > $OUT/dev.clamp.u$u.memcheck.jsonl 2> $OUT/dev.clamp.u$u.memcheck.log; echo $? > $OUT/dev.clamp.u$u.memcheck.rc
done
# ---- synthetic parity (65000/65001/65002, 4K and 2K) against the host renderer, plus memcheck of the same decode
for c in 65000 65001 65002; do for d in 4096 2048; do
  ups="1 2"; [ $d = 4096 ] && ups="1 2 -1"
  for u in $ups; do
    # sym_bits 2 (65002) does not allow upsampling -1 in EERRenderer::read
    [ $c = 65002 ] && [ $u = -1 ] && continue
    $L $B/eer_device_exp compare --eer $FX/syn_${c}_$d.eer --grouping 4 --upsampling $u --label syn-$c-$d-u$u --timing 0 > $OUT/syn.$c.$d.u$u.json 2> $OUT/syn.$c.$d.u$u.err
    $L $CS --tool memcheck --error-exitcode 99 $B/eer_device_exp compare --eer $FX/syn_${c}_$d.eer --grouping 4 --upsampling $u --label syn-$c-$d-u$u --verify 0 --timing 0 > $OUT/syn.$c.$d.u$u.memcheck.json 2> $OUT/syn.$c.$d.u$u.memcheck.log; echo $? > $OUT/syn.$c.$d.u$u.memcheck.rc
  done
done; done
# ---- host: one process per fraction so a crash does not hide the rest; release and ASan builds
for fx in mut48 trunc_last trunc_file empty_strip; do
  for u in 1 2; do
    n=48; : > $OUT/host.$fx.u$u.release.jsonl; : > $OUT/host.$fx.u$u.asan.jsonl
    f=0
    while [ $f -lt $n ]; do
      timeout 300 taskset -c 96-103 $B/eer_device_exp host-frames --eer $FX/$fx.eer --upsampling $u --first $f --last $f > $OUT/tmp.out 2> $OUT/tmp.err; rc=$?
      if [ -s $OUT/tmp.out ]; then cat $OUT/tmp.out >> $OUT/host.$fx.u$u.release.jsonl; else echo "{\"f\":$f,\"crash_rc\":$rc}" >> $OUT/host.$fx.u$u.release.jsonl; fi
      [ $rc -ne 0 ] && echo "f=$f rc=$rc $(head -c 300 $OUT/tmp.err | tr '\n' ' ')" >> $OUT/host.$fx.u$u.release.rcs
      timeout 600 taskset -c 96-103 $B/eer_device_exp_asan host-frames --eer $FX/$fx.eer --upsampling $u --first $f --last $f > $OUT/tmp.out 2> $OUT/tmp.err; rc=$?
      if [ -s $OUT/tmp.out ] && [ $rc -eq 0 ]; then cat $OUT/tmp.out >> $OUT/host.$fx.u$u.asan.jsonl; else
        echo "{\"f\":$f,\"asan_rc\":$rc,\"asan\":\"$(grep -m1 -E 'ERROR: AddressSanitizer|Segmentation|SEGV' $OUT/tmp.err | tr -d '"' | head -c 200)\"}" >> $OUT/host.$fx.u$u.asan.jsonl
        cp $OUT/tmp.err $OUT/host.$fx.u$u.asan.f$f.log
      fi
      f=$((f+1))
    done
  done
done
echo malformed done
