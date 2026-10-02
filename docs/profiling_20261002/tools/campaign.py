#!/usr/bin/env python3
"""Interleaved ablation campaign: 7 arms x N reps, matched conditions, complete products."""
import csv,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path

W=Path('/home/alex/mc-release-20261002'); DATA=Path('/home/alex/mc-unified-20260930/data')
UUID='GPU-eddb42fe-4f9a-adde-76d3-b924e14add54'; MASK='64-71'; REPS=int(sys.argv[1]) if len(sys.argv)>1 else 5
ARMS=['a0_main','a1_base','a2_gain','a3_premask','a4_globalpool','a5_patchpool','a6_final']
OPTS=['--i','movies.star','--use_own','--dose_weighting','--dose_per_frame','1.277','--patch_x','5','--patch_y','5',
      '--bfactor','150','--gainref','Movies/gain.mrc','--seed','1','--gpu','0','--j','6','--max_io_threads','6',
      '--ingest','nvcomp']
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def cap(a): return subprocess.check_output(a,text=True).strip()

ROOT=W/'campaign'; shutil.rmtree(ROOT,ignore_errors=True); ROOT.mkdir(parents=True)
bins={a:W/f'bld-{a}'/'motioncorr' for a in ARMS}
binsha={a:sha(p) for a,p in bins.items()}
inputs=[DATA/'movies.star',DATA/'Movies/gain.mrc']+sorted(DATA.glob('Movies/*.tiff'))
insha={str(p):sha(p) for p in inputs}
(ROOT/'provenance.json').write_text(json.dumps({
 'arms':{a:{'binary':str(bins[a]),'sha256':binsha[a]} for a in ARMS},
 'reps':REPS,'options':OPTS,'cpu_mask_requested':MASK,'expected_gpu_uuid':UUID,
 'gpu':cap(['nvidia-smi','--query-gpu=index,uuid,name,memory.total','--format=csv']),
 'driver':cap(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader']).splitlines()[0],
 'cpu_topology':cap(['lscpu','-e=CPU,CORE,SOCKET,NODE']),
 'thp':Path('/sys/kernel/mm/transparent_hugepage/enabled').read_text().strip(),
 'env':{k:v for k,v in os.environ.items() if k.startswith(('OMP_','CUDA_','MC_'))},
 'input_sha256':insha,'start_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
 'wall_scope':'whole process, wrapper-inclusive, including all requested reports and the writer drain',
},indent=2))

recs=[]; disc=[]; retry=0
for rep in range(1,REPS+1):
    order=ARMS if rep%2 else ARMS[::-1]      # alternate direction to cancel within-rep drift
    todo=list(order)
    while todo:
        arm=todo.pop(0)
        occ=cap(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'])
        waited=0
        while occ and waited<600: time.sleep(10); waited+=10; occ=cap(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'])
        if occ: raise SystemExit('GPU still occupied after %ds: %s'%(waited,occ))
        d=ROOT/f'{arm}-{rep}'; out=d/'output'; out.mkdir(parents=True)
        res=d/'resource.txt'; log=d/'run.log'
        dev=open(d/'device.csv','w')
        smi=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,uuid,utilization.gpu,memory.used',
                              '--format=csv,noheader,nounits','-lms','100'],stdout=dev,stderr=subprocess.STDOUT)
        apps=open(d/'gpu-apps.csv','w')
        ap=subprocess.Popen(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory',
                             '--format=csv,noheader,nounits','-lms','100'],stdout=apps,stderr=subprocess.STDOUT)
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=UUID,OMP_NUM_THREADS='6')
        cmd=['/usr/bin/time','-v','-o',str(res),'taskset','-c',MASK,str(bins[arm]),*OPTS,
             '--o',str(out)+'/','--ingest_witness',str(d/'ingest.witness')]
        t=time.monotonic()
        with open(log,'w') as lf:
            proc=subprocess.Popen(cmd,cwd=DATA,stdout=lf,stderr=subprocess.STDOUT,env=env)
            # /usr/bin/time forks, but taskset EXECs the target rather than forking,
            # so the payload can appear at depth 1 or depth 2. Walk all descendants and
            # match on the resolved exe instead of assuming a fixed depth.
            payload=None
            def descendants(root):
                seen=[]; stack=[root]
                while stack:
                    q=stack.pop()
                    try:
                        for tk in Path(f'/proc/{q}/task').iterdir():
                            for ch in (tk/'children').read_text().split():
                                ch=int(ch)
                                if ch not in seen: seen.append(ch); stack.append(ch)
                    except OSError: pass
                return seen
            target=bins[arm].resolve()
            while proc.poll() is None:
                if payload is None:
                    for q in [proc.pid]+descendants(proc.pid):
                        try:
                            if Path(f'/proc/{q}/exe').resolve()==target: payload=q; break
                        except OSError: pass
                time.sleep(0.02)
            rc=proc.returncode
        wall=time.monotonic()-t
        for p in (smi,ap): p.terminate(); p.wait(timeout=10)
        dev.close(); apps.close()
        if rc: raise SystemExit(f'{arm} rep{rep} returned {rc}')
        txt=res.read_text()
        g=lambda pat,d=None:(re.search(pat,txt).group(1) if re.search(pat,txt) else d)
        native='\n'.join([log.read_text()]+[q.read_text() for q in out.rglob('*.log')])
        rows=[r.split(',') for r in (d/'device.csv').read_text().splitlines() if r.strip()]
        vals=[(float(r[2]),float(r[3])) for r in rows if len(r)>3 and r[2].strip().replace('.','').isdigit()]
        approws=[r.split(',') for r in (d/'gpu-apps.csv').read_text().splitlines() if r.strip()]
        pids={r[0].strip() for r in approws if len(r)>1}
        # any pid on any device that is not our payload is a co-tenant; a same-GPU
        # neighbour has a MATCHING uuid, so a uuid test cannot see it
        foreign=sorted(pids-{str(payload)}) if payload else sorted(pids)
        pin=re.findall(r'pinned staging=(\d+)/(\d+) reserved, (\d+) payload',native)
        retained=re.search(r'retained across movies: ([\d.]+) MiB',native)
        rec={'rep':rep,'arm':arm,'wall_seconds':wall,'rc':rc,
             'user_s':float(g(r'User time \(seconds\): ([\d.]+)',0)),
             'sys_s':float(g(r'System time \(seconds\): ([\d.]+)',0)),
             'cpu_percent':int(g(r'Percent of CPU this job got: (\d+)%',0)),
             'gnu_elapsed':g(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)'),
             'max_rss_KiB':int(g(r'Maximum resident set size \(kbytes\): (\d+)',0)),
             'gpu_util_mean_pct':(sum(v[0] for v in vals)/len(vals)) if vals else None,
             'device_mem_peak_MiB':max((v[1] for v in vals),default=None),
             'device_mem_samples':len(vals),
             'pinned_reserved_bytes':int(pin[-1][0]) if pin else None,
             'pinned_cap_bytes':int(pin[-1][1]) if pin else None,
             'retained_MiB':float(retained.group(1)) if retained else None,
             'peak_vram_MiB':float(re.search(r'Peak VRAM: ([\d.]+) MiB',native).group(1)) if 'Peak VRAM:' in native else None,
             'w_global':native.count('[CUDA Global Alignment] completed'),
             'w_patch':native.count('[CUDA Patch Alignment] completed'),
             'w_dw':native.count('[CUDA Dose-Weighted Reconstruction Profile'),
             'warnings':native.count('WARNING:'),
             'nvcomp_witnesses':len((d/'ingest.witness').read_text().splitlines()),
             'products':sum(1 for _ in out.rglob('*') if _.is_file()),
             'payload_pid':payload,'foreign_gpu_pids':foreign,'directory':str(d)}
        bad=[k for k,v in (('w_global',24),('w_patch',600),('w_dw',24),('nvcomp_witnesses',24),('products',109)) if rec[k]!=v]
        if bad or rec['warnings']: raise SystemExit(f'{arm} rep{rep} grade failure: {bad} warn={rec["warnings"]}')
        if payload is None: raise SystemExit(f'{arm} rep{rep}: no verified payload pid')
        occ2=cap(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader'])
        if foreign or occ2:
            rec['DISCARDED']='co-tenant on the box during this run: pids=%s after=%r'%(foreign,occ2)
            disc.append(rec); (ROOT/'discarded.json').write_text(json.dumps(disc,indent=2))
            print(f"  DISCARD {arm} rep{rep}: co-tenant pids={foreign} after={occ2!r}",flush=True)
            shutil.rmtree(d,ignore_errors=True); retry+=1
            if retry>12: raise SystemExit('too many contaminated runs; box is not quiet enough to time on')
            todo.append(arm); time.sleep(5); continue
        recs.append(rec); (ROOT/'runs.json').write_text(json.dumps(recs,indent=2))
        print(f"{arm:14s} rep{rep}  {wall:7.3f}s  cpu={rec['user_s']+rec['sys_s']:7.2f}s  rss={rec['max_rss_KiB']/1048576:5.3f}GiB  vram={rec['device_mem_peak_MiB']}MiB",flush=True)

if {a:sha(p) for a,p in bins.items()}!=binsha: raise SystemExit('binary changed during campaign')
if {str(p):sha(p) for p in inputs}!=insha: raise SystemExit('input changed during campaign')
print('CAMPAIGN_COMPLETE')
