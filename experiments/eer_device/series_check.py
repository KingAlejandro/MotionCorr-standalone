#!/usr/bin/env python3
"""Print 'ok' if a timing series is clean: foreign CPU <= 0.25 cores on every run. Otherwise prints the reason
(the series is then retried; its files are kept). Activity seen on GPUs 1-3 is appended for the record. usage: series_check.py <timing.json> <gpu-samples.csv>"""
import csv, json, sys
try:
    d = json.loads(open(sys.argv[1]).read())
    p = d['pairs']
    fc = max(max(p['device']['foreign_cores']['values'], default=0), max(p.get('host', {}).get('foreign_cores', {}).get('values', [0]), default=0))
    msg = []
    if fc > 0.25:
        msg.append('foreign_cpu=%.3f' % fc)
    busy = total = 0
    try:
        for row in csv.reader(open(sys.argv[2])):
            if len(row) >= 4 and row[1].strip() in ('1', '2', '3'):
                total += 1
                busy += int(row[2].strip().split()[0]) > 0
    except OSError:
        pass
    # GPU 1-3 activity is recorded, not a retry criterion (other programme lanes use them by design)
    print(('ok' if not msg else ' '.join(msg)) + ('' if not busy else ' [other_gpu_busy_samples=%d/%d]' % (busy, total)))
except Exception as e:
    print('bad:%s' % e)
