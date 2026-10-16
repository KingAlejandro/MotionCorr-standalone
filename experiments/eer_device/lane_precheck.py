#!/usr/bin/env python3
"""Record foreign use of the lane before a timing series: CPU busy time on the allowed CPUs over
a short idle sample, and compute processes on the GPU. Prints one JSON object; exit 1 if the
foreign CPU use exceeds the limit. Usage: lane_precheck.py <gpu-uuid> <cpu-list e.g. 96-103> [seconds] [limit-cores]"""
import json, os, subprocess, sys, time

def cpus(spec):
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out

def busy(cs):
    hz = os.sysconf('SC_CLK_TCK'); tot = 0.0
    for line in open('/proc/stat'):
        f = line.split()
        if f[0].startswith('cpu') and f[0] != 'cpu' and int(f[0][3:]) in cs:
            u, n, s, idle, iow, irq, sirq, steal = map(int, f[1:9])
            tot += (u + n + s + irq + sirq + steal) / hz
    return tot

uuid, spec = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
limit = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
cs = cpus(spec)
b0, t0 = busy(cs), time.time()
time.sleep(secs)
cores = (busy(cs) - b0) / (time.time() - t0)
apps = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name,used_memory', '--format=csv,noheader'],
                      capture_output=True, text=True).stdout.strip().splitlines()
mine = [a for a in apps if a.startswith(uuid)]
ps = subprocess.run(['ps', '-eLo', 'psr,pid,user,comm'], capture_output=True, text=True).stdout.splitlines()[1:]
onlane = sorted({' '.join(l.split()[1:]) for l in ps if l.split() and l.split()[0].isdigit() and int(l.split()[0]) in cs})
print(json.dumps({'time': time.strftime('%Y-%m-%dT%H:%M:%S'), 'cpus': spec, 'sample_s': secs, 'foreign_cores': round(cores, 4),
                  'limit_cores': limit, 'gpu_foreign_compute_apps': mine, 'threads_seen_on_lane_cpus': onlane[:20]}))
sys.exit(1 if cores > limit or mine else 0)
