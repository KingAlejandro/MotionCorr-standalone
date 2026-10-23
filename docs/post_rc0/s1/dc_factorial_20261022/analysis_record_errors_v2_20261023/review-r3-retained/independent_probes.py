import pathlib,subprocess,importlib.util,os,json,hashlib,math,datetime
P=pathlib.Path(__file__).resolve().parent; D=P/'exact/docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023'
spec=importlib.util.spec_from_file_location('gen',D/'run_controls.py');gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
ENV=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
def strict(path):
 def f(s):
  n=float(s)
  if not math.isfinite(n):raise ValueError(s)
  return n
 def obj(kvs):
  d={}
  for k,v in kvs:
   if k in d:raise ValueError(k)
   d[k]=v
  return d
 return json.loads(path.read_text(),parse_float=f,parse_constant=lambda s:(_ for _ in ()).throw(ValueError(s)),object_pairs_hook=obj)
def inspect(r):
 E=r['derived_errors']; assert len(E)==r['derived_error_count']; assert [e['id'] for e in E]==list(range(len(E)))
 owned=[]; ids={a['filename_id'] for a in r['record_audit']}
 for e in E:
  assert e['operation'] in ['cell_median','paired_subtraction','paired_median'] and e['input_ids'] and set(e['input_ids'])<=ids and isinstance(e['reason'],str)
 for row in r['rows']:
  cov=row['coverage']; assert sum(cov[k] for k in ['evaluated','missing','unrun','error'])==10
  assert cov['present']==cov['evaluated']+cov['unrun']+cov['error'] and row['n']==cov['evaluated']
  refs=row['derived_error_ids']; owned+=refs; assert row['derived_error_count']==len(refs)
  for i in refs:assert all(E[i][k]==row[k] for k in ['condition','backend','arm']) and E[i]['operation']=='cell_median'
 for q in r['pairs']:
  cov=q['coverage']; assert sum(cov[k] for k in ['matched','error','missing','unrun'])==10
  assert q['pairs']==cov['matched']==q['finite_delta_count']+q['unrepresentable_delta_count']
  assert q['wins']+q['losses']+q['ties']==q['finite_delta_count']
  refs=q['derived_error_ids'];owned+=refs;assert q['derived_error_count']==len(refs)
  for i in refs:assert all(E[i][k]==q[k] for k in ['condition','backend','arm','metric']) and E[i]['operation']!='cell_median'
  for i in q['cell_derived_error_ids']:assert E[i]['operation']=='cell_median' and E[i]['condition']==q['condition'] and E[i]['backend']==q['backend'] and E[i]['arm'] in ['none',q['arm']]
  blocked=bool(r['global_error_count'] or cov['error'] or refs or q['cell_derived_error_ids'])
  assert (q['category']=='EVALUATION_ERROR')==blocked
  if blocked:assert q['sign_p'] is None and q['failure_mcnemar_p'] is None
  if q['unrepresentable_delta_count']:assert q['median_delta'] is None
 assert sorted(owned)==list(range(len(E))), 'every derived event has exactly one row or pair owner'
 for reg in r['regressions']:
  if reg['delta'] is None:
   e=E[reg['derived_error_id']]; assert e['operation']=='paired_subtraction' and all(e[k]==reg[k] for k in ['condition','backend','arm','metric','seed'])
 return True
receipts=[]
for name in ['negative-rms-overflow','negative-transfer-overflow','none-cell-propagation','mixed-record-and-derived']:
 folder=P/'independent-01'/name; ev=folder/'eval/B';ev.mkdir(parents=True,exist_ok=False)
 data=[gen.record(s,a) for s in range(10) for a in ['none','global','local','both']]
 for m in data:
  if name=='negative-rms-overflow' and m['group']=='pedestal32-s00' and m['arm'] in ['none','global']:m['truth']['field']['px']['rms']=1e308 if m['arm']=='none' else -1e308
  if name=='negative-transfer-overflow' and m['group']=='pedestal32-s00' and m['arm'] in ['none','global']:m['image']['interior']['transfer_inband']=1e308 if m['arm']=='none' else -1e308
  if name=='none-cell-propagation' and m['arm']=='none':m['truth']['field']['px']['rms']=1e308
  if name=='mixed-record-and-derived':
   if m['arm']=='global':m['truth']['field']['px']['p95']=1e308
   if m['group']=='pedestal32-s00':
    if m['arm'] in ['none','global']:m['truth']['field']['px']['rms']=-1e308 if m['arm']=='none' else 1e308
    if m['arm']=='local':m['status']='INPUT_ERROR';m['reason']='independent mixed-error control'
  (ev/(m['id']+'.json')).write_text(json.dumps(m,allow_nan=False))
 argv=['/Users/alex.konstantinov/.local/bin/python3','-B',str(D/'summarize_v2_2.py'),str(ev.parent),str(folder/'out')]
 r=subprocess.run(argv,env=ENV,capture_output=True,text=True,timeout=20)
 (folder/'stdout.log').write_text(r.stdout);(folder/'stderr.log').write_text(r.stderr)
 item=dict(name=name,argv=argv,exit=r.returncode,inputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(ev.glob('*.json'))},passed=False)
 try:
  assert r.returncode==2 and (folder/'out/coverage.md').is_file()
  result=strict(folder/'out/tierB-v2.json');inspect(result)
  q=next(q for q in result['pairs'] if (q['condition'],q['backend'],q['arm'],q['metric'])==('pedestal32','cpu','global','transfer' if 'transfer' in name else 'rms'))
  if name.startswith('negative-'):
   assert q['finite_delta_count']==9 and q['unrepresentable_delta_count']==1
   reg=[x for x in result['regressions'] if x['condition']=='pedestal32' and x['backend']=='cpu' and x['arm']=='global' and x['seed']==0 and x['metric']==q['metric']]
   assert len(reg)==(1 if 'transfer' in name else 0)
   if reg:assert reg[0]['delta'] is None
   assert result['global_error_count']==0 and all(not a['reasons'] for a in result['record_audit'])
  if name=='none-cell-propagation':
   assert len(result['derived_errors'])==4
   affected=[q for q in result['pairs'] if q['condition']=='pedestal32' and q['backend']=='cpu'];assert len(affected)==12 and all(q['cell_derived_error_ids']==[0] and q['category']=='EVALUATION_ERROR' for q in affected)
  if name=='mixed-record-and-derived':
   assert len(result['derived_errors'])==2 and sum(bool(a['reasons']) for a in result['record_audit'])==1
   assert q['pairs']==10 and q['coverage']['error']==0
   assert sum(x['coverage']['error'] for x in result['rows'])==1
  item.update(passed=True,derived_events=result['derived_errors'])
 except Exception as exc:item['assertion_error']=repr(exc)
 receipts.append(item);(P/'INDEPENDENT_PROBES.json').write_text(json.dumps(receipts,indent=2,allow_nan=False));print(name,item['passed'],item.get('assertion_error'),flush=True)
 if not item['passed']:raise SystemExit(1)
# Inspect independently all fixed-source outputs from the already-completed controls.
outputs=[]
for path in sorted(P.glob('*-01/**/tierB-v2.json')):
 result=strict(path);inspect(result);outputs.append(str(path.relative_to(P)))
(P/'OUTPUT_ACCOUNTING.json').write_text(json.dumps({'passed':True,'count':len(outputs),'outputs':outputs},indent=2));print('strict/accounting',len(outputs),flush=True)
