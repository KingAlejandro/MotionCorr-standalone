"""Post-processing only (no scoring): regressions.csv and rehash comparison from stage2_score.json and the admission files."""
import csv, json, sys, hashlib
from pathlib import Path
R = Path(sys.argv[1])
j = json.loads((R/'results/stage2_score.json').read_text())
with (R/'results/regressions.csv').open('w', newline='') as f:
    w = csv.writer(f); w.writerow(['movie', 'set', 'metric', 'B2_A', 'CM_A', 'delta_A', 'B2_passes', 'CM_passes'])
    for g in j['regressions']: w.writerow([g['movie'], g['set'], g['metric'], repr(g['B2']), repr(g['CM']), repr(g['delta_A']), g['B2_passes'], g['CM_passes']])
b = json.loads((R/'admission/admission_before.json').read_text()); a = json.loads((R/'admission/admission_after.json').read_text())
ref = json.loads((R/'authority_w8_0b3478b5/docs/post_rc0/s1/first_divergence_20261022/w8_intercept_refit_20261026/results/admission.json').read_text())
rep = dict(before_equals_after=b['files'] == a['files'], manifest_before=b['input_manifest_sha256'], manifest_after=a['input_manifest_sha256'],
           equals_W8_admission=a['files'] == ref['files'], pinned_sha_matches=a['input_manifest_sha256'] == '60a67d64729ee0c93317ffa0fa110c9d2b647b390a33fd07dfd7ec334ce29ad9')
for name in ('authority_w8_0b3478b5', 'src_4fa272f6'):
    pin = {l.split()[1]: l.split()[0] for l in (R/f'pins/{name}.sha256').read_text().splitlines()}
    rep[name+'_unchanged'] = all(hashlib.sha256((R/name/p).read_bytes()).hexdigest() == h for p, h in pin.items())
rep['plan_unchanged_since_freeze'] = hashlib.sha256((R/'PLAN.md').read_bytes()).hexdigest() == (R/'pins/PLAN.frozen.sha256').read_text().split()[0]
(R/'admission/rehash_comparison.json').write_text(json.dumps(rep, indent=1)+'\n'); print(json.dumps(rep))
import statistics
rows = j['movies']
print('d_rms_px median/max', statistics.median(x['d_rms_px'] for x in rows), max(x['d_rms_px'] for x in rows))
print('inmodel dMS<0', sum(x['dMS_direct_A2'] < 0 for x in rows if x['set'] == 'inmodel'), '/80; outmodel', sum(x['dMS_direct_A2'] < 0 for x in rows if x['set'] == 'outmodel'), '/10')
print('regressions in B2-failing 12 rows:', len({g['movie'] for g in j['regressions']} & {m for g in j['summary']['seed_groups_failing_rows'].values() for m in g['rows']}))
print('rows B2 fail -> CM pass', [x['movie'] for x in rows if x['set']=='inmodel' and any(x['B2'][k]>{'rms':.2,'p95':.4,'max':.8}[k] for k in ('rms','p95','max')) and all(x['CM'][k]<={'rms':.2,'p95':.4,'max':.8}[k] for k in ('rms','p95','max'))])
print('rows 12 failing still failing', [x['movie'] for x in rows if x['movie'] in {m for g in j['summary']['seed_groups_failing_rows'].values() for m in g['rows']} and any(x['CM'][k]>{'rms':.2,'p95':.4,'max':.8}[k] for k in ('rms','p95','max'))])
