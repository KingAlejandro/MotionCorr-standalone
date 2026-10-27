import os,sys,json,subprocess,hashlib,re,pathlib,shutil,time,socket
sha=lambda p: hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
bins={
'def':('/home/alex/mc-dcnative2-20261026/build-def/motioncorr','2db45b2df8241e14bda28e9dbe3d7eae0ce9f5612a7b775bc33990aeb27bed6a'),
'exp':('/home/alex/mc-dcnative2-20261026/build-exp/motioncorr','b918cadc571eb09d753fd454a20554400ea6443b6b0738e14670f96c7afb2857'),
'iso':('/home/alex/mc-dcnative2-20261026/build-iso/motioncorr','3a7d4f472c0f795f6e3d7fdb7c31ab5c3e6bdef00ccf95d08a5cf5855155d0ff'),
'oracle_exp':('/home/alex/mc-dcnative2-20261026/build-exp/experiment_ccf_dc_stage','3b93be6a06a5a6c41148671bdb654e1a4b33ad500f49e601a451e36e3c95b026'),
'oracle_iso':('/home/alex/mc-dcnative2-20261026/build-iso/experiment_ccf_dc_stage','99f1f35228681ea60836094d300237020b89a806ab5a5ebdd872f8b1cc3dfdb5')}
allow=('PATH','HOME','LANG','LC_ALL','LC_CTYPE','TMPDIR','USER','LOGNAME')
scrub={k:os.environ[k] for k in allow if k in os.environ}
out={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'hostname':socket.gethostname(),'scope':'Read-only current loader and resource snapshot, no native execution or allocation. Historical Stage B resolution is unavailable.','loader':{},'scrub_environment':scrub,'inherited_loader_names_present':[k for k in ('LD_LIBRARY_PATH','LD_PRELOAD') if k in os.environ]}
for name,(b,expected) in bins.items():
    actual=sha(b)
    if actual!=expected: raise RuntimeError('binary pin mismatch: '+name)
    records={}
    for label,env in [('scrub',scrub),('full',dict(os.environ))]:
        p=subprocess.run(['ldd',b],env=env,text=True,capture_output=True,timeout=15)
        if p.returncode or 'not found' in p.stdout: raise RuntimeError('ldd failed '+name+'/'+label+': '+p.stderr+p.stdout)
        lines=sorted(re.sub(r' \(0x[0-9a-f]+\)$','',line.strip()) for line in p.stdout.splitlines() if line.strip())
        paths=set()
        for line in lines:
            tokens=line.split()
            path=tokens[2] if '=>' in tokens and len(tokens)>=3 else tokens[0]
            if path.startswith('/'): paths.add(path)
        if not paths: raise RuntimeError('empty loader paths '+name)
        records[label]={'lines':lines,'libraries':{p:{'realpath':os.path.realpath(p),'sha256':sha(p)} for p in sorted(paths)}}
    equal=records['scrub']==records['full']
    out['loader'][name]={'path':b,'sha256':actual,'current_resolutions_equal':equal,**records}
    if not equal: raise RuntimeError('current full vs scrub loader mismatch '+name)
def capture(cmd):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=15)
    return {'argv':cmd,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
out['gpus']=capture(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
out['gpu_processes']=capture(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'])
out['process_metadata']=capture(['ps','-eo','pid,ppid,user,psr,pcpu,comm','--sort=-pcpu'])
out['memory']=pathlib.Path('/proc/meminfo').read_text()
out['disk_free_bytes']=shutil.disk_usage('/home/alex').free
out['locks']={}
locks=pathlib.Path('/proc/locks').read_text()
for p in ['/tmp/motioncorr-cuda-boundary-cpu80-87.lock','/tmp/motioncorr-gpu2-correctness.lock','/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock']:
    st=os.stat(p)
    matches=[line for line in locks.splitlines() if line.split()[5].split(':')[-1]==str(st.st_ino)]
    out['locks'][p]={'inode':st.st_ino,'device':st.st_dev,'matching_proc_lock_lines':matches}
def ticks():
    rows={}
    for line in pathlib.Path('/proc/stat').read_text().splitlines():
        t=line.split()
        if t and t[0] in ['cpu'+str(i) for i in range(80,88)]: rows[t[0]]=list(map(int,t[1:9]))
    if len(rows)!=8:raise RuntimeError('missing CPU rows')
    return rows
a=ticks();time.sleep(2);b=ticks()
out['cpu_busy_fraction']={}
for c in a:
    d=[x-y for x,y in zip(b[c],a[c])];total=sum(d)
    if total<=0:raise RuntimeError('bad CPU interval')
    out['cpu_busy_fraction'][c]=(total-d[3]-d[4])/total
out['terminal_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
print(json.dumps(out,indent=2))
