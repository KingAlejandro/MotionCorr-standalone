#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse,hashlib,json,os,struct,subprocess,threading,time
from pathlib import Path
import numpy as np,tifffile,imagecodecs
from owned_process import run

UUID='GPU-eddb42fe-4f9a-adde-76d3-b924e14add54'
MASK=set(range(96,104))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok:raise RuntimeError(msg)
def read_dump(path,expected):
    raw=Path(path).read_bytes();need(len(raw)>=32,'dump header missing')
    x,y,f,b=struct.unpack('<4q',raw[:32]);need((f,y,x)==expected.shape and b==expected.dtype.itemsize,'exact dump dimensions/type')
    need(len(raw)==32+x*y*f*b,'exact dump byte extent')
    return np.frombuffer(raw[32:],dtype='<u%d'%b).reshape(f,y,x)
def grade(dump,top):
    expected=top[:,::-1,:];actual=read_dump(dump,expected)
    need(np.array_equal(actual,expected),'every native sample vs independent oracle')
    # Each control mutates real returned samples; sums alone cannot pass these.
    controls={}
    controls['unflipped']=not np.array_equal(actual,top)
    bad=expected.copy();bad[0,0,0],bad[0,0,1]=bad[0,0,1],bad[0,0,0]
    controls['within_row_swap']=not np.array_equal(actual,bad) and np.array_equal(bad.sum(axis=2,dtype=np.uint64),expected.sum(axis=2,dtype=np.uint64))
    bad=expected.copy();bad[-1,-1,-1]^=np.array(1,dtype=bad.dtype)
    controls['last_frame_bit']=not np.array_equal(actual,bad)
    controls['missing_last']=actual.shape!=expected[:-1].shape
    if actual.dtype.itemsize==2:controls['byte_order']=not np.array_equal(actual,expected.byteswap())
    need(all(controls.values()),'every comparator control powered')
    return dict(samples=int(actual.size),dtype=str(actual.dtype),shape=list(actual.shape),controls=controls,payload_sha256=hashlib.sha256(actual.tobytes()).hexdigest())
class Monitor(threading.Thread):
    def __init__(self):super().__init__(daemon=True);self.done=False;self.rows=[];self.errors=[]
    def run(self):
        while not self.done:
            try:
                p=subprocess.run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name,used_gpu_memory','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
                need(p.returncode==0,'compute sampler query');rows=[]
                for line in p.stdout.splitlines():
                    parts=[x.strip() for x in line.split(',',3)];need(len(parts)==4 and parts[0].isdigit(),'compute row format')
                    if parts[1]!=UUID:continue
                    pid=int(parts[0]);proc=Path('/proc')/str(pid)
                    try:
                        stat=(proc/'stat').read_text();birth=stat[stat.rfind(')')+2:].split()[19]
                        rows.append(dict(pid=pid,birth=birth,uuid=parts[1],gpu_memory_mib=parts[3],exe=os.readlink(proc/'exe'),affinity=sorted(os.sched_getaffinity(pid)),maps=(proc/'maps').read_text(),status=(proc/'status').read_text()))
                    except FileNotFoundError:continue # transient exits cannot prove identity
                self.rows.extend(rows)
            except Exception as e:self.errors.append(str(e));break
            time.sleep(.05)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--binary',required=True);ap.add_argument('--predecessor',required=True);ap.add_argument('--fault-library',required=True);ap.add_argument('--inputs',required=True);ap.add_argument('--work',required=True);a=ap.parse_args()
    need(set(os.sched_getaffinity(0))==MASK,'actual caller CPU mask')
    binary=str(Path(a.binary).resolve());fault=str(Path(a.fault_library).resolve());inputs=Path(a.inputs).resolve();work=Path(a.work).resolve();work.mkdir(exist_ok=False)
    manifest=json.loads((inputs/'manifest.json').read_text());before={r['path']:sha(inputs/r['path']) for r in manifest['inputs']}
    need(all(before[r['path']]==r['sha256'] for r in manifest['inputs']),'generated input pin')
    old=str(Path(a.predecessor).resolve())
    report=dict(binary=dict(path=binary,sha256=sha(binary)),predecessor=dict(path=old,sha256=sha(old)),fault_library=dict(path=fault,sha256=sha(fault)),inputs=before,versions={m.__name__:m.__version__ for m in [np,tifffile,imagecodecs]},rows=[])
    mon=Monitor();mon.start()
    def call(name,movie,args=(),faultmode=None,trusted=True,binary_override=None):
        dump=work/(name+'.bin');command=[binary_override or binary,'--movie',str(movie),'--max-input-bytes',str(128<<20),'--max-output-bytes',str(64<<20)]
        if trusted:command+=['--trusted-input']
        command+=list(args)
        if '--probe-only' not in args:command+=['--dump',str(dump)]
        if faultmode is not None:command=['env','LD_PRELOAD='+fault,'MC_NVTIFF_FAULT='+faultmode]+command
        rc,log,owned=run(command,work/(name+'.log'),timeout=180)
        row=dict(name=name,returncode=rc,owned=owned,log_sha256=sha(work/(name+'.log')))
        parsed=[json.loads(line) for line in log.splitlines() if line.startswith('{')]
        if parsed:row['probe']=parsed[-1]
        report['rows'].append(row)
        (work/'partial-report.json').write_text(json.dumps(report,indent=2)+'\n')
        need(not list(work.glob(name+'.bin.tmp.*')),'temporary leaked '+name)
        return rc,log,row,dump
    try:
        rc,log,row,dump=call('old-absent-depth',inputs/'u8-strip-p1.tiff',binary_override=old)
        need(rc==3 and not dump.exists() and row['probe']['decode_executed'] is False and all(f['depth']==0 and f['nvtiff_status']==0 and f['experiment_admitted'] is False for f in row['probe']['frames']),'actual old source refuses SDK-supported absent-depth2D')
        for item in manifest['inputs']:
            movie=inputs/item['path'];name=item['name']
            if item['expected']=='refused':
                rc,log,row,dump=call(name,movie,args=['--first','0','--count','1'])
                need(rc==3 and not dump.exists() and row.get('probe',{}).get('decode_executed') is False,'full movie admission refusal '+name)
                continue
            rc,log,row,dump=call(name,movie)
            # A controlled unsupported layout is an honest support-table result.
            if rc==3:
                need(not dump.exists() and row['probe']['decode_executed'] is False,'unsupported no decode/publication')
                need(any(f['nvtiff_status']!=0 for f in row['probe']['frames']),'probe admission defect must not be labelled libraryunsupported')
                row['verdict']='LIBRARY_UNSUPPORTED';continue
            need(rc==0 and row.get('probe',{}).get('cleanup_complete') is True,'decode complete '+name)
            need(row['probe']['uuid_hex']==UUID[4:].replace('-','') and row['probe']['decoder_internal_device_bytes'] is None,'UUID/scratch truthful '+name)
            with tifffile.TiffFile(movie) as tf:top=np.stack([p.asarray() for p in tf.pages])
            row['oracle']=grade(dump,top);row['verdict']='PASS'
            need(all(f['tag_depth']==1 and f['depth']<=1 for f in row['probe']['frames']),'rawdepthunit/absent vs SDK2D')
        for base in ['u8-strip-p1','u16-strip-p2']:
            item=next(r for r in report['rows'] if r['name']==base);need(item.get('verdict')=='PASS','minimum U8/U16 LZW coverage')
            movie=inputs/(base+'.tiff');rc,log,row,dump=call(base+'-range',movie,args=['--first','3','--count','5','--batch-frames','4'])
            need(rc==0 and row['probe']['first']==3 and row['probe']['count']==5,'selected range decode')
            with tifffile.TiffFile(movie) as tf:top=np.stack([p.asarray() for p in tf.pages])
            row['oracle']=grade(dump,top[3:8]);need(not np.array_equal(read_dump(dump,top[3:8]),top[:5,::-1,:]),'wrong first frame control')
        movie=inputs/'u8-strip-p1.tiff'
        for name,args,trust,needle in [('no-trust',[],False,'--trusted-input are required'),('input-cap',['--max-input-bytes','1'],True,'within --max-input-bytes'),('output-cap',['--max-output-bytes','1'],True,'decoded batch exceeds'),('first-oob',['--first','24'],True,'first frame out of range'),('count-oob',['--first','23','--count','2'],True,'frame range exceeds')]:
            rc,log,row,dump=call(name,movie,args=args,trusted=trust);need(rc!=0 and needle in log and not dump.exists(),'powered named refusal '+name)
        target=work/'existing.bin';target.write_bytes(b'preserve-original');original=sha(target)
        rc,log,row,dump=call('existing',movie);need(rc!=0 and 'destination must not exist' in log and sha(target)==original,'no overwrite')
        symlink=work/'input-symlink.tiff';symlink.symlink_to(movie)
        rc,log,row,dump=call('symlink',symlink);need(rc!=0 and 'open input' in log and not dump.exists(),'symlink refusal')
        rc,log,row,dump=call('interposer-healthy',movie,faultmode='healthy')
        need(rc==0 and 'INTERPOSER decode 24' in log,'real API interposer positive')
        with tifffile.TiffFile(movie) as tf:top=np.stack([p.asarray() for p in tf.pages])
        row['oracle']=grade(dump,top)
        for mode,needle in [('decode-refusal','decode: nvTIFF=4'),('decode-execution','decode: nvTIFF=6'),('completion','completion='),('destroy','decoder destroy: nvTIFF status 8')]:
            rc,log,row,dump=call('fault-'+mode,movie,faultmode=mode)
            need(rc!=0 and needle in log and not dump.exists(),'API failure no publication '+mode)
            if mode!='destroy':need(log.count('INTERPOSER decode ')==1,'no redispatch after fault '+mode)
            need('INTERPOSER '+('completion' if mode=='completion' else 'destroy' if mode=='destroy' else 'decode 1') in log,'actual interposed boundary reached')
        need(before=={r['path']:sha(inputs/r['path']) for r in manifest['inputs']},'immutable input hashes after')
        report['status']='CONTENT_PASS'
    finally:
        mon.done=True;mon.join(timeout=20);report['compute_samples']=mon.rows;report['sampler_errors']=mon.errors
        (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    need(not mon.errors,'physical sampler errors')
    pids={r['owned']['pid']:str(r['owned']['original_start']) for r in report['rows']}
    witnesses=[s for s in mon.rows if s['pid'] in pids and s['birth']==pids[s['pid']] and s['exe']==binary]
    need(witnesses and all(set(s['affinity'])==MASK and 'libnvtiff.so' in s['maps'] for s in witnesses),'physical GPU/actual binary/load/mask witness')
    report['physical_witness_count']=len(witnesses);report['status']='PASS'
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',rows=len(report['rows']),physical_witnesses=len(witnesses),binary_sha256=sha(binary))))
if __name__=='__main__':main()
