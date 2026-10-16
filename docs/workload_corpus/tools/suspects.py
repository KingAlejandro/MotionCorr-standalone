#!/usr/bin/env python3
"""Write the redo file for run_matrix.py --redo: arms with no usable record yet.

Usage: suspects.py FAMILIES_JSON RESULTS_DIR GEN OUT_JSON
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runfilter  # noqa: E402


def main():
    fams = {f['id']: f for f in json.load(open(sys.argv[1]))['families']}
    results, gen, out = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    runs = [json.loads(l) for l in open(os.path.join(results, 'runs.jsonl')) if l.strip()]
    usable, _ = runfilter.usable_records(runs)
    arms = set()
    for r in runs:
        if r['kind'] == 'warmup':
            continue
        k = runfilter.arm_key(r)
        if k not in usable:
            arms.add(k)
    json.dump({'gen': gen, 'arms': sorted(arms)}, open(out, 'w'), indent=1)
    print(len(arms), 'arms to redo')
    for a in sorted(arms):
        print(' ', a)


if __name__ == '__main__':
    main()
