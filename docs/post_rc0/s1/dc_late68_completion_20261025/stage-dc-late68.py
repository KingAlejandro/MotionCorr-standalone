import pathlib,subprocess,hashlib,json,datetime,uuid
P=pathlib.Path('/tmp/motioncorr-20261025-parent')
col=json.loads((P/'dc-late68-collection-result.json').read_text())
assert col['exit']==0 and 'COLLECTED_ALL_EXPECTED_HASHES_MATCH' in col['stderr']
archive=pathlib.Path(col['archive']);runner=P/'stage-dc-late68-receiver.py'
rh=hashlib.sha256(runner.read_bytes()).hexdigest();assert rh=='dc7e1ef779cb0d677b859bfc2c8fa22fcef8c49d00390d93ec914e7852934e91'
assert archive.stat().st_size==col['archive_bytes']
u=str(uuid.uuid4());ns='/tmp/motioncorr-dc-late68-stage-20261025-'+u;boot='/tmp/motioncorr-dc-late68-receiver-'+u+'.py'
r=subprocess.run(['ssh','-o','BatchMode=yes','cpu64',f'test ! -e {boot} && cat > {boot}'],input=runner.read_bytes(),capture_output=True);assert r.returncode==0,r.stderr
cmd=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','cpu64',f'echo "{rh}  {boot}" | sha256sum -c - >&2 && taskset -c 62 /usr/bin/python3 -I -B {boot} {ns} {col["archive_sha256"]}']
start={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'byte staging only, no evaluator/native','namespace':ns,'receiver_sha256':rh,'archive_sha256':col['archive_sha256'],'argv':cmd}
(P/'dc-late68-stage-start.json').write_text(json.dumps(start,indent=2)+'\n')
with archive.open('rb') as f:r=subprocess.run(cmd,stdin=f,capture_output=True,timeout=1200)
x=dict(start,exit=r.returncode,stdout=r.stdout.decode(),stderr=r.stderr.decode(),end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(P/'dc-late68-stage-result.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
raise SystemExit(0 if r.returncode==0 else 1)
