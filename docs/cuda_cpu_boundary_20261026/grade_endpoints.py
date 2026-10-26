#!/usr/bin/env python3
import os,pathlib,subprocess,json,hashlib
R=pathlib.Path('/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026')
T=pathlib.Path('/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools/compare_motioncorr.py')
out=R/'endpoint-grades';out.mkdir(exist_ok=False);rows=[]
for case in ['00021','00046']:
 for layout in ['G','L']:
  label=f'{case}-{layout}';a=R/'baseline'/(label+'-cpu')/'out/Movies';b=R/'baseline'/(label+'-cuda')/'out/Movies';stem=f'20170629_{case}_frameImage'
  argv=['/home/alex/.mc-venv/bin/python3',str(T),'--gate','relaxed','--ref-mrc',str(a/(stem+'.mrc')),'--test-mrc',str(b/(stem+'.mrc')),'--ref-star',str(a/(stem+'.star')),'--test-star',str(b/(stem+'.star')),'--test-log',str(b.parent.parent/'time.txt'),'--require-complete-coverage','--json-out',str(out/(label+'.json'))]
  env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='8')
  with (out/(label+'.txt')).open('w') as log:rc=subprocess.call(argv,stdout=log,stderr=subprocess.STDOUT,env=env)
  rows.append({'label':label,'argv':argv,'rc':rc,'comparator_sha256':hashlib.sha256(T.read_bytes()).hexdigest()})
(out/'RUN.json').write_text(json.dumps(rows,indent=2)+'\n');print(rows)
