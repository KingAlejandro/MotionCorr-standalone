#!/usr/bin/env python3
"""Evaluate immutable native records; preserve the interim schema-1 diagnostics."""
import concurrent.futures,json,pathlib,sys
REPO=pathlib.Path(__file__).resolve().parents[4]
# Supports both a repository execution and copied task scripts.
if not (REPO/'tools').exists(): REPO=pathlib.Path.cwd()
sys.path[:0]=[str(REPO/'tools'),str(REPO/'test-data')]
import check_realistic_motion as check


def one(args):
 root,run=args;out=run.parent;row=json.loads(run.read_text())
 receipt=root/'fixtures'/out.parent.name/'RECEIPT.json';r=json.loads(receipt.read_text())['recipe']
 if row['exit']:raise ValueError((run,'native process failure',row['exit']))
 interim=out/'metrics.json'
 if interim.exists():
  old=json.loads(interim.read_text())
  if old['schema']=='motion-counting-metrics/1':interim.rename(out/'metrics-v1-interim.json')
 star=out/'output/movie.star';check.validate_star_rows(star,r);s=check.read_motion_star(star)
 model=json.loads((out/'runtime.json').read_text());m=check.evaluate(r,model,s)
 m['convergence']=check.convergence(out/'output/movie.log')
 m['identity']={str(p.relative_to(root)):check.gen.digest(p) for p in [run,receipt,out/'runtime.json',star,out/'output/movie.log']}
 m['checker_sha256']=check.gen.digest(pathlib.Path(check.__file__))
 (out/'metrics.json').write_text(json.dumps(m,indent=2,allow_nan=False)+'\n')
 return out.parent.name,out.name


def main():
 root=pathlib.Path(sys.argv[1]).resolve();runs=sorted((root/'results').glob('*/*/RUN.json'))
 if len(runs)!=900:raise ValueError(f'expected 900 immutable native RUN records, got {len(runs)}')
 with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
  rows=list(pool.map(one,[(root,r) for r in runs]))
 print('evaluated',len(rows),'records',flush=True)

if __name__=='__main__':main()
