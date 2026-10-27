#!/bin/bash
# Read-only kernel Xid snapshot (the only privileged use granted for i8: passwordless sudo, log reads only).
# usage: c1_xid.sh LABEL   -> $C1_SCR/logs/xid-LABEL.txt : every 'NVRM: Xid' line of /var/log/kern.log* (rotated logs via zgrep) and the Xid lines of 'dmesg -T',
# with PCI id -> GPU UUID table, so a later snapshot can be diffed against an earlier one.
set -u
source "$(dirname "$0")/c1_env.sh" || exit 1
o="$C1_SCR/logs/xid-$1.txt"; mkdir -p "$C1_SCR/logs"
{
  date -u +%FT%TZ
  echo "--- pci -> uuid"; nvidia-smi --query-gpu=index,uuid,pci.bus_id --format=csv,noheader
  echo "--- kern.log* (grep NVRM: Xid, ISO-timestamp lines only)"
  sudo -n grep -h "NVRM: Xid" /var/log/kern.log /var/log/kern.log.1 2>&1 | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' | cut -c1-260
  for z in /var/log/kern.log.*.gz; do sudo -n zgrep -h "NVRM: Xid" "$z" 2>&1 | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' | cut -c1-260; done
  echo "--- dmesg -T (Xid lines)"; sudo -n dmesg -T 2>&1 | grep -E 'NVRM: Xid' | cut -c1-260
  echo "--- counts"; echo "kern.log: $(sudo -n grep -c 'NVRM: Xid' /var/log/kern.log 2>&1)  kern.log.1: $(sudo -n grep -c 'NVRM: Xid' /var/log/kern.log.1 2>&1)"
} > "$o" 2>&1
echo "$o: $(grep -cE '^[0-9]{4}-.*NVRM: Xid' "$o") timestamped Xid lines"
