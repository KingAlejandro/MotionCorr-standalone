import pathlib,json,math,struct
s=pathlib.Path('/mnt/clathrin/alex-motioncorr-peakfit');rows=json.load(open(s/'rows-all.json'));out=[]
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def mix(h):
 h&=0xffffffff;h^=h>>16;h=(h*0x85EBCA6B)&0xffffffff;h^=h>>13;h=(h*0xC2B2AE35)&0xffffffff;h^=h>>16;return h
for r in rows:
 for seed in [1,2]:
  d=s/'runs'/('%s-p%d-Nnative%d'%(r['movie'],r['grid'],seed));q={'movie':r['movie'],'grid':r['grid'],'seed':seed,'records':0,'output_replay_mismatch':0,'target_sum_square':0.,'actual_sum_square':0.,'dot_with_directed_correction':0.,'max_axis_magnitude_error_px':0.,'max_vector_magnitude_error_px':0.,'positive_signs':0,'negative_signs':0}
  for l in open(d/'null-dose.txt'):
   t=l.split();p,it,fr=map(int,t[:3]);x,y,bx,by,nx,ny=map(float,t[3:]);h=mix(mix(mix(seed ^ ((p+2)&0xffffffff)) ^ it) ^ fr)
   ax,ay=f32(abs(bx-x)),f32(abs(by-y));sx=1 if h&1 else -1;sy=1 if h&2 else -1
   ex,ey=f32(x+sx*ax),f32(y+sy*ay)
   q['records']+=1;q['output_replay_mismatch']+=ex!=nx or ey!=ny
   target=math.hypot(ax,ay);actual=math.hypot(nx-x,ny-y)
   q['target_sum_square']+=target*target;q['actual_sum_square']+=actual*actual;q['dot_with_directed_correction']+=(nx-x)*(bx-x)+(ny-y)*(by-y)
   q['max_axis_magnitude_error_px']=max(q['max_axis_magnitude_error_px'],abs(abs(nx-x)-ax),abs(abs(ny-y)-ay));q['max_vector_magnitude_error_px']=max(q['max_vector_magnitude_error_px'],abs(actual-target))
   for sign,amplitude in [(sx,ax),(sy,ay)]:
    if amplitude:q['positive_signs' if sign>0 else 'negative_signs']+=1
  q['rms_ratio_actual_to_target']=math.sqrt(q['actual_sum_square']/q['target_sum_square']) if q['target_sum_square'] else None
  den=math.sqrt(q['actual_sum_square']*q['target_sum_square']);q['cosine_with_directed_correction']=q['dot_with_directed_correction']/den if den else None
  assert q['output_replay_mismatch']==0,q
  out.append(q)
json.dump(out,open(s/'null-validation.json','w'),indent=1)
print('null configs',len(out),'records',sum(q['records'] for q in out),'max_axis_error',max(q['max_axis_magnitude_error_px'] for q in out),'RMSratio range',min(q['rms_ratio_actual_to_target'] for q in out),max(q['rms_ratio_actual_to_target'] for q in out))
