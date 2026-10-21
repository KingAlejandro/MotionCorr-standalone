import pathlib,json,struct,hashlib,math,tarfile
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');rows=json.load(open(s/'configuration-witnesses.json'));o=s/'first-map-frames';o.mkdir(exist_ok=True);results=[];missing=[]
def locate(d,tag,p,it):
 iy,ix=map(int,p.split(','));items=[]
 if not (d/'maps/index.txt').exists():return None
 for l in (d/'maps/index.txt').read_text().splitlines():
  t=l.split();name,tg,y,x,c,k,kind,nf,ny,nx=t
  if tg==tag and int(y)==iy and int(x)==ix and int(k)==it and kind=='map':items.append((int(c),pathlib.Path(name),int(nf),int(ny),int(nx)))
 return min(items) if items else None
def frame(entry,f,name):
 c,p,nf,ny,nx=entry;assert 1<=f<=nf
 with p.open('rb') as fh:fh.seek((f-1)*nx*ny*4);data=fh.read(nx*ny*4)
 assert len(data)==nx*ny*4
 (o/name).write_bytes(data)
 return struct.unpack('<%df'%(nx*ny),data),ny,nx,hashlib.sha256(data).hexdigest()
def at(v,nx,ny,xy):return v[(xy[1]%ny)*nx+(xy[0]%nx)]
def ulp(v):
 e=(struct.unpack('<I',struct.pack('<f',abs(v)))[0]>>23)&255
 return 2.**(e-127-23) if e else 2.**-149
for r in rows:
 if r['kind']!='different integer peak':continue
 mv,pg,arm=r['case'].rsplit('-',2);g=int(pg[1:]);c=s/'runs'/('%s-p%d-map-cpu'%(mv,g));d=s/'runs'/('%s-p%d-map-%s'%(mv,g,arm))
 ce=locate(c,'cpu',r['patch'],r['iteration']);ge=locate(d,r['cuda_tag'],r['patch'],r['iteration'])
 if ce is None or ge is None:missing.append(r);continue
 a,ny,nx,ha=frame(ce,r['frame'],r['case']+'-cpu.f32');b,gy,gx,hb=frame(ge,r['frame'],r['case']+'-cuda.f32');assert (ny,nx)==(gy,gx)
 cp,gp=r['cpu_position'],r['cuda_position'];cm,gm=at(a,nx,ny,cp),at(b,nx,ny,gp)
 def five(v,p):
  x,y=p;return [at(v,nx,ny,z) for z in [(x,y),(x+1,y),(x-1,y),(x,y+1),(x,y-1)]]
 assert five(a,cp)==r['cpu_five_samples'],(r['case'],'CPU samples changed')
 assert five(b,gp)==r['cuda_five_samples'],(r['case'],'CUDA samples changed')
 mc=cm-at(a,nx,ny,gp);mg=gm-at(b,nx,ny,cp)
 # A constant difference cannot change the ordering of the two peak samples.
 am,bm=sum(a)/len(a),sum(b)/len(b);err=math.sqrt(sum(((y-bm)-(x-am))**2 for x,y in zip(a,b))/len(a));std=math.sqrt(sum((x-am)**2 for x in a)/len(a))
 q={**r,'margin_evidence':'native full-frame CCF map','cpu_margin':mc,'cuda_margin':mg,'cpu_margin_ulps':mc/ulp(cm),'cuda_margin_ulps':mg/ulp(gm),'map_dimensions':[ny,nx],'cpu_map_sha256':ha,'cuda_map_sha256':hb,'after_mean_removal_relative_rms_map_difference':err/std if std else None,'cpu_map_parent_identity':json.load(open(c/'identity-parent.json'))['identical'],'cuda_map_parent_identity':json.load(open(d/'identity-parent.json'))['identical']}
 assert q['cpu_map_parent_identity'] and q['cuda_map_parent_identity']
 results.append(q)
json.dump(results,open(s/'first-map-margins.json','w'),indent=1);json.dump(missing,open(s/'missing-witness-maps.json','w'),indent=1)
with tarfile.open(s/'first-map-frames.tar.gz','w:gz') as t:
 for p in sorted(o.iterdir()):t.add(p,arcname=p.name)
print('map witnesses',len(results),'missing',len(missing));print([(r['case'],r['patch']) for r in missing])
