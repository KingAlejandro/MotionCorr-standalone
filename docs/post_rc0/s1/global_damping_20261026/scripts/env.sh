# Sourced on cpu64. Lane: CPUs 48-55 only, non-blocking lock, venv cmake/python.
# Required: DS_SC (scratch under /tmp/motioncorr-damping-<sha12>), DS_CAND_SHA, DS_BASE_SHA.
: "${DS_SC:?}" "${DS_CAND_SHA:?}" "${DS_BASE_SHA:?}"
case "$DS_SC" in /tmp/motioncorr-damping-*) ;; *) echo "scratch outside /tmp/motioncorr-damping-*" >&2; return 1 2>/dev/null || exit 1;; esac
export DS_CPUS=48-55
export DS_LOCK=/tmp/motioncorr-damping-cpu48-55.lock
export DS_VENV=$HOME/.mc-venv
export DS_PY=$DS_VENV/bin/python3
export PATH=$DS_VENV/bin:$PATH
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
unset PYTHONOPTIMIZE OMP_PROC_BIND OMP_PLACES
# Run a command under the lane: nonblocking lock, CPU affinity. usage: lane CMD...
lane() { flock -n "$DS_LOCK" taskset -c "$DS_CPUS" "$@"; }
