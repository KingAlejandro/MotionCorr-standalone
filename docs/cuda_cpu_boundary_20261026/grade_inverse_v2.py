#!/usr/bin/env python3
import json,numpy as np
import analysis_helpers as h
R=h.R;P=R/'inverse-repair-v2';old=R/'replays';checks={};cases={}
def cmp(a,b):return h.stats(np.fromfile(a,dtype='<f4'),np.fromfile(b,dtype='<f4'))
def peaks(d,g):return {f:h.peak(np.fromfile(d/f'map-{f}.f32',dtype='<f4').reshape(int(g['ccf_ny']),int(g['ccf_nx'])),g) for f in [0,4]}
for case in ['00021','00046']:
 cases[case]={}
 for stored in ['cpu','cuda']:
  cap=R/'capture'/f'{case}-G-{stored}/capture';g=h.geometry(cap)
  compat=P/f'{case}-inverse-{stored}-cuda/data';validcpu=P/f'{case}-inverse-projected-{stored}-cpu/data';validcuda=P/f'{case}-inverse-valid-{stored}-cuda/data';common=P/f'{case}-common-projected-{stored}'
  rawcpu=old/f'{case}-inverse-{stored}-cpu/data'
  label=f'{case}-{stored}';checks[label+'-projection-noop-marker']=(validcuda/'projection-noop.txt').read_text()=='PASS\n'
  z={'raw_actual_input_is_Hermitian':{},'projected_validity':{},'same_valid_input_sha256':{},'maps':{},'raw_compatibility_peaks':{'CPU_actual_raw':peaks(rawcpu,g),'CUDA_projection_plus_C2R':peaks(compat,g)},'projected_valid_peaks':{'CPU':peaks(validcpu,g),'CUDA_byte_noop_projection_then_C2R':peaks(validcuda,g)}}
  for f in [0,4]:
   raw=np.fromfile(cap/f'spectrum-{f}.c64',dtype='<c8').reshape(int(g['ccf_ny']),int(g['ccf_nx'])//2+1);proj=np.fromfile(common/f'spectrum-{f}.c64',dtype='<c8').reshape(raw.shape)
   z['raw_actual_input_is_Hermitian'][f]=h.hermitian(raw);z['projected_validity'][f]=h.hermitian(proj)
   same=h.sha(common/f'spectrum-{f}.c64');z['same_valid_input_sha256'][f]=same
   checks[f'{label}-{f}-valid']=z['projected_validity'][f]['valid']
   checks[f'{label}-{f}-byteidentical-valid-input']=same==h.sha(validcuda/f'projected-spectrum-{f}.c64')
   z['maps'][f]={'raw_compatibility':cmp(rawcpu/f'map-{f}.f32',compat/f'map-{f}.f32'),'same_valid_input_inverse':cmp(validcpu/f'map-{f}.f32',validcuda/f'map-{f}.f32'),'rawCUDA_vs_validCUDA':cmp(compat/f'map-{f}.f32',validcuda/f'map-{f}.f32'),'original_v1_selected_map_vs_v2':cmp(old/f'{case}-inverse-{stored}-cuda/data/map-{f}.f32',compat/f'map-{f}.f32')}
   checks[f'{label}-{f}-same-consumed-transform']=z['maps'][f]['rawCUDA_vs_validCUDA']['different_bits']==0
   if stored=='cuda':
    z['maps'][f]['native_capture_vs_v2']=cmp(cap/f'map-{f}.f32',compat/f'map-{f}.f32')
    checks[f'{label}-{f}-native-capture-selfreproduction']=z['maps'][f]['native_capture_vs_v2']['different_bits']==0
    checks[f'{label}-{f}-native-actual-IFFT-input']=h.sha(cap/f'ifft-input-{f}.c64')==same
  cases[case][stored]=z
runs=[json.loads(p.read_text()) for p in P.glob('*/RUN.json')];checks['12-inverse-only-exits-and-input-unchanged']=len(runs)==12 and all(x['rc']==0 and x['input_unchanged'] for x in runs)
checks['12-child-affinity']=all(x['child_affinities'] and all(t['mask']==list(range(80,88)) for t in x['child_affinities']) for x in runs)
checks['12-fresh-admission']=all(json.loads(p.read_text())['admitted'] for p in P.glob('*/ADMISSION.json'))
o={'source_fix':'031f333a2863218c74951117989c84423ad9c92e','old_v1_inverse_status':'INVALID complete-batch provenance; original4CUDA+4projectedCPU attempts retained, not promoted','new_inverse_processes':12,'controls':checks,'all_controls_pass':all(checks.values()),'cases':cases};p=R/'inverse-v2-analysis.json';assert not p.exists();p.write_text(json.dumps(o,indent=2)+'\n');print('controls',sum(checks.values()),'/',len(checks),o['all_controls_pass'])
for case,z in cases.items():
 for stored,v in z.items():print(case,stored,'validpeaks',v['projected_valid_peaks'],'maps',v['maps'])
