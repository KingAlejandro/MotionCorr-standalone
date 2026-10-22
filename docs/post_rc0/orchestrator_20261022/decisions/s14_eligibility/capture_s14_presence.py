# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only presence/byte-size probe; no raw payload/hash/decode or endpoint access."""
import hashlib,json,pathlib,subprocess,datetime
P=pathlib.Path(__file__).parent;f=P/'s14-sweep-manifest-snapshot.json';m=json.loads(f.read_text())
paths=set()
for r in m['movies']:
 paths.add(r['movie_source']);paths.add('/mnt/clathrin/alex-motioncorr-s1/sweep/inputs/'+r['id']+'/movies.star')
 if r.get('gain_source'):paths.add(r['gain_source'])
assert all('\x00' not in p and '\n' not in p and '\t' not in p and p.startswith(('/mnt/clathrin/','/home/alex/')) for p in paths)
cmd=['ssh','-J','ccp4-gateway','-oBatchMode=yes','-oConnectTimeout=10','-oConnectionAttempts=1','4GPUs',"xargs -0 stat -L --printf='%n\\t%s\\t%F\\n' --"]
r=subprocess.run(cmd,input=b''.join(p.encode()+b'\x00' for p in sorted(paths)),capture_output=True,timeout=25)
(P/'s14-presence.stdout').write_bytes(r.stdout);(P/'s14-presence.stderr').write_bytes(r.stderr)
rows={}
for line in r.stdout.decode().splitlines():
 p,size,kind=line.split('\t',2);rows[p]={'bytes':int(size),'kind':kind}
assert set(rows)<=paths
out={'kind':'fresh metadata-only filesystem stat; no raw-integrity or scientific claim','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifest_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'command':cmd,'exit':r.returncode,'requested':len(paths),'observed':len(rows),'missing':sorted(paths-set(rows)),'rows':rows,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest(),'raw_payload_rehashed':False,'new_download':False,'image_decode':False,'scientific_endpoint_access':False};(P/'s14-presence.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['utc','exit','requested','observed','missing']},indent=2))
