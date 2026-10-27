#!/bin/bash
# Read-only live measurement of cpu64 access, occupancy, memory, disk, lock state and earlier scratch. Creates nothing, deletes nothing.
set -u
echo "utc $(date -u +%FT%TZ)"; echo "host $(hostname)"; uptime; echo "nproc $(nproc)"
free -b | head -2; df -B1 /tmp | tail -2
echo "--- top processes"; ps -eo pid,ppid,psr,pcpu,args --sort=-pcpu | head -15 | cut -c1-200
echo "--- locks (flock -n probe on the existing file, never created or removed here)"
for f in /tmp/motioncorr*.lock; do
  if flock -n "$f" -c true 2>/dev/null; then echo "free  $f"; else echo "HELD  $f"; fi
done
echo "--- earlier scratch (bytes, regular files)"
for d in /tmp/motioncorr-* /tmp/mc-*; do [ -d "$d" ] && printf '%s\t%s\n' "$(du -sb "$d" 2>/dev/null | cut -f1)" "$d"; done | sort -n
echo "--- toolchain"
ls -l /home/ubuntu/.mc-venv/bin/cmake /home/ubuntu/.mc-venv/bin/ctest /home/ubuntu/.mc-venv/bin/python3 2>&1
/home/ubuntu/.mc-venv/bin/cmake --version | head -1; /home/ubuntu/.mc-venv/bin/python3 -c "import sys,numpy;print('python',sys.version.split()[0],'numpy',numpy.__version__,numpy.__file__)"
g++ --version | head -1; ld --version | head -1; echo "glibc $(ldd --version | head -1)"
