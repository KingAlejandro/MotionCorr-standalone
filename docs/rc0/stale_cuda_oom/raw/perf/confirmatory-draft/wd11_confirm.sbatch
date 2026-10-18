#!/bin/bash
# DRAFT / NOT RUN. W-D11 confirmatory timing (rule.txt next to this file), main 71ab841e vs fix, on ONE exclusive
# SCARF GPU node. Both arms built here with identical options; same GPU, NUMA-local 8-CPU mask and
# node-local inputs. Four windows back to back in the declared order. FIX_SHA must be set to the PR head
# at submission (its src/ must equal e723a737; the job checks this).

#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 03:00:00
#SBATCH -J wd11-confirm
#SBATCH -o /home/vol05/scarf1415/wd11-run/confirm-%j.out

set -uo pipefail
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVC=/work4/scd/scarf1415/W-D11/nvcomp/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVC/lib:${LD_LIBRARY_PATH:-}"
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES
export OMP_NUM_THREADS=8 TMPDIR=/tmp

MAIN_SHA=71ab841e69869b615555bb02f8f393db59c22d73
FIX_SHA=${FIX_SHA:?set FIX_SHA to the PR #228 head at submission}
FIX_CODE_SHA=e723a73755b1d49b7b47be0a2f872ffb87ac9358   # src/ identical from here on
STAGE=/work4/scd/scarf1415/W-D11
HOMEDIR=/home/vol05/scarf1415/wd11-run
E=$HOMEDIR/confirm-$SLURM_JOB_ID          # evidence in home: batch output on /work4 has vanished before
W=/tmp/wd11c-$SLURM_JOB_ID
mkdir -p "$E" "$W"
exec > >(tee "$E/job.log") 2>&1

echo "== provenance"; date -Is; hostname; uptime
scontrol show job "$SLURM_JOB_ID" | grep -E 'NodeList|NumCPUs|TRES|Gres|Features' || true
grep Cpus_allowed_list /proc/self/status
lscpu | grep -E 'Model name|^CPU\(s\)|Thread|NUMA node'
cat /sys/kernel/mm/transparent_hugepage/enabled
nvidia-smi; nvidia-smi --query-gpu=name,uuid,driver_version,clocks.max.sm --format=csv; nvidia-smi topo -m
nvcc --version | tail -1; cmake --version | head -1; gcc --version | head -1; python3 --version
df -h /tmp

echo "== CPU mask: first 8 cores of the GPU's NUMA-local CPU affinity"
AFF=$(nvidia-smi topo -m | awk '/^GPU0/{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$/ && $i ~ /-/){print $i; exit}}')
FIRST=${AFF%%-*}; FIRST=${FIRST%%,*}
CPUS="$FIRST-$((FIRST+7))"; RUNNER="$((FIRST+8))-$((FIRST+15))"   # driver + nvidia-smi sampler kept off the payload cores
echo "GPU0 CPU affinity=$AFF -> payload mask $CPUS, runner mask $RUNNER"
[ -n "$AFF" ] || { echo "cannot read GPU CPU affinity"; exit 1; }

echo "== staging marker (written after the inputs were transferred and verified)"
for i in $(seq 1 120); do [ -f "$STAGE/READY" ] && break; sleep 30; done
[ -f "$STAGE/READY" ] || { echo "staging not ready after 60 min"; exit 1; }
cat "$STAGE/READY"

echo "== sources"
for n in main fix; do git clone -q --no-checkout "$STAGE/wd11.bundle" "$W/src-$n"; done
git -C "$W/src-main" checkout -q --detach $MAIN_SHA
git -C "$W/src-fix" checkout -q --detach $FIX_SHA
echo "main=$(git -C $W/src-main rev-parse HEAD) fix=$(git -C $W/src-fix rev-parse HEAD)"
[ -z "$(git -C $W/src-fix diff --name-only $FIX_CODE_SHA HEAD -- src)" ] || { echo "fix src/ differs from $FIX_CODE_SHA"; exit 1; }
git -C "$W/src-fix" diff --stat $MAIN_SHA HEAD -- src CMakeLists.txt | tee "$E/fix-vs-main-compiled.diffstat"

echo "== builds (identical options, motioncorr target only)"
OPTS=(-DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80
      -DCMAKE_CUDA_COMPILER=$CUDA_HOME/bin/nvcc -DCUDAToolkit_ROOT=$CUDA_HOME -DUSE_NVCOMP=ON -DNVCOMP_ROOT=$NVC)
printf '%s\n' "${OPTS[@]}" > "$E/cmake-options.txt"
for n in main fix; do
  cmake -S "$W/src-$n" -B "$W/build-$n" "${OPTS[@]}" > "$E/configure-$n.log" 2>&1 || { echo "configure $n failed"; exit 1; }
  cmake --build "$W/build-$n" --target motioncorr -j 16 > "$E/build-$n.log" 2>&1 || { echo "build $n failed"; tail -30 "$E/build-$n.log"; exit 1; }
  grep -h -- '-O3' "$W/build-$n/CMakeFiles/motioncorr.dir/flags.make" | head -1
  sha256sum "$W/build-$n/motioncorr" | tee -a "$E/binaries.sha256"
  ldd "$W/build-$n/motioncorr" | grep -E 'nvcomp|cufft|cudart|fftw|tiff' > "$E/ldd-$n.txt"
done

echo "== inputs (node-local /tmp, verified)"
mkdir -p "$W/tut/Movies" "$W/e10216/Movies"
cp /home/vol05/scarf1415/i53-scarf/relion30_tutorial/Movies/*.tiff /home/vol05/scarf1415/i53-scarf/relion30_tutorial/Movies/gain.mrc "$W/tut/Movies/"
cp "$STAGE/tutorial-movies.star" "$W/tut/movies.star"
( cd "$W/tut/Movies" && grep -E 'frameImage|gain' "$STAGE/tutorial-SHA256SUMS.txt" | sha256sum -c --quiet ) && echo "tutorial sha256 OK" || { echo "tutorial sha256 FAILED"; exit 1; }
cp "$STAGE/data/e10216.mrc" "$W/e10216/e10216.mrc"
echo "f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56  $W/e10216/e10216.mrc" | sha256sum -c --quiet && echo "e10216 sha256 OK" || { echo "e10216 sha256 FAILED"; exit 1; }
for i in 1 2 3; do ln -s ../e10216.mrc "$W/e10216/Movies/e10216_$i.mrcs"; done
cp "$STAGE/e10216-movies.star" "$W/e10216/movies.star"

D=$W/src-fix/docs/rc0/stale_cuda_oom/raw/perf/confirmatory-draft
cp $D/rule.txt $D/confirm_pairs.py "$E/"; echo "rule recorded before timing: $(sha256sum $E/rule.txt)"
G=(--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp)
EL=(--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact)
P="taskset -c $RUNNER python3 $E/confirm_pairs.py run --a $W/build-main/motioncorr --b $W/build-fix/motioncorr --cpus $CPUS --src $W/src-fix --windows 2"
win() { echo "== $1 window $3 $(date -Is)"; uptime; $P --workload $1 --n $2 --window $3 --data "$4" --out "$E/$1" -- "${@:5}" > "$E/$1-window$3.driver.out" 2>&1; echo "rc=$? $(date -Is)"; }
win tutG 256 1 "$W/tut" "${G[@]}"
win e10216L 176 1 "$W/e10216" "${EL[@]}"
win tutG 256 2 "$W/tut" "${G[@]}"
win e10216L 176 2 "$W/e10216" "${EL[@]}"
for w in tutG e10216L; do python3 $E/confirm_pairs.py combine --workload $w --out "$E/$w" --src $W/src-fix; done
echo "== end $(date -Is)"; uptime; nvidia-smi --query-compute-apps=pid --format=csv
rm -rf "$W"
echo WD11_CONFIRM_DONE
