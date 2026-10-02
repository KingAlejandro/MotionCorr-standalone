"""Verify the sole intentional output-log delta: one denominator-plane allocation."""
import re
from pathlib import Path

def validate_vram_delta(base,candidate,nx,ny,require_dose=True):
 b={p.relative_to(base):p for p in Path(base).rglob('*.log')};c={p.relative_to(candidate):p for p in Path(candidate).rglob('*.log')}
 if b.keys()!=c.keys():raise RuntimeError('log inventory differs')
 rows=[];expected=ny*(nx//2+1)*4/1024**2
 for rel in b:
  def fields(p):
   stage='';out=[]
   for line in p.read_text().splitlines():
    if line.lstrip().startswith('[CUDA '):stage=line.strip()
    if line.lstrip().startswith('Peak VRAM:'):
     m=re.fullmatch(r'\s*Peak VRAM:\s*([0-9.]+) MiB\s*',line)
     if not m:raise RuntimeError('malformed allocation telemetry')
     out.append((stage,float(m[1])))
   return out
  x,y=fields(b[rel]),fields(c[rel])
  if len(x)!=len(y):raise RuntimeError('allocation telemetry inventory differs')
  for (stage,old),(newstage,new) in zip(x,y):
   if stage!=newstage:raise RuntimeError('allocation telemetry stage differs')
   delta=expected if stage=='[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]' else 0
   if abs((new-old)-delta)>.011:raise RuntimeError('unexpected allocation delta '+str((rel,stage,old,new,delta)))
   rows.append({'log':str(rel),'stage':stage,'baseline_MiB':old,'candidate_MiB':new,'expected_added_MiB':delta})
 if require_dose and not any(x['expected_added_MiB']>0 for x in rows):raise RuntimeError('no dose plane allocation telemetry')
 return rows
