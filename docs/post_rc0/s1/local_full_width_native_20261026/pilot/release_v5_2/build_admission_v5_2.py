"""Write ADMISSION_V5_2.json (from the frozen ADMISSION_V5.json plus the continuation block and the original-scratch baseline root) and COMMANDS_V5_2.json
(byte copy of COMMANDS_V5.json), then set the admission anchor in pair_decision_v5_2.py. Launches nothing."""
from pathlib import Path
import hashlib, json, re, sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V5 = HERE.parent / 'release_v5'
NS = '/tmp/motioncorr-lfw-v5-20261026'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
adm = json.loads((V5 / 'ADMISSION_V5.json').read_text())
idx = json.loads((HERE / 'REUSED_OFF_INDEX.json').read_text())
inv = {k[len('noisy/OFF/'):]: v for k, v in idx['evidence_inventory'].items()}
assert len(inv) == 15 and inv['RUN.json'] == idx['run_json_sha256']
adm.update({
    'schema': 'local-full-width-admission-v5_2', 'version': 'v5.2', 'status': 'FROZEN_PENDING_OPUS_DELTA_REVIEW_CONTINUATION',
    'supersedes_v5_admission': {'file': 'release_v5/ADMISSION_V5.json', 'sha256': sha(V5 / 'ADMISSION_V5.json')},
    'baseline_root': '/tmp/motioncorr-b2-factorial-20261026/evidence/runs',
    'baseline_root_note': 'canonical ORIGINAL scratch root: the pinned baseline files embed it; bytes identical to the durable copy and to the 152 pins',
    'continuation': {
        'kind': 'reuse_first_off_after_r1_stop', 'case': 'noisy', 'arm': 'OFF', 'run_json_sha256': idx['run_json_sha256'],
        'evidence_inventory': inv, 'evidence_inventory_sha256': hashlib.sha256(json.dumps(inv, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'r1_decision_dir': NS + '/decision-native-r1', 'r1_ledger_sha256': idx['r1_ledger_sha256'], 'r1_stop_sha256': idx['r1_stop_sha256'],
        'r1_release_sha256': idx['r1_release_sha256'], 'r1_release_index_sha256': idx['r1_release_index_sha256'],
        'launches_before': 1, 'remaining': 15, 'global_ceiling': 16,
        'reused_off_index_sha256': sha(HERE / 'REUSED_OFF_INDEX.json'), 'continuation_plan_sha256': sha(HERE / 'CONTINUATION_PLAN.md')},
})
(HERE / 'ADMISSION_V5_2.json').write_text(json.dumps(adm, indent=2, allow_nan=False) + '\n')
(HERE / 'COMMANDS_V5_2.json').write_bytes((V5 / 'COMMANDS_V5.json').read_bytes())
mod = (HERE / 'pair_decision_v5_2.py').read_text()
mod = re.sub(r"ADMISSION_V5_2_SHA256 = '[^']*'", "ADMISSION_V5_2_SHA256 = '%s'" % sha(HERE / 'ADMISSION_V5_2.json'), mod)
(HERE / 'pair_decision_v5_2.py').write_text(mod)
print('admission', sha(HERE / 'ADMISSION_V5_2.json'), 'commands', sha(HERE / 'COMMANDS_V5_2.json'), 'inventory_sha', adm['continuation']['evidence_inventory_sha256'])
