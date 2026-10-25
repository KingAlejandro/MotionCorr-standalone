#!/usr/bin/env python3
"""Snapshot-only consumer: joins process exit AND recorded state for the C1 CPU (cpu1d) and DC campaigns.
Reads only copied JSON/receipt files under SNAP; no remote access, no payload parsing. Output JSON on stdout."""
import json, sys, glob, collections, pathlib
snap = pathlib.Path(sys.argv[1]); J = lambda p: json.load(open(p))
out = {}
# --- C1 cpu1d: stage exit joined with state
stages = [s.strip() for s in open(sys.argv[2]) if s.strip()]
rc = {s: (snap/'c1/logs'/f'{s}.exit').read_text().strip() for s in stages}
dec = J(snap/'c1/census-cpu-decision.json'); v2 = J(snap/'c1/cpu1d-v2-check.json')
cmp_ = {l: J(snap/f'c1/t24-cpu1d/compare/F-cpu_vs_c1-cpu-{l}.class.json')['state'] for l in 'GL'}
rows = {k: (r['checker_status'], r['checker_exit'], r['sampling_status'], r['field_gate']) for k, r in v2['rows'].items()}
out['c1'] = dict(stages=len(stages), stage_exit0=sum(v == '0' for v in rc.values()),
    census_decision=dec['verdict'], t24_compare=cmp_, v2check_rows=rows,
    v2_exit_state_disagree=[k for k, (st, ex, sm, fg) in rows.items() if (st in ('PASS',) ) != (ex == 0) or (st == 'UNIDENTIFIABLE' and ex != 0) or sm != 'VALID'])
# --- DC: queue x RUN exit x evaluation presence
q = J(snap/'dc/queue.json'); ev = set(J(snap/'dc/evaluation-snapshots/B-pass3-20261022-2244/EVALUATIONS.json')['sha256'])
runs = {l.split()[0]: l.split()[1] for l in open(sys.argv[3])}  # "<id> <exit>"
cell = collections.Counter()
for x in q:
    i = x['id']; cell[(x['tier'], x['backend'], 'RUN' if i in runs else 'NO_RUN', 'exit' + runs.get(i, '-'),
        'evaluated' if i in ev else ('tierA_summary' if x['tier'] == 'A' else 'unevaluated'))] += 1
out['dc'] = {' | '.join(k): v for k, v in sorted(cell.items())}
print(json.dumps(out, indent=1))
