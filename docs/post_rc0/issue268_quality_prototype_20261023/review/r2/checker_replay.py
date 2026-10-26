"""Data-only replay of unmodified frozen report checks with a memory filesystem.
Raw non-UTF8-named members stay in RAM. Absent input/product bytes are explicitly
hash-only objects from campaign_files.sha256; sizes derive from logged geometry.
This checks report/receipt consistency, NOT absent product bytes or C++ runtime.
"""
import pathlib as P,os,json,hashlib,tarfile,sys,contextlib,unittest.mock as M,collections,copy
W=P.Path(__file__).parent; D=W/'exact/docs/post_rc0/issue268_quality_prototype_20261023'; E=D/'evidence-2f434253-4gpus'
sys.path.insert(0,str(D)); import quality_controls_v2 as v2
V=os.fsencode(W/'MEMORY_ONLY'); store={}
class HashOnly:
 def __init__(self,digest,size=None): self.digest=digest; self.size=size
for line in (E/'receipts/campaign_files.sha256').read_bytes().splitlines():
 h,n=line.split(b'  ',1)
 if n.startswith(b'campaign/negative_controls_v2/'): continue
 store[V+b'/'+n[len(b'campaign/'):]]=HashOnly(h.decode(),246784 if b'/in/' in n and n.endswith(b'.mrcs') else None)
for p in (E/'campaign').rglob('*'):
 if p.is_file(): store[V+b'/'+os.fsencode(p.relative_to(E/'campaign'))]=p.read_bytes()
with tarfile.open(E/'nonutf8_named_files.tar.gz') as t:
 for m in t.getmembers(): store[V+b'/'+os.fsencode(m.name)[len(b'campaign/'):]]=t.extractfile(m).read()
def key(p): return os.fsencode(p)
def isvirt(p): return key(p).startswith(V)
def dirs(): return {p[:i] for p in store for i,c in enumerate(p) if c==47}
def rb(p):
 v=store[key(p)]
 if isinstance(v,HashOnly): raise RuntimeError('cannot read hash-only file '+repr(key(p)))
 return v
def rt(p,encoding=None,errors=None): return rb(p).decode(encoding or 'utf8',errors or 'strict')
def wt(p,data,encoding=None,errors=None,newline=None): store[key(p)]=data.encode(encoding or 'utf8',errors or 'strict'); return len(data)
def walk(p,*a,**kw):
 pb=key(p); asbytes=isinstance(os.fspath(p),bytes)
 for d in sorted(x for x in dirs() if x==pb or x.startswith(pb+b'/')):
  dd=[x[len(d)+1:] for x in dirs() if x.startswith(d+b'/') and b'/' not in x[len(d)+1:]]
  fs=[x[len(d)+1:] for x in store if x.startswith(d+b'/') and b'/' not in x[len(d)+1:]]
  cv=(lambda x:x) if asbytes else os.fsdecode
  yield cv(d),list(map(cv,dd)),list(map(cv,fs))
def ls(p):
 pb=key(p); cv=(lambda x:x) if isinstance(os.fspath(p),bytes) else os.fsdecode
 return [cv(x) for x in sorted(set(n[len(pb)+1:].split(b'/')[0] for n in store if n.startswith(pb+b'/')))]
def size(p):
 v=store[key(p)]
 if isinstance(v,HashOnly):
  if v.size is None: raise RuntimeError('unknown size')
  return v.size
 return len(v)
def clone(src,dst,**kw):
 a,b=key(src),key(dst)
 for n,v in list(store.items()):
  if n.startswith(a+b'/'): store[b+n[len(a):]]=copy.deepcopy(v)
 return dst
def rm(p,*a,**k):
 for n in list(store):
  if n.startswith(key(p)+b'/'): del store[n]
def digest(p):
 v=store[key(p)]; return v.digest if isinstance(v,HashOnly) else hashlib.sha256(v).hexdigest()
orig={name:getattr(P.Path,name) for name in ('read_bytes','read_text','write_text','exists','is_file')}
with contextlib.ExitStack() as stack:
 for name,fn in [('read_bytes',rb),('read_text',rt),('write_text',wt),('exists',lambda p:key(p) in store or key(p) in dirs()),('is_file',lambda p:key(p) in store)]:
  saved=orig[name]
  stack.enter_context(M.patch.object(P.Path,name,lambda p,*a,_fn=fn,_saved=saved,**kw:_fn(p,*a,**kw) if isvirt(p) else _saved(p,*a,**kw)))
 for target,fn in [('os.walk',walk),('os.listdir',ls),('os.path.getsize',size),('os.path.isdir',lambda p:key(p) in dirs()),('os.path.isfile',lambda p:key(p) in store),('shutil.copytree',clone),('shutil.rmtree',rm)]: stack.enter_context(M.patch(target,fn))
 stack.enter_context(M.patch.object(v2.v1,'sha256',digest))
 root=P.Path(os.fsdecode(V)); manifest=json.loads(rb(root/'manifest.json')); binary=manifest['binaries']['v2']['sha256']; rev=manifest['revision']
 results=[]
 for q,fn,kw in [('Q4',v2.report_run,{}),('Q6',v2.collision_checks,{}),('Q8',v2.encoding_checks,{}),('Q9',v2.resume_checks,{}),('Q12',v2.report_run,{'expect_pub':{b'in/integer.mrcs':'failed'}}),('Q15',v2.report_run,{})]:
  errs=fn(root/q,binary,rev,**kw); assert not errs,(q,errs); results.append((q,'PASS'))
 nc=v2.negative_controls(root,binary,rev); assert len(nc)==13 and all(x['verdict']=='PASS' for x in nc),nc
 # Rebind modified sidecar hashes so field probes are not trivially caught by the summary digest.
 def probe(name,fn):
  run=clone(root/'Q4',root/'probes'/name); path=run/'out/in/affine.quality.json'; d=json.loads(rb(path)); fn(d); wt(path,json.dumps(d))
  sp=run/'out/quality_summary.json'; s=json.loads(rb(sp))
  for e in s['movies']:
   if e['movie']=='in/affine.mrcs': e['sidecar']['sha256']=digest(path)
  wt(sp,json.dumps(s)); return v2.report_run(run,binary,rev)
 probes={
 'global_state_only':lambda d:d['global_alignment'].update(state='iteration_limit'),
 'patch_solver_returned':lambda d:d['local_alignment']['patches'][0]['attempts'][0].update(solver_returned=False),
 'patch_max_iter':lambda d:d['local_alignment']['patches'][0]['attempts'][0].update(max_iter=987),
 'largest_delta':lambda d:d['local_model'].update(largest_delta_px=999),
 'summary_options':lambda d:d['identity']['options'].update(bfactor='999'),
 }
 probe_results={n:probe(n,fn) for n,fn in probes.items()}
print('Frozen checks:',results)
for r in nc: print(r['verdict'],r['row'])
print('Rebound field probes (empty errors = accepted):',json.dumps(probe_results))
(W/'checker_replay_results.json').write_text(json.dumps(dict(checks=results,negative_controls=nc,rebound_probes=probe_results,scope='Hash-only input/MRC bindings use receipts; raw named members memory only; no C++ execution'),indent=2))
