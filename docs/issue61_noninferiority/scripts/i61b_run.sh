#!/bin/bash
# Issue 61 follow-up: margin-calibrated Stage B sensitivity controls, cpu64.
#
# Arms run in priority order so that a truncated run still yields the required evidence:
#   cpu              - baseline, and the cross-host reproduction control against 4GPUs
#   ctrl_noise_f011  - predicted rho ~0.929, BEYOND the 0.95 harm margin: must be rejected
#   ctrl_noise_f0076 - predicted rho ~0.950, AT the margin: locates the detection boundary
#   ctrl_noise_f020  - completes the interval PR #65 reported as a point estimate only
#
# Allocation: cores 32-63 (NUMA node 1), <=12 concurrent, under
# /tmp/motioncorr-issue96-cpu-validation.lock.  ctffind processes are left untouched.
set -u
ROOT=/home/ubuntu/mc-issue61b
SIF=/home/ubuntu/relion-5.1.0-cuda12.8-sm80-full-plus-tomo-r2.vm.sif
RUN="numactl --cpunodebind=1 --preferred=1 singularity exec $SIF"
PY=/home/ubuntu/.mc-i61-venv/bin/python
NPAR=12
DEV=$'00021\n00046'

echo "START $(date -u +%FT%TZ)  affinity=$(taskset -cp $$ | sed 's/.*: //')"
numactl --show | tr '\n' ' '; echo

for arm in cpu ctrl_noise_f011 ctrl_noise_f0076 ctrl_noise_f020; do
  P=$ROOT/proj/$arm
  cd "$P" || exit 1

  if [ ! -f Extract61/particles.star ]; then
    rm -rf Extract61; mkdir -p Extract61
    /usr/bin/time -v $RUN /opt/relion/bin/relion_preprocess \
      --i CtfFind/job003/micrographs_ctf.star \
      --reextract_data_star Refine3D/job019/run_data.star \
      --recenter --recenter_x 0 --recenter_y 0 --recenter_z 0 \
      --part_star Extract61/particles.star --pick_star Extract61/extractpick.star \
      --part_dir Extract61/ --extract --extract_size 360 --minimum_pick_fom -3 \
      --scale 256 --norm --bg_radius 71 --white_dust -1 --black_dust -1 --invert_contrast \
      > $ROOT/logs/extract_$arm.log 2> $ROOT/logs/extract_$arm.time
    echo "extract $arm rc=$? parts=$(grep -c mrcs Extract61/particles.star) wall=$(grep -m1 'Elapsed (wall' $ROOT/logs/extract_$arm.time|awk '{print $NF}')"
  fi

  mkdir -p $ROOT/stars/$arm $ROOT/rec/$arm $ROOT/pp/$arm
  $PY - "$arm" <<'PYEOF'
import os, sys
ROOT="/home/ubuntu/mc-issue61b"; arm=sys.argv[1]; DEV={"00021","00046"}
L=open(f"{ROOT}/proj/{arm}/Extract61/particles.star").read().splitlines()
i=L.index("data_particles"); j=i
while not L[j].strip().startswith("loop_"): j+=1
k=j+1; cols=[]
while L[k].strip().startswith("_rln"): cols.append(L[k].strip().split()[0]); k+=1
mic=cols.index("_rlnMicrographName"); rows=[l for l in L[k:] if l.strip()]
mid=lambda r: r.split()[mic].split("_")[-2]
held=sorted({mid(r) for r in rows}-DEV); assert len(held)==22, len(held)
sets={"held22":set(held)}
for m in held: sets[f"jk_{m}"]=set(held)-{m}
for n,keep in sets.items():
    sel=[r for r in rows if mid(r) in keep]
    open(f"{ROOT}/stars/{arm}/{n}.star","w").write("\n".join(L[:i]+L[i:k]+sel)+"\n")
print(f"   subsets: {len(sets)} (held22 n={len(sets['held22']) and sum(1 for r in rows if mid(r) in sets['held22'])})")
PYEOF

  : > $ROOT/jobs_$arm.txt
  for s in $ROOT/stars/$arm/*.star; do
    n=$(basename $s .star)
    for h in 1 2; do
      o=$ROOT/rec/$arm/${n}_half${h}_class001_unfil.mrc
      [ -f "$o" ] || echo "cd $P && $RUN /opt/relion/bin/relion_reconstruct --i $s --o $o --ctf --sym D2 --subset $h --pad 2 > $ROOT/logs/rec_${arm}_${n}_h${h}.log 2>&1" >> $ROOT/jobs_$arm.txt
    done
  done
  nj=$(wc -l < $ROOT/jobs_$arm.txt)
  t0=$(date +%s)
  [ "$nj" -gt 0 ] && nice -n 5 xargs -P $NPAR -I{} -d '\n' bash -c '{}' < $ROOT/jobs_$arm.txt
  echo "reconstruct $arm: $nj jobs in $(( $(date +%s) - t0 ))s  maps=$(ls $ROOT/rec/$arm/*.mrc|wc -l)"

  : > $ROOT/jobs_pp_$arm.txt
  for f in $ROOT/rec/$arm/*_half1_class001_unfil.mrc; do
    n=$(basename $f _half1_class001_unfil.mrc)
    [ -f "$ROOT/pp/$arm/$n.star" ] || echo "cd $P && $RUN /opt/relion/bin/relion_postprocess --i $f --o $ROOT/pp/$arm/$n --mask MaskCreate/job020/mask.mrc --angpix 1.244531 --mtf mtf_k2_200kV.star --mtf_angpix 0.885 --auto_bfac --autob_lowres 10 > $ROOT/logs/pp_${arm}_${n}.log 2>&1" >> $ROOT/jobs_pp_$arm.txt
  done
  t0=$(date +%s)
  nice -n 5 xargs -P $NPAR -I{} -d '\n' bash -c '{}' < $ROOT/jobs_pp_$arm.txt
  echo "postprocess $arm: $(wc -l < $ROOT/jobs_pp_$arm.txt) jobs in $(( $(date +%s) - t0 ))s  pp=$(ls $ROOT/pp/$arm/*.star|wc -l)"

  [ "$arm" != "cpu" ] && rm -f $ROOT/arms/$arm/*.mrc
  echo "ARM_DONE $arm $(date -u +%FT%TZ)"
done
echo "CROSS-HOST cpu baseline digests (compare with 4GPUs):"
sha256sum $ROOT/rec/cpu/held22_half1_class001_unfil.mrc $ROOT/rec/cpu/held22_half2_class001_unfil.mrc
echo "ALL_DONE $(date -u +%FT%TZ)"
