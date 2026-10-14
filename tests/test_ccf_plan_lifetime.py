#!/usr/bin/env python3
"""Exercise the actual caller, including a compiled no-reuse negative control."""
import argparse, os, subprocess, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--negative',action='store_true');a=p.parse_args()
repo=Path(__file__).resolve().parents[1]
movie=repo/'test-data/fixtures/synthetic_128x128_8frames.mrcs'
with tempfile.TemporaryDirectory(prefix='ccf-lifetime-') as tmp:
 for j in (1,4):
  for patch in (1,5):
   cmd=[a.binary,'--i',str(movie),'--o',f'{tmp}/j{j}-p{patch}','--use_own','--j',str(j),'--angpix','1','--voltage','300','--patch_x',str(patch),'--patch_y',str(patch),'--bfactor','150','--skip_logfile_pdf']
   r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=dict(os.environ,OMP_DYNAMIC='false'))
   print(r.stdout)
   output=Path(f"{tmp}/j{j}-p{patch}")
   assert list(output.rglob("*.mrc")) and len(list(output.rglob("*.star"))) >= 2, "runner did not complete its products"
   if a.negative:
    assert r.returncode==86 and 'CCF lifetime FAIL: reused=0' in r.stdout
   else:
    assert r.returncode==0 and 'CCF lifetime PASS:' in r.stdout
