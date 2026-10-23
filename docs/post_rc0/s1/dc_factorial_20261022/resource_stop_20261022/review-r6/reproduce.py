# Reviewer R6: data-only, guarded same-interpreter calls; no process harness.
import ast, contextlib, hashlib, importlib.util, json, os, runpy, signal, subprocess, sys, time
from pathlib import Path
from unittest.mock import patch
N=Path(__file__).parent
T=N/'docs/post_rc0/s1/dc_factorial_20261022/tools'
E=T.parent/'resource_stop_20261022/gpu_worker_v6_1_controls'
commands=[]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def forbidden(*a,**kw): raise AssertionError('R6 forbids real process/signal/handler installation')
def run(name,path,args):
    argv=[str(path)]+args
    with open(N/(name+'.out'),'w') as out, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), patch.object(sys,'argv',argv):
        try: runpy.run_path(str(path),run_name='__main__'); code=0
        except SystemExit as exc: code=exc.code
    commands.append(dict(name=name,mode='guarded runpy in lease-holder interpreter',argv=[sys.executable,'-B']+argv,exit=code))
    (N/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
    return code
result=dict(source='2f32e7be4d75c4451d46fbef66a87540716f48c6',final='52ad29a1531a1fb1cbe3df2254eac319a05f7f37',load=os.getloadavg(),utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),inputs={p.name:sha(p) for p in T.iterdir() if p.is_file()},scope='data-only; no actual Popen, PID/group signal, signal handler installation or process harness')
assert max(result['load'][:2])<=os.cpu_count()
try:
    with patch.object(subprocess,'Popen',side_effect=forbidden), patch.object(os,'kill',side_effect=forbidden), patch.object(os,'killpg',side_effect=forbidden), patch.object(signal,'signal',side_effect=forbidden):
        assert run('static-units',T/'test_v6_1_static.py',['--json',str(N/'static-units.json')])==0
        assert run('admission-units',T/'test_run_v6_admission.py',['--runner',str(T/'run_v6_1_controls.py'),'--json',str(N/'admission-units.json')])==0
        H=load('r6_harness',T/'test_gpu_worker_v6_1.py'); W=T/'gpu_worker_v6_1.py'
        focused=dict(K22=H.k22(W),K36=H.k36(W),K28_K30=H.r3_controls(W,['K28','K30']))
        (N/'focused-controls.json').write_text(json.dumps(focused,indent=2)+'\n')
        assert focused['K22'][0] and focused['K36'][0] and all(v[0] for v in focused['K28_K30'].values())
        mutations=json.loads((T/'v6_1_mutants.json').read_text()); checks=[]
        for name,spec in mutations.items():
            source=W.read_text()
            for old,new in spec['replace']:
                assert source.count(old)==1,(name,'non-unique target')
                source=source.replace(old,new)
            compile(source,name,'exec')
            row=dict(name=name,unique=True,compiles=True,process_execution='UNRUN',synthetic_execution='UNRUN')
            if name in ('k22_own_group_exclusion_removed','late_observer_root_signal_removed'):
                p=E/'iteration-01-2f32e7be'/(name+'.py')
                assert p.read_text()==source
                code=run('mutant-'+name,T/'test_v6_1_static.py',['--worker',str(p),'--json',str(N/('mutant-'+name+'.json'))])
                data=json.loads((N/('mutant-'+name+'.json')).read_text())
                want='test_k22_exact_fixture_interface_and_own_group_exclusion' if name.startswith('k22') else 'test_k36_healthy_and_late_error_interleavings'
                assert code==1 and not data['errors'] and len(data['failures'])==1 and want in data['failures'][0]['test']
                row.update(synthetic_execution='FAIL as expected',sha256=sha(p),failed_check=data['failures'][0]['test'])
            checks.append(row)
        (N/'MUTANTS.json').write_text(json.dumps(checks,indent=2)+'\n')
        old=ast.parse((T/'gpu_worker_v6.py').read_text()); new=ast.parse(W.read_text())
        fn=lambda tree:next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='signal_job_group')
        assert ast.dump(fn(old),include_attributes=False)==ast.dump(fn(new),include_attributes=False)
        result['checked_fallback_ast_unchanged']=True
        result['result']='PASS within data-only scope'
except BaseException:
    import traceback
    result.update(result='FAIL; frozen, no in-place retry',trace=traceback.format_exc())
finally:
    result.update(commands=commands,end_load=os.getloadavg())
    (N/'REPRODUCTION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
