"""Versioned direct CPU64 pull, after preserving the stopped relay; no evaluator."""
import pathlib,subprocess,hashlib,json,datetime,uuid,shlex
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
col=json.loads((P/'dc-late68-collection-result.json').read_text());assert col['exit']==0
stop=json.loads((P/'dc-late68-relay-stop.json').read_text());assert stop['exit']==0
prod=P/'dc-late68-direct-producer.py';recv=P/'stage-dc-late68-receiver.py'
ph=hashlib.sha256(prod.read_bytes()).hexdigest();rh=hashlib.sha256(recv.read_bytes()).hexdigest()
assert ph=='5bd170de3c1dfaa768a68b3ab3e03057d83349cdc0f24b29a639e646b4bdff30'
assert rh=='dc7e1ef779cb0d677b859bfc2c8fa22fcef8c49d00390d93ec914e7852934e91'
u=str(uuid.uuid4());ns='/tmp/motioncorr-dc-late68-direct-v2-20261025-'+u;pb='/tmp/dc-late68-producer-'+u+'.py';rb='/tmp/dc-late68-direct-receiver-'+u+'.py'
for host,path,f in [('4GPUs',pb,prod),('cpu64',rb,recv)]:
 r=subprocess.run(['ssh','-o','BatchMode=yes',host,f'test ! -e {path} && cat > {path}'],input=f.read_bytes(),capture_output=True);assert r.returncode==0,r.stderr
source=f'echo "{ph}  {pb}" | sha256sum -c - >&2 && taskset -c 8-9 /usr/bin/python3 -I -B {pb}'
pipeline='set -euo pipefail; '+f'echo "{rh}  {rb}" | sha256sum -c - >&2; '+'ssh -o BatchMode=yes -o ConnectTimeout=10 alex@130.246.80.58 '+shlex.quote(source)+' | '+f'taskset -c 62 /usr/bin/python3 -I -B {rb} {ns} {col["archive_sha256"]}'
cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','cpu64','bash -c '+shlex.quote(pipeline)]
start={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'direct current authenticated CPU64->4GPU data pull; no evaluator/native','namespace':ns,'receiver_sha256':rh,'producer_sha256':ph,'archive_sha256':col['archive_sha256'],'argv':cmd,'prior_partial_relay':'retained immutable with explicit owned-receiver stop receipt','auth':'existing configured forwarded-agent SSH succeeded; no keys/trust/gateway changed'}
(P/'dc-late68-direct-stage-start.json').write_text(json.dumps(start,indent=2)+'\n')
r=subprocess.run(cmd,capture_output=True,text=True,timeout=1200)
x=dict(start,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(P/'dc-late68-direct-stage-result.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2));raise SystemExit(0 if r.returncode==0 else 1)
