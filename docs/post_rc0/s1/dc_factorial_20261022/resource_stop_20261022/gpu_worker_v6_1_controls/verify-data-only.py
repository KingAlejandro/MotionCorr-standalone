# SPDX-License-Identifier: GPL-2.0-or-later
"""One data-only v6.1 iteration. No child processes or real signal calls; preserve every result."""
import ast, contextlib, difflib, fcntl, hashlib, importlib.util, json, os, platform, runpy, shutil, signal, socket, subprocess, sys, time, uuid
from pathlib import Path
from unittest.mock import patch

REPO=Path.cwd(); T=REPO/'docs/post_rc0/s1/dc_factorial_20261022/tools'
SOURCE='2f32e7be4d75c4451d46fbef66a87540716f48c6'
N=Path('/tmp')/('motioncorr-dc262-v6_1-data-'+str(uuid.uuid4())); N.mkdir()
lease=open(N/'.lease','a'); fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',TMPDIR=str(N))
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
files=['gpu_worker_v6_1.py','test_gpu_worker_v6_1.py','run_v6_1_controls.py','test_v6_1_static.py','v6_1_mutants.json','test_run_v6_admission.py','campaign.py']
space=shutil.disk_usage(N); assert space.free>=256*1024**2
rec=dict(schema='dc262-v6.1-data-attempt/1',source_sha=SOURCE,namespace=str(N),start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
    host=socket.gethostname(),platform=platform.platform(),python=sys.version,python_executable=sys.executable,
    interpreter_sha256=sha(sys.executable),numeric_threads=1,load=os.getloadavg(),logical_cpus=os.cpu_count(),free_bytes=space.free,
    affinity='not pinned; macOS affinity unavailable',scratch_cap_bytes=256*1024**2,private_lifetime_lease='nonblocking acquired',
    inputs={f:sha(T/f) for f in files},ownership_sha256=sha(REPO/'tools/multi_gpu/process_ownership.py'),
    driver_sha256=sha(__file__),process_suite='UNRUN/unspent; frozen provider-bound owner admission unavailable; not invoked',
    limits='data-only mocked Popen/process tables/signals; no worker/mock/query process or real signal; no process/native/GPU qualification',commands=[])
(N/'PREFLIGHT.json').write_text(json.dumps(rec,indent=1)+'\n')

def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(name,path,args):
    argv=[str(path)]+args
    with open(N/(name+'.out'),'w') as out, contextlib.redirect_stdout(out),contextlib.redirect_stderr(out),patch.object(sys,'argv',argv):
        try:runpy.run_path(str(path),run_name='__main__');code=0
        except SystemExit as e:code=e.code
    rec['commands'].append(dict(name=name,mode='runpy in same interpreter; no child process',argv=[sys.executable,'-B']+argv,exit=code))
    return code

def write():
    rec.update(end_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),end_load=os.getloadavg(),scratch_bytes=sum(p.stat().st_size for p in N.rglob('*') if p.is_file()))
    assert rec['scratch_bytes']<rec['scratch_cap_bytes']
    (N/'ATTEMPT.json').write_text(json.dumps(rec,indent=1)+'\n')

def forbidden(*a,**k):raise AssertionError('forbidden real process/signal in data-only verification')

try:
    with patch.object(subprocess,'Popen',side_effect=forbidden),patch.object(os,'kill',side_effect=forbidden),patch.object(os,'killpg',side_effect=forbidden),patch.object(signal,'signal',side_effect=forbidden):
        # All named tool sources and embedded fixtures compile; no fixture is executed.
        for name in files:
            if name.endswith('.py'):compile((T/name).read_text(),str(T/name),'exec')
        assert run('static-units',T/'test_v6_1_static.py',['--json',str(N/'static-units.json')])==0,'baseline failure: freeze this iteration'
        assert run('admission-units',T/'test_run_v6_admission.py',['--runner',str(T/'run_v6_1_controls.py'),'--json',str(N/'admission-units.json')])==0,'admission failure: freeze this iteration'
        H=load('v6_1_focused_harness',T/'test_gpu_worker_v6_1.py'); W=T/'gpu_worker_v6_1.py'
        focused={'K22':H.k22(W),'K36':H.k36(W),'K28_K30':H.r3_controls(W,['K28','K30'])}
        (N/'focused-controls.json').write_text(json.dumps(focused,indent=1)+'\n')
        assert focused['K22'][0] and focused['K36'][0] and all(v[0] for v in focused['K28_K30'].values()),'focused failure: freeze this iteration'
        mutations=json.loads((T/'v6_1_mutants.json').read_text()); source=W.read_text(); checks=[]
        for name,spec in mutations.items():
            text=source
            for old,new in spec['replace']:
                assert text.count(old)==1,(name,'replacement is not unique'); text=text.replace(old,new)
            compile(text,name,'exec')
            row=dict(name=name,targets_unique=True,compiles=True,process_control='UNRUN')
            if name in ['late_observer_root_signal_removed','k22_own_group_exclusion_removed']:
                # Only two targeted mutant bytes retained. Existing dependencies are imported in place.
                path=N/(name+'.py');path.write_text(text)
                # Worker import searches ancestors for the ownership helper; frozen bytes in scratch supply it.
                (N/'tools/multi_gpu').mkdir(parents=True,exist_ok=True)
                shutil.copy2(REPO/'tools/multi_gpu/process_ownership.py',N/'tools/multi_gpu/process_ownership.py')
                shutil.copy2(T/'campaign.py',N/'campaign.py')
                code=run('mutant-'+name,T/'test_v6_1_static.py',['--worker',str(path),'--json',str(N/('mutant-'+name+'.json'))])
                result=json.loads((N/('mutant-'+name+'.json')).read_text())
                want='test_k36_healthy_and_late_error_interleavings' if name.startswith('late') else 'test_k22_exact_fixture_interface_and_own_group_exclusion'
                assert code==1 and len(result['failures'])==1 and not result['errors'] and want in result['failures'][0]['test'],(name,'unexpected mutant outcome: freeze this iteration')
                row.update(mutant_sha256=sha(path),synthetic_verdict='FAIL as expected',failed_check=result['failures'][0]['test'])
            checks.append(row)
        (N/'MUTANT-CHECKS.json').write_text(json.dumps(checks,indent=1)+'\n')
        # Bind version references and show that the checked fallback's body is identical to frozen v6.
        old_ast=ast.parse((T/'gpu_worker_v6.py').read_text());new_ast=ast.parse(W.read_text())
        old_fn=next(x for x in old_ast.body if isinstance(x,ast.FunctionDef) and x.name=='signal_job_group')
        new_fn=next(x for x in new_ast.body if isinstance(x,ast.FunctionDef) and x.name=='signal_job_group')
        assert ast.dump(old_fn,include_attributes=False)==ast.dump(new_fn,include_attributes=False)
        runner=load('v6_1_runner_refs',T/'run_v6_1_controls.py')
        assert runner.INPUTS['worker']==W and runner.INPUTS['harness']==T/'test_gpu_worker_v6_1.py' and runner.INPUTS['mutants']==T/'v6_1_mutants.json'
        (N/'REFERENCE-CHECKS.json').write_text(json.dumps(dict(original_group_fallback_ast_unchanged=True,runner_inputs={k:str(v) for k,v in runner.INPUTS.items()},schema='dc262-run/v6.1',all_sources_compiled=True,amendment_sha256=sha(T.parent/'resource_stop_20261022/AMENDMENT-v6.1.md')),indent=1)+'\n')
        rec['result']='PASS within data-only scope'
except BaseException:
    import traceback
    rec.update(result='FAIL: iteration frozen; no in-place retry',error=traceback.format_exc())
finally:
    write()
    print(json.dumps(dict(namespace=str(N),source_sha=SOURCE,result=rec['result'],commands=rec['commands'],load=rec['load'],scratch_bytes=rec['scratch_bytes']),indent=1))
