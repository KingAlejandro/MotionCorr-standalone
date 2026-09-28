#!/bin/bash
# Paired serial-vs-prefetch end-to-end screen for issue #94.
#
# THIS SCRIPT DOES NOT RUN WITHOUT AN ASSIGNED SLOT. #26 owns this round's
# initial GPU benchmark slot; set MC94_SLOT_GRANTED to the assigning reference
# to proceed. That guard exists so the script cannot be run by accident while
# somebody else is measuring on the same box.
#
# Design, and why each part is here:
#   * Paired, with the arm order ALTERNATING inside each pair, and the order
#     label kept. Unpaired series on this host have produced conclusions with
#     the wrong sign; the positional bias (page-cache warming for the arm that
#     runs second) is a property of the workload and has measured ~20 ms for
#     TIFF-read/MRC-write changes, so it is never assumed negligible. Splitting
#     the pairs by order afterwards recovers it from the same data for free.
#   * The build happens INSIDE the benchmark lock, because compiles do not take
#     it themselves and would otherwise land between acquiring and measuring.
#   * The settle gate runs AFTER acquiring, never before: the lock serialises
#     ownership but not the previous holder's load decay tail.
#   * Quiescence is probed with `pgrep -x` by exact process name. `pgrep -f`
#     matches the guard's own command line and is permanently non-zero, which
#     degrades silently to "wait the whole timeout, then run anyway".
#   * Foreign load is sampled continuously at 1 Hz, not before and after: a
#     point probe straddles spikes.
#   * The sampler is never started inside $( ). A backgrounded subshell there
#     inherits the command-substitution pipe and the parent blocks forever.
#   * Every run records its inherited Cpus_allowed_list, the lscpu topology,
#     the NUMA policy and the GPU UUID. The taskset mask is an admission lane,
#     not a claim of locality.
#
# Outputs one directory per run with the complete corrected products retained,
# so the arms can be compared exactly rather than by a scalar checksum.
set -u

usage() {
	cat <<'USAGE'
usage: prefetch_gpu_screen.sh --binary PATH --star PATH --outdir PATH [options]

  --binary PATH     motioncorr built with -DCUDA=ON -DCMAKE_BUILD_TYPE=Release
  --star PATH       input movie STAR (the 24 tutorial movies)
  --outdir PATH     results root; must not already exist
  --gpu N           device id to use (default 0); one GPU first
  --pairs N         paired blocks, minimum 3 (default 3)
  --threads N       --j for both arms (default 8); keep both arms identical
  --cpus LIST       taskset list (default 96-111, the round's aggregate lane)
  --prefetch-mem N  --prefetch_mem_mb for the prefetch arm (default 0 = auto)
  --angpix N        pixel size; default 0.885 is the RELION tutorial value and
                    MUST be checked against the protocol actually being used
  --dose N          dose per frame; default 1.277, same caveat
  --extra "ARGS"    extra motioncorr arguments applied to BOTH arms
USAGE
}

[ -n "${MC94_SLOT_GRANTED:-}" ] || {
	echo "REFUSING: no GPU slot assigned. #26 owns this round's initial slot." >&2
	echo "Set MC94_SLOT_GRANTED=<assigning reference> once Codex assigns one." >&2
	exit 3
}

# The WHOLE series must hold one benchmark lock: a compile or a competing run
# landing between two arms invalidates the pair. Re-exec under the lock once,
# rather than trusting the caller to wrap the invocation.
if [ -z "${MC94_LOCKED:-}" ]; then
	export MC94_LOCKED=$(date +%s)
	exec flock -w 7200 /tmp/motioncorr-bench.lock "$0" "$@"
fi

BINARY=""; STAR=""; OUTDIR=""; GPU=0; PAIRS=3; THREADS=8
CPUS="96-111"; PREFETCH_MEM=0; EXTRA=""; ANGPIX=0.885; DOSE=1.277
while [ $# -gt 0 ]; do
	case "$1" in
		--binary) BINARY="$2"; shift 2;;
		--star) STAR="$2"; shift 2;;
		--outdir) OUTDIR="$2"; shift 2;;
		--gpu) GPU="$2"; shift 2;;
		--pairs) PAIRS="$2"; shift 2;;
		--threads) THREADS="$2"; shift 2;;
		--cpus) CPUS="$2"; shift 2;;
		--prefetch-mem) PREFETCH_MEM="$2"; shift 2;;
		--extra) EXTRA="$2"; shift 2;;
		--angpix) ANGPIX="$2"; shift 2;;
		--dose) DOSE="$2"; shift 2;;
		-h|--help) usage; exit 0;;
		*) echo "unknown argument: $1" >&2; usage; exit 2;;
	esac
done

[ -x "$BINARY" ] || { echo "no such binary: $BINARY" >&2; exit 2; }
[ -f "$STAR" ] || { echo "no such STAR: $STAR" >&2; exit 2; }
[ -n "$OUTDIR" ] || { usage; exit 2; }
[ -e "$OUTDIR" ] && { echo "outdir already exists, refusing to overwrite: $OUTDIR" >&2; exit 2; }
[ "$PAIRS" -ge 3 ] || { echo "at least 3 paired blocks are required" >&2; exit 2; }

mkdir -p "$OUTDIR"
OUTDIR=$(cd "$OUTDIR" && pwd)
MANIFEST="$OUTDIR/manifest.txt"

# --- provenance, recorded before anything is measured ----------------------
{
	echo "script: $0"
	echo "slot_reference: $MC94_SLOT_GRANTED"
	echo "date_utc: $(date -u +%FT%TZ)"
	echo "host: $(hostname)"
	echo "binary: $BINARY"
	echo "binary_sha256: $(sha256sum "$BINARY" | awk '{print $1}')"
	echo "star: $STAR"
	echo "star_sha256: $(sha256sum "$STAR" | awk '{print $1}')"
	echo "threads: $THREADS"
	echo "taskset_cpus: $CPUS"
	echo "pairs: $PAIRS"
	echo "gpu_index: $GPU"
	echo "prefetch_mem_mb: $PREFETCH_MEM"
	echo "angpix: $ANGPIX"
	echo "dose_per_frame: $DOSE"
	echo "lock: /tmp/motioncorr-bench.lock held for the whole series"
	echo "extra_args: $EXTRA"
	echo "--- input movies (sha256) ---"
	awk '/\.(tif|tiff|mrc|mrcs|eer)/ {print $1}' "$STAR" | while read -r m; do
		f="$(dirname "$STAR")/$m"
		[ -f "$f" ] && echo "$(sha256sum "$f")"
	done
	echo "--- lscpu topology (CPU,NODE,SOCKET,CORE) ---"
	lscpu -p=CPU,NODE,SOCKET,CORE,ONLINE 2>/dev/null | grep -v '^#'
	echo "--- numactl hardware ---"
	numactl --hardware 2>/dev/null || echo "numactl unavailable"
	echo "--- gpu inventory ---"
	nvidia-smi --query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu \
	           --format=csv 2>/dev/null || echo "nvidia-smi unavailable"
	echo "--- pre-existing load ---"
	uptime
	ps -eo user,pid,pcpu,comm --sort=-pcpu | head -15
} > "$MANIFEST" 2>&1

# --- 1 Hz foreign-load sampler; never started inside $( ) -------------------
SAMPLER_PID=""
start_sampler() {   # sets SAMPLER_PID as a global, deliberately
	local out="$1"
	( while true; do
		echo "$(date +%s.%N) $(ps -eo user,pcpu --no-headers 2>/dev/null \
		        | awk -v me="$(id -un)" '$1!=me {s+=$2} END {printf "%.1f", s+0}')"
		sleep 1
	  done ) > "$out" 2>/dev/null &
	SAMPLER_PID=$!
}
stop_sampler() {
	[ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
	wait "$SAMPLER_PID" 2>/dev/null
	SAMPLER_PID=""
}

# --- one measured run -------------------------------------------------------
run_arm() {   # run_arm <arm> <pair> <position>
	local arm="$1" pair="$2" position="$3"
	local dir="$OUTDIR/pair${pair}_${position}_${arm}"
	mkdir -p "$dir/out"
	local args=(--i "$STAR" --o "$dir/out/" --use_own --j "$THREADS"
	            --gpu "$GPU" --angpix "$ANGPIX" --voltage 300 --dose_per_frame "$DOSE"
	            --patch_x 5 --patch_y 5 --bfactor 150 --grouping_for_ps 3 --ps_size 512)
	# shellcheck disable=SC2206
	[ -n "$EXTRA" ] && args+=($EXTRA)
	if [ "$arm" = "prefetch" ]; then
		args+=(--prefetch --prefetch_mem_mb "$PREFETCH_MEM")
	fi

	start_sampler "$dir/foreign_load.txt"
	# 5 ms NVML sampling: a 50 ms sampler under-read a VRAM peak by 4 MiB on
	# this host, and every sampled peak is a lower bound on the true peak.
	nvidia-smi --query-gpu=index,memory.used --format=csv,noheader -lms 5 \
	           -i "$GPU" > "$dir/vram.csv" 2>/dev/null &
	local nvsmi_pid=$!

	{
		echo "arm: $arm"
		echo "pair: $pair"
		echo "position_in_pair: $position"
		echo "start_utc: $(date -u +%FT%T.%NZ)"
		echo "command: taskset -c $CPUS ${args[*]}"
	} > "$dir/run.txt"

	local t0 t1
	t0=$(date +%s.%N)
	taskset -c "$CPUS" /usr/bin/time -v "$BINARY" "${args[@]}" \
		> "$dir/stdout.txt" 2> "$dir/stderr.txt"
	local rc=$?
	t1=$(date +%s.%N)

	kill "$nvsmi_pid" 2>/dev/null; wait "$nvsmi_pid" 2>/dev/null
	stop_sampler

	{
		echo "end_utc: $(date -u +%FT%T.%NZ)"
		echo "exit_code: $rc"
		echo "wall_seconds: $(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", b-a}')"
		echo "max_rss_kb: $(grep -m1 'Maximum resident set size' "$dir/stderr.txt" | awk '{print $NF}')"
		echo "peak_vram_mib: $(awk -F, 'NR>0{gsub(/[^0-9]/,"",$2); if ($2+0>m) m=$2+0} END{print m+0}' "$dir/vram.csv" 2>/dev/null)"
		echo "foreign_load_mean_max_n: $(awk '{s+=$2; if($2>m)m=$2; n++} END{printf "%.1f %.1f %d", (n?s/n:0), m+0, n+0}' "$dir/foreign_load.txt" 2>/dev/null)"
		echo "prefetch_stats:"
		grep '^ prefetch:' "$dir/stdout.txt" || echo "  (serial arm: none)"
		echo "outputs_mrc: $(find "$dir/out" -name '*.mrc' | wc -l)"
		echo "outputs_star: $(find "$dir/out" -name '*.star' | wc -l)"
	} >> "$dir/run.txt"
	echo "$pair $position $arm $(awk -v a="$t0" -v b="$t1" 'BEGIN{printf "%.3f", b-a}') $rc" \
		>> "$OUTDIR/pairs.tsv"
	return $rc
}

# --- settle gate, AFTER acquiring the lock ---------------------------------
# The lock serialises ownership but not the previous holder's load decay tail:
# a run starting at the instant of release still competes with its residue, and
# load1 is a ~1-minute decayed figure, so pgrep can legitimately read 0 while
# the box is still recovering. The observed wait is logged so a long one shows.
export OMP_NUM_THREADS="$THREADS"
{
	echo "lock_acquired_after_s: $(( $(date +%s) - MC94_LOCKED ))"
	echo "inherited_cpus_allowed: $(grep Cpus_allowed_list /proc/self/status | awk '{print $2}')"
	echo "numa_policy: $(numactl --show 2>/dev/null | tr '\n' ';')"
} >> "$MANIFEST"

settle_start=$(date +%s)
while :; do
	# `pgrep -x` by exact process name. `pgrep -f` matches the guard's own
	# command line, is permanently non-zero, and degrades silently to
	# "wait the whole timeout, then run anyway".
	compilers=$({ pgrep -x cc1plus; pgrep -x nvcc; pgrep -x cicc; pgrep -x ptxas; } | wc -l)
	load1=$(awk '{print $1}' /proc/loadavg)
	if [ "$compilers" -eq 0 ] && awk -v l="$load1" 'BEGIN{exit !(l<2.0)}'; then break; fi
	if [ $(( $(date +%s) - settle_start )) -ge 900 ]; then
		echo "settle_gate: TIMED OUT after 900s (compilers=$compilers load1=$load1)" >> "$MANIFEST"
		echo "WARNING: the settle gate timed out; these numbers are contaminated." >&2
		break
	fi
	sleep 10
done
{
	echo "settle_waited_s: $(( $(date +%s) - settle_start ))"
	echo "settle_load1: $(awk '{print $1}' /proc/loadavg)"
	echo "taskset_cpus_effective: $(taskset -c "$CPUS" grep Cpus_allowed_list /proc/self/status | awk '{print $2}')"
} >> "$MANIFEST"

: > "$OUTDIR/pairs.tsv"
FAILED=0
for pair in $(seq 1 "$PAIRS"); do
	if [ $(( pair % 2 )) -eq 1 ]; then
		run_arm serial   "$pair" first  || FAILED=1
		run_arm prefetch "$pair" second || FAILED=1
	else
		run_arm prefetch "$pair" first  || FAILED=1
		run_arm serial   "$pair" second || FAILED=1
	fi
done

echo "failed_runs: $FAILED" >> "$MANIFEST"
echo
echo "pairs.tsv (pair position arm wall_s exit):"
cat "$OUTDIR/pairs.tsv"
echo
echo "Outputs retained per run under $OUTDIR. Compare arms exactly with:"
echo "  tools/compare_prefetch_arms.py --root $OUTDIR"
echo "No conclusion is drawn here: analysis is a separate, reviewable step."
