"""Read-only publication/identity/resource summaries, no producer or scientific refit."""
import hashlib,json,re,os,sys
from pathlib import Path
ROOT=Path('/tmp/motioncorr-b2-native-20261026');E=ROOT/'evidence'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(p.read_text())
pins=load(ROOT/'h7_payload_pins.json');inputs=load(ROOT/'input_pins.json');rows=[];timing=[]
for name in ('dose1-s01','dose05-s00','dose4-s00','pedestal32-s00'):
 inp=load(E/(name+'-input.json'));assert inp['movie_sha256']==inputs[name]['receipt']['files']['movie.mrcs']
 order=('OFF1','ON1','ON2','OFF2','OFF_AA1','OFF_AA2','OFF_AA3','OFF_AA4') if name=='dose1-s01' else ('OFF1','ON1')
 baseline=None;onfirst=None;per=[]
 for label in order:
  d=E/'pilot'/name/label;rr=load(d/'RUN.json');rt=load(d/'runtime.json');m=load(d/'metrics.json');admit=load(d/'admission.json');assert rr['exit']==0
  expected={'movie.mrc','movie.star','movie.log','corrected_micrographs.star'};actual={p.name for p in (d/'output').iterdir() if p.is_file()};assert expected<=actual
  payload=sha((d/'output/movie.mrc').read_bytes()[1024:]);star=(d/'output/movie.star').read_bytes();text=star.decode();obs=text.split('data_local_shift',1)[1] if 'data_local_shift' in text else ''
  if baseline is None:
   baseline=(rt,star,payload,obs);assert payload==pins[name];assert star==(ROOT/'h7_inputs'/name/'movie.star').read_bytes();assert rt==load(ROOT/'h7_inputs'/name/'runtime.json')
  if label.startswith('OFF'):assert (rt,star,payload,obs)==baseline
  else:
   assert rt['global']==baseline[0]['global'];assert obs==baseline[3]
   if onfirst is None:onfirst=(rt,star,payload)
   else:assert (rt,star,payload)==onfirst
  assert admit['affinity']==list(range(32,48));assert '/tmp/motioncorr-cpu64-bench.lock' in admit['acquired_locks'];assert admit['scratch_bytes']<=25*1024**3
  assert rr['threads']==8;assert rr['binary_sha256']=='531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb'
  conv=m['convergence'];patch=conv['patches'];aa=m['serialized_field']['angstrom'];sg='PASS' if all(aa[k]<=v for k,v in [('rms',.20),('p95',.40),('max',.80)]) else 'FAIL'
  time=(d/'time.txt').read_text();rss=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',time)[1]);fit=re.findall(r'Polynomial fit RMSD:.*',(d/'output/movie.log').read_text())
  row=dict(movie=name,label=label,exit=rr['exit'],publication_files=sorted(actual),binary_sha256=rr['binary_sha256'],seconds=rr['whole_job_seconds'],peak_RSS_KiB=rss,requested_OpenMP_threads=8,affinity=admit['affinity'],scratch_bytes_before=admit['scratch_bytes'],local_enabled=rt['local_enabled'],global_converged=conv['global_converged'],patches_attempted=len(patch),patches_converged=sum(p['converged'] is True for p in patch),patches_rejected=sum(p['converged'] is False for p in patch),patches_ambiguous=sum(p['converged'] is None for p in patch),fit_RMS_logged=fit,fit_RMS_estimand='nuisance-adjusted observation residual' if label.startswith('ON') else 'inherited observation residual',runtime=m['field']['angstrom'],runtime_gate=m['field_distance_status'],STAR=aa,STAR_gate=sg,STAR_roundtrip=m['star_roundtrip_loss'],sampling=m['sampling_status'],payload_sha256=payload,case_STAR_sha256=sha(star),observation_block_sha256=sha(obs.encode()),global_sha256=sha(json.dumps(rt['global'],separators=(',',':')).encode()))
  per.append(row);timing.append(row)
 rows.append(dict(movie=name,input_sha256=inp['movie_sha256'],receipt_sha256=sha((E/(name+'-RECEIPT.json')).read_bytes()),OFF_payload_matches_pinned_H7=True,baseline_repeats_exact=True,ON_repeats_exact=True,all_upstream_obs_globals_exact=True,runs=per))
assert len(timing)==14
s={r['label']:r['seconds'] for r in timing if r['movie']=='dose1-s01'}
ratios=dict(AB_ON1_over_OFF1=s['ON1']/s['OFF1'],BA_ON2_over_OFF2=s['ON2']/s['OFF2'],mean_ON_over_mean_OFF=(s['ON1']+s['ON2'])/(s['OFF1']+s['OFF2']),AA1_OFF_AA2_over_OFF_AA1=s['OFF_AA2']/s['OFF_AA1'],AA2_OFF_AA4_over_OFF_AA3=s['OFF_AA4']/s['OFF_AA3'])
(E/'verification-summary.json').write_text(json.dumps(dict(status='PASS_IDENTITY_PUBLICATION_ONLY',native_producers=14,source_production_review_commit='326f03a073aec0d26c9cd585ce4f701d1c808245',binary_sha256=timing[0]['binary_sha256'],movies=rows,dose1_descriptive_ratios=ratios,timing_claim='Descriptive samples only; no stable speedup. Per-run preflight; late live observer does not cover dose1 paired/AA samples.',full100='UNRUN',full_CPU_qualification='UNRUN',GPU_native='UNRUN',candidate_promotion='BLOCKED_K267_NOISY_HARM'),indent=2)+'\n')
print(json.dumps(dict(status='PASS_IDENTITY_PUBLICATION_ONLY',native_producers=14,descriptive_ratios=ratios),indent=2))
