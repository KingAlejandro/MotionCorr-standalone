import json, hashlib, sys
from pathlib import Path
D = Path(sys.argv[1]); tools = D / 'tools'; base = D / 'resource_stop_20261022/gpu_worker_v3_controls'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
v3 = (tools / 'gpu_worker_v3.py').read_text(); muts = json.loads((tools / 'v3_mutants.json').read_text())
summary = json.loads((base / 'SUMMARY.json').read_text())
rows = []
for a in sorted(base.glob('attempt-*')):
    at = json.loads((a / 'ATTEMPT.json').read_text()); c = json.loads((a / 'controls.json').read_text())
    w, t = sha(a / 'worker_under_test.py'), sha(a / 'test.py')
    exp = None
    if at['mutant']:
        src = v3
        for x, y in muts[at['mutant']]['replace']:
            assert src.count(x) == 1; src = src.replace(x, y)
        exp = hashlib.sha256(src.encode()).hexdigest()
    else: exp = sha(tools / 'gpu_worker_v3.py')
    fails = [r['control'].split()[0] for r in c['results'] if r['result'] != 'PASS']
    harness_err = [r['control'].split()[0] for r in c['results'] if 'harness_error' in json.dumps(r['detail'])]
    left = [r['control'].split()[0] for r in c['results'] if '"leftovers": [{' in json.dumps(r['detail'])]
    expf = muts[at['mutant']]['expect_fail'] if at['mutant'] else []
    rows.append(dict(attempt=a.name, exit=at['exit'], worker_match=(w == at['worker_sha256'] == c['worker_sha256'] == exp),
        test=t[:8], test_match=(t == at['test_sha256'] == c['test_sha256']), n=len(c['results']), fails=fails,
        expected_subset=set(expf) <= set(fails), harness_err=harness_err, leftovers=left, platform=c['platform'],
        load=[round(x, 1) for x in at['load_avg']], pid=at['launch']['pid'], fallback=at.get('fallback')))
for r in rows: print(json.dumps(r))
print('summary attempts', len(summary.get('attempts', summary)) if isinstance(summary, dict) else len(summary))
