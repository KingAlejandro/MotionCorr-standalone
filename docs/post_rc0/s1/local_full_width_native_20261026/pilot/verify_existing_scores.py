"""No new producer: reproduce four retained affine/noisy runtime+STAR score pairs."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).parent))
import score_fields as S

HERE=Path(__file__).parent
RAW=Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
FIX=Path('/tmp/motioncorr-b2-retained-challenge-20261026/v2fixtures')
manifest=json.loads((FIX/'MANIFEST.json').read_text())
assert S.sha(FIX/'MANIFEST.json')=='9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
rows=[]
for case in ['noisy','affine']:
 for arm in ['UP_only','UP_B2']:
  d=RAW/case/arm
  m=S.field_metrics(d/'runtime.json',d/'output'/f'{case}.star',FIX/f'{case}_field.npy',manifest['cases'][case],manifest['cases'][case]['files'][f'{case}_field.npy'])
  old=json.loads((d/'metrics.json').read_text())
  err=max(abs(m[a]['angstrom'][k]-old[a]['angstrom'][k]) for a in ['runtime','STAR'] for k in S.LIMITS)
  assert err<=1e-12,(case,arm,err)
  # These retained fetches are metadata-only. They MUST fail publication admission.
  missing_publication_rejected=False
  try:S.complete_publication(d,case,json.loads((d/'RUN.json').read_text())['binary_sha256'])
  except ValueError:missing_publication_rejected=True
  assert missing_publication_rejected
  rows.append({'case':case,'arm':arm,'metrics':m,'max_abs_difference_A':err,'metadata_only_fetch_rejected_as_complete_producer':True})
(HERE/'EXISTING_SCORE_CHECK.json').write_text(json.dumps({'rows':rows,'status':'PASS for four metadata-only score reproductions; no new native qualification','tolerance_A':1e-12},indent=2,allow_nan=False)+'\n')
print('four retained score pairs reproduce, maxdiff_A',max(r['max_abs_difference_A'] for r in rows))
