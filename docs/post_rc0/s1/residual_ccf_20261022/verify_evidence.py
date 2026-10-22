#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Strict expanded product comparisons and source/artifact bindings; no native run."""
import datetime,hashlib,json,pathlib,re,sys
r=pathlib.Path(sys.argv[1]);pairs=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for case in ['integer','fractional','affine','noisy']:
 for backend in ['cpu','cuda']:
  a=r/'runs'/f'{backend}-{case}-off';b=r/'runs'/f'{backend}-{case}-on';checks={}
  for pattern in ['*.star','*.mrc','*.mrcs']:
   aa={str(p.relative_to(a/'out')):p for p in (a/'out').rglob(pattern)};bb={str(p.relative_to(b/'out')):p for p in (b/'out').rglob(pattern)}
   checks[pattern+'-inventory']=aa.keys()==bb.keys()
   for name in aa.keys()&bb.keys():
    if pattern=='*.star':
     av=aa[name].read_text().replace(str(a/'out'),'{OUTPUT}');bv=bb[name].read_text().replace(str(b/'out'),'{OUTPUT}')
    else:
     def norm(p):
      data=p.read_bytes();return data[:224]+re.sub(rb'Relion    [0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}',b'Relion    DD-Mon-YY  HH:MM:SS',data[224:1024])+data[1024:]
     av,bv=norm(aa[name]),norm(bb[name])
    checks[name]=av==bv
  for name in ['global.txt','model.txt']:checks[name]=(a/'state'/name).read_bytes()==(b/'state'/name).read_bytes()
  pairs.append(dict(case=case,backend=backend,status='PASS' if all(checks.values()) else 'FAIL',checks=checks))
assert all(x['status']=='PASS' for x in pairs)
source=json.loads((r/'source-binding.json').read_text());overlay=json.loads((r/'overlay-binding.json').read_text())
for name,sh in overlay['overlay_files'].items():assert sha(r/'src'/name)==sh
for name,key in [('mc-residual-source-805.tar.gz','source_archive_sha256'),('mc-residual-overlay.tar.gz','overlay_archive_sha256')]:assert sha(r/name)==source[key]
summary=json.loads((r/'analysis-summary.json').read_text());assert summary['same_map_exact_candidate_records']==summary['captured_frame_records']==300
assert summary['source_faithful_update_checks']==60
assert all(c['accuracy_status']=='FAIL' and c['field_distance_status']=='FAIL' for c in summary['checker_results'])
assert all(x['same_inventory'] and x['identical_all'] for x in summary['retry_comparisons'])
assert (r/'run.exit').read_text().strip()=='0' and (r/'analysis-final.exit').read_text().strip()=='0'
ledger=json.loads((r/'run-logs/commands.json').read_text());native=[x for x in ledger if x['label'] in {f'{b}-{c}-{m}' for b in ['cpu','cuda'] for c in ['integer','fractional','affine','noisy'] for m in ['off','on']}]
assert len(native)==16 and all(x['exit']==0 for x in native)
receipt=dict(status='PASS',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expanded_neutrality=pairs,application_processes=16,native_exit_zero=16,unchanged_truth_checker_failures=16,same_map_candidates_exact=300,source_faithful_updates_exact=60,normalization='all MRC bytes except exact Relion timestamp; all STAR bytes except arm output prefix; pre-write state exact',source_archive_sha256=source['source_archive_sha256'],overlay_patch_sha256=overlay['patch_sha256'],source_files={p:sha(r/'src'/p) for p in ['test-data/generate_motion_diagnostics.py','test-data/generate_known_motion_fixture.py','tools/check_motion_diagnostics.py','tools/motion_field.py']},tools={p.name:sha(p) for p in r.glob('*.py')})
(r/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n');print('strict extended neutrality, source and evidence verification PASS')
