import pathlib,json,hashlib,tarfile,datetime
S=pathlib.Path(__file__).parent;E=S/'sealed/evidence';index={x['path']:x for x in json.loads((E/'verified-file-index.json').read_text())}
a=json.loads((E/'archive-binding.json').read_text());p=pathlib.Path(a['local_archive']);assert p.stat().st_size==a['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==a['sha256']
with tarfile.open(p) as tf:
 assert len(tf.getmembers())==473
 ledger=json.loads((E/'producer-ledger.json').read_text());assert len(ledger)==28
 for row in ledger:
  data=tf.extractfile(row['receipt']).read();assert hashlib.sha256(data).hexdigest()==row['receipt_sha256'];run=json.loads(data);assert run['rc']==row['rc']==0
 runnames=[n for n in tf.getnames() if n.startswith('replays/') and n.endswith('/RUN.json')];assert len(runnames)==28
 assert not any(n.startswith('endpoint-grades/') for n in tf.getnames())
first=[];neutral=[]
for case in ['00021','00046']:
 for f in [0,4]:
  def cap(b,n):return index[f'capture/{case}-G-{b}/capture/{n}']['sha256']
  first.append({'case':case,'frame':f,'pre_hashes_equal':cap('cpu',f'pre-{f}.f32')==cap('cuda',f'pre-{f}.f32'),'fft_hashes_differ':cap('cpu',f'fft-{f}.c64')!=cap('cuda',f'fft-{f}.c64'),'basis':'sealed index attestations only; arrays not downloaded'})
 for mode in ['G','L']:
  for backend in ['cpu','cuda']:
   suffix=f'{case}-{mode}-{backend}/out/Movies/20170629_{case}_frameImage'
   for ext in ['.mrc','.star']:
    base=index['baseline/'+suffix+ext]['sha256']; off=index['off/'+suffix+ext]['sha256']; offv2=index['off-v2/'+suffix+ext]['sha256']
    neutral.append({'label':f'{case}-{mode}-{backend}','extension':ext,'baseline_sha256':base,'off_sha256':off,'off_v2_sha256':offv2,'whole_file_equal':base==off==offv2,'basis':'whole-file hashes only; MRC payload equality is producer-reported and not inferred from these hashes'})
endpoints=[]
for run in json.loads((E/'endpoint-grades/RUN.json').read_text()):
 label=run['label'];grade=json.loads((E/f'endpoint-grades/{label}.json').read_text());assert run['rc']==1 and grade['overall_status']=='FAIL' and grade['coverage']['complete'] and grade['coverage']['required'];assert grade['tolerances']['image_relative_rmse']==.001
 assert grade['checks']['motion_trajectory']['passed'] and grade['checks']['star_fields']['passed']
 image=grade['checks']['corrected_image'];assert image['passed'] is False and len(image['fail_reasons'])==1 and image['relative_rmse']>.001
 endpoints.append({'label':label,'relative_image_rmse':image['relative_rmse'],'status':'FAIL','sole_failure':image['fail_reasons'],'coverage':grade['coverage'],'basis':'committed saved comparator scalar JSON/RUN audit; no pixel read or rerun'})
out={'archive':a,'ledger_receipt_hashes_verified':28,'original_replay_receipts':28,'v1_invalid_attempts_remain_invalid':8,'first_sampled_bit_boundary':first,'source_neutrality_index_audit':neutral,'endpoint_saved_grade_audit':endpoints,'endpoint_directory_absent_from_original_archive':True,'supplemental_archive_not_fetched_or_verified':True}
(S/'metadata-results-v2.json').write_text(json.dumps(out,indent=2)+'\n');print('metadata audits PASS; producer-only claims remain receipt/index attestations')
