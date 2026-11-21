#!/bin/bash
# C1 CPU-only qualification, plan cpu1c (frozen before launch; supersedes the unlaunched plans cpu1 and cpu1b, whose helpers accepted equal checker ABORT rows, non-finite sums and non-object runs).
# Launch: nohup setsid taskset -c 8-9 bash chain-cpu1c.sh  (the whole chain, including the Python-only stages, is pinned to CPUs 8-9; the chain verifies and records Cpus_allowed_list). Tested source e77a51a2 (exact checkout); CPU binary build-cpu/motioncorr (no CUDA linkage) and the frozen RC0 CPU
# binary read in place as the same-host control; unchanged tools packet 4facd76d (tools-v2.3-run) plus the frozen cpu1 helpers. CPUs 8-9, max 2 (--j 2, OMP 2).
# NO GPU is used: no lease, no nvidia-smi, no --gpu, CUDA_VISIBLE_DEVICES exported empty. GPU rows and L attribution stay pending (not part of this chain).
# Every stage is a c1_stage.sh stage (exclusive name, PID/exit receipts). The chain STOPS at the first stage whose exit is outside its allowed set (logs/chain-cpu1c.stop); no retry.
SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb
export C1_SCR=$SC C1_SHA=e77a51a220cb0d91f4ac3c7fac211876d0c6833f C1_T24_DIR=t24-cpu1c PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=
V=$SC/tools-cpu1c-run; PY=/home/alex/.mc-venv/bin/python3; F=/mnt/clathrin/alex-motioncorr-rc0/W-QF; SYN=$SC/src/docs/post_rc0/s1/synth_combined
SCIPY=/mnt/clathrin/alex-motioncorr-synth-combined/venv/bin/python3; IDS=$SC/cpu1c-identities.json; TOOLS_EXPECTED=$SC/cpu1c-tools-expected.sha256; PINS=$SC/cpu1c-pins
C1SHA=5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c; FSHA=43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42; FCPU=$F/build-cpu/motioncorr; CCPU=$SC/build-cpu/motioncorr
cd $SC
until [ -f logs/chain-cpu1c.go ]; do sleep 10; done          # released only by the parent's confirmation of the frozen plan
awk '/Cpus_allowed_list/{print $2}' /proc/self/status > logs/chain-cpu1c.cpus
echo $$ > logs/chain-cpu1c.pid; date -u +%FT%TZ > logs/chain-cpu1c.started
[ "$(cat logs/chain-cpu1c.cpus)" = 8-9 ] || { { echo "chain not pinned to CPUs 8-9: $(cat logs/chain-cpu1c.cpus)"; date -u +%FT%TZ; } > logs/chain-cpu1c.stop; exit 1; }
go() { n=$1; ok=$2; shift 2; bash $V/c1_stage.sh "$n" "$@"; rc=$?
  case " $ok " in *" $rc "*) return 0;; esac
  { echo "stage $n exited $rc (allowed: $ok)"; date -u +%FT%TZ; } > logs/chain-cpu1c.stop; exit 1; }
go cpu1c-prereq 0 $PY $V/cpu1c_prereq.py $SC/chain-cpu1c.sh $IDS $TOOLS_EXPECTED $PINS $SC/cpu1c-prereq.json
# K267 CPU: C1 and the same-host frozen-F CPU, same fixtures and options (derived driver: --j 2); exact field metrics must agree
go cpu1c-v2-cpu-c1 0 bash $V/c1_v2.sh cpu
go cpu1c-v2-cpu-F 0 $PY -I $V/c1_run_v2_cases.py $SC/v2 cpuF-unset cpu $FCPU unset 8-9
go cpu1c-v2-eval-F 0 $PY -I $SYN/eval_v2.py $SC/v2/v2fixtures $SC/v2/cpuF-unset $SC/v2/cpuF-unset.eval.json
go cpu1c-v2-check 0 $PY $V/cpu1c_sums.py v2check $SC/v2/cpu-unset.eval.json $SC/v2/cpuF-unset.eval.json $SYN/evidence/v2-comb-cpu-none.eval.json $SC/cpu1c-v2-check.json
# T24 CPU, G and L: C1 CPU vs the completed frozen-F CPU baselines (iteration-1 arms, rc 0); the products must be IDENTICAL
for cfg in G L; do
  go cpu1c-run-c1-cpu-$cfg 0 $PY $V/c1_tutorial24.py run c1-cpu $CCPU $cfg --cpu
  go cpu1c-cmp-cpu-$cfg 0 $PY $V/c1_tutorial24.py compare $SC/t24/F-cpu-$cfg/out $SC/t24-cpu1c/c1-cpu-$cfg/out F-cpu_vs_c1-cpu-$cfg
done
# K269 CPU census (100 movies, arm none) with retained main-CPU sums as reference and a same-host F-cpu control on the 10 dose1 movies
go cpu1c-extract-ref 0 bash $V/cpu1_extract_ref.sh
go cpu1c-census-cpu 0 $PY $V/c1_census.py run cpu $CCPU results-c1-cpu
go cpu1c-census-cmp-retained "0 1" $PY $V/cpu1c_sums.py compare $SC/census results-c1-cpu $SC/census-ref-cpu $SC/census-cpu-vs-retained.json $IDS all $C1SHA
go cpu1c-census-F-control 0 $PY $V/c1_census_runner.py --root $SC/census --binary $FCPU --backend cpu --cpus 8-9 --dc-arms none --double-conditions --results results-F-cpu-dose1 --conditions dose1 --max-idle-seconds 600
# decide exit 3 (INCONCLUSIVE: cross-host difference, equal to same-host F) is a documented outcome that lets the independent metrics and image rows continue; its status is preserved, never an aggregate PASS. 4 (FAIL) and 5 (INCOMPLETE) stop.
go cpu1c-census-decision "0 3" $PY $V/cpu1c_sums.py decide $SC/census results-c1-cpu results-F-cpu-dose1 $SC/census-ref-cpu $IDS $SC/census-cpu-decision.json $C1SHA $FSHA
go cpu1c-census-metrics 0 $PY $V/c1_census.py metrics results-c1-cpu cpu $SC/census-cpu-metrics.json
# K272 CPU: image-level check (existing SciPy venv; source, ROI, thresholds unchanged) on the CPU published sums, plus the seed-0 positive/negative controls
go cpu1c-image-cpu 0 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 $SCIPY $SYN/image_batch.py eval $SC/census results-c1-cpu x 2
go cpu1c-image-controls 0 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 $SCIPY $SYN/image_batch.py controls $SC/census dose1-s00 $SC/cpu1c-image-controls.json
date -u +%FT%TZ > logs/chain-cpu1c.finished; echo chain-done > logs/chain-cpu1c.done
