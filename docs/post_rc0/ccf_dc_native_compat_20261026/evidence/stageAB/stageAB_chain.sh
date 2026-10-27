#!/bin/bash
# Stage A (GPU hidden) and Stage B (one shared GPU) bounded correctness window. No build, no timing, no retry.
# Run on 4GPUs as:  setsid taskset -c 80-87 bash stageAB_chain.sh > logs/chain.out 2>&1 < /dev/null &
# Every STOP is final for the affected stage: no GPU fallback, no reschedule, no waiver.
set -u
S=/home/alex/mc-dcnative-ab-20261026
L=$S/logs
A2=/home/alex/mc-dcnative2-20261026
PY=/home/alex/.mc-venv/bin/python3
GPU2=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598
FOREIGN_PID=3983855
CHK=$S/stageAB_check.py
export PATH=/home/alex/.mc-venv/bin:$PATH
mkdir -p $L

ts() { date -u +%FT%TZ; }
stop() { echo "STOP $1: $2 ($(ts))"; exit "$3"; }

# --- leases (non-blocking): own lease and the overlapping CPU range lease; the GPU2 correctness lease before stage B
exec 10>>/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock; flock -n 10 || stop lease "motioncorr-dcnative-gpu2-cpu80-87 busy" 90
exec 11>>/tmp/motioncorr-cuda-boundary-cpu80-87.lock; flock -n 11 || stop lease "motioncorr-cuda-boundary-cpu80-87 busy" 90
echo "leases acquired: dcnative-gpu2-cpu80-87, cuda-boundary-cpu80-87 at $(ts)"

# --- guard: fresh GPU2 / CPU 80-87 / scratch / memory snapshot, with the predeclared stop rules
guard() {  # $1 label, $2 need_gpu (0/1)
  echo "== guard $1 $(ts)"
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader
  nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory,process_name --format=csv,noheader
  local a b busy max=0 core
  a=$(mktemp); grep "^cpu[0-9]" /proc/stat > $a; sleep 3
  busy=$(grep "^cpu[0-9]" /proc/stat | paste -d" " $a - | awk '{u1=$2+$3+$4+$7+$8; t1=u1+$5+$6; u2=$13+$14+$15+$18+$19; t2=u2+$16+$17; d=t2-t1; n=$1; sub("cpu","",n); if (n>=80 && n<=87 && d>0) printf "%s %.0f\n", $1, 100*(u2-u1)/d}')
  rm -f $a
  echo "cpu80-87 busy%: $(echo $busy | tr '\n' ' ')"
  max=$(echo "$busy" | awk '{if ($2>m) m=$2} END {print m+0}')
  echo "processes currently running on cpu80-87:"; ps -eo psr,stat,pcpu,user,pid,args --no-headers | awk '$1>=80 && $1<=87 && $2 ~ /^R/' | cut -c1-140
  df -h /home/alex | tail -1; free -g | sed -n 2p; du -sh $S 2>/dev/null
  [ "$max" -gt 50 ] && stop guard "a core in 80-87 is >50% busy ($max%)" 13
  if [ "$2" = 1 ]; then
    local others util
    others=$(nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | awk -F", " -v g=$GPU2 -v f=$FOREIGN_PID '$2==g && $1!=f')
    [ -n "$others" ] && stop guard "other compute app on GPU2: $others" 11
    util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i $GPU2)
    [ "$util" -gt 50 ] && stop guard "GPU2 utilisation $util% > 50%" 12
  fi
  echo "guard $1 passed"
}

health() {  # $1 file
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu,power.draw,pstate,clocks_throttle_reasons.active --format=csv > $1 2>&1
  nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory,process_name --format=csv >> $1 2>&1
}

# ============================== staging (no build) ==============================
echo "== staging $(ts)"; echo "affinity: $(taskset -cp $$)"; nproc
test "$(sha256sum $S/src.tar | cut -d' ' -f1)" = "$(cat $S/src.tar.sha256 | cut -d' ' -f1)" || stop stage "archive sha mismatch" 20
mkdir -p $S/src96e && tar -xf $S/src.tar -C $S/src96e && echo "extracted files=$(find $S/src96e -type f | wc -l) appledouble=$(find $S/src96e -name '._*' | wc -l)"
echo "archive sha256: $(cat $S/src.tar.sha256)  source commit: $(cat $S/GIT_HEAD)"
echo "== source-tree proof: attempt-2 src (94e39570) vs staged 96e7e7be, src tests test-data CMakeLists.txt"
for p in src tests test-data; do diff -rq $A2/src/$p $S/src96e/$p > $L/diff-$p.txt 2>&1; echo "diff -rq $p rc=$? lines=$(wc -l < $L/diff-$p.txt)"; done
diff -q $A2/src/CMakeLists.txt $S/src96e/CMakeLists.txt; echo "diff CMakeLists.txt rc=$?"
echo "== tools differing between attempt-2 tree and 96e7e7be:"; diff -rq $A2/src/tools $S/src96e/tools | sed 's#/home/alex/##'
echo "== binaries and oracles (attempt 2) vs recorded hashes"
for k in def exp iso; do sha256sum $A2/build-$k/motioncorr; grep -c "$(sha256sum $A2/build-$k/motioncorr | cut -d' ' -f1)" $A2/logs/binary-$k.sha256 | sed "s/^/recorded-in-attempt2-$k: /"; done
for k in exp iso; do sha256sum $A2/build-$k/experiment_ccf_dc_stage; done
for k in exp iso; do [ "$(grep -c "$(sha256sum $A2/build-$k/motioncorr | cut -d' ' -f1)" $A2/logs/binary-$k.sha256)" = 1 ] || stop stage "binary $k hash differs from the attempt-2 record" 21; done
sha256sum $A2/build-def/motioncorr | grep -q "$(awk '{print $1}' $A2/logs/binary-def.sha256)" || stop stage "binary def hash differs" 21
echo "== python identity"
$PY - <<PYEOF > $L/python-identity.txt 2>&1
import sys, hashlib, platform
sys.path.insert(0, "$S/src96e/tools"); sys.path.insert(0, "$S/src96e/test-data")
import numpy
print("python", sys.version.split()[0], sys.executable)
print("numpy", numpy.__version__, numpy.__file__)
print(platform.platform())
for m in ("ccf_dc_native_rows", "ccf_dc_tap_field", "check_motion_diagnostics", "check_realistic_motion", "motion_field", "generate_ccf_dc_n_controls", "generate_motion_diagnostics"):
    mod = __import__(m)
    print(m, mod.__file__, hashlib.sha256(open(mod.__file__, "rb").read()).hexdigest())
bad = [p for p in sys.path if "mc-dcnative2-20261026" in p or "mc-dcnative-20261026" in p]
print("old-attempt paths on sys.path:", bad)
PYEOF
cat $L/python-identity.txt; grep -q "old-attempt paths on sys.path: \[\]" $L/python-identity.txt || stop stage "old attempt path on sys.path" 22
echo "== fixtures at the venue (hashes only)"
$PY $S/src96e/test-data/generate_motion_diagnostics.py --outdir $S/fx-k267 > $L/gen-k267.log 2>&1; echo "gen-k267 rc=$?"
$PY $S/src96e/test-data/generate_ccf_dc_n_controls.py --outdir $S/fx-n > $L/gen-n.log 2>&1; echo "gen-n rc=$?"
(cd $S && sha256sum fx-k267/MANIFEST.json fx-n/MANIFEST.json fx-k267/*.mrcs fx-k267/*.star fx-n/*.mrcs fx-n/*.star > $L/input-hashes.sha256); sha256sum $L/input-hashes.sha256 | cut -c1-64
grep -E "MANIFEST" $L/input-hashes.sha256

# ============================== Stage A: GPU hidden ==============================
REQ_PURE="test_n_score_reproduces_all_16_retained_rows test_n_score_percentile_is_over_the_dense_roi_not_the_frames test_witness_selectivity_on_every_reached_site test_n_control_generator test_run_env_thread_pins test_pinned_commands"
REQ_NATIVE="$REQ_PURE test_positive_affine_both test_absent_tap_fails_closed test_n_tap_with_a_local_model_is_invalid test_invalid_tap_rows_are_not_labelled_scored test_def_build_row_is_star_only_by_declaration test_two_failed_runs_are_not_an_identity test_global_only_row_cannot_claim_local_coverage test_skip_logfile_does_not_change_the_products test_n_control_row test_identity_report test_failed_exit_is_not_rescued_by_a_complete_tap test_placeholder_tap_and_tap_star_disagreement"
stageA() {  # $1 tag, rest: args to the tool test
  local tag=$1; shift
  guard "A-$tag" 0
  echo "== stage A $tag: CUDA_VISIBLE_DEVICES='' $PY $S/src96e/tools/test_ccf_dc_native_rows.py $* -v" | tee $L/A-$tag.cmd
  CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES=void $PY $S/src96e/tools/test_ccf_dc_native_rows.py "$@" -v > $L/A-$tag.stdout 2> $L/A-$tag.stderr; echo "A-$tag rc=$?" | tee $L/A-$tag.rc
  $PY $CHK unittest $L/A-$tag.stderr $REQ_NATIVE | tee $L/A-$tag.check
  tail -4 $L/A-$tag.stderr
}
echo "== STAGE A $(ts)"
# pure: the native class is expected to skip here (no binary); only its own pure tests are required
guard "A-pure" 0
echo "== stage A pure: CUDA_VISIBLE_DEVICES='' $PY $S/src96e/tools/test_ccf_dc_native_rows.py -v" | tee $L/A-pure.cmd
CUDA_VISIBLE_DEVICES="" NVIDIA_VISIBLE_DEVICES=void $PY $S/src96e/tools/test_ccf_dc_native_rows.py -v > $L/A-pure.stdout 2> $L/A-pure.stderr; echo "A-pure rc=$?" | tee $L/A-pure.rc
$PY $CHK unittest $L/A-pure.stderr $REQ_PURE | tee $L/A-pure.check; tail -4 $L/A-pure.stderr
stageA exp --binary $A2/build-exp/motioncorr
stageA iso --iso --binary $A2/build-iso/motioncorr
echo "== STAGE A done $(ts)"

# ============================== Stage B: one shared GPU ==============================
echo "== STAGE B $(ts)"
guard "B-pre" 1
exec 12>>/tmp/motioncorr-gpu2-correctness.lock; flock -n 12 || stop lease "motioncorr-gpu2-correctness busy" 90
echo "lease acquired: gpu2-correctness at $(ts)"
oracle() {  # $1 kind (exp|iso)
  local k=$1 B=$A2/build-$1
  guard "B-$k" 1
  health $L/B-$k.health.pre
  sha256sum $B/experiment_ccf_dc_stage | tee $L/B-$k.oracle.sha256
  echo "== stage B $k: CUDA_VISIBLE_DEVICES=$GPU2 CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=2 taskset -c 80,81 $B/experiment_ccf_dc_stage --json $L/oracle-$k.json" | tee $L/B-$k.cmd
  ( while :; do t=$(date +%s.%N); g=$(nvidia-smi --query-gpu=uuid,utilization.gpu,memory.used --format=csv,noheader,nounits | tr '\n' ';'); a=$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits | tr '\n' ';'); echo "$t|$g|$a"; sleep 0.1; done ) > $L/B-$k.sampler 2>&1 &
  local SP=$! n=0
  while [ "$(wc -l < $L/B-$k.sampler)" -lt 3 ] && [ $n -lt 100 ]; do sleep 0.1; n=$((n+1)); done
  [ "$(wc -l < $L/B-$k.sampler)" -lt 3 ] && { kill $SP 2>/dev/null; stop sampler "sampler not ready before the oracle; no retry" 30; }
  CUDA_VISIBLE_DEVICES=$GPU2 CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=2 taskset -c 80,81 $B/experiment_ccf_dc_stage --json $L/oracle-$k.json > $L/oracle-$k.stdout 2> $L/oracle-$k.stderr &
  local OPID=$!
  echo "oracle pid $OPID" | tee $L/B-$k.pid
  wait $OPID; echo "oracle-$k rc=$?" | tee $L/oracle-$k.rc
  sleep 0.5; kill $SP 2>/dev/null; wait $SP 2>/dev/null
  health $L/B-$k.health.post
  $PY $CHK oracle $L/oracle-$k.json $L/oracle-$k.stdout | tee $L/oracle-$k.check
  $PY $CHK witness $L/B-$k.sampler $OPID $GPU2 | tee $L/B-$k.witness
  tail -8 $L/oracle-$k.stdout
}
oracle exp
oracle iso
echo "== STAGE B done $(ts)"
echo "== scratch and logs"; du -sh $S; (cd $L && sha256sum * > $S/logs.sha256); wc -l $S/logs.sha256
echo "== done $(ts)"
