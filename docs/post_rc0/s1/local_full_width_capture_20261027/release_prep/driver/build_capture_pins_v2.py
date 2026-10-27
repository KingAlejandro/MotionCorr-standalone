"""Writes CAPTURE_RUN_PINS_v2.json (staged as RUN_PINS_v2.json) from the frozen v1 pins: only the keys named in CHANGED differ; asserts everything else is byte-identical, and
writes PINS_V1_V2_DIFF.json. Reads and hashes files only; launches nothing."""
import hashlib, json
from pathlib import Path
HERE = Path(__file__).resolve().parent; PREP = HERE.parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
v1 = json.loads((HERE / 'CAPTURE_RUN_PINS.json').read_text()); v2 = json.loads(json.dumps(v1))
prep = {k: v for k, v in v1['prep_files'].items() if k != 'run_capture_fw.py'}; prep['run_capture_fw_v2.py'] = sha(HERE / 'run_capture_fw_v2.py')
v2.update(release_id='lfw-capture-v2', status='FROZEN_HELD_NOT_RELEASED', prep_files=prep,
          supersedes={'pins_v1_sha256': sha(HERE / 'CAPTURE_RUN_PINS.json'), 'driver_v1_sha256': v1['prep_files']['run_capture_fw.py'], 'reason': 'driver execution review conditions C1 and C2 (and N1-N5), see DRIVER_RESPONSE_CRITERIA.md'},
          driver={'file': 'run_capture_fw_v2.py', 'pins_file_name': 'RUN_PINS_v2.json', 'job_timeout_seconds': 600, 'grant_format': ['granted_by', 'utc', 'cpus=32-47', 'lane_locks=pinned', 'jobs=[OFF,ON]', 'receipt_sha256 (64 hex)'], 'grant_note': 'format check only; the parent binds the actual grant externally'})
CHANGED = ['release_id', 'prep_files', 'supersedes', 'driver']
for k in v1:
    if k not in CHANGED: assert v1[k] == v2[k], k
(HERE / 'CAPTURE_RUN_PINS_v2.json').write_text(json.dumps(v2, indent=2, sort_keys=True) + '\n')
(HERE / 'PINS_V1_V2_DIFF.json').write_text(json.dumps({'changed_or_added_keys': sorted(set(CHANGED) | (set(v2) - set(v1))), 'unchanged_keys_identical': sorted(k for k in v1 if k not in CHANGED),
                                                         'prep_files_removed': ['run_capture_fw.py'], 'prep_files_added': {'run_capture_fw_v2.py': prep['run_capture_fw_v2.py']}}, indent=1) + '\n')
print('pins v2', sha(HERE / 'CAPTURE_RUN_PINS_v2.json')[:16], 'driver v2', prep['run_capture_fw_v2.py'][:16])
