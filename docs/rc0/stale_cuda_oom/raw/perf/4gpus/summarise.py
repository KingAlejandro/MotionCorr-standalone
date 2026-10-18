#!/usr/bin/env python3
"""Summarise the 4GPUs D11 timing windows: D14 label per workload and host load per window.
Label (D14): Fail = resolved slowdown (95% CI of median d entirely above 0); Pass = not Fail and
CI upper <= +0.5% of median main wall; Unresolved = otherwise."""
import json, re, statistics, sys
from pathlib import Path
T = Path(sys.argv[1]); rows = []
for w in ('tutG', 'tutL', 'e10216L'):
    d = T / w
    if not (d / 'result.json').exists():
        rows.append({'workload': w, 'missing': True}); continue
    r = json.loads((d / 'result.json').read_text())
    lo, hi = r['ci95_s']; ma = r['median_wall_A_s']
    label = 'Fail' if lo > 0 else ('Pass' if hi <= 0.005 * ma else 'Unresolved')
    # mpstat: per-CPU %idle samples; payload lane 88-95, runner 120-123, everything else = other.
    busy = {'lane': [], 'runner': [], 'other': []}
    for line in (d / 'mpstat.txt').read_text().splitlines():
        f = line.split()
        if f and f[0] != 'Average:' and len(f) > 2 and f[1] in ('AM', 'PM'):
            f = [f[0]] + f[2:]
        if len(f) > 11 and f[1].isdigit() and re.match(r'\d\d:\d\d:\d\d', f[0]):
            cpu, idle = int(f[1]), float(f[-1])
            k = 'lane' if 88 <= cpu <= 95 else 'runner' if 120 <= cpu <= 123 else 'other'
            busy[k].append(100 - idle)
    n_other = 124 - 8 - 4
    other_cores = statistics.mean(busy['other']) * n_other / 100 if busy['other'] else None
    util = {}
    for line in (d / 'nvidia-smi.csv').read_text().splitlines()[1:]:
        f = [x.strip() for x in line.split(',')]
        if len(f) >= 4 and f[1].isdigit():
            util.setdefault(int(f[1]), []).append(float(f[2].split()[0]))
    apps = (d / 'compute-apps.txt').read_text()
    foreign_apps = sorted({m for m in re.findall(r'(GPU-[0-9a-f-]+), (\d+)', apps) if not m[0].startswith('GPU-b2cb2c39')})
    win = (d / 'window.txt').read_text()
    rows.append({
        'workload': w, 'label': label, 'N': r['pairs'], 'AB': r['pairs_AB'], 'BA': r['pairs_BA'],
        'incomplete': r['incomplete'], 'median_d_s': r['median_d_s'], 'median_d_pct': r['median_d_pct'],
        'ci95_s': r['ci95_s'], 'ci_lower_pct': r['ci_lower_pct'], 'ci_upper_pct': r['ci_upper_pct'],
        'ci_confidence': r['ci_confidence'], 'median_wall_A_s': ma, 'median_wall_B_s': r['median_wall_B_s'],
        'iqr_A_s': r['iqr_A_s'], 'iqr_B_s': r['iqr_B_s'], 'null_pairs': r['null_pairs'],
        'null_median_s': r['null_median_s'], 'null_ci95_s': r['null_ci95_s'], 'null_range_s': r['null_range_s'],
        'pilot_sd_s': r['design']['pilot_robust_sd_s'], 'design_N': r['design']['N'],
        'expected_upper_s': r['design']['expected_upper_s_at_N'],
        'identity_identical': (r['identity'] or {}).get('identical'),
        'retries': sum(1 for l in (d / 'runs.jsonl').read_text().splitlines() if '"retained": false' in l),
        'window': re.findall(r'window (?:start|end) (\S+)', win),
        'lane_busy_pct_mean': statistics.mean(busy['lane']) if busy['lane'] else None,
        'other_cpus_busy_cores_mean': other_cores,
        'other_cpus_busy_cores_max': max(busy['other']) if busy['other'] else None,
        'gpu_util_mean_pct': {k: round(statistics.mean(v), 1) for k, v in util.items()},
        'foreign_gpu_apps_seen': foreign_apps,
    })
(T / 'summary.json').write_text(json.dumps(rows, indent=1))
for r in rows:
    if r.get('missing'): print(r['workload'], 'missing'); continue
    print(f"{r['workload']:<8} {r['label']:<10} N={r['N']} ({r['AB']}/{r['BA']}) median {r['median_d_s']:+.4f} s ({r['median_d_pct']:+.2f}%) "
          f"CI [{r['ci95_s'][0]:+.4f}, {r['ci95_s'][1]:+.4f}] s = [{r['ci_lower_pct']:+.2f}%, {r['ci_upper_pct']:+.2f}%] "
          f"null {r['null_median_s']:+.4f} CI {r['null_ci95_s']} | A {r['median_wall_A_s']:.3f} IQR {r['iqr_A_s']:.3f} "
          f"B {r['median_wall_B_s']:.3f} IQR {r['iqr_B_s']:.3f} | retries {r['retries']} identity {r['identity_identical']} "
          f"| window {r['window']} lane {r['lane_busy_pct_mean']:.0f}% other cores {r['other_cpus_busy_cores_mean']:.1f} gpu {r['gpu_util_mean_pct']} foreign {r['foreign_gpu_apps_seen'][:4]}")
