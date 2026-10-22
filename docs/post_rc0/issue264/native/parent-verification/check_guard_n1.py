from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E,re,datetime
p=Path('/tmp/motioncorr-orchestrator-20261022');raw=p/'guard264-n1-raw-parent-readback.json';j=json.loads(raw.read_text());assert j['source_head']['stdout'].strip()=='0a1f64ab3e192c3ebad57b35149d872b21331730';assert j['source_status']['stdout']==''
report={'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source_head':j['source_head']['stdout'].strip(),'source_clean':True,'captured_utc':j['captured_utc'],'configs':{},'limitations':['N1 CTest/source/collection only; N2/N3/N4 remain incomplete.','Listed sets obtained from existing configured builds; not a historical frozen expected-union file.','GPU health receipts are verified separately, not inferred from exit0.']}
for cfg,expected in [('cpu',77),('cuda',111),('nvcomp',114)]:
 k='ctest-cand-'+cfg;f=j['files'];xml=E.fromstring(f[k+'.junit.xml']['text']);cases=xml.findall('.//testcase');names=[c.attrib['name'] for c in cases];r=j['listed'][cfg];assert r['exit']==0;rj=json.loads(r['stdout']);listed=[c['name'] for c in rj['tests']]
 assert len(names)==len(set(names))==expected,(cfg,len(names));assert set(names)==set(listed);assert all(not any(c.find(t) is not None for t in ['failure','error','skipped']) for c in cases)
 assert all(c.get('status')=='run' for c in cases)
 for required in ['LocalMotionDistortionGuard','LocalMotionGuardModel','LocalMotionGuardCall']:assert required in names
 log=f[k+'.log']['text'];assert 'HEAD='+report['source_head'] in log;assert 'validate_test_collection rc=0' in log;assert re.search(r'ctest rc=0 end',log);assert f[k+'.exit']['text'].strip()=='0';assert f['logs/'+k+'.exit']['text'].strip()=='0'
 if cfg=='cpu':assert 'test_ci_fail_closed rc=0' in log
 report['configs'][cfg]={'pass':len(names),'listed_equal_run':True,'no_duplicate_or_skipped_or_failure_or_error':True,'collection_exit':0,'stage_exit':0,'required_guard_tests_present':True,'binary_hash_line':next(x for x in log.splitlines() if 'binary sha256:' in x),'source_header':log.splitlines()[0]}
report['health_files']=[k for k in j['files'] if k.startswith('health')]
(p/'guard264-n1-parent-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
