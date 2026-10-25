import pathlib,subprocess,json,os,sys,hashlib,datetime
P=pathlib.Path(__file__).resolve().parent
D=P/'exact/docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023'
PYTHON='/Users/alex.konstantinov/.local/bin/python3'
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',GIT_DIR=subprocess.check_output(['git','rev-parse','--absolute-git-dir'],text=True).strip())
results=[]
for name,script,args in [('derived','derived_controls_v2_2.py',[]),('range','range_controls_v2_2.py',[]),('focused','run_controls_v2_2.py',[]),('baseline','compare_baseline_v2_2.py',['/tmp/motioncorr-orchestrator-20261022/dc-B-pass3-collected'])]:
 usage=sum(x.stat().st_blocks*512 for x in P.rglob('*') if x.is_file() and not x.is_symlink()); assert usage<60*1024*1024
 disk=subprocess.check_output(['df','-h','/System/Volumes/Data'],text=True)
 occ=subprocess.check_output(['ps','-axo','pid,ppid,%cpu,%mem,comm'],text=True)
 (P/(name+'-occupancy.txt')).write_text(disk+occ)
 argv=[PYTHON,'-B',str(D/script),*args,str(P/(name+'-01'))]
 row=dict(name=name,argv=argv,environment={k:env[k] for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','GIT_DIR']},utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),script_sha256=hashlib.sha256((D/script).read_bytes()).hexdigest(),target_sha256=hashlib.sha256((D/'summarize_v2_2.py').read_bytes()).hexdigest(),python_sha256=hashlib.sha256(pathlib.Path(PYTHON).resolve().read_bytes()).hexdigest(),scratch_allocated=usage)
 (P/(name+'-START.json')).write_text(json.dumps(row,indent=2))
 r=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=90)
 (P/(name+'-stdout.log')).write_text(r.stdout);(P/(name+'-stderr.log')).write_text(r.stderr)
 row.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr)
 (P/(name+'-EXIT.json')).write_text(json.dumps(row,indent=2));results.append(row)
 print(name,r.returncode,r.stdout,r.stderr,flush=True)
 if r.returncode: break
(P/'CHECK_RUNS.json').write_text(json.dumps(results,indent=2))
sys.exit(0 if len(results)==4 and all(r['exit']==0 for r in results) else 1)
