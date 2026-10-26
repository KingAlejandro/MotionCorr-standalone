"""Read-only integrity and consistency checks for the retained native receipts."""
import hashlib, json, tarfile
from pathlib import Path
D=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
expected=(D/'archive.sha256').read_text().split()[0]
assert sha((D/'raw-logs.tgz').read_bytes())==expected
index=json.loads((D/'raw-index.json').read_text())
native=json.loads((D/'native.json').read_text())
with tarfile.open(D/'raw-logs.tgz') as tf:
    members=tf.getmembers()
    assert len(members)==len(index['files'])==len({m.name for m in members})
    assert {m.name for m in members}=={r['path'] for r in index['files']}
    def data(name):return tf.extractfile(name).read()
    for row in index['files']:
        m=tf.getmember(row['path']); b=data(row['path'])
        assert m.isfile() and not row['path'].startswith('/') and '..' not in Path(row['path']).parts
        assert len(b)==row['bytes'] and sha(b)==row['sha256']
        assert Path(row['path']).suffix not in ('.mrc','.pdf','.pyc')
    assert json.loads(data('native.json'))==native
    for name in ('configure','compile','host-controls','native','native-original','mutant-compile',
                 'restored-compile','native-restored','products','production-source-final',
                 'released-gpu3-correctness','released-build','released-bench'):
        assert int(data('logs/'+name+'.exit'))==0,name
    assert int(data('logs/native-omission-mutant.exit'))==1
    assert b'FAIL: incorrect complete retry admission boundary' in data('logs/native-omission-mutant.log')
    positive=data('logs/native-restored.log').decode()
    assert positive.count('BOUNDARY free=')==28
    assert 'REVIEW free=175000000 admitted=0' in positive
    assert 'spectrum=158299360 complete_required=191819184' in positive
    assert 'PASS: local workspace boundary 6135264 bytes' in positive
    source_checks=data('logs/production-source-final.log').decode().splitlines()
    assert len(source_checks)==266 and all(l.endswith(': OK') for l in source_checks)
    assert [r['spec'] for r in native['products']]==['e10216-L-auto@'+x for x in ('none','8','8.5','8.75')]
    for r in native['products']:
        assert r['exit']==0 and not r['timed_out'] and r['all_products'] and r['joint_star']
        assert r['balloon_gone'] and not r['gpu_apps_after'] and r['gpu_used_after_mib']==1
        if r['target_free_gib'] is None:continue
        prefix='runs/'+r['spec']+'/'
        product=json.loads(data(prefix+'identity-products.json'))
        strict=json.loads(data(prefix+'identity-strict.json'))
        assert r['compare']['products_rc']==0 and product['status']=='PASS' and not product['different_products']
        assert r['compare']['strict_rc']==1 and strict['status']=='FAIL'
        assert len(strict['different_files'])==1 and strict['different_files'][0].endswith('.log')
        for arm in ('base','candidate'):
            assert product[arm]['mrc_count']==1 and product[arm]['star_count']==2
            assert product[arm]['pixel_count']==16777216
        for hashes in product['mrc_sha256'].values():
            for part in ('header','extended','payload'):
                assert hashes['base_'+part]==hashes['candidate_'+part]
    health=[json.loads(l) for l in data('logs/health.jsonl').splitlines()]
    assert len(health)==native['health_sample_count']==198
    for h in health:
        assert h['uuid']==native['gpu_uuid']
        assert all(v=='0' for k in ('volatile_ecc','aggregate_ecc') for v in h[k].values())
        assert h['remapped']=={'remapped_row_corr':'0','remapped_row_unc':'0','remapped_row_pending':'No','remapped_row_failure':'No'}
    assert native['post_health']['apps']==[] and native['post_health']['util']=='0 %'
    assert native['post_health']['memory_used']=='1 MiB'
print(json.dumps({'status':'PASS','archive_files_verified':len(members),'production_files_verified':266,
                  'native_retry_boundaries':28,'review_interval_declined':True,'omission_mutant_rejected':True,
                  'strict_product_comparisons':3,'expected_log_only_tree_failures':3,
                  'health_samples_verified':len(health)},indent=2))
