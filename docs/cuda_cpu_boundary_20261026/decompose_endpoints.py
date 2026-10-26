#!/usr/bin/env python3
"""Descriptive STAR observation/field ledger; not a causal fit or reconstruction test."""
import json,numpy as np
import analysis_helpers as h
R=h.R;o={}
for c in ['00021','00046']:
 a=h.read_motion_star(h.products('baseline',f'{c}-L-cpu',c)[1]);b=h.read_motion_star(h.products('baseline',f'{c}-L-cuda',c)[1])
 def rows(s):return {(int(r['rlnMicrographFrameNumber']),r['rlnCoordinateX'],r['rlnCoordinateY']):np.array([r['rlnMicrographShiftX'],r['rlnMicrographShiftY']]) for r in s.local_shifts}
 aa,bb=rows(a),rows(b);assert aa.keys()==bb.keys() and len(aa)==len(a.local_shifts)==len(b.local_shifts)==600
 delta=np.stack([bb[k]-aa[k] for k in sorted(aa)])
 x,y=np.meshgrid(np.linspace(.1*a.nx,.9*a.nx,17),np.linspace(.1*a.ny,.9*a.ny,17));ix=x.ravel();iy=y.ravel()
 local=b.local_field(a.frames,ix,iy)-a.local_field(a.frames,ix,iy);global_delta=np.stack([b.global_shift_x-a.global_shift_x,b.global_shift_y-a.global_shift_y],axis=-1);total=b.field(a.frames,ix,iy)-a.field(a.frames,ix,iy)
 def v(z):return {'vector_rms_px':float(np.sqrt(np.mean(np.sum(z*z,axis=-1)))),'max_vector_px':float(np.max(np.sqrt(np.sum(z*z,axis=-1))))}
 o[c]={'row_count':600,'matching_frame_center_keys':True,'accepted_patches_cpu':len({k[1:] for k in aa}),'accepted_patches_cuda':len({k[1:] for k in bb}),'observation_difference':v(delta),'STAR_global_difference':v(global_delta),'STAR_local_field_difference_17x17_10to90pct':v(local),'STAR_total_field_difference_17x17_10to90pct':v(total),'field_ledger_mean_squared_total':float(np.mean(np.sum(total*total,axis=-1))),'field_ledger_mean_squared_local':float(np.mean(np.sum(local*local,axis=-1))),'field_ledger_mean_squared_global':float(np.mean(np.sum(global_delta*global_delta,axis=-1))),'field_ledger_cross_term':float(2*np.mean(np.sum(local*global_delta[:,None,:],axis=-1))),'limits':'Printed STAR precision only. Different upstream global/observations; this is descriptive, not same-state fit attribution. Same-field applied reconstruction and fullprecision local capture UNRUN.'}
p=R/'endpoint-decomposition.json';assert not p.exists();p.write_text(json.dumps(o,indent=2)+'\n');print(json.dumps(o,indent=2))
