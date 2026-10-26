"""Fake-receipt negatives for score_fields_v2 (scratch only; no producer)."""
import copy, hashlib, json, os, shutil, sys
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path('/tmp/mc-local-full-width-pilot-20261026')
sys.path.insert(0, str(PILOT))
import score_fields_v2 as S
import numpy as np

SCR = Path(sys.argv[1]); OUT = Path(sys.argv[2])
RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
FIX = Path('/tmp/motioncorr-b2-retained-challenge-20261026/v2fixtures')
manifest = json.loads((FIX / 'MANIFEST.json').read_text())
BIN = 'a' * 64
case = 'noisy'
sha = lambda b: hashlib.sha256(b).hexdigest()
REQ = [case + '.star', case + '.mrc', case + '.log', 'corrected_micrographs.star', 'logfile.pdf']

def make(name, mutate=None, files=None, runtime=True):
    d = SCR / name
    if d.exists(): shutil.rmtree(d)
    (d / 'output').mkdir(parents=True)
    pub = {}
    for rel in (files or REQ):
        b = (rel + ' fake').encode(); (d / 'output' / rel).write_bytes(b); pub[rel] = dict(bytes=len(b), sha256=sha(b))
    run = dict(case=case, arm='OFF', exit=0, binary_sha256=BIN, publication=pub)
    if mutate: mutate(d, run)
    (d / 'RUN.json').write_text(json.dumps(run))
    if runtime: (d / 'runtime.json').write_text('{}')
    return d

def expect(name, d, should_pass, binary=BIN, c=case):
    try: S.complete_publication(d, c, binary); got, err = True, None
    except Exception as e: got, err = False, f'{type(e).__name__}: {e}'
    return dict(name=name, expected='ADMIT' if should_pass else 'REJECT', observed='ADMIT' if got else 'REJECT', error=err, as_expected=got == should_pass)

rows = []
rows.append(expect('positive_control_complete', make('pos'), True))
rows.append(expect('wrong_case', make('wc', lambda d, r: r.update(case='affine')), False))
rows.append(expect('exit_1', make('e1', lambda d, r: r.update(exit=1)), False))
rows.append(expect('exit_str_0', make('es', lambda d, r: r.update(exit='0')), False))
rows.append(expect('exit_true', make('et', lambda d, r: r.update(exit=True)), False))
rows.append(expect('exit_false_bool', make('ef', lambda d, r: r.update(exit=False)), False))
rows.append(expect('exit_float_0', make('ef0', lambda d, r: r.update(exit=0.0)), False))
rows.append(expect('exit_missing', make('em', lambda d, r: r.pop('exit')), False))
rows.append(expect('receipt_binary_differs', make('bd', lambda d, r: r.update(binary_sha256='b' * 64)), False))
rows.append(expect('expected_binary_uppercase', make('bu', lambda d, r: r.update(binary_sha256='A' * 64)), False, binary='A' * 64))
rows.append(expect('expected_binary_short', make('bs', lambda d, r: r.update(binary_sha256='a' * 63)), False, binary='a' * 63))
rows.append(expect('missing_required_in_receipt', make('mr', files=REQ[:-1]), False))
def shrink(d, r): (d / 'output' / REQ[0]).write_bytes(b'x')
rows.append(expect('bytes_mismatch', make('bm', shrink), False))
def samesize(d, r):
    p = d / 'output' / REQ[0]; b = bytearray(p.read_bytes()); b[0] ^= 1; p.write_bytes(bytes(b))
rows.append(expect('sha_mismatch_same_size', make('sm', samesize), False))
def delete(d, r): (d / 'output' / REQ[1]).unlink()
rows.append(expect('listed_file_absent', make('la', delete), False))
def escape(d, r):
    b = b'outside'; (d / 'outside.txt').write_bytes(b); r['publication']['../outside.txt'] = dict(bytes=len(b), sha256=sha(b))
rows.append(expect('dotdot_escape', make('dd', escape), False))
def absolute(d, r):
    b = b'outside'; p = d / 'abs.txt'; p.write_bytes(b); r['publication'][str(p.resolve())] = dict(bytes=len(b), sha256=sha(b))
rows.append(expect('absolute_path_escape', make('ab', absolute), False))
def symlink(d, r):
    b = b'outside'; t = d / 'tgt.txt'; t.write_bytes(b); (d / 'output' / 'link.txt').symlink_to(t)
    r['publication']['link.txt'] = dict(bytes=len(b), sha256=sha(b))
rows.append(expect('symlink_escape', make('sl', symlink), False))
rows.append(expect('runtime_tap_missing', make('rm', runtime=False), False))
rows.append(expect('publication_as_list', make('pl', lambda d, r: r.update(publication=list(r['publication']))), False))
rows.append(expect('publication_pin_not_dict', make('pn', lambda d, r: r['publication'].update({REQ[0]: 'x'})), False))
# Gaps (expected to be rejected by a complete consumer; adapter behaviour recorded).
def extra(d, r): (d / 'output' / 'unlisted_stale.mrc').write_bytes(b'stale')
rows.append(expect('GAP_unlisted_extra_output_file', make('ex', extra), False))
rows.append(expect('GAP_arm_label_ON_passed_as_OFF_slot', make('arm', lambda d, r: r.update(arm='ON')), False))
rows.append(expect('GAP_arm_field_absent', make('arm0', lambda d, r: r.pop('arm')), False))
def rt_garbage(d, r): pass
dd = make('rtg'); (dd / 'runtime.json').write_text('not json')
rows.append(expect('GAP_runtime_tap_unparseable_and_unpinned', dd, False))

# field_metrics negatives on mutated copies of the retained noisy UP_only metadata.
src = RAW / 'noisy/UP_only'; meta = manifest['cases']['noisy']; tsha = meta['files']['noisy_field.npy']
base_rt = json.loads((src / 'runtime.json').read_text()); star = src / 'output/noisy.star'; truth = FIX / 'noisy_field.npy'
def fm(name, rt=None, st=star, tr=truth, m=meta, ts=tsha, should_pass=False):
    p = SCR / 'fm' / (name + '.json'); p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(base_rt if rt is None else rt))
    try: res = S.field_metrics(p, st, tr, m, ts); got, err = True, None
    except Exception as e: res, got, err = None, False, f'{type(e).__name__}: {e}'
    row = dict(name=name, expected='ACCEPT' if should_pass else 'REJECT', observed='ACCEPT' if got else 'REJECT', error=err, as_expected=got == should_pass)
    if res: row['runtime_rms_A'] = res['runtime']['angstrom']['rms']; row['STAR_rms_A'] = res['STAR']['angstrom']['rms']
    return row
def mod(**kw):
    r = copy.deepcopy(base_rt); r.update(kw); return r
rows.append(fm('fm_positive_control', should_pass=True))
rows.append(fm('fm_local_enabled_missing', {k: v for k, v in base_rt.items() if k != 'local_enabled'}))
rows.append(fm('fm_local_enabled_int', mod(local_enabled=1)))
rows.append(fm('fm_global_4_frames', mod(**{'global': base_rt['global'][:4]})))
rows.append(fm('fm_coeff_17', mod(coeff_x=base_rt['coeff_x'][:17])))
rows.append(fm('fm_coeff_nan', json.loads(json.dumps(mod(coeff_y=[float('nan')] + base_rt['coeff_y'][1:])).replace('NaN', 'NaN'))))
rows.append(fm('fm_disabled_nonzero_coeff', mod(local_enabled=False)))
rows.append(fm('fm_truth_sha_mismatch', ts='0' * 64))
rows.append(fm('fm_wrong_truth_file', tr=FIX / 'affine_field.npy'))  # same bytes as noisy: identical hash
bad = copy.deepcopy(meta); bad['roi'] = [0, 97, 0, 128]
rows.append(fm('fm_roi_out_of_bounds', m=bad))
alt = copy.deepcopy(meta); alt['roi'] = [0, 96, 0, 128]
rows.append(fm('GAP_fm_roi_in_bounds_but_not_pinned_72x104', m=alt))
ps = copy.deepcopy(meta); ps['recipe'] = dict(meta['recipe'], pixel_size=0.1)
rows.append(fm('GAP_fm_pixel_size_not_pinned', m=ps))
rows.append(fm('GAP_fm_cross_case_star_affine_with_noisy_runtime', st=RAW / 'affine/UP_only/output/affine.star'))
for r in rows: print(('OK ' if r['as_expected'] else 'XX ') + r['name'], r['observed'], (r['error'] or '')[:90])
OUT.write_text(json.dumps(dict(rows=rows, all_as_expected=all(r['as_expected'] for r in rows), python=sys.version, numpy=np.__version__,
                               adapter_sha256=hashlib.sha256((PILOT / 'score_fields_v2.py').read_bytes()).hexdigest()), indent=2) + '\n')
