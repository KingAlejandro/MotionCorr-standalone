#!/usr/bin/env python3
"""Same-backend artifact gate: strict MRC structure, all pixels/full headers and STAR.
Only actual writer timestamps in label zero and output directory roots are normalized.
No science, performance, log or PDF verdict follows from this gate.
"""
import argparse,datetime,hashlib,json,re,struct
from pathlib import Path
STAMP=re.compile(rb'\d{2}-[A-Za-z]{3}-\d{2}  \d{2}:\d{2}:\d{2}')
def mrc(p):
 b=p.read_bytes()
 if len(b)<1024:raise ValueError(f'{p}: short header')
 nx,ny,nz,mode=struct.unpack_from('<4i',b)
 ext=struct.unpack_from('<i',b,92)[0]
 if min(nx,ny,nz)<=0 or mode!=2 or ext<0:raise ValueError(f'{p}: invalid MRC dimensions/mode/extended size')
 pixels=nx*ny*nz
 if len(b)!=1024+ext+pixels*4:raise ValueError(f'{p}: declared versus actual payload length')
 labels=struct.unpack_from('<i',b,220)[0]
 if not 0<=labels<=10:raise ValueError(f'{p}: invalid label count')
 h=bytearray(b[:1024+ext])
 if labels:
  label=b[224:304]
  if not label.startswith(b'Relion '):raise ValueError(f'{p}: unexpected timestamp label producer')
  hits=list(STAMP.finditer(label))
  if len(hits)!=1:raise ValueError(f'{p}: missing/ambiguous writer timestamp')
  m=hits[0];datetime.datetime.strptime(m.group().decode(),'%d-%b-%y  %H:%M:%S')
  h[224+m.start():224+m.end()]=b'0'*len(m.group())
 return bytes(h),b[1024+ext:],pixels

def compare(a,b,nimages,nstars):
 aa={p.relative_to(a) for p in a.rglob('*') if p.suffix in ('.mrc','.star')}
 bb={p.relative_to(b) for p in b.rglob('*') if p.suffix in ('.mrc','.star')}
 if aa!=bb:raise ValueError('missing/extra image or STAR pairs')
 images=stars=pixels=0
 for rel in sorted(aa):
  p,q=a/rel,b/rel
  if rel.suffix=='.mrc':
   ha,pa,na=mrc(p);hb,pb,nb=mrc(q)
   if ha!=hb or pa!=pb or na!=nb:raise ValueError(f'{rel}: full header/extended header/pixel mismatch')
   images+=1;pixels+=na
  else:
   # No timing/date filtering of STAR metadata is permitted.
   ta=p.read_text().replace(str(a),'<OUT>');tb=q.read_text().replace(str(b),'<OUT>')
   if ta!=tb:raise ValueError(f'{rel}: STAR mismatch')
   stars+=1
 if images!=nimages or stars!=nstars:raise ValueError(f'inventory {images}/{stars}, expected {nimages}/{nstars}')
 return dict(images=images,stars=stars,pixels=pixels,full_normalized_headers='exact',image_pixels='exact',STAR='exact')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('reference',type=Path);ap.add_argument('candidate',type=Path);ap.add_argument('--images',required=True,type=int);ap.add_argument('--stars',required=True,type=int);ap.add_argument('--report',required=True,type=Path);a=ap.parse_args()
 report=compare(a.reference.resolve(),a.candidate.resolve(),a.images,a.stars)
 a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
