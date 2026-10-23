"""Two fresh tiny fixtures: procedure-isolation detection, not Linux qualification."""
import argparse,contextlib,hashlib,importlib.util,io,json,os,pathlib,subprocess
R=pathlib.Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
def load(path):
 s=importlib.util.spec_from_file_location('index_case',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
results=[]
for bypass in (False,True):
 d=R/('index-isolation-bypass' if bypass else 'index-isolation-exact');d.mkdir();root=d/'input';tree=root/'tree';(tree/'src').mkdir(parents=True);(d/'proc').mkdir()
 for name in ['motioncorr_runner.cpp','local_motion_guard.h']:(tree/'src'/name).write_text(name+'\n')
 def git(*args):return subprocess.check_output(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(tree),*args],env=env,stderr=subprocess.DEVNULL)
 git('init','-q');git('add','.');git('-c','user.name=Review','-c','user.email=review@example.invalid','commit','-qm','fixture')
 want={'head':git('rev-parse','HEAD').decode().strip(),'status':[],'diff_sha256':sha(b''),'runner_sha256':sha((tree/'src/motioncorr_runner.cpp').read_bytes()),'helper_sha256':sha((tree/'src/local_motion_guard.h').read_bytes())}
 (d/'EXPECT.json').write_text(json.dumps({'trees':{'tree':want},'binaries':{}}))
 f=tree/'src/motioncorr_runner.cpp';st=f.stat();os.utime(f,ns=(st.st_atime_ns,st.st_mtime_ns+3000000000))
 src=(R/'regrade_v2_2.py').read_text()
 if bypass:
  for a,b in [("'GIT_INDEX_FILE': private_index,","'GIT_INDEX_FILE': os.path.join(tree, '.git', 'index'),"),("answer = _git(tree, private, *args)","answer = _git(tree, os.path.join(tree, '.git', 'index'), *args)")]:
   assert src.count(a)==1;src=src.replace(a,b)
 path=d/'regrade_v2_2.py';path.write_text(src);m=load(path);idx=tree/'.git/index'
 def identity(p):return {'sha256':sha(p.read_bytes()),'stat':list(m.stable_stat(p.stat()))}
 before=identity(idx);old=m._git;refresh=[]
 def wrapper(t,selected,*args):
  answer=old(t,selected,*args)
  if args==('status','--porcelain'):
   p=pathlib.Path(selected);pre=identity(p)
   e=dict(env,GIT_INDEX_FILE=selected,GIT_OPTIONAL_LOCKS='1')
   q=subprocess.run(['/usr/bin/git','-C',t,'update-index','--refresh'],env=e,capture_output=True)
   refresh.append({'selected':selected,'before':pre,'after':identity(p),'exit':q.returncode})
  return answer
 m._git=wrapper;buf=io.StringIO()
 with contextlib.redirect_stdout(buf):rc=m.cmd_precheck_live(argparse.Namespace(scratch_root=str(root),expect=str(d/'EXPECT.json'),proc_root=str(d/'proc'),out=str(d/'live.json')))
 after=identity(idx);record={'bypass':bypass,'exit':rc,'expected':1 if bypass else 0,'before':before,'after':after,'refresh':refresh,'stdout':buf.getvalue(),'source_sha256':sha(src.encode()),'kind':'procedure-isolation detection; guard still rejects bypass'}
 record['ok']=rc==record['expected'] and (before!=after)==bypass and bool(refresh) and refresh[0]['exit']==0 and refresh[0]['before']!=refresh[0]['after']
 results.append(record);(d/'CONTROL.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
(R/'INDEX-ISOLATION.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(0 if all(x['ok'] for x in results) else 1)
