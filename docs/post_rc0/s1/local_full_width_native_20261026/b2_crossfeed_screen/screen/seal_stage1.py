"""Seal stage 1 (hash every plan, pin, script, staged manifest and stage-1 output) BEFORE stage 2 loads any truth."""
import hashlib, json, sys, time
from pathlib import Path
W = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
names = ['PLAN.md', 'PINS.json', 'FREEZE.txt', 'stage1_stage_inputs.py', 'stage1_fit.py', 'seal_stage1.py', 'out/stage1_staged_manifest.json', 'out/stage1_fit.json', 'out/stage1_audit_open_log.json', 'out/stage1.stdout', 'out/stage1.stderr',
         'out/attempt1/stage1_fit.json', 'out/attempt1/NOTE.md', 'src_w8/w8_fit.py', 'src_w8/w8_refit.py', 'src_w8/w8_gate.py']
staged = sorted(str(p.relative_to(W)) for p in (W / 'stage1_root').rglob('*') if p.is_file())
seal = {'schema': 'stage1-seal/1', 'sealed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'files': {n: sha(W / n) for n in names}, 'staged_root_files': {n: sha(W / n) for n in staged},
        'stage2_may_load_truth_only_after_this_file_exists': True, 'stage1_overall_pass': json.loads((W / 'out/stage1_fit.json').read_text())['overall_pass']}
(W / 'out' / 'stage1_seal.json').write_text(json.dumps(seal, indent=1) + '\n')
print('sealed', seal['sealed_utc'], 'pass', seal['stage1_overall_pass'], len(seal['files']), 'files +', len(staged), 'staged')
