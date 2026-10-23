import pathlib,os,sys,json,subprocess,hashlib,importlib.util,math
P=pathlib.Path(__file__).resolve().parent; D=P/'exact/docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023'; py='/Users/alex.konstantinov/.local/bin/python3'
spec=importlib.util.spec_from_file_location('gen',D/'run_controls.py'); gen=importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1'); rec=[]
for name in ['finite-large-median','finite-large-difference']:
 ev=P/'boundary-01'/name/'eval/B'; ev.mkdir(parents=True,exist_ok=False)
 data=[gen.record(s,a) for s in range(10) for a in ['none','global']]
 if name=='finite-large-median':
  for m in data:
   if m['arm']=='global': m['truth']['field']['px']['rms']=1e308
 else:
  for m in data:
   if m['group']=='pedestal32-s00': m['truth']['field']['px']['rms']=(-1e308 if m['arm']=='none' else 1e308)
 for m in data: (ev/(m['id']+'.json')).write_text(json.dumps(m,allow_nan=False))
 argv=[py,'-B',str(D/'summarize_v2_1.py'),str(ev.parent),str(ev.parent.parent/'out')]
 r=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=15)
 (ev.parent.parent/'stdout.log').write_text(r.stdout); (ev.parent.parent/'stderr.log').write_text(r.stderr)
 item={'name':name,'justification':'Numeric-range fix checks only finite inputs before unchanged median/delta arithmetic. Probe whether accepted finite schema values still lose strict-JSON diagnostics. No source/policy modification.','argv':argv,'exit':r.returncode,'input_values_finite':all(math.isfinite(m['truth']['field']['px']['rms']) for m in data),'summary_exists':(ev.parent.parent/'out/tierB-v2.json').exists(),'coverage_exists':(ev.parent.parent/'out/coverage.md').exists(),'inputs':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(ev.glob('*.json'))},'stderr':r.stderr}
 rec.append(item); print(name,r.returncode,item['summary_exists'],r.stderr,flush=True)
(P/'BOUNDARY_PROBES.json').write_text(json.dumps(rec,indent=2,allow_nan=False))
