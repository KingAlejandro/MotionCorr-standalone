import pathlib,json,subprocess,tarfile,hashlib,datetime
S=pathlib.Path(__file__).parent
idx=json.loads((S/'sealed/evidence/verified-file-index.json').read_text()); index={x['path']:x for x in idx}; paths=[]
for c in ['00021','00046']:
 for b in ['cpu','cuda']:
  paths.append(f'capture/{c}-G-{b}/capture/geometry.txt')
  paths += [f'capture/{c}-G-{b}/capture/peak-{a}.'+('f64' if b=='cpu' else 'f32') for a in ['x','y']]
  paths += [f'capture/{c}-G-{b}/capture/spectrum-{f}.c64' for f in [0,4]]
  if b=='cuda': paths += [f'capture/{c}-G-cuda/capture/{n}-{f}.{ext}' for f in [0,4] for n,ext in [('map','f32'),('ifft-input','c64')]]
  for route,names in [(f'{c}-inverse-{b}-cuda',['projected-spectrum-0.c64','projected-spectrum-4.c64','map-0.f32','map-4.f32']),(f'{c}-inverse-projected-{b}-cpu',['map-0.f32','map-4.f32']),(f'{c}-inverse-valid-{b}-cuda',['projected-spectrum-0.c64','projected-spectrum-4.c64','projection-noop.txt','map-0.f32','map-4.f32'])]:
   paths += [f'inverse-repair-v2/{route}/data/{n}' for n in names]
assert len(paths)==len(set(paths)); total=sum(index[p]['bytes'] for p in paths); assert total<250_000_000
(S/'fetch-list.txt').write_text('\n'.join(paths)+'\n'); print('FETCH',len(paths),total,flush=True)
argv=['ssh','-o','BatchMode=yes','4GPUs','tar','-c','-f','-','-C','/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026','-T','-']
with (S/'fetched.tar').open('xb') as out, (S/'fetch-stderr.txt').open('xb') as err:
 r=subprocess.run(argv,input=('\n'.join(paths)+'\n').encode(),stdout=out,stderr=err)
(S/'fetch-command.json').write_text(json.dumps({'argv':argv,'rc':r.returncode,'payload_bytes':total,'paths':paths,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)); assert r.returncode==0
with tarfile.open(S/'fetched.tar') as tf:
 assert set(tf.getnames())==set(paths)
 for m in tf.getmembers():
  assert m.isfile() and m.name in paths
  p=S/'data'/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tf.extractfile(m).read())
records=[]
for n in paths:
 p=S/'data'/n; d=p.read_bytes(); h=hashlib.sha256(d).hexdigest(); good=len(d)==index[n]['bytes'] and h==index[n]['sha256']; records.append({'path':n,'bytes':len(d),'sha256':h,'match':good}); assert good,n
(S/'fetch-hashes.json').write_text(json.dumps(records,indent=2));print('VERIFIED',len(records),total,flush=True)
