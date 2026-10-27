"""Tests of the four capture-ON witnesses and the coverage check, on a real FullWidthPair capture produced by the actual capture code
(gen_fw_capture), the real native pilot logs (full-width ON and old-weight OFF) and the real old-weight capture. Every negative must raise the named Stop.
Usage: test_capture_witness.py GENERATOR_BINARY"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'scripts')]
import numpy as np
import capture_witness as C
import weight_oracle as O
BUNDLE = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/runs/noisy')
OLD_CAPTURE = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/capture-bundle-r1/evidence/runs/ON/capture')
on_log = (BUNDLE / 'ON/noisy.log').read_text(); off_log = (BUNDLE / 'OFF/noisy.log').read_text()
o42, o22 = O.weight_map(42), O.weight_map(22)
tmp = Path(tempfile.mkdtemp(prefix='capwit-')); good = tmp / 'good'
subprocess.run([sys.argv[1], str(good)], check=True, env=dict(os.environ, OMP_NUM_THREADS='2'))
passed = []
def ok(name): passed.append(name)
def expect(name, fn, stop):
    try: fn()
    except C.Stop as e:
        assert e.name == stop, (name, e.name, e.why); ok(name); return
    raise AssertionError('NOT STOPPED: ' + name)
def variant(name):
    d = tmp / name; shutil.copytree(good, d); return d
def edit(path, fn):
    j = json.loads(path.read_text()); fn(j); path.write_text(json.dumps(j))
# positive: everything passes on the real capture and the real full-width native log
res = C.run_all(good, on_log, o42, o22)
assert res['coverage']['104,15']['executed_iterations'] == 2 and res['W4_log']['witness_lines'] == 9 and res['W2_norm']['62,79']['weight_x_norm'] == 42; ok('positive: all witnesses and coverage pass')
# W1
expect('real old-weight capture (schema /1, other coordinates) is refused', lambda: C.check_session(OLD_CAPTURE), 'W1_SESSION')
for label, mut in [('schema /1', lambda j: j.__setitem__('schema', 'local-ccf-capture/1')), ('mode Legacy', lambda j: j.__setitem__('capture_mode', 'legacy')), ('weight flag false', lambda j: j.__setitem__('local_full_width_weight', False)),
                   ('coords legacy', lambda j: j.__setitem__('selected_centres', [[62, 47], [62, 79]])), ('coords swapped', lambda j: j.__setitem__('selected_centres', [[62, 79], [104, 15]])), ('truth input true', lambda j: j.__setitem__('native_truth_input', True))]:
    d = variant('s_' + label.replace(' ', '_').replace('/', '')); edit(d / 'session.json', mut); expect('W1 ' + label, lambda d=d: C.check_session(d), 'W1_SESSION')
d = variant('s_extra_dir'); (d / 'patch-62-47').mkdir(); expect('W1 extra patch directory', lambda: C.check_session(d), 'W1_SESSION')
d = variant('s_patch_mode'); edit(d / 'patch-104-15/patch.json', lambda j: j.pop('capture_mode')); expect('W1 patch.json without mode', lambda: C.check_session(d), 'W1_SESSION')
d = variant('s_extents'); edit(d / 'patch-62-79/patch.json', lambda j: j.__setitem__('extents_xy_halfopen', [42, 84, 47, 79])); expect('W1 wrong extents', lambda: C.check_session(d), 'W1_SESSION')
# W2
for label, mut in [('22', lambda j: j.__setitem__('weight_x_norm', 22)), ('missing', lambda j: j.pop('weight_x_norm')), ('41', lambda j: j.__setitem__('weight_x_norm', 41))]:
    d = variant('n_' + label); edit(d / 'patch-104-15/fft-config.json', mut); expect('W2 weight_x_norm ' + label, lambda d=d: C.check_norm(d), 'W2_NORM')
d = variant('n_B'); edit(d / 'patch-62-79/fft-config.json', lambda j: j.__setitem__('scaled_B', 100)); expect('W2 scaled_B differs', lambda: C.check_norm(d), 'W2_NORM')
# W3
d = variant('w_inherited'); (d / 'patch-62-79/weights.bin').write_bytes(np.ascontiguousarray(o22, dtype='<f4').tobytes()); expect('W3 inherited (x_norm 22) map in the weights file', lambda: C.check_weights(d, o42, o22), 'W3_WEIGHTS')
d = variant('w_bit'); b = bytearray((d / 'patch-104-15/weights.bin').read_bytes()); b[100] ^= 1; (d / 'patch-104-15/weights.bin').write_bytes(bytes(b)); expect('W3 one flipped bit', lambda: C.check_weights(d, o42, o22), 'W3_WEIGHTS')
d = variant('w_meta'); edit(d / 'patch-104-15/weights.json', lambda j: j.__setitem__('dtype', '>f4')); expect('W3 wrong dtype metadata', lambda: C.check_weights(d, o42, o22), 'W3_WEIGHTS')
d = variant('w_short'); (d / 'patch-62-79/weights.bin').write_bytes((d / 'patch-62-79/weights.bin').read_bytes()[:-4]); expect('W3 truncated weights', lambda: C.check_weights(d, o42, o22), 'W3_WEIGHTS')
expect('W3 oracle that cannot discriminate', lambda: C.check_weights(good, o42, o42), 'W3_WEIGHTS')
# W4
expect('W4 old-weight native log (0 witness lines)', lambda: C.check_log(off_log), 'W4_LOG')
lines = on_log.splitlines()
expect('W4 one witness line removed', lambda: C.check_log('\n'.join(l for i, l in enumerate(lines) if i != next(j for j, x in enumerate(lines) if 'EXPERIMENTAL' in x))), 'W4_LOG')
first = next(j for j, x in enumerate(lines) if 'EXPERIMENTAL' in x)
expect('W4 one line with x_norm 22', lambda: C.check_log('\n'.join(l.replace('x_norm = 42', 'x_norm = 22') if i == first else l for i, l in enumerate(lines))), 'W4_LOG')
expect('W4 extra witness line', lambda: C.check_log(on_log + C.LOG_WITNESS + '\n'), 'W4_LOG')
sel = next(i for i, l in enumerate(lines) if l.startswith('Patch (') and 'Center = (104, 15)' in l)
expect('W4 witness not directly after its header', lambda: C.check_log('\n'.join(lines[:sel + 1] + [' Iteration 1: RMSD = 1 px'] + lines[sel + 1:])), 'W4_LOG')
expect('W4 header of a selected patch renamed', lambda: C.check_log(on_log.replace('Center = (104, 15)', 'Center = (104, 16)')), 'W4_LOG')
# coverage
d = variant('c_missing'); next(iter(sorted((d / 'patch-104-15').glob('iter2-frame4-real-map.bin')))).unlink(); expect('coverage missing real map', lambda: C.check_coverage(d), 'COVERAGE')
d = variant('c_extra'); (d / 'patch-62-79/extra.bin').write_bytes(b'x'); expect('coverage extra file', lambda: C.check_coverage(d), 'COVERAGE')
d = variant('c_iter'); edit(d / 'patch-62-79/alignment-complete.json', lambda j: j.__setitem__('iterations', 3)); expect('coverage iteration count mismatch', lambda: C.check_coverage(d), 'COVERAGE')
d = variant('c_list'); edit(d / 'patch-104-15/patch-files.json', lambda j: j['files'].pop()); expect('coverage patch-files.json short', lambda: C.check_coverage(d), 'COVERAGE')
d = variant('c_complete'); (d / 'COMPLETE.json').unlink(); expect('coverage COMPLETE.json missing', lambda: C.check_coverage(d), 'COVERAGE')
d = variant('c_peak'); edit(d / 'patch-104-15/iter1-frame2-peak.json', lambda j: j.__setitem__('frame', 3)); expect('coverage peak identity', lambda: C.check_coverage(d), 'COVERAGE')
shutil.rmtree(tmp)
print('PASS %d checks' % len(passed)); [print(' -', p) for p in passed]
