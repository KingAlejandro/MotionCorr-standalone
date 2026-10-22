#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify compact receipt bytes and trajectory arithmetic without native execution."""
import ast,hashlib,json,math,pathlib,subprocess,tarfile
p=pathlib.Path(__file__).resolve().parent
idx=json.loads((p/'receipt-index.json').read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
assert sha((p/'receipts.tar.gz').read_bytes())==idx['archive_sha256']
with tarfile.open(p/'receipts.tar.gz') as t:
 assert set(t.getnames())==set(idx['files'])
 for name,info in idx['files'].items():
  b=t.extractfile(name).read();assert len(b)==info['bytes'] and sha(b)==info['sha256'],name
 for name in ['analysis-summary.json','verification.json','direct-witness.json','source-binding.json','overlay-binding.json','DESIGN.md']:
  assert (p/name).read_bytes()==t.extractfile(name).read(),name
 tools=json.load(t.extractfile('verification.json'))['tools']
 for file in p.glob('*.py'):
  ast.parse(file.read_text())
  remote={'replay.py':'replay-final.py','replay_initial.py':'replay.py'}.get(file.name,file.name)
  if remote in tools:assert sha(file.read_bytes())==tools[remote],file
 rows=json.load(t.extractfile('trajectories.json'))
 for r in rows:
  errors=[[a-b for a,b in zip(estimate,truth)] for estimate,truth in zip(r['native_accumulated_plus_global_xy'],r['truth_xy'])]
  assert errors==r['truth_error_xy']
  # This only checks printed compact arithmetic, not native/raw-array scientific validity.
  rms=math.sqrt(sum(sum(x*x for x in e) for e in errors)/len(errors))
  assert math.isclose(rms,r['truth_vector_rms'],rel_tol=1e-14,abs_tol=1e-14)
 s=json.loads((p/'analysis-summary.json').read_text())
 assert len(rows)==s['source_faithful_update_checks']==60
 assert s['same_map_exact_candidate_records']==s['captured_frame_records']==300
 assert all(x['status']=='PASS' for x in json.loads((p/'verification.json').read_text())['expanded_neutrality'])
 assert all(x['accuracy_status']=='FAIL' and x['field_distance_status']=='FAIL' for x in s['checker_results'])
 assert all(x['identical_all'] and x['same_inventory'] for x in s['retry_comparisons'])
binding=json.loads((p/'overlay-binding.json').read_text())
assert sha((p/'diagnostic.patch').read_bytes())==binding['patch_sha256']
assert sha((p/'capture.h').read_bytes())==binding['overlay_files']['src/residual_capture.h']
for name,h in binding['base_files'].items():
 assert sha(subprocess.check_output(['git','show',binding['base']+':'+name]))==h
assert not [l for l in (p/'diagnostic.patch').read_text().splitlines() if l.startswith('-') and not l.startswith('---')]
print('PASS:',len(idx['files']),'receipt members, 60 compact trajectory metrics, source/tool bindings; raw arrays remain remote')
