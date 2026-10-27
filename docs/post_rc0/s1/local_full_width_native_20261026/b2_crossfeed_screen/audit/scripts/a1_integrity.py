"""A1: integrity and chronology. Read-only. Packet manifest, durable copy index, bundle manifest, stage-1 seal, staged-root identity, attempt diff."""
import hashlib, json, sys, difflib
from pathlib import Path
P = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve()
D = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-crossfeed-screen-r1')
B = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1')
RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
R = {}
pins = {'PLAN.md': 'df804f523613c742e0220f87e7e2f70cb476324e0b08f9b6a4835796c2875da7', 'PINS.json': '18841057ab2021937148e2c089bf1574161515a5032bbf311c657f8524100358',
        'out/stage1_seal.json': '41fed948524c23dd1538719e144eb04d1f79c2d4ea5fcda79dd579c7e21541c6', 'out/stage2_result.json': 'c5520cf3b0601f82fec56484579211c23e45c1f9ab82b6d95aa70ce6601722dd',
        'MANIFEST.json': '36b5253d89d82a5f0a1299a300c857128c9e967b6b5c5cbca3b6e23cd1be71b9'}
R['pins_match'] = {k: sha(P / k) == v for k, v in pins.items()}
R['durable_index_sha_ok'] = sha(D / 'COPY_INDEX.tsv') == '4de4c522987b395f06d91126bc9cd0aa1275cfbf58c99d11517cd14c9cd0a8b6'
# packet manifest vs packet files
man = json.loads((P / 'MANIFEST.json').read_text())
files = man['files']
items = files.items() if isinstance(files, dict) else [(f['path'], f['sha256']) for f in files]
items = [(k, v if isinstance(v, str) else v.get('sha256')) for k, v in items]
R['packet_manifest_n'] = len(items)
R['packet_manifest_mismatch'] = [k for k, v in items if not (P / k).is_file() or sha(P / k) != v]
on_disk = sorted(str(p.relative_to(P)) for p in P.rglob('*') if p.is_file())
R['packet_files_unlisted'] = sorted(set(on_disk) - {k for k, _ in items})
# durable copy index vs durable copy vs packet
idx = [l.split('\t') for l in (D / 'COPY_INDEX.tsv').read_text().splitlines() if l.strip()]
R['durable_index_n'] = len(idx)
R['durable_mismatch_vs_copy'] = [p for h, p in idx if sha(D / p) != h]
R['durable_mismatch_vs_packet'] = [p for h, p in idx if not (P / p[len('./work/'):]).is_file() or sha(P / p[len('./work/'):]) != h]
dur_files = sorted('./' + str(p.relative_to(D)) for p in D.rglob('*') if p.is_file() and p.name != 'COPY_INDEX.tsv')
R['durable_files_unindexed'] = sorted(set(dur_files) - {p for _, p in idx})
R['packet_files_not_in_durable'] = sorted(set(on_disk) - {p[len('./work/'):] for _, p in idx})
# bundle manifest: files we use
bm = json.loads((B / 'MANIFEST.json').read_text())
bfiles = bm['files'] if 'files' in bm else bm
def bentry(rel):
    v = bfiles.get(rel) if isinstance(bfiles, dict) else next((f for f in bfiles if f.get('path') == rel), None)
    return v if isinstance(v, str) or v is None else v.get('sha256')
R['bundle_manifest_sha_ok'] = sha(B / 'MANIFEST.json') == '49698c7ca37fd840b5930063ae13d946604e0407dd1102bf283696b86bbb669e'
R['bundle_manifest_count'] = len(bfiles)
used = [f'runs/{c}/{a}/{n}' for c in ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated'] for a in ('OFF', 'ON') for n in ('runtime.json', f'{c}.star')]
R['bundle_used_files_hash_mismatch'] = [r for r in used if bentry(r) is None or sha(B / r) != bentry(r)]
tm = json.loads((B / 'truth/MANIFEST.json').read_text())
R['truth_manifest_sha_ok'] = sha(B / 'truth/MANIFEST.json') == '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
R['truth_npy_vs_truth_manifest'] = {c: sha(B / f'truth/{c}_field.npy') == tm['cases'][c]['files'][f'{c}_field.npy'] for c in tm['cases']}
# retained controls vs PINS
pj = json.loads((P / 'PINS.json').read_text())
R['old_harm_control_raw_ok'] = {k: sha(RAW / k) == v for k, v in pj['old_harm_control_raw'].items()}
# seal re-verification and staged root
seal = json.loads((P / 'out/stage1_seal.json').read_text())
R['seal_utc'] = seal['sealed_utc']
R['seal_files_mismatch'] = [n for n, h in {**seal['files'], **seal['staged_root_files']}.items() if sha(P / n) != h]
staged = sorted(str(p.relative_to(P)) for p in (P / 'stage1_root').rglob('*') if p.is_file())
R['staged_root_n'] = len(staged); R['staged_names'] = sorted({Path(s).name for s in staged})
R['staged_equals_seal_list'] = staged == sorted(seal['staged_root_files'])
sm = json.loads((P / 'out/stage1_staged_manifest.json').read_text())
R['staged_vs_source_now'] = [k for k, v in sm.items() if sha(v['source']) != v['sha256'] or sha(P / 'stage1_root' / k) != v['sha256']]
R['seal_covers_stage2_script'] = 'stage2_score.py' in seal['files']
# stage-2 provenance
s2 = json.loads((P / 'out/stage2_result.json').read_text())
R['stage2_plan_sha'] = s2['plan_sha256'] == pins['PLAN.md']; R['stage2_seal_sha'] = s2['stage1_seal_sha256'] == pins['out/stage1_seal.json']
# attempt1 vs attempt2: code diff and numerical content
a1 = (P / 'out/attempt1/stage1_fit.attempt1.py').read_text().splitlines(); a2 = (P / 'stage1_fit.py').read_text().splitlines()
R['attempt_code_diff'] = [l for l in difflib.unified_diff(a1, a2, lineterm='', n=0) if not l.startswith(('---', '+++', '@@'))]
j1 = json.loads((P / 'out/attempt1/stage1_fit.json').read_text()); j2 = json.loads((P / 'out/stage1_fit.json').read_text())
strip = lambda j: {k: v for k, v in j.items() if k not in ('isolation', 'environment')}
R['attempt_numeric_content_equal_excl_isolation_env'] = strip(j1) == strip(j2)
R['attempt1_overall_pass'] = j1['overall_pass']; R['attempt1_isolation_counts'] = j1['isolation']['opened_counts']
R['attempt2_isolation_counts'] = j2['isolation']['opened_counts']; R['attempt2_other'] = j2['isolation']['other_opened']
R['attempt1_other_outside_packet'] = [p for p in j1['isolation']['other_opened'] if not p.startswith('/private/tmp/mc-lfw-b2-crossfeed-20261026-r1')]
log = json.loads((P / 'out/stage1_audit_open_log.json').read_text())
R['audit_all_opened_foreign'] = [p for p in log['all_opened'] if not any(Path(p).resolve().as_posix().startswith(x) for x in (str(P / 'stage1_root'), str(P / 'src_w8'), '/opt', '/usr', '/Library', '/Users/alex.konstantinov/.local', '/Users/alex.konstantinov/.pyenv', '/Users/alex.konstantinov/Library'))]
R['audit_interp_roots_sample'] = sorted({'/'.join(Path(p).resolve().parts[:5]) for p in log['classes']['interpreter_numpy_tree']})
json.dump(R, sys.stdout, indent=1); print()
