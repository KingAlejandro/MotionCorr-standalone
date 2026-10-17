#!/usr/bin/env python3
"""Grade QF item 13 output against #204's recorded verdicts (item_records/mrc_204.json).

Rule, per record: the frozen-SHA verdict equals #204's, except in the two `errors` runs, where every
record must now PASS (fail explicitly, publish nothing): #205 (F3, maintainer D5) is the declared
intentional change from #204's 20/26. A record present on one side only is a FAIL (coverage). The
six `damaged` records #204 recorded as FAIL are F4 (compressed decoder exit status ignored, a
documented RC0 limitation, #214); they must still FAIL and are listed as KNOWN-F4. A known-F4 record
that now passes is reported as a change and fails the grade until explained.
Usage: grade_item13.py $QF_W/item13-mrc     (writes grade.json there; exit 0 only on PASS)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from item13_keys import real_verdicts, synth_verdicts  # noqa: E402

O = Path(sys.argv[1])
REC = json.loads((HERE / 'item_records' / 'mrc_204.json').read_text())['runs']
EXPECT_ALL_PASS = {'cuda-errors', 'cpu-errors'}


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def current():
    cur = {}
    synth = {'cuda-matrix': ['cuda-matrix'], 'cuda-refuse': ['cuda-refuse'], 'cuda-compressed': ['cuda-compressed'],
             'cuda-errors': ['cuda-errors'], 'cuda-options': ['cuda-options'], 'cpu-matrix': ['cpu-matrix'],
             'cpu-errors': ['cpu-errors']}
    for run, files in synth.items():
        doc = load(O / f'{files[0]}.json')
        cur[run] = synth_verdicts(doc) if doc else None
    doc = load(O / 'real.json')
    cur['real'] = real_verdicts(doc) if doc is not None else None
    for run in REC:
        if run.startswith('opts-'):
            doc = load(O / f'opts_{run[5:]}.json')
            cur[run] = real_verdicts(doc, run[5:]) if doc is not None else None
    return cur


cur = current()
report = {'record': 'PR #204 @ 5944617b', 'runs': {}, 'problems': [], 'known_f4': []}
for run, rec in REC.items():
    got = cur.get(run)
    r = {'recorded': len(rec), 'current': None if got is None else len(got), 'mismatches': []}
    if got is None:
        report['problems'].append(f'{run}: no output (UNRUN)')
    else:
        for key in sorted(set(rec) | set(got)):
            want = 'PASS' if run in EXPECT_ALL_PASS else rec.get(key)
            have = got.get(key)
            if key not in got or key not in rec:
                r['mismatches'].append(f'{key}: recorded {rec.get(key)}, current {have}')
            elif have != want:
                r['mismatches'].append(f'{key}: expected {want}, current {have}')
            elif run == 'cuda-compressed' and key.startswith('damaged') and have == 'FAIL':
                report['known_f4'].append(key)
        report['problems'] += [f'{run}: {m}' for m in r['mismatches']]
    report['runs'][run] = r
report['verdict'] = 'PASS' if not report['problems'] else 'FAIL'
(O / 'grade.json').write_text(json.dumps(report, indent=1) + '\n')
print(json.dumps({k: report[k] for k in ('verdict', 'problems', 'known_f4')}, indent=1))
sys.exit(0 if report['verdict'] == 'PASS' else 1)
