import pathlib,json,subprocess,hashlib,shlex,datetime,uuid
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
stage=json.loads((P/'dc-late68-direct-stage-result.json').read_text());assert stage['exit']==0
verified=json.loads(stage['stdout']);assert verified['state']=='STAGED_ALL_411_PAYLOAD_HASHES_MATCH' and verified['files']==411
ns=stage['namespace'];ids=pathlib.Path('/tmp/motioncorr-20261025-dc-late68-plan/late68-ids.txt').read_text().splitlines()
# Reconcile the native VM immediately before any late-record evaluation.
check='import pathlib,json\ns=pathlib.Path("/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b")\nids='+repr(ids)+'\npresent=[i for i in ids if (s/"eval/B"/(i+".json")).exists()]\nassert not present,present\nprint(json.dumps({"late68_existing_current_evaluations":present,"currentB":len(list((s/"eval/B").glob("*.json")))}))\n'
r=subprocess.run(['ssh','-o','BatchMode=yes','4GPUs','python3 -'],input=check.encode(),capture_output=True);assert r.returncode==0,r.stderr
(P/'dc-late68-current-eval-before-launch.json').write_bytes(r.stdout)
packet=P/'dc-late68-tools-v1.tar';ph=hashlib.sha256(packet.read_bytes()).hexdigest();assert ph=='2fc0226b08f6e255bd4903edabee714ca60bb91a311d9b4b31f92c94141cda5b'
code='import pathlib,sys,tarfile,io,hashlib,json\nd=pathlib.Path(sys.argv[1])/"tools"\nb=sys.stdin.buffer.read();assert hashlib.sha256(b).hexdigest()=="'+ph+'"\nd.mkdir()\nwith tarfile.open(fileobj=io.BytesIO(b)) as t:\n assert all(m.isfile() and not pathlib.PurePosixPath(m.name).is_absolute() and ".." not in pathlib.PurePosixPath(m.name).parts for m in t.getmembers())\n t.extractall(d,filter="data")\nprint(json.dumps({"tools_sha256":"'+ph+'","files":len(list(d.rglob("*")))}))\n'
r=subprocess.run(['ssh','-o','BatchMode=yes','cpu64','/usr/bin/python3 -I -B -c '+shlex.quote(code)+' '+shlex.quote(ns)],input=packet.read_bytes(),capture_output=True);assert r.returncode==0,r.stderr
(P/'dc-late68-tool-staging.json').write_bytes(r.stdout)
wrapper=P/'dc-late68-admitted-exec.py';wh=hashlib.sha256(wrapper.read_bytes()).hexdigest();boot='/tmp/dc-late68-admission-'+str(uuid.uuid4())+'.py'
r=subprocess.run(['ssh','-o','BatchMode=yes','cpu64',f'test ! -e {boot} && cat > {boot}'],input=wrapper.read_bytes(),capture_output=True);assert r.returncode==0,r.stderr
cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','cpu64',f'echo "{wh}  {boot}" | sha256sum -c - >&2 && taskset -c 62 /usr/bin/timeout --signal=TERM --kill-after=10s 1200s /usr/bin/python3 -I -B {boot} {ns}']
start={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'namespace':ns,'wrapper_sha256':wh,'tools_sha256':ph,'argv':cmd,'scope':'one68recordexistingoutput evaluator; not native execution/scientific acceptance'}
(P/'dc-late68-evaluation-start.json').write_text(json.dumps(start,indent=2)+'\n')
r=subprocess.run(cmd,capture_output=True,text=True,timeout=1250)
rec=dict(start,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(P/'dc-late68-evaluation-execution.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec,indent=2))
raise SystemExit(0 if r.returncode==0 else 1)
