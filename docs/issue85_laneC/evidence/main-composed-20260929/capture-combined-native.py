import json,os,subprocess,sys,threading,time
from pathlib import Path
R=Path(sys.argv[3]).resolve()
R.mkdir(parents=True,exist_ok=False)
source=Path(sys.argv[1]).resolve()
binary=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(source/'tests'))
import test_runner_contract as contract
raw_run=subprocess.run
records=[]
def observed_run(cmd,**kw):
    assert kw.pop('capture_output') and kw.pop('text')
    timeout=kw.pop('timeout')
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,**kw)
    proc=Path('/proc')/str(p.pid)
    for _ in range(100):
        if (proc/'exe').resolve()==Path(cmd[0]).resolve():break
        time.sleep(.001)
    else: raise AssertionError('payload executable was not witnessed')
    rec={'command':cmd,'pid':p.pid,'exe':str((proc/'exe').resolve()),'stat':(proc/'stat').read_text(),'status':(proc/'status').read_text(),'numa_maps':(proc/'numa_maps').read_text(),'cuda_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],'gpu_samples':[]}
    done=threading.Event()
    def sample():
        while not done.is_set():
            s=raw_run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],text=True,capture_output=True,timeout=15)
            rec['gpu_samples'].append({'time':time.time(),'exit':s.returncode,'stdout':s.stdout,'stderr':s.stderr})
            done.wait(.05)
    t=threading.Thread(target=sample);t.start()
    try:out,err=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill();p.communicate();raise
    finally:done.set();t.join(timeout=20)
    rec['returncode']=p.returncode
    rec['physical_gpu_witness']=any(str(p.pid) in row and os.environ['CUDA_VISIBLE_DEVICES'] in row for sample in rec['gpu_samples'] for row in sample['stdout'].splitlines())
    records.append(rec)
    (R/'payload-witness.json').write_text(json.dumps(records,indent=2))
    assert rec['physical_gpu_witness'],rec
    return subprocess.CompletedProcess(cmd,p.returncode,out,err)
contract.subprocess.run=observed_run
work=R/'products-candidate-witness';work.mkdir()
contract.interpolate_shifts(binary,work,gpu=0)
print('PASS two actual payload PID/start/executable/affinity/NUMA/physical UUID witnesses and native selected-frame oracle')
