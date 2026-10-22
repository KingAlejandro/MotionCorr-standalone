"""Remove each required CUDA control with the count held fixed; no native execution."""
import json,subprocess,sys
from pathlib import Path
W=Path('/mnt/clathrin/alex-226-d2-d3-integration-20261022T154900Z')
data=json.loads((W/'logs/collection-for-missing.log').read_text())
rows=[]
for name in ('CudaLocalAdmission','CudaEarlyStreamingOom','CudaStreamingPlanClassificationCleanup'):
    mutant=dict(data)
    mutant['tests']=[t for t in data['tests'] if t['name']!=name]
    assert len(mutant['tests'])==len(data['tests'])-1
    mutant['tests'].append(dict(name='IntegrationAdditiveFiller',command=['/bin/true']))
    path=W/'logs'/('missing-'+name+'.json')
    path.write_text(json.dumps(mutant,indent=2)+'\n')
    cmd=[sys.executable,str(W/'src/tools/validate_test_collection.py'),'--json',str(path),'--cuda']
    r=subprocess.run(cmd,capture_output=True,text=True)
    row=dict(dropped=name,argv=cmd,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,count=len(mutant['tests']))
    rows.append(row)
    assert r.returncode==1 and 'Missing required test(s): '+name in r.stdout,row
(W/'logs/missing-controls.json').write_text(json.dumps(rows,indent=2)+'\n')
print('PASS: all three required CUDA removals rejected at unchanged collection count')
