import pathlib,json,math,struct,csv
s=pathlib.Path('/tmp/mc-peakfit-records/runs');rows=json.load(open('/tmp/mc-rows-all.json'));out=[]
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def read(p):
 z={}
 for l in open(p):
  t=l.split()
  if t[0]!='cuda-global' or int(t[4])!=1:continue
  z[int(t[6])]={'pos':list(map(int,t[8:10])),'samples':[f32(float(v)) for v in t[27:32]],'candidate':list(map(float,t[33:35]))}
 return z
for r in rows:
 name='%s-p%d'%(r['movie'],r['grid']);a,b=read(s/(name+'-A0')/'ccf.txt'),read(s/(name+'-A1')/'ccf.txt')
 for f,x in a.items():
  y=b[f];assert x['samples']==y['samples'] and x['pos']==y['pos']
  out.append({'movie':r['movie'],'grid':r['grid'],'frame':f,'integer_position':x['pos'],'five_samples':x['samples'],'A0_candidate':x['candidate'],'A1_candidate':y['candidate'],'difference_px':math.hypot(*(x['candidate'][i]-y['candidate'][i] for i in [0,1]))})
json.dump(out,open('/tmp/mc-final-tables/first-global-candidates.json','w'),indent=1)
for bad in [False,True]:
 q=[r for r in out if (r['movie']=='e10216-01')==bad];print('known bad' if bad else 'other',len(q),'max',max(r['difference_px'] for r in q),'rms',math.sqrt(sum(r['difference_px']**2 for r in q)/len(q)));print(max(q,key=lambda r:r['difference_px']))
