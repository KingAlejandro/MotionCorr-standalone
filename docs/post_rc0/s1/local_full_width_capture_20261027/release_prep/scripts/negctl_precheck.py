"""Negative controls for the driver's pre-launch checks, run on cpu64 against in-memory mutated copies of the pins (nothing on disk is changed)."""
import copy, json, sys
sys.path.insert(0, '/tmp/motioncorr-lfw-capture-20261027/prep')
import run_capture_fw as D
import shutil
ALIAS = D.ROOT / 'receipts/negctl_alias/noisy/ON'
if not ALIAS.exists(): shutil.copytree('/tmp/motioncorr-lfw-v5-20261026/evidence/noisy/ON', ALIAS)
pins = json.loads((D.ROOT / 'RUN_PINS.json').read_text())
D.pre_checks(pins); print('POSITIVE: pre_checks pass on the real pins')
def mutate(name, fn, ok_text=None):
    p = copy.deepcopy(pins); fn(p)
    try: D.pre_checks(p)
    except D.Refuse as e: print('REFUSED as required:', name, '->', str(e)[:90]); return
    print('NOT REFUSED (control failed):', name); sys.exit(1)
k0 = next(iter(pins['libs']))
for name, fn in [('binary hash', lambda p: p.__setitem__('binary_sha256', '0' * 64)), ('one library hash', lambda p: p['libs'].__setitem__(k0, '0' * 64)), ('extra pinned library', lambda p: p['libs'].__setitem__('/usr/lib/x', '0' * 64)),
                 ('loader hash', lambda p: p.__setitem__('loader_sha256', '0' * 64)), ('baseline product hash', lambda p: p['baseline']['products'].__setitem__('noisy.mrc', '0' * 64)),
                 ('baseline run hash', lambda p: p['baseline'].__setitem__('run_json_sha256', '0' * 64)), ('baseline dir is an alias copy of the baseline (the r1 pilot failure mode)', lambda p: p['baseline'].__setitem__('dir', str(ALIAS))), ('baseline dir missing', lambda p: p['baseline'].__setitem__('dir', '/nonexistent/noisy/ON')),
                 ('input hash', lambda p: p['input_files'].__setitem__('noisy.mrcs', '0' * 64)), ('review verdict', lambda p: p['independent_source_review'].__setitem__('verdict', 'HOLD')),
                 ('review for another source', lambda p: p['independent_source_review'].__setitem__('source_commit', '0' * 40)), ('source blob list', lambda p: p.__setitem__('blob_list_sha256', '0' * 64)),
                 ('comparator hash', lambda p: p['comparator'].__setitem__('sha256', '0' * 64)), ('interpreter version', lambda p: p['interpreter'].__setitem__('version', '3.0.0')),
                 ('driver hash', lambda p: p['prep_files'].__setitem__('run_capture_fw.py', '0' * 64)), ('witness hash', lambda p: p['prep_files'].__setitem__('capture_witness.py', '0' * 64)),
                 ('baseline argv', lambda p: p['baseline'].__setitem__('argv', p['baseline']['argv'][:-1]))]:
    mutate(name, fn)
print('all negative controls refused')
