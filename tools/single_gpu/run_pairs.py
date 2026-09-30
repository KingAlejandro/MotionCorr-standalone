#!/usr/bin/env python3
"""Matched complete-process runs, payload identity, exact products, no stage extrapolation."""
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--cpus',required=True);p.add_argument('--gpu-uuid',required=True);p.add_argument('--phase',required=True);p.add_argument('--pairs',type=int,required=True);a=p.parse_args()
if a.pairs<1: p.error("--pairs must be positive")

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()

def capture(argv):return subprocess.check_output(argv,text=True).strip()

def payload_info(pid,binary,full=True):
 q=Path('/proc')/str(pid)
 try:
  if q.joinpath('exe').resolve()!=binary.resolve():return None
  status=q.joinpath('status').read_text();stat=q.joinpath('stat').read_text().rsplit(')',1)[1].split()
  return {'pid':pid,'start_ticks':stat[19],'executable':str(q.joinpath('exe').resolve()),'status':status,'numa_maps':q.joinpath('numa_maps').read_text() if full else None,'cmdline':q.joinpath('cmdline').read_bytes().replace(b'\0',b' ').decode()}
 except OSError:return None

root=a.root/a.phase;root.mkdir(parents=True,exist_ok=False)
opts=['--i','movies.star','--use_own','--dose_weighting','--dose_per_frame','1.277','--patch_x','5','--patch_y','5','--bfactor','150','--gainref','Movies/gain.mrc','--seed','1','--gpu','0','--j','6','--max_io_threads','6','--ingest','nvcomp']
meta={'baseline_binary':str(a.baseline),'candidate_binary':str(a.candidate),'baseline_sha256':sha(a.baseline),'candidate_sha256':sha(a.candidate),'cpu_mask_requested':a.cpus,'env':{k:v for k,v in os.environ.items() if k.startswith(('OMP_','CUDA_','MC_','SLURM_'))},'expected_gpu_uuid':a.gpu_uuid,'gpu':capture(['nvidia-smi','--query-gpu=index,uuid,name','--format=csv']),'cpu_topology':capture(['lscpu','-e=CPU,CORE,SOCKET,NODE']),'input_star_sha256':sha(a.input_dir/'movies.star'),'options':opts,'phase':a.phase,'source_stamp':(a.source/'SOURCE_PIN.json').read_text()}
(root/'provenance.json').write_text(json.dumps(meta,indent=2))
manifest=json.loads((a.source/'docs/issue85_laneC/tutorial_24_movie_manifest.json').read_text())
expected=set(manifest['movies'])
input_paths=[a.input_dir/'movies.star',a.input_dir/'Movies/gain.mrc',*[a.input_dir/q for q in sorted(expected)]]
input_hashes={str(q):sha(q) for q in input_paths}
(root/'inputs.json').write_text(json.dumps(input_hashes,indent=2))
records=[]
for pair in range(1,a.pairs+1):
 for arm in (['baseline','candidate'] if pair%2 else ['candidate','baseline']):
  binary=a.baseline if arm=='baseline' else a.candidate
  d=root/f'{arm}-{pair}';d.mkdir();out=d/'output';out.mkdir();log=d/'run.log';resource=d/'resource.txt'
  occupants=capture(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'])
  if occupants:raise RuntimeError('GPU occupancy before controlled run: '+occupants)
  smi_log=open(d/'gpu-apps.csv','w');smi=subprocess.Popen(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits','-lms','200'],stdout=smi_log,stderr=subprocess.STDOUT)
  devices=open(d/'device.csv','w');dev=subprocess.Popen(['nvidia-smi','-i','0','--query-gpu=timestamp,uuid,utilization.gpu,memory.used','--format=csv,noheader,nounits','-lms','200'],stdout=devices,stderr=subprocess.STDOUT)
  cmd=['/usr/bin/time','-v','-o',str(resource),'taskset','-c',a.cpus,str(binary),*opts,'--o',str(out)+'/', '--ingest_witness',str(d/'ingest.witness')]
  t=time.monotonic();ident=None;peak=0
  with open(log,'w') as lf:
   proc=subprocess.Popen(cmd,cwd=a.input_dir,stdout=lf,stderr=subprocess.STDOUT)
   try:
    while proc.poll() is None:
     try:children=Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split()
     except OSError:children=[]
     for child in children:
      info=payload_info(int(child),binary,ident is None)
      if info and ident is None:ident=info
      if info:
       nowmask=re.search(r'^Cpus_allowed_list:\s+(.*)$',info['status'],re.M)[1]
       if ident and nowmask!=re.search(r'^Cpus_allowed_list:\s+(.*)$',ident['status'],re.M)[1]:raise RuntimeError('CPU affinity changed during run')
       m=re.search(r'^VmRSS:\s+(\d+) kB',info['status'],re.M)
       if m:peak=max(peak,int(m[1])*1024)
     time.sleep(.02)
    wall=time.monotonic()-t;rc=proc.returncode
   finally:
    for observer in (smi,dev):observer.terminate();observer.wait(timeout=10)
    smi_log.close();devices.close()
  if not ident:raise RuntimeError('No verified MotionCorr payload identity')
  actual=re.search(r'^Cpus_allowed_list:\s+(.*)$',ident['status'],re.M)[1]
  def mask(s):
   out=set()
   for item in s.split(','):
    v=list(map(int,item.split('-')));out.update(range(v[0],v[-1]+1))
   return out
  if mask(actual)!=mask(a.cpus):raise RuntimeError('payload CPU mask mismatch')
  (d/'payload.json').write_text(json.dumps(ident,indent=2))
  gpu_text=(d/'gpu-apps.csv').read_text()
  rows=[x.split(',') for x in gpu_text.splitlines() if x.strip()]
  if not any(x[0].strip()==str(ident['pid']) and x[1].strip()==a.gpu_uuid for x in rows):raise RuntimeError('No allocated physical GPU process witness')
  if any(x[0].strip()!=str(ident['pid']) or x[1].strip()!=a.gpu_uuid for x in rows):raise RuntimeError('Competing or unexpected GPU process during controlled run')
  if rc:raise RuntimeError(f'{arm} returned {rc}')
  witnesses=(d/'ingest.witness').read_text().splitlines()
  parsed=[x.split() for x in witnesses]
  if len(parsed)!=24 or any(len(x)!=2 or x[1]!='nvcomp' for x in parsed) or {x[0] for x in parsed}!=expected:raise RuntimeError('Incomplete/duplicate/foreign nvCOMP witnesses')
  warnings=[str(q) for q in [log,*out.rglob('*.log')] if 'WARNING:' in q.read_text()]
  native='\n'.join(q.read_text() for q in [log,*out.rglob('*.log')])
  if native.count('[CUDA Global Alignment] completed')!=24 or native.count('[CUDA Patch Alignment] completed')!=600:raise RuntimeError('Incomplete native alignment witnesses')
  if native.count('[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]')!=24:raise RuntimeError('Incomplete native DW reconstruction witnesses')
  if warnings:raise RuntimeError('Unexpected fallback/warning '+str(warnings))
  record={'pair':pair,'arm':arm,'whole_process_wall_seconds':wall,'peak_sampled_payload_rss_bytes':peak,'resource':resource.read_text(),'directory':str(d),'actual_cpu_mask':actual,'payload_pid':ident['pid']}
  records.append(record);(root/'runs.json').write_text(json.dumps(records,indent=2))
  print(arm,pair,wall,flush=True)
 b=root/f'baseline-{pair}'/'output';c=root/f'candidate-{pair}'/'output'
 compare=[os.environ.get('MC_PYTHON','python3'),str(a.source/'docs/issue85_laneC/compare_output_trees.py'),str(b),str(c),'--manifest',str(a.source/'docs/issue85_laneC/tutorial_24_movie_manifest.json'),'--input-star',str(a.input_dir/'movies.star'),'--json-out',str(root/f'exact-{pair}.json')]
 result=subprocess.run(compare,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (root/f'exact-{pair}.log').write_text(result.stdout)
 if result.returncode:raise RuntimeError('Exact complete non-PDF tree comparison failed: '+result.stdout)
if sha(a.baseline)!=meta['baseline_sha256'] or sha(a.candidate)!=meta['candidate_sha256']:raise RuntimeError('Binary changed during campaign')
if {str(q):sha(q) for q in input_paths}!=input_hashes:raise RuntimeError('Input content changed during campaign')
print('PAIRS_COMPLETE',flush=True)
