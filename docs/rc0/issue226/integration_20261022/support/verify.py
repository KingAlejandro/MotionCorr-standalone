"""Read-only verification of every retained integration archive member and gate."""
import hashlib,json,tarfile
from pathlib import Path
import xml.etree.ElementTree as ET
D=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((D/'raw-logs.tgz').read_bytes())==(D/'archive.sha256').read_text().split()[0]
index=json.loads((D/'raw-index.json').read_text())
record=json.loads((D/'integration.json').read_text())
with tarfile.open(D/'raw-logs.tgz') as tf:
    members=tf.getmembers()
    assert len(members)==len(index['files'])==len({m.name for m in members})
    assert {m.name for m in members}=={r['path'] for r in index['files']}
    def data(name):return tf.extractfile(name).read()
    for r in index['files']:
        p=Path(r['path']);b=data(r['path'])
        assert tf.getmember(r['path']).isfile() and not p.is_absolute() and '..' not in p.parts
        assert len(b)==r['bytes'] and sha(b)==r['sha256']
        assert p.suffix not in ('.mrc','.mrcs','.pdf','.pyc')
    assert json.loads(data('integration.json'))==record
    for phase in ('configure','compile','host-controls','collection-control','complete-build','compile-remaining','collection-validation-final','missing-controls','local-admission','early-oom','plan-matrix','native','products','production-source-final','released-gpu3-correctness','released-build','released-bench'):
        assert int(data('logs/'+phase+'.exit'))==0,phase
    assert int(data('logs/collection-validation.exit'))==1
    initial=json.loads(data('logs/collection-validation.json'))
    assert initial['status']=='FAIL' and initial['unrunnable_tests']
    collection=json.loads(data('logs/collection-validation-final.json'))
    assert collection['status']=='PASS' and collection['collected_count']==115
    controls=('CudaLocalAdmission','CudaEarlyStreamingOom','CudaStreamingPlanClassificationCleanup')
    assert set(controls)<=set(collection['required_tests'])
    for r in json.loads(data('logs/missing-controls.json')):
        assert r['exit']==1 and 'Missing required test(s): '+r['dropped'] in r['stdout']
        assert r['count']==115
    local=data('logs/local-admission.log').decode()
    assert local.count('BOUNDARY free=')==28
    assert 'spectrum=158299360 complete_required=191819184' in local
    assert 'REVIEW free=175000000 admitted=0' in local
    production=data('logs/production-source-final.log').decode().splitlines()
    assert len(production)==266 and all(l.endswith(': OK') for l in production)
    def binaries(name):
        return {Path(line.split(None,1)[1]).name:line.split()[0]
                for line in data(name).decode().splitlines()}
    assert binaries('logs/binaries.sha256')==binaries('logs/binaries-final.log')
    grades=json.loads(data('matrix/grades.json'))
    assert len(grades)==16 and all(not r['problems'] for r in grades)
    receipts=[json.loads(data(m.name)) for m in members if m.name.startswith(('matrix/','early/')) and m.name.endswith('.json')]
    receipts=[r for r in receipts if 'binary_sha256' in r]
    assert len(receipts)==19 and all(r['affinity']==[10,11,12,13] for r in receipts)
    assert all(r['cuda_visible_devices']==record['gpu_uuid'] for r in receipts)
    for r in record['products']:
        assert r['exit']==0 and not r['timed_out'] and r['all_products'] and r['joint_star']
        assert r['balloon_gone'] and not r['gpu_apps_after']
        if r['target_free_gib'] is None:continue
        prefix='runs/'+r['spec']+'/'
        prod=json.loads(data(prefix+'identity-products.json'));strict=json.loads(data(prefix+'identity-strict.json'))
        assert r['compare']['products_rc']==0 and prod['status']=='PASS' and not prod['different_products']
        assert r['compare']['strict_rc']==1 and strict['status']=='FAIL'
        assert len(strict['different_files'])==1 and strict['different_files'][0].endswith('.log')
        for arm in ('base','candidate'):
            assert prod[arm]['mrc_count']==1 and prod[arm]['star_count']==2 and prod[arm]['pixel_count']==16777216
        for hashes in prod['mrc_sha256'].values():
            for part in ('header','extended','payload'):assert hashes['base_'+part]==hashes['candidate_'+part]
    health=[json.loads(l) for l in data('logs/health.jsonl').splitlines()]
    assert len(health)==record['health_sample_count']
    for h in health:
        assert h['uuid']==record['gpu_uuid'] and h['recovery_action']=='None'
        assert all(v=='0' for k in ('volatile_ecc','aggregate_ecc') for v in h[k].values())
        assert h['remapped']=={'remapped_row_corr':'0','remapped_row_unc':'0','remapped_row_pending':'No','remapped_row_failure':'No'}
    xml_members=[m for m in members if m.name.startswith('logs/health-') and m.name.endswith('.xml')]
    assert len(xml_members)==len(health)
    for m in xml_members:
        gpu=ET.fromstring(data(m.name)).find('gpu')
        assert gpu.findtext('uuid')==record['gpu_uuid']
        assert gpu.findtext('gpu_recovery_action')=='None'
        for section in ('ecc_errors','retired_pages'):
            for leaf in gpu.find(section).iter():
                value=(leaf.text or '').strip()
                if len(leaf)==0 and value.isdigit():assert int(value)==0,(m.name,leaf.tag,value)
        for field in ('pending_blacklist','pending_retirement'):
            assert gpu.findtext('retired_pages/'+field) in ('No','N/A')
        assert gpu.findtext('remapped_rows/remapped_row_corr')=='0'
        assert gpu.findtext('remapped_rows/remapped_row_unc')=='0'
        assert gpu.findtext('remapped_rows/remapped_row_pending')=='No'
        assert gpu.findtext('remapped_rows/remapped_row_failure')=='No'
    owned=[json.loads(l) for l in data('logs/owned-processes.jsonl').splitlines()]
    reaped=[r for r in owned if 'reaped_pid' in r]
    assert len(reaped)==3 and all(r['exit']==-15 for r in reaped)
    post=record['post_health'];assert post['apps']==[] and post['util']=='0 %' and post['memory_used']=='1 MiB'
print(json.dumps(dict(status='PASS',archive_files_verified=len(members),production_files_verified=266,native_boundaries=28,D3_matrix_rows=16,strict_product_comparisons=3,expected_log_only_tree_failures=3,health_samples_verified=len(health),process_counts=record['process_counts']),indent=2))
