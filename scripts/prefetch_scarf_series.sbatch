#!/bin/bash -l
#SBATCH --job-name=mc94-prefetch
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --exclusive
#SBATCH --output=/work4/scd/scarf1415/motioncorr/mc-issue94/slurm-%j.out
#SBATCH --error=/work4/scd/scarf1415/motioncorr/mc-issue94/slurm-%j.err
#
# Issue #94: native CUDA prefetch off/on correctness, then controlled paired
# performance and RSS, on a DEDICATED SCARF allocation.
#
# Deliberate properties:
#  * One allocation for the whole series, so no other MotionCorr work shares
#    these devices or this host. The shared 4GPU VM is untouched: #53 owns
#    GPU0/1 with CPUs 96-111 and #69 owns GPU2 with 112-119.
#  * Correctness BEFORE timing. A speed number from arms that do not produce
#    identical products is meaningless, so the off/on comparison runs first and
#    a mismatch is reported rather than smoothed.
#  * Paired timings with the arm order ALTERNATING inside each pair and the
#    order label retained, because the positional bias (page-cache warming for
#    whichever arm runs second) is a property of the workload, not the host.
#  * Identical source, binary, inputs, options and CPU budget in both arms.
#    --j 8 in both; the prefetch arm's reader threads come out of the same
#    16-CPU allocation and are counted, not treated as free.
#  * RSS is sampled over the OWNED PROCESS TREE, not one pid and not the node.
set -u
SHA=ab9cd6b9a3ee5c2f0de11a623d849dc921a71448
W=/work4/scd/$USER/motioncorr/mc-issue94
SRC=$W/src-ab9cd6b9a3ee
BUILD=$SRC/build-cuda
DATA=$W/data
OUT=$W/run-${2:-series}-${SLURM_JOB_ID}
mkdir -p "$OUT"
MAN="$OUT/manifest.txt"

log() { echo "[$(date -u +%FT%T.%NZ)] $*"; }

# ---------------------------------------------------------------- provenance
{
	echo "job_id: ${SLURM_JOB_ID}"
	echo "series_label: ${2:-series}"
	echo "requested_cpulist: ${1:-auto-single-numa-node}"
	echo "date_utc: $(date -u +%FT%TZ)"
	echo "node: $(hostname)"
	echo "source_sha: $SHA"
	echo "slurm_cpus_per_task: ${SLURM_CPUS_PER_TASK}"
	echo "slurm_mem: ${SLURM_MEM_PER_NODE:-unset}"
	echo "slurm_job_gpus: ${SLURM_JOB_GPUS:-unset}"
	echo "cuda_visible_devices: ${CUDA_VISIBLE_DEVICES:-unset}"
	echo "--- inherited cpuset (the allocation's real mask, not the request) ---"
	grep Cpus_allowed_list /proc/self/status
	echo "--- NUMA ---"
	numactl --show 2>/dev/null | tr '\n' ';' ; echo
	numactl --hardware 2>/dev/null | head -12
	echo "--- lscpu topology for the allowed CPUs ---"
	ALLOWED=$(grep Cpus_allowed_list /proc/self/status | awk '{print $2}')
	lscpu -p=CPU,NODE,SOCKET,CORE,ONLINE | grep -v '^#' | head -200 > "$OUT/lscpu_all.csv"
	echo "allowed: $ALLOWED"
	echo "--- devices: UUID is the only stable identity; ordinals are not ---"
	nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu --format=csv
	echo "--- who else is on these devices right now ---"
	nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv
	echo "--- node occupancy ---"
	uptime; squeue -w $(hostname -s) -o "%.10i %.10u %.8T %.6C %.10b" 2>/dev/null | head -10
	echo "--- input identity ---"
	cat "$W/input_sha256.txt"
} > "$MAN" 2>&1

# ------------------------------------------------------------------- toolchain
# The shebang is `bash -l`: MODULEPATH is set by the node's login profile, and
# it differs by CPU architecture, so letting the node resolve it is both
# necessary and more correct than hardcoding the login node's tree.
#
# Do NOT pipe `module load` -- it would run in a subshell and the PATH change
# would be discarded, which is exactly how the first attempt at this job
# reached cmake with no nvcc and burned an allocation.
# The login profile exports a TMPDIR that does not exist on this node, and
# `${TMPDIR:-/tmp}` keeps a non-empty bad value. nvcc writes its intermediates
# there, so that is a build failure with a confusing message. Force a
# job-local, node-local directory we create ourselves.
export TMPDIR="/tmp/mc94-${SLURM_JOB_ID}"
mkdir -p "$TMPDIR" || { echo "cannot create TMPDIR $TMPDIR"; exit 1; }
export TMP="$TMPDIR" TEMP="$TMPDIR" CUDA_CACHE_PATH="$TMPDIR/nv"
trap 'rm -rf "$TMPDIR"' EXIT
module load GCC/13.2.0 CMake/3.27.6-GCCcore-13.2.0 CUDA/12.8.0 \
            FFTW/3.3.10-GCC-13.2.0 LibTIFF/4.6.0-GCCcore-13.2.0 \
            libpng/1.6.40-GCCcore-13.2.0 libjpeg-turbo/3.0.1-GCCcore-13.2.0 \
            zlib/1.2.13-GCCcore-13.2.0
MODRC=$?
{
	echo "--- module load rc: $MODRC ---"
	echo "--- module list ---"; module list 2>&1
	echo "nvcc: $(command -v nvcc || echo MISSING)"; nvcc --version 2>&1 | tail -2
	echo "gcc: $(gcc --version | head -1)"
	echo "cmake: $(cmake --version | head -1)"
} >> "$MAN" 2>&1

# Preflight: fail before the build rather than after, so a toolchain problem
# releases the allocation in seconds instead of holding an exclusive GPU node.
PREFLIGHT_OK=1
for tool in nvcc cmake gcc g++ numactl taskset nvidia-smi python3; do
	command -v "$tool" >/dev/null 2>&1 || { log "PREFLIGHT: missing $tool"; PREFLIGHT_OK=0; }
done
[ -d "$DATA/Movies" ] || { log "PREFLIGHT: missing input Movies"; PREFLIGHT_OK=0; }
[ "$(ls "$DATA"/Movies/*_frameImage.tiff 2>/dev/null | wc -l)" -eq 24 ] || \
	{ log "PREFLIGHT: expected 24 movies"; PREFLIGHT_OK=0; }
nvidia-smi -L > /dev/null 2>&1 || { log "PREFLIGHT: no visible GPU"; PREFLIGHT_OK=0; }
touch "$TMPDIR/.w" 2>/dev/null && rm -f "$TMPDIR/.w" || \
	{ log "PREFLIGHT: TMPDIR $TMPDIR not writable"; PREFLIGHT_OK=0; }
# Compile a trivial .cu here rather than discovering at cmake time that nvcc
# cannot write its intermediates.
echo '__global__ void k(){} int main(){return 0;}' > "$TMPDIR/probe.cu"
nvcc -o "$TMPDIR/probe" "$TMPDIR/probe.cu" > "$OUT/nvcc_probe.log" 2>&1 || \
	{ log "PREFLIGHT: nvcc cannot compile a trivial kernel"; tail -5 "$OUT/nvcc_probe.log"; PREFLIGHT_OK=0; }
if [ $PREFLIGHT_OK -ne 1 ]; then
	echo "PREFLIGHT FAILED -- allocation released without running" >> "$MAN"
	log "PREFLIGHT FAILED"; exit 1
fi
log "preflight ok: nvcc=$(nvcc --version | tail -1 | tr -s ' ')"

log "=== build (inside the allocation, so nothing else perturbs it) ==="
cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DCUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON > "$OUT/configure.log" 2>&1
log "configure rc=$?"
cmake --build "$BUILD" -j 8 > "$OUT/build.log" 2>&1
BRC=$?
log "build rc=$BRC"
if [ $BRC -ne 0 ]; then tail -40 "$OUT/build.log"; echo "BUILD FAILED" >> "$MAN"; exit 1; fi
{
	echo "--- build flags actually used ---"
	grep -m1 CXX_FLAGS "$BUILD"/CMakeFiles/motioncorr_core.dir/flags.make
	echo "motioncorr sha256: $(sha256sum "$BUILD"/motioncorr | awk '{print $1}')"
	echo "cuda symbols present: $(nm -C "$BUILD"/motioncorr 2>/dev/null | grep -c cuda)"
} >> "$MAN" 2>&1

# ------------------------------------------------- fixed CPU budget for BOTH arms
# The allocation is exclusive, so the job's cpuset is the whole node. That is
# what keeps other users off the host, but it is NOT a fixed budget: without
# pinning, the prefetch arm's reader threads would simply spread into CPUs the
# serial arm never used, and the comparison would be between two different
# machines. Pin both arms to the same 16 logical CPUs on ONE NUMA node.
# Taken as a positional script argument, NOT through --export: sbatch splits
# --export on commas at the top level, so --export=MC94_CPUS=0,1,2,3 sets
# MC94_CPUS=0 and silently treats the rest as separate variable names. That
# turned a "16 CPU" series into a 1-CPU series, which the manifest caught only
# because it records the mask actually applied rather than the one requested.
if [ -n "${1:-}" ]; then
  CPULIST="$1"
else
CPULIST=$(python3 - <<'PYC'
import re, collections
allowed = open("/proc/self/status").read()
spec = re.search(r"Cpus_allowed_list:\s*(\S+)", allowed).group(1)
cpus = []
for part in spec.split(","):
    if "-" in part:
        a, b = part.split("-"); cpus += list(range(int(a), int(b) + 1))
    else:
        cpus.append(int(part))
node_of = {}
for line in open("/proc/self/root/sys/devices/system/node/online"):
    pass
import subprocess
out = subprocess.run(["lscpu", "-p=CPU,NODE,CORE"], capture_output=True, text=True).stdout
for line in out.splitlines():
    if line.startswith("#"):
        continue
    c, n, core = line.split(",")[:3]
    node_of[int(c)] = (int(n), int(core))
by_node = collections.defaultdict(list)
for c in cpus:
    if c in node_of:
        by_node[node_of[c][0]].append(c)
best = max(by_node, key=lambda n: len(by_node[n]))
# Prefer distinct physical cores before taking SMT siblings.
seen, chosen = set(), []
for c in sorted(by_node[best]):
    core = node_of[c][1]
    if core not in seen:
        seen.add(core); chosen.append(c)
    if len(chosen) == 16:
        break
for c in sorted(by_node[best]):
    if len(chosen) == 16:
        break
    if c not in chosen:
        chosen.append(c)
print(",".join(str(c) for c in sorted(chosen)))
PYC
)
fi
{
	echo "--- fixed CPU budget applied to BOTH arms ---"
	echo "taskset_cpulist: $CPULIST"
	# Derived by tools/cpu_mask_topology.py, not by an awk split on commas.
	# The comma-only version silently reported zero for a Linux RANGE list
	# like "0-7,32-39" -- which is the form both Cpus_allowed_list and
	# taskset -c use -- and did exactly that in job 3511138's manifest.
	python3 "$SRC/tools/cpu_mask_topology.py" --lscpu "$OUT/lscpu_all.csv" \
	        --mask "$CPULIST" 2>&1 || echo "topology helper unavailable"
} >> "$MAN"

# ---------------------------------------------------------------- run helper
OPTS_COMMON="--i movies.star --use_own --j 8 --gpu 0 --angpix 0.885 --voltage 200 \
 --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --dose_weighting \
 --save_noDW --grouping_for_ps 3 --ps_size 512 --gainref Movies/gain.mrc"

sample_tree_rss() {   # owned process tree only, 200 ms, to a file
	local root=$1 out=$2
	( while kill -0 "$root" 2>/dev/null; do
		total=0
		for p in $(pgrep -P "$root" -d' ' 2>/dev/null) $root; do
			v=$(awk '/^VmRSS:/{print $2}' /proc/$p/status 2>/dev/null)
			[ -n "$v" ] && total=$((total+v))
		done
		echo "$(date +%s.%N) $total"
		sleep 0.2
	  done ) > "$out" 2>/dev/null &
	RSS_SAMPLER=$!
}

run_arm() {   # run_arm <label> <extra args...>
	local label=$1; shift
	local dir="$OUT/$label"
	mkdir -p "$dir/out"
	cd "$DATA"
	nvidia-smi --query-gpu=uuid,memory.used --format=csv,noheader -lms 100 \
	    > "$dir/vram.csv" 2>/dev/null &
	local nv=$!
	local t0 t1
	t0=$(date +%s.%N)
	OMP_NUM_THREADS=8 taskset -c "$CPULIST" \
	  /usr/bin/time -v "$BUILD/motioncorr" $OPTS_COMMON --o "$dir/out/" "$@" \
	    > "$dir/stdout.txt" 2> "$dir/stderr.txt" &
	local pid=$!
	sample_tree_rss "$pid" "$dir/rss_kb.txt"
	wait $pid; local rc=$?
	t1=$(date +%s.%N)
	kill $nv 2>/dev/null; wait $nv 2>/dev/null
	kill $RSS_SAMPLER 2>/dev/null; wait $RSS_SAMPLER 2>/dev/null
	{
		echo "label: $label"
		echo "args: $*"
		echo "cpulist: $CPULIST"
		echo "exit: $rc"
		echo "wall_s: $(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.3f", b-a}')"
		echo "time_v_maxrss_kb: $(grep -m1 'Maximum resident set size' "$dir/stderr.txt" | awk '{print $NF}')"
		echo "tree_peak_rss_kb: $(awk '{if($2>m)m=$2}END{print m+0}' "$dir/rss_kb.txt")"
		echo "peak_vram_mib: $(awk -F, '{gsub(/[^0-9]/,"",$2); if($2+0>m)m=$2+0}END{print m+0}' "$dir/vram.csv")"
		echo "mrc_outputs: $(find "$dir/out" -name '*.mrc' | wc -l)"
		echo "star_outputs: $(find "$dir/out" -name '*.star' | wc -l)"
		echo "prefetch_lines:"; grep '^ prefetch:' "$dir/stdout.txt" || echo "  (off)"
		echo "stage_timers:"; grep -iE "^ *(read movie|apply gain|detect hot|global FFT|global alignment|patch)" "$dir/stdout.txt" | head -12 || true
	} > "$dir/run.txt"
	log "$label exit=$rc wall=$(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.1f", b-a}')s"
	return $rc
}

# ------------------------------------------------- 1. correctness, before timing
log "=== correctness: prefetch off vs on, 24 movies ==="
run_arm correctness_off
run_arm correctness_on --prefetch

log "=== exact same-backend comparison ==="
# One implementation, the maintained one. This block used to be an inline
# heredoc that compared only bytes 0..224 and set the 800-byte label area
# aside wholesale -- so the correctness_compare.txt artifacts it produced
# backed a much weaker claim than the surrounding prose made. It was preceded
# by `compare_prefetch_arms.py --root /dev/null >/dev/null 2>&1 || true`,
# which looked like a tool invocation and established nothing at all.
#
# The self-test runs first and is FATAL: a comparison whose own negative
# control fails must not be allowed to certify anything.
python3 "$SRC/tools/compare_prefetch_arms.py" --self-test > "$OUT/compare_self_test.txt" 2>&1
SELFRC=$?
echo "compare_self_test_rc: $SELFRC" >> "$MAN"
if [ $SELFRC -ne 0 ]; then
	log "COMPARISON SELF-TEST FAILED -- refusing to certify anything with it"
	cat "$OUT/compare_self_test.txt"
	exit 4
fi
python3 "$SRC/tools/compare_prefetch_arms.py" \
        --pair "$OUT/correctness_off" "$OUT/correctness_on" \
        > "$OUT/correctness_compare.txt" 2>&1
CMP=$?
log "correctness comparison rc=$CMP"
cat "$OUT/correctness_compare.txt"
echo "correctness_compare_rc: $CMP" >> "$MAN"

if [ $CMP -ne 0 ]; then
	log "ARMS DISAGREE -- refusing to produce timings from arms that do not match"
	echo "TIMING SKIPPED: correctness failed" >> "$MAN"
	exit 2
fi

# ------------------------------------------------------- 2. paired timings
log "=== paired timings, arm order alternating, 3 pairs ==="
: > "$OUT/pairs.tsv"
for pair in 1 2 3; do
	if [ $((pair % 2)) -eq 1 ]; then
		run_arm pair${pair}_first_off;           run_arm pair${pair}_second_on --prefetch
	else
		run_arm pair${pair}_first_on --prefetch; run_arm pair${pair}_second_off
	fi
	for f in $OUT/pair${pair}_*; do
		[ -f "$f/run.txt" ] || continue
		lbl=$(basename $f)
		printf "%s\t%s\t%s\t%s\n" "$pair" "$lbl" \
		  "$(awk -F': ' '/^wall_s/{print $2}' $f/run.txt)" \
		  "$(awk -F': ' '/^tree_peak_rss_kb/{print $2}' $f/run.txt)" >> "$OUT/pairs.tsv"
	done
done

log "=== timing summary (no verdict: n=3 is a screen) ==="
cat "$OUT/pairs.tsv"
log "=== ALL DONE ==="
echo "finished_utc: $(date -u +%FT%TZ)" >> "$MAN"
