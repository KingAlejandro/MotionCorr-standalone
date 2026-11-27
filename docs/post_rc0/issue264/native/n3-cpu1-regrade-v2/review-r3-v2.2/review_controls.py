import argparse, ast, contextlib, hashlib, importlib.util, io, json, os, pathlib, shutil, struct, subprocess, sys, tarfile, traceback
R=pathlib.Path(__file__).resolve().parent
HEAD='593c9e2cc53663655a1628ab7500fadddee5d261'
REPO='/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-d9b98408'
ENV=dict(os.environ,GIT_OPTIONAL_LOCKS='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
os.environ.update(ENV)
sha=lambda b:hashlib.sha256(b).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
g=load('exact',R/'regrade_v2_2.py');driver=load('driver',R/'remote_run_v2_2.py');packer=load('packer',R/'package_v2_2.py')
results=[]
def record(name,ok,**kw):
 x=dict(name=name,ok=bool(ok),**kw);results.append(x);print(json.dumps(x),flush=True)
 (R/'RESULTS.json').write_text(json.dumps(results,indent=2)+'\n')
 if sum(p.stat().st_size for p in R.rglob('*') if p.is_file() and not p.is_symlink())>384<<20:raise RuntimeError('cap')
def new(name):
 p=R/name;p.mkdir(exist_ok=False);return p
def mutant(name,replacements):
 p=new('mutant-'+name)/'regrade_v2_2.py';s=(R/'regrade_v2_2.py').read_text()
 for a,b in replacements:
  assert s.count(a)==1,a;s=s.replace(a,b)
 p.write_text(s);return load(name,p)
def cmd(argv,**kw):
 return subprocess.run(argv,check=True,capture_output=True,env=ENV,**kw)
def inventory(root):
 return {str(p.relative_to(root)):{'sha256':sha(p.read_bytes()),'stat':list(g.stable_stat(p.stat()))} for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
def live(name,mode):
 d=new(name);root=d/'input';root.mkdir();proc=d/'proc';proc.mkdir();expect={'trees':{},'binaries':{}}
 for i in range(5):
  t=root/('tree'+str(i));(t/'src').mkdir(parents=True)
  (t/'src/motioncorr_runner.cpp').write_text('runner '+str(i)+'\n');(t/'src/local_motion_guard.h').write_text('helper\n')
  git=lambda *args:cmd(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(t),*args]).stdout
  git('init','-q');git('add','.');git('-c','user.name=Review','-c','user.email=review@example.invalid','commit','-qm','fixture')
  expect['trees'][t.name]={'head':git('rev-parse','HEAD').decode().strip(),'diff_sha256':sha(b''),'status':[],'runner_sha256':sha((t/'src/motioncorr_runner.cpp').read_bytes()),'helper_sha256':sha((t/'src/local_motion_guard.h').read_bytes())}
  # Stale cache stat, without content changes, independently created per target.
  if mode!='clean':
   f=t/'src/motioncorr_runner.cpp';s=f.stat();os.utime(f,ns=(s.st_atime_ns,s.st_mtime_ns+2000000000))
 for i in range(3):
  arm='cpu'+str(i);b=('binary '+str(i)).encode();(root/('build-'+arm)).mkdir();(root/('build-'+arm)/'motioncorr').write_bytes(b)
  expect['binaries'][arm]=sha(b);(root/('build-'+arm+'.binaries.sha256')).write_text(sha(b)+'  motioncorr\n')
 (d/'EXPECT.json').write_text(json.dumps(expect))
 if mode=='modified':(root/'tree0/src/motioncorr_runner.cpp').write_text('modified\n')
 m=load('live_'+name,R/'regrade_v2_2.py');before=inventory(root);calls=[];real=m.subprocess.run;oldgit=m._git
 def observe(argv,**kw):
  calls.append({'argv':argv,'env':kw.get('env')});return real(argv,**kw)
 def hook(tree,private,*args):
  answer=oldgit(tree,private,*args)
  if mode=='refresh_private' and args==('status','--porcelain'):
   env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_INDEX_FILE':private,'GIT_OPTIONAL_LOCKS':'1'}
   real(['/usr/bin/git','-C',tree,'update-index','--refresh'],capture_output=True,check=True,env=env)
  if mode=='touch_original' and args==('status','--porcelain'):
   p=pathlib.Path(tree)/'.git/index';s=p.stat();os.utime(p,ns=(s.st_atime_ns,s.st_mtime_ns+1000000000))
  return answer
 m.subprocess.run=observe;m._git=hook
 try:
  with contextlib.redirect_stdout(io.StringIO()):rc=m.cmd_precheck_live(argparse.Namespace(scratch_root=str(root),expect=str(d/'EXPECT.json'),proc_root=str(proc),out=str(d/'live.json')))
 finally:m.subprocess.run=real
 after=inventory(root);changed=[n for n in before if before[n]!=after[n]];rep=json.loads((d/'live.json').read_bytes())
 valid=all(c['argv'][0]=='/usr/bin/git' and c['env']['GIT_OPTIONAL_LOCKS']=='0' and not pathlib.Path(c['env']['GIT_INDEX_FILE']).is_relative_to(root) for c in calls)
 (d/'IDENTITIES.json').write_text(json.dumps({'before':before,'after':after,'calls':calls},indent=1)+'\n')
 expected=1 if mode in ('touch_original','modified') else 0
 record(name,rc==expected and valid and (bool(changed)==(mode=='touch_original')),exit=rc,expected=expected,changed=changed,calls=len(calls),problems=rep['problems'],private_environment=valid)
def stream(name,kind,mutation):
 d=new(name);(d/'binary').write_bytes(b'abcd');m=g if not mutation else mutant(name,mutation)
 original=m.os.read;once=False;sizes=[]
 def read(fd,n):
  nonlocal once
  if not once:
   once=True
   if kind=='grow':
    with (d/'binary').open('ab') as f:f.write(b'efgh')
   if kind=='rewrite':(d/'binary').write_bytes(b'wxyz')
   if kind=='replace':(d/'replacement').write_bytes(b'abcd');os.replace(d/'replacement',d/'binary')
  b=original(fd,n);sizes.append({'request':n,'read':len(b)});return b
 m.os.read=read
 try:
  try:answer=m.DirReader(str(d)).hash_stream('binary',cap=4);rc=0;error=None
  except m.Invalid as e:answer=None;rc=1;error=str(e)
 finally:m.os.read=original
 expected=0 if kind=='stable' or (mutation and (kind!='grow' or len(mutation)==2)) else 1
 record(name,rc==expected,exit=rc,expected=expected,error=error,result=answer,reads=sizes,source_sha256=sha(pathlib.Path(m.__file__).read_bytes()))
def main():
 record('occupancy',True,load=os.getloadavg(),free=shutil.disk_usage(R).free,python=sys.version,python_sha256=sha(pathlib.Path(sys.executable).resolve().read_bytes()),threads={k:ENV[k] for k in ENV if k.endswith('NUM_THREADS') or k=='VECLIB_MAXIMUM_THREADS'})
 for name,mode in [('live-clean','clean'),('live-stale','stale'),('live-private-real-refresh','refresh_private'),('live-original-guard','touch_original'),('live-source-binding','modified')]:live(name,mode)
 bound=[('if n > cap:','if False:')];identity=[('if stable_stat(st) != stable_stat(end) or stable_stat(end) != stable_stat(named) or n != st.st_size:','if False:')]
 for name,kind,mut in [('stream-positive','stable',[]),('stream-growth','grow',[]),('stream-growth-bound-mutant','grow',bound),('stream-growth-combo-mutant','grow',bound+identity),('stream-rewrite','rewrite',[]),('stream-rewrite-mutant','rewrite',identity),('stream-replace','replace',[]),('stream-replace-mutant','replace',identity)]:stream(name,kind,mut)
 for kind in ['parent','other','sibling','launch','cwd','fd','self']:
  d=new('proc-'+kind);root=str(d/'input');pathlib.Path(root).mkdir();proc=d/'proc';pid=os.getpid() if kind=='self' else os.getppid() if kind in ('parent','launch') else 999999;p=proc/str(pid);p.mkdir(parents=True)
  arg='--input='+root+'/file' if kind in ('parent','other','self') else root+'-package/file'
  if kind=='launch':arg='exec /usr/bin/timeout 180s /usr/bin/taskset -c 13 /usr/bin/python3 -I -B '+root+'-package/remote_run_v2_2.py --out '+root+'-run'
  (p/'cmdline').write_bytes(('writer\0'+arg+'\0').encode())
  if kind=='cwd':(p/'cwd').symlink_to(root+'/data')
  if kind=='fd':(p/'fd').mkdir();(p/'fd/3').symlink_to(root+'/data')
  hits,u=g._scan_processes(str(proc),root);record('proc-'+kind,bool(hits)==(kind in ('parent','other','cwd','fd')) and not u,hits=hits,fake_proc=True)
  if kind=='parent':
   m=mutant('ancestor',[('skip = {os.getpid()}','skip = {os.getpid(), os.getppid()}')]);mh,_=m._scan_processes(str(proc),root);record('ancestor-mutant',bool(hits) and not mh,exact_hits=hits,mutant_hits=mh,acceptance_changing=True)
 # Build once from exact objects; only HERE is supplied to the copied packer's object reader.
 packer.HERE=pathlib.Path(REPO);receipt=packer.build(HEAD,R/'package-build');package=new('package-clean')
 with tarfile.open(R/'package-build/package.tar') as t:
  for m in t:
   assert m.isfile() and m.name==pathlib.Path(m.name).name
   (package/m.name).write_bytes(t.extractfile(m).read())
 verified=driver.verify_package(package,HEAD,receipt['package_manifest_sha256'])
 record('package-positive',True,package_bytes=receipt['package_bytes'],content_bytes=verified['content_bytes'],package_sha256=receipt['package_sha256'])
 for kind in ['driver','manifest','source','extra','missing','symlink']:
  p=R/('package-'+kind);shutil.copytree(package,p);commit=HEAD
  if kind=='driver':(p/'remote_run_v2_2.py').write_bytes(b'wrong')
  if kind=='manifest':(p/'PACKAGE.json').write_bytes(b'{}')
  if kind=='source':commit='0'*40
  if kind=='extra':(p/'extra').write_bytes(b'x')
  if kind=='missing':(p/'CONTRACT.md').unlink()
  if kind=='symlink':(p/'CONTRACT.md').unlink();(p/'CONTRACT.md').symlink_to(package/'CONTRACT.md')
  try:driver.verify_package(p,commit,receipt['package_manifest_sha256']);rejected=False;error=None
  except (ValueError,FileNotFoundError) as e:rejected=True;error=str(e)
  record('package-'+kind,rejected,error=error)
 # Explicit Linux refusal is permitted, not a simulated Linux driver run.
 p=cmd([sys.executable,'-I','-B',str(R/'remote_run_v2_2.py'),'--help']);record('driver-cli-parse',p.returncode==0)
 p=subprocess.run([sys.executable,'-I','-B',str(R/'remote_run_v2_2.py'),'--source-commit',HEAD,'--package-manifest-sha256',receipt['package_manifest_sha256'],'--out',str(R/'forbidden-local-run')],capture_output=True,text=True,env=ENV)
 record('driver-local-refusal',p.returncode==1 and not (R/'forbidden-local-run').exists(),exit=p.returncode,stderr=p.stderr)
 # Preserved stage comparisons; no Linux calls.
 pre={'verdict':'PASS','scratch_root':'S','expect_sha256':'e','binaries':{'x':'b'},'trees':{'t':{'index_after':{'sha256':'i'},'git_calls':['old']}}}
 post=json.loads(json.dumps(pre));post['trees']['t']['git_calls']=['new'];driver.compare_live(pre,post);record('compare-private-ignored',True)
 post['trees']['t']['index_after']['sha256']='changed'
 try:driver.compare_live(pre,post);rejected=False
 except ValueError:rejected=True
 record('compare-original-rejected',rejected)
 # One retained tar CLI read in place. Exact support path is obtained from frozen suite source.
 tar=pathlib.Path(REPO)/'docs/post_rc0/issue264/native/n3-cpu1-result/raw/evidence.tar';pin='3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760';record('retained-tar-input',sha(tar.read_bytes())==pin,path=str(tar),sha256=pin)
 out=R/'tar-grade';argv=[sys.executable,'-I','-B',str(R/'regrade_v2_2.py'),'grade','--evidence-tar',str(tar),'--evidence-sha256',pin,'--predictions',str(R/'predictions_iter2.json'),'--manifest',str(R/'EVIDENCE_MANIFEST.json'),'--out',str(out)]
 q=subprocess.run(argv,capture_output=True,text=True,env=ENV);(R/'TAR-COMMAND.json').write_text(json.dumps({'argv':argv,'exit':q.returncode,'stdout':q.stdout,'stderr':q.stderr},indent=1)+'\n');rep=json.loads((out/'REGRADE_V2_2.json').read_bytes())
 record('retained-tar-grade',q.returncode==2 and rep['star_layer_verdict']=='PASS' and rep['full_verdict']=='UNRUN' and rep['n4']['status']=='PASS' and not rep['row_parity_problems'],exit=q.returncode,consumed=len(rep['consumed']['files']))
 # Data-only, independently made MRC and global-row negative controls.
 h=bytearray(1024);struct.pack_into('<4i',h,0,768,512,1,2);h[208:212]=b'MAP ';valid=bytes(h)+bytes(768*512*4)
 for kind,b in [('valid',valid),('truncated',valid[:-1]),('header',valid[:1024]),('extra',valid+b'x'),('map',valid[:208]+b'FAIL'+valid[212:])]:
  try:g.mrc_check(b);accepted=True
  except g.Invalid:accepted=False
  record('mrc-'+kind,accepted==(kind=='valid'),accepted=accepted,sha256=sha(b),size=len(b))
 star='data_global_shift\nloop_\n_rlnMicrographFrameNumber #1\n_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n'+''.join(f'{i} 0 0\n' for i in range(1,13))
 rows=g.global_rows(star)
 for kind,s,eq in [('exponent',star.replace(' 0 0',' +0e0 0.000'),True),('signed-y',star.replace('1 0 0\n','1 0 -0\n'),False),('changed-y',star.replace('1 0 0\n','1 0 0.0001\n'),False),('frame12',star.replace('12 0 0\n',''),False),('unicode',star.replace('1 0 0\n','1 ٠ 0\n'),False)]:
  try:equal=g.rows_equal(rows,g.global_rows(s));error=None
  except g.Invalid as e:equal=False;error=str(e)
  record('rows-'+kind,equal==eq,equal=equal,error=error)
 record('all-controls',all(x['ok'] for x in results))
 return 0 if all(x['ok'] for x in results) else 1
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:
  (R/'UNEXPECTED.json').write_text(json.dumps({'error':repr(e),'traceback':traceback.format_exc()},indent=2)+'\n');raise
