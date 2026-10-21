#!/usr/bin/env python3
"""Toggle-off identity, source/binary provenance and global selectivity controls."""
import hashlib,json,pathlib,struct,sys
import numpy as np
import analyze as a
s=pathlib.Path(sys.argv[1]);out=s/'analysis';out.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def identity(x,y):
 p,q=a.primary(x),a.primary(y)
 b,c=p.read_bytes(),q.read_bytes();hb,=struct.unpack_from('<i',b,92);hc,=struct.unpack_from('<i',c,92)
 z={'a':str(x),'b':str(y),'core_header_equal':b[:224]==c[:224],'payload_equal':b[1024+hb:]==c[1024+hc:],'labels_equal_not_in_verdict':b[224:1024]==c[224:1024],'extended_header_equal_not_in_verdict':b[1024:1024+hb]==c[1024:1024+hc],'star_equal':a.star(x).read_bytes()==a.star(y).read_bytes(),'payload_sha256':[hashlib.sha256(b[1024+hb:]).hexdigest(),hashlib.sha256(c[1024+hc:]).hexdigest()],'star_sha256':[sha(a.star(x)),sha(a.star(y))]}
 z['pass']=z['core_header_equal'] and z['payload_equal'] and z['star_equal'];return z
results={'toggle_off':[],'capture_enabled_off':[],'neutrality_controls':[],'cross_host':[],'global_selectivity':[],'capture_neutrality':[],'legacy_cuda_identity':[]}
for mv in ['e10216-00','e12963-00','e10474f3-00']:
 for g in [5,3]:
  label=f'{mv}-p{g}';root=s/'runs'
  for p,q in [('parentCPU','offCPU'),('parentGPU','offGPU'),('parentCPU','C_none'),('parentGPU','G_none')]:
   x,y=root/(label+'-'+p),root/(label+'-'+q)
   if (x/'run.json').exists() and (y/'run.json').exists():results['toggle_off' if q.startswith('off') else 'capture_enabled_off'].append(identity(x,y))
  r,rp=root/(label+'-R'),root/(label+'-Rprime')
  if (rp/'run.json').exists():
   i,j=a.info(r),a.info(rp);results['neutrality_controls'].append({'config':label,'global_px':a.norms(j['global']-i['global']),'local_field_native_px':a.norms(a.field(j['coeff']-i['coeff'],i['geometry'][2])),'accepted_star_sets_equal':i['set']==j['set'],'product':a.metric(r,rp)})
  c=s/'cpu64/runs'/(label+'-C_none');f=root/(label+'-C_none')
  if (c/'run.json').exists() and a.primary(c).exists() and (f/'run.json').exists():results['cross_host'].append(identity(f,c))
for backend,root in [('G',s/'runs'),('C',s/'cpu64/runs')]:
 for mv in [f'{fam}-{i:02d}' for fam in ['e10216','e12963','e10474f3'] for i in range(10)]:
  for g in [5,3]:
   label=f'{mv}-p{g}'
   for p,q in [('none','local'),('global','both')]:
    x,y=root/(label+'-'+backend+'_'+p),root/(label+'-'+backend+'_'+q)
    if not all((d/'run.json').exists() and (d/'global.txt').exists() for d in [x,y]):continue
    results['global_selectivity'].append({'config':label,'backend':backend,'pair':[p,q],'bit_equal':(x/'global.txt').read_bytes()==(y/'global.txt').read_bytes()})
# Observation capture reruns must preserve the product exactly.
for mv,g in [('e10216-00',3),('e12963-00',5)]:
 for arm in ['R','Rprime']:
  x,y=s/'runs'/f'{mv}-p{g}-{arm}',s/'runs'/f'{mv}-p{g}-capture-{arm}'
  if (y/'run.json').exists():results['capture_neutrality'].append(identity(x,y))
# Re-running all GPU arms avoids substituting old results. This control records
# whether the unconditioned CUDA path still reproduces the retained #261 A1.
old=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit/runs')
for d in sorted((s/'runs').glob('*-G_none')):
 if not (d/'run.json').exists():continue
 o=old/(d.name[:-6]+'A1')
 if (o/'run.json').exists():results['legacy_cuda_identity'].append(identity(o,d))
json.dump(results,open(out/'controls.json','w'),indent=1)
print({k:(len(v),sum(r.get('pass',r.get('bit_equal',False)) for r in v)) for k,v in results.items()})
assert all(x['pass'] for x in results['toggle_off']+results['capture_enabled_off'])
assert all(x['bit_equal'] for x in results['global_selectivity'])
assert all(x['pass'] for x in results['capture_neutrality'])
