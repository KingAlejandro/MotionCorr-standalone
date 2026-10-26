#!/usr/bin/env python3
"""GPU3 health check for C1 pre/post-run gates. usage: c1_health_check.py LABEL   (logs/health.jsonl, logs/LABEL.xml)

The checks are those of the project's existing fail-closed guard (docs/rc0/issue226/d2/native_retry_20261022/support/health.py, snapshot()):
lane GPU identity (UUID, A100 80GB PCIe), correctable/uncorrectable ECC counts all zero (volatile and aggregate, fields must exist),
remapped-row counters zero with no pending or failure, no pending retired page, and no compute process on the lane GPU. Exit 0 pass;
3 compute process present; 4 nvidia-smi unusable; 6 identity/ECC/remap/retired anomaly. A missing field is a failure, not a default.
It does not read kernel logs: Xid inspection stays UNRUN (no privileged log access) and an apps-only snapshot is never reported as GPU-health PASS.
"""
import json, os, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

label = sys.argv[1]; uuid = os.environ['C1_GPU_UUID']; scr = Path(os.environ['C1_SCR'])
(scr / 'logs').mkdir(exist_ok=True)
r = subprocess.run(['nvidia-smi', '-i', uuid, '-q', '-x'], capture_output=True, text=True)
if r.returncode:
    print('nvidia-smi failed:', r.stderr[-300:], file=sys.stderr); sys.exit(4)
try:
    g = ET.fromstring(r.stdout).find('gpu')
    def text(p):
        e = g.find(p)
        if e is None or e.text is None: raise ValueError('missing GPU health field ' + p)
        return e.text.strip()
    rec = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'label': label, 'uuid': text('uuid'), 'name': text('product_name'),
           'memory_used': text('fb_memory_usage/used'), 'util': text('utilization/gpu_util'),
           'volatile_ecc': {e.tag: e.text.strip() for e in g.findall('ecc_errors/volatile/*') if 'correctable' in e.tag},
           'aggregate_ecc': {e.tag: e.text.strip() for e in g.findall('ecc_errors/aggregate/*') if 'correctable' in e.tag},
           'remapped': {e.tag: e.text.strip() for e in g.findall('remapped_rows/*') if len(e) == 0},
           'retired_pending': text('retired_pages/pending_blacklist'),
           'apps': [int(e.text) for e in g.findall('processes/process_info/pid')]}
except (ET.ParseError, ValueError, AttributeError) as exc:
    print('health snapshot unusable:', exc, file=sys.stderr); sys.exit(6)
with (scr / 'logs/health.jsonl').open('a') as f: f.write(json.dumps(rec) + '\n')
(scr / 'logs' / f'{label}.xml').write_text(r.stdout)
problems = []
if rec['uuid'] != uuid or rec['name'] != 'NVIDIA A100 80GB PCIe': problems.append('GPU identity mismatch')
if not rec['volatile_ecc'] or not rec['aggregate_ecc']: problems.append('missing ECC counts')
if any(int(v) for vals in (rec['volatile_ecc'], rec['aggregate_ecc']) for v in vals.values() if v.isdigit()) or \
   any(not v.isdigit() for vals in (rec['volatile_ecc'], rec['aggregate_ecc']) for v in vals.values()): problems.append('GPU ECC error or unreadable count')
rows = rec['remapped']
if rows.get('remapped_row_unc') != '0' or rows.get('remapped_row_corr') != '0' or rows.get('remapped_row_pending') != 'No' or rows.get('remapped_row_failure') != 'No':
    problems.append('GPU row remap error/pending or unrecognized fields: ' + str(rows))
if rec['retired_pending'] not in ('No', 'N/A'): problems.append('retired page pending')
if problems:
    print('GPU health FAIL:', '; '.join(problems), file=sys.stderr); sys.exit(6)
if rec['apps']:
    print('compute process(es) on the lane GPU:', rec['apps'], file=sys.stderr); sys.exit(3)
print('GPU health PASS (identity, ECC, row remap, retired pages, no compute process); kernel Xid log: UNRUN')
