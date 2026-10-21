# Local-only analysis of #250-format records, including same-sample arithmetic.
import json,sys,math,struct,gzip
from pathlib import Path

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def parse(p):
 out={};op=gzip.open if str(p).endswith('.gz') else open
 for l in op(p,'rt'):
  t=l.split();key=(t[0],int(t[1]),int(t[2]),int(t[4]),int(t[6]));out[key]={'pos':tuple(map(int,t[8:10])),'sub':tuple(f32(float(x)) for x in t[27:32]),'cur':tuple(map(float,t[33:35])),'note':t[35]}
 return out

def compare(a,b):
 A,B=parse(a),parse(b);out={}
 for tag in sorted({k[0] for k in A}):
  keys=[k for k in A if k[0]==tag and k in B]
  if not keys:continue
  ds=[math.hypot(*(A[k]['cur'][i]-B[k]['cur'][i] for i in (0,1))) for k in keys]
  same=[d for d,k in zip(ds,keys) if A[k]['sub']==B[k]['sub'] and A[k]['pos']==B[k]['pos']]
  out[tag]={'common_frame_iterations':len(keys),'max_candidate_vector_delta_px':max(ds),'rms_candidate_vector_delta_px':math.sqrt(sum(d*d for d in ds)/len(ds)),'identical_five_samples_and_winner':len(same),'max_same_samples_candidate_delta_px':max(same,default=None),'integer_winner_changes':sum(A[k]['pos']!=B[k]['pos'] for k in keys)}
 return out
if __name__=='__main__':json.dump(compare(sys.argv[1],sys.argv[2]),sys.stdout,indent=1)
