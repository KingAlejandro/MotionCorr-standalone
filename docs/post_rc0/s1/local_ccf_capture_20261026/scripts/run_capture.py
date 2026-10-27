"""Two authorized producers only; never retry an existing namespace."""
import hashlib,json,os,subprocess,sys,time,threading,shutil
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/tmp/motioncorr-local-ccf-20261026');EVID=ROOT/'evidence'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def check(v,s):
 if not v:
  if not (EVID/'STOP.json').exists():write(EVID/'STOP.json',dict(reason=s,utc=time.strftime('%FT%TZ',time.gmtime())))
  raise RuntimeError(s)
def admission(d,pins):
 locks=json.loads(os.environ['MOTIONCORR_HELD_LEASES']);cpus=sorted(os.sched_getaffinity(0))
 check('/tmp/motioncorr-cpu64-bench.lock' in locks and cpus==list(range(32,48)),'leases/affinity differ')
 ps=subprocess.check_output(['ps','-eo','pid,ppid,psr,pcpu,args','--sort=-pcpu'],text=True);(d/'occupancy-before.txt').write_text(ps)
 rows=[s.split(None,4) for s in ps.splitlines()[1:]];own={os.getpid(),os.getppid()}
 while True:
  prior=len(own);own.update(int(r[0]) for r in rows if len(r)==5 and int(r[1]) in own)
  if len(own)==prior:break
 for r in rows:
  if len(r)!=5 or int(r[0]) in own or float(r[3])<50:continue
  try:mask=sorted(os.sched_getaffinity(int(r[0])))
  except ProcessLookupError:continue
  check(not set(mask)&set(cpus),'foreign heavy process overlapping allowed CPU mask: '+str((r,mask)))
 roots=[ROOT,Path('/tmp/motioncorr-b2-native-20261026'),Path('/tmp/motioncorr-b2-factorial-20261026')]
 used=sum(p.stat().st_size for r in roots for p in r.rglob('*') if p.is_file());mem={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()}
 check(used<25*1024**3 and shutil.disk_usage(ROOT).free>2*1024**3 and mem['MemAvailable']>4*1024**3,'scratch/disk/memory admission failed')
 check(sha(pins['binary_path'])==pins['binary_sha256'],'binary changed')
 for f,h in pins['source_files'].items():check(sha(f)==h,'source changed: '+f)
 for f,h in pins['input_files'].items():check(sha(f)==h,'input changed: '+f)
 write(d/'admission.json',dict(utc=time.strftime('%FT%TZ',time.gmtime()),locks=locks,whole_chain_affinity=cpus,requested_native_threads=2,OMP_NUM_THREADS='2',BLAS_threads=1,combined_scratch_bytes=used,limit_bytes=25*1024**3,mem_available_bytes=mem['MemAvailable'],disk_free_bytes=shutil.disk_usage(ROOT).free,assessment='no foreign >=50% process whose allowed mask overlaps lane at fresh admission; receipt only, no timing claim'))
def monitor(pid,path,done):
 with path.open('w') as out:
  while not done.is_set():
   # Whole process tree actual masks/threads/RSS; no payload inspection.
   ps=subprocess.check_output(['ps','-eo','pid,ppid'],text=True);pairs=[tuple(map(int,l.split())) for l in ps.splitlines()[1:] if len(l.split())==2];own={pid}
   while True:
    n=len(own);own.update(p for p,pp in pairs if pp in own)
    if n==len(own):break
   records=[]
   for p in sorted(own):
    try:
     fields=dict(l.split(':',1) for l in Path(f'/proc/{p}/status').read_text().splitlines() if ':' in l)
     records.append(dict(pid=p,name=fields['Name'].strip(),allowed=fields['Cpus_allowed_list'].strip(),threads=int(fields['Threads']),rss=fields.get('VmRSS','').strip()))
    except FileNotFoundError:pass
   out.write(json.dumps(dict(monotonic=time.monotonic(),processes=records))+'\n');out.flush();done.wait(.05)
def identity(a,b,d,pins):
 check((a/'runtime.json').read_bytes()==(b/'runtime.json').read_bytes(),'runtime bytes differ')
 check((a/'output/noisy.star').read_bytes()==(b/'output/noisy.star').read_bytes(),'raw case STAR bytes differ')
 cp=subprocess.run([sys.executable,'-B',pins['comparator'],str(a/'output'),str(b/'output'),str(d/'products.json')],capture_output=True,text=True)
 (d/'products.stdout').write_text(cp.stdout+cp.stderr);check(cp.returncode==0,'product identity failed')
 write(d/'identity.json',dict(runtime_byte_equal=True,case_STAR_byte_equal=True,product_comparator='IDENTICAL',runtime_sha256=sha(a/'runtime.json'),case_STAR_sha256=sha(a/'output/noisy.star'),MRC='header0-223+size+pixels exact; labels inventoried',logs_PDF='inventory only'))
def run(label,pins):
 d=EVID/'runs'/label;d.mkdir(parents=True,exist_ok=False);admission(d,pins)
 old=json.loads(Path(pins['baseline_RUN']).read_text());cmd=old['argv'].copy();cmd[0]=pins['binary_path'];cmd[cmd.index('--o')+1]=str(d/'output')
 env={k:v for k,v in os.environ.items() if not k.startswith(('MC_DIAG_','MC_EXPERIMENT_'))}
 env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',MC_EXPERIMENT_CCF_DC_ARM='both',MC_DIAG_MODEL_OUT=str(d/'runtime.json'),PYTHONDONTWRITEBYTECODE='1')
 if label=='ON':env['MC_DIAG_LOCAL_CCF_DIR']=str(d/'capture')
 start=time.monotonic();done=threading.Event()
 with (d/'stdout.log').open('w') as out:
  p=subprocess.Popen(['/usr/bin/time','-v','-o',str(d/'time.txt'),*cmd],cwd=ROOT/'native-input',env=env,stdout=out,stderr=subprocess.STDOUT)
  t=threading.Thread(target=monitor,args=(p.pid,d/'actual-resources.jsonl',done));t.start();rc=p.wait();done.set();t.join()
 receipt=dict(label=label,exit=rc,argv=cmd,cwd=str(ROOT/'native-input'),binary_sha256=sha(pins['binary_path']),wall_receipt_only=time.monotonic()-start,environment={k:v for k,v in env.items() if k.startswith(('MC_','OMP_','OPENBLAS_','MKL_','NUMEXPR_'))},device='CPU; GPU not applicable',products={str(p.relative_to(d/'output')):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (d/'output').rglob('*') if p.is_file()})
 write(d/'RUN.json',receipt);check(rc==0,'producer exit '+str((label,rc)))
 check({'noisy.star','noisy.mrc','noisy.log','corrected_micrographs.star'}<=set(receipt['products']),'publication incomplete')
 if label=='ON':check((d/'capture/COMPLETE.json').is_file(),'capture incomplete')
 return d
if __name__=='__main__':
 EVID.mkdir(exist_ok=False);pins=json.loads((ROOT/'RUN_PINS.json').read_text())
 check(pins['independent_source_review']=='CLEAR','independent review not clear')
 check(sorted(p.name for p in (ROOT/'native-input').iterdir())==['noisy.mrcs','noisy.star'],'native input directory scope differs')
 baseline=Path(pins['baseline_run_dir'])
 old=json.loads(Path(pins['baseline_RUN']).read_text())
 for rel,h in old['publication'].items():check(sha(baseline/'output'/rel)==h['sha256'],'baseline product changed: '+rel)
 off=run('OFF',pins);identity(baseline,off,off,pins)
 on=run('ON',pins);identity(off,on,on,pins)
 write(EVID/'NATIVE_COMPLETE.json',dict(producers=2,identity='PASS both comparisons',source_commit=pins['source_commit'],binary_sha256=pins['binary_sha256'],no_timing_claim=True))
