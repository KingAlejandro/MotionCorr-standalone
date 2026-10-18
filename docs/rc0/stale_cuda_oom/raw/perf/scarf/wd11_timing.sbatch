#!/bin/bash
# W-D11 (#226 D1, PR #228): paired healthy-input timing, main 71ab841e vs fix, on ONE exclusive
# SCARF GPU node. Both arms are built here with identical options, run on the same GPU, the same
# NUMA-local 8-CPU mask and the same node-local inputs. The design (pilot, sizing, definitive) is declared in
# wd11_pairs.py (docstring; copied to rule.txt below before any timed run). No pass/fail verdict.

#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --exclusive
#SBATCH --constraint=scarf23
#SBATCH -t 04:00:00
#SBATCH -J wd11-timing
#SBATCH -o /home/vol05/scarf1415/wd11-run/slurm-%j.out

set -uo pipefail
export CUDA_HOME=/apps20/sw/easybuilt/rocky/9/amd/zen2/software/CUDA/12.8.0
NVC=/work4/scd/scarf1415/W-D11/nvcomp/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$NVC/lib:${LD_LIBRARY_PATH:-}"
unset GLIBC_TUNABLES OMP_PROC_BIND OMP_PLACES
export OMP_NUM_THREADS=8 TMPDIR=/tmp

MAIN_SHA=71ab841e69869b615555bb02f8f393db59c22d73
FIX_SHA=da402cab31110cdd8a5837889ae3a205511450c3
FIX_CODE_SHA=e723a73755b1d49b7b47be0a2f872ffb87ac9358   # src/ identical from here on
STAGE=/work4/scd/scarf1415/W-D11
HOMEDIR=/home/vol05/scarf1415/wd11-run
E=$HOMEDIR/ev-$SLURM_JOB_ID          # evidence in home: batch output on /work4 has vanished before
W=/tmp/wd11-$SLURM_JOB_ID
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
echo "src drift fix vs $FIX_CODE_SHA: $(git -C $W/src-fix diff --name-only $FIX_CODE_SHA HEAD -- src | tr '\n' ' ')<end>"
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

python3 -c "import sys; sys.path.insert(0,'$STAGE'); import wd11_pairs; print(wd11_pairs.__doc__)" > "$E/rule.txt"
cp "$STAGE/wd11_pairs.py" "$STAGE/wd11_timing.sbatch" "$E/"
echo "rule recorded before timing: $(sha256sum $E/rule.txt)"

G=(--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp)
EL=(--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact)
P="taskset -c $RUNNER python3 $STAGE/wd11_pairs.py --a $W/build-main/motioncorr --b $W/build-fix/motioncorr --cpus $CPUS --src $W/src-fix"
echo "== tutG $(date -Is)"; $P --name tutG --data "$W/tut" --out "$E/tutG" -- "${G[@]}"
echo "== tutL $(date -Is)"; $P --name tutL --data "$W/tut" --out "$E/tutL" -- "${G[@]}" --patch_x 5 --patch_y 5
echo "== e10216L $(date -Is)"; $P --name e10216L --data "$W/e10216" --out "$E/e10216L" -- "${EL[@]}"
echo "== end $(date -Is)"; uptime; nvidia-smi --query-compute-apps=pid --format=csv
rm -rf "$W"
echo WD11_DONE
