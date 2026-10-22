#!/bin/bash
ROOT=/home/alex/mc-issue61
BIN=/home/alex/relion-container-tests/bin/relion-container-bin-r2
PRE=/home/alex/relion-container-tests/data/spa-relion50-precalculated/extracted
PY=/home/alex/relion-container-tests/venvs/pipeliner-onedep-adapter/bin/python
{
echo "generated_utc: $(date -u +%FT%TZ)"
echo "host: $(hostname)  kernel: $(uname -r)"
echo "study_cpu_policy: 4GPUs work under top-level taskset -c 96-103 behind /tmp/motioncorr-bench.lock;"
echo "                  cpu64 follow-up work under taskset -c 32-63 (NUMA node 1) behind /tmp/motioncorr-issue96-cpu-validation.lock"
# observed, not asserted: what this regeneration actually ran under
echo "observed_affinity_of_this_run: $(taskset -cp $$ 2>/dev/null | sed 's/.*: //')"
echo "observed_numa_of_this_run: $(numactl --show 2>/dev/null | tr '\n' ' ' || echo numactl-absent)"
echo "mem_total_GB: $(free -g|awk 'NR==2{print $2}')"
echo
echo "## Tool versions"
echo "relion: $($BIN/relion_reconstruct --version 2>&1|grep -i 'RELION version')"
echo "ctffind_help_line1: $($BIN/ctffind --version 2>&1 | grep -m1 Usage)"
PYV=$($PY -c "import sys,numpy,scipy;print(sys.version.split()[0], numpy.__version__, scipy.__version__)"); echo "python/numpy/scipy: $PYV"
echo
echo "## Container / binary digests"
for f in $BIN/relion_reconstruct $BIN/relion_postprocess $BIN/relion_preprocess $BIN/relion_run_ctffind $BIN/ctffind; do
  echo "$(sha256sum $f)"
done
echo "wrapper_dir: $BIN"
# Review finding 4111302990: the container image was resolved into IMG and then never
# emitted or hashed, so the section claimed container provenance it did not contain.
for W in $BIN/relion_reconstruct $BIN/relion_run_ctffind; do
  IMG=$(grep -m1 -oE '/[^"} ]*\.sif' "$W" 2>/dev/null | head -1)
  [ -n "${IMG:-}" ] && [ -f "$IMG" ] && { echo "container_image: $IMG"; sha256sum "$IMG"; break; }
done
[ -n "${IMG:-}" ] && [ -f "${IMG:-}" ] || echo "container_image: UNRESOLVED from the wrapper scripts"
echo
echo "## Motion-correction arm provenance (consumed from Issue #36)"
cat /home/alex/MotionCorr-issue36-full24/provenance.md
echo
echo "## Downstream matched inputs (RELION 5.0 tutorial precalculated project)"
for f in $PRE/Refine3D/job019/run_data.star $PRE/MaskCreate/job020/mask.mrc \
         $PRE/CtfFind/job003/micrographs_ctf.star $PRE/mtf_k2_200kV.star \
         $PRE/Class3D/job016/run_it025_class002_box256.mrc; do
  echo "$(sha256sum $f)"
done
echo
echo "## Input movie + gain digests (as used by the consumed arms)"
sha256sum /home/alex/mc-issue61/../MotionCorr-issue36-full24/tutorial/Movies/gain.mrc 2>/dev/null || true
} > $ROOT/results/environment.txt 2>&1
wc -l $ROOT/results/environment.txt
