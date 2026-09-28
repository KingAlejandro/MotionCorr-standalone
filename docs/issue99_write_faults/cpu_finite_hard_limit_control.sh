#!/bin/bash
set -uo pipefail
source ~/.mc-venv/bin/activate
R=$HOME/mc-i99r2
exec > >(tee "$R/hardlimit.log") 2>&1
echo "=== external finite-hard-limit control, corrected ==="
date -Is; hostname; uptime
echo "-- why the first attempt was void: bash's 'ulimit -H -f N' leaves the soft"
echo "-- limit at infinity, so soft > hard and setrlimit returns EINVAL:"
taskset -c 32-63 bash -c 'ulimit -H -f 8192; echo "  rc=$?"; python3 -c "import resource;print(\"  resulting pair:\", resource.getrlimit(resource.RLIMIT_FSIZE))"'
echo "-- 'ulimit -f N' sets BOTH, which is what the control needs:"
taskset -c 32-63 bash -c 'ulimit -f 8192; echo "  rc=$?"; python3 -c "import resource;print(\"  resulting pair:\", resource.getrlimit(resource.RLIMIT_FSIZE))"'
echo "-- payload cpuset/NUMA witness for the runs below:"
taskset -c 32-63 bash -c 'grep -E "Cpus_allowed_list|Mems_allowed_list" /proc/self/status; (numactl --show 2>/dev/null | head -4)'

run_under () {  # name builddir
  local name=$1 bd=$2
  echo
  echo "===== $name : ctest -V -R 'ImageWriteFaults|WriteFaults' under hard=soft=8388608 ====="
  ( cd "$bd" && taskset -c 32-63 bash -c '
      ulimit -f 8192 || { echo "ULIMIT FAILED"; exit 90; }
      python3 -c "import resource;print(\"inherited by ctest:\", resource.getrlimit(resource.RLIMIT_FSIZE))"
      ctest -V -R "ImageWriteFaults|WriteFaults"' ) > "$R/hl-$name.log" 2>&1
  echo "exit=$?"
  grep -E 'inherited by ctest|inherited RLIMIT|setrlimit|ValueError|OSError|Traceback|preexec|unexpected exception|phase [0-9]|finite-hard|Passed|\*\*\*|tests passed|tests failed' "$R/hl-$name.log" | head -30
}

body () {
  echo "### lock acquired"; date -Is
  run_under candidate      "$R/src-new/build-cpu"
  run_under predelta-tests "$R/src-oldt/build-cpu"
  echo
  echo "===== predelta-tests WITHOUT any finite hard limit (isolates the cause) ====="
  ( cd "$R/src-oldt/build-cpu" && taskset -c 32-63 ctest -R "ImageWriteFaults|WriteFaults" ) \
      > "$R/hl-predelta-nolimit.log" 2>&1
  echo "exit=$?"; grep -E 'tests passed|tests failed' "$R/hl-predelta-nolimit.log"
  echo "### load at end:"; uptime
}
flock /tmp/motioncorr-issue96-cpu-validation.lock bash -c "R=$R; $(declare -f run_under); $(declare -f body); body"
echo "=== HL DONE rc=$? ==="; date -Is
