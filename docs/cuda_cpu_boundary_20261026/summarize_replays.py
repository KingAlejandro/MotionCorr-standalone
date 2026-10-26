#!/usr/bin/env python3
import json,pathlib,numpy as np
import analysis_helpers as h
R=h.R;P=R/'replays'
def arr(p):return np.fromfile(p,dtype='<f4')
def compare(a,b):return h.stats(arr(a),arr(b))
def vectors(d):return {'rms':float(np.sqrt(np.mean(np.sum(d*d,axis=-1)))),'max_vector':float(np.max(np.sqrt(np.sum(d*d,axis=-1)))),'max_component':float(np.max(np.abs(d)))}
def peaks(d,g):return {f:h.peak(arr(d/f'map-{f}.f32').reshape(int(g['ccf_ny']),int(g['ccf_nx'])),g) for f in [0,4]}
def raw(d,b):return np.stack([np.fromfile(d/f'peak-{axis}.f64' if b=='cpu' else d/f'peak-{axis}.f32',dtype='<f8' if b=='cpu' else '<f4') for axis in ['x','y']],axis=-1)
def herm(p,g):return h.hermitian(np.fromfile(p,dtype='<c8').reshape(int(g['ccf_ny']),int(g['ccf_nx'])//2+1))
result={};controls={}
for case in ['00021','00046']:
 cap={b:R/'capture'/f'{case}-G-{b}'/'capture' for b in ['cpu','cuda']};g=h.geometry(cap['cpu']);z={'geometry':g,'self_reproduction':{},'same_state':{},'native_observations':{},'raw_map_peaks':{}}
 def out(name,b):return P/(case+'-'+name+'-'+b)/'data'
 for b in ['cpu','cuda']:
  selfcheck={}
  for f in [0,4]:selfcheck[f'forward-{f}']=compare(cap[b]/f'fft-{f}.c64',out('forward-'+b,b)/f'fft-{f}.c64')
  for name in ['reference.c64','weight.f32','spectrum-0.c64','spectrum-4.c64','map-0.f32','map-4.f32']:
   selfcheck['window-'+name]=compare(cap[b]/name,out('window-'+b,b)/name)
  for f in [0,4]:selfcheck[f'inverse-{f}']=compare(cap[b]/f'map-{f}.f32',out('inverse-'+b,b)/f'map-{f}.f32')
  if b=='cuda':
   for f in [0,4]:selfcheck[f'actual-projection-{f}']=compare(cap[b]/f'ifft-input-{f}.c64',out('inverse-'+b,b)/f'projected-spectrum-{f}.c64')
  z['self_reproduction'][b]=selfcheck
  for k,v in selfcheck.items():controls[f'{case}-{b}-{k}']=v['different_bits']==0
  z['raw_map_peaks'][b]=peaks(cap[b],g)
 c=raw(cap['cpu'],'cpu').astype(np.float64);vraw=raw(cap['cuda'],'cuda');v=vraw.astype(np.float64)
 assert c.shape==v.shape==(24,2) and np.isfinite(c).all() and np.isfinite(v).all()
 ca=c-c[0];va=v-v[0];native_va=(vraw-vraw[0]).astype(np.float64)
 z['native_observations']={'cpu_raw_px':c.tolist(),'cuda_raw_px':v.tolist(),'raw_cuda_minus_cpu_px':(v-c).tolist(),'raw_delta_vector_px':vectors(v-c),'anchor_adjusted_delta_px':(va-ca).tolist(),'anchor_adjusted_delta_vector_px':vectors(va-ca),'native_float_anchor_adjusted_delta_px':(native_va-ca).tolist(),'native_float_anchor_delta_vector_px':vectors(native_va-ca),'common_frame0_delta_px':(v[0]-c[0]).tolist(),'raw_map_recompute_minus_native_px':{b:{f:(np.array(z['raw_map_peaks'][b][f]['shift_px'])-(c if b=='cpu' else v)[f]).tolist() for f in [0,4]} for b in ['cpu','cuda']}}
 for stored in ['cpu','cuda']:
  base=out('window-'+stored,'cpu');gpu=out('window-'+stored,'cuda');raw_cpu=out('inverse-'+stored,'cpu');raw_gpu=out('inverse-'+stored,'cuda');valid_cpu=out('inverse-projected-'+stored,'cpu')
  ss={'window_ref':compare(base/'reference.c64',gpu/'reference.c64'),'window_weight':compare(base/'weight.f32',gpu/'weight.f32'),'window_peaks':{'cpu':peaks(base,g),'cuda':peaks(gpu,g)},'cross_raw_inverse_peaks':{'cpu':peaks(raw_cpu,g),'cuda':peaks(raw_gpu,g)},'projected_valid_inverse_peaks':{'cpu':peaks(valid_cpu,g),'cuda':peaks(raw_gpu,g)},'maps':{},'spectra':{},'Hermitian':{}}
  for f in [0,4]:
   ss['maps'][f]={'window_cpu_vs_cuda':compare(base/f'map-{f}.f32',gpu/f'map-{f}.f32'),'raw_compatibility_cpu_vs_cuda':compare(raw_cpu/f'map-{f}.f32',raw_gpu/f'map-{f}.f32'),'projected_valid_cpu_vs_cuda':compare(valid_cpu/f'map-{f}.f32',raw_gpu/f'map-{f}.f32'),'CPU_raw_vs_projected':compare(raw_cpu/f'map-{f}.f32',valid_cpu/f'map-{f}.f32')}
   ss['spectra'][f]={'window_cpu_vs_cuda':compare(base/f'spectrum-{f}.c64',gpu/f'spectrum-{f}.c64'),'native_raw_to_projection':compare(cap[stored]/f'spectrum-{f}.c64',raw_gpu/f'projected-spectrum-{f}.c64')}
   ss['Hermitian'][f]={'actual_raw':herm(cap[stored]/f'spectrum-{f}.c64',g),'projected_valid':herm(raw_gpu/f'projected-spectrum-{f}.c64',g)}
   controls[f'{case}-{stored}-projected-valid-{f}']=ss['Hermitian'][f]['projected_valid']['valid']
  z['same_state'][stored]=ss
 # Hold the downstream operator fixed while replacing only initial FFT-window input.
 z['forward_input_effect_at_fixed_operator']={b:{f:{'map':compare(out('window-cpu',b)/f'map-{f}.f32',out('window-cuda',b)/f'map-{f}.f32'),'peak_shift_delta_px':(np.array(peaks(out('window-cuda',b),g)[f]['shift_px'])-np.array(peaks(out('window-cpu',b),g)[f]['shift_px'])).tolist()} for f in [0,4]} for b in ['cpu','cuda']}
 result[case]=z
runs=[json.loads(p.read_text()) for p in P.glob('*/RUN.json')]
controls['all28-replay-exits-and-input-immutability']=len(runs)==28 and all(x['rc']==0 and x['input_unchanged'] for x in runs)
controls['all28-child-affinity']=all(x['child_affinities'] and all(t['mask']==list(range(80,88)) for t in x['child_affinities']) for x in runs)
o={'controls':controls,'all_controls_pass':all(controls.values()),'cases':result}
p=R/'replay-analysis.json';assert not p.exists();p.write_text(json.dumps(o,indent=2)+'\n');print('controls',sum(controls.values()),'/',len(controls),'PASS',o['all_controls_pass'])
for c,z in result.items():
 print(c,'native raw',z['native_observations']['raw_delta_vector_px'],'anchored',z['native_observations']['anchor_adjusted_delta_vector_px'],'frame0',z['native_observations']['common_frame0_delta_px'])
 print('self failures',{b:[k for k,v in d.items() if v['different_bits']] for b,d in z['self_reproduction'].items()})
 print('forwardinput',z['forward_input_effect_at_fixed_operator'])
 for stored,d in z['same_state'].items():print(stored,'crossraw peaks',d['cross_raw_inverse_peaks'],'valid peaks',d['projected_valid_inverse_peaks'])
