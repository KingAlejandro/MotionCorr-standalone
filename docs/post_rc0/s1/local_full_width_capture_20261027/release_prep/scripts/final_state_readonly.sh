#!/bin/bash
# Read-only end-of-preparation state: no owned process, locks free, namespace inventory and size, no evidence or native-input directory, nothing under the baseline changed.
R=/tmp/motioncorr-lfw-capture-20261027
echo "utc $(date -u +%FT%TZ)"; uptime
echo "--- processes owned by the preparation (cwd/args under the namespace)"; ps -eo pid,ppid,psr,pcpu,args | grep -E "motioncorr-lfw-capture|lane.py|run_capture_fw|motioncorr " | grep -v grep | head
echo "--- locks (probe only)"; for f in /tmp/motioncorr*.lock; do if flock -n "$f" -c true 2>/dev/null; then echo "free $f"; else echo "HELD $f"; fi; done | sort | uniq -c -w4
echo "--- namespace"; du -sb $R | cut -f1; ls -1 $R; ls -1 $R/prep $R/receipts | head -60
echo "--- future outputs absent"; ls -d $R/evidence $R/native-input $R/PARENT_RELEASE.json 2>&1
echo "--- build tree unchanged since the records"; sha256sum $R/build/motioncorr $R/build/local_ccf_capture | cut -c1-64
echo "--- baseline unchanged"; (cd /tmp/motioncorr-lfw-v5-20261026/evidence/noisy/ON && find . -type f | sort | xargs sha256sum | sha256sum)
