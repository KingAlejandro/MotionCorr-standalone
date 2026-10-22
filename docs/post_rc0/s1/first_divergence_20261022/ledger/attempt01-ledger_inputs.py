#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline evidence for the 16-arm W4 ledger. No MotionCorr execution.

Reads the committed #273 native archive (bound by native-index.json at 805d9de2),
regenerates the eight fixtures and requires hash identity with the pinned
MANIFEST, and replays global stages from the #275 captures for affine/noisy.

usage: ledger_inputs.py REPO RAW FILE_INDEX OUT.json
"""
import hashlib, importlib.util, io, json, pathlib, re, subprocess, sys, tarfile, tempfile
import numpy as np

REPO, RAW, INDEX, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
import generate_motion_diagnostics as gen
here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stages_lib', here/'offline_stages_lib.py')
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
_src = (here/'offline_stages.py').read_text()
_lib = (here/'offline_stages_lib.py').read_text().split('from scipy.optimize import minimize\n\n', 1)[1]
for _block in _lib.split('\n\n'):
    assert _block.strip() in _src, _block[:60]  # shared functions are verbatim copies

C273 = '805d9de27898b4a10e6212e65098d5995a40fdb1'; P273 = 'docs/post_rc0/parallel_20261022/numerics/'
def sha(b): return hashlib.sha256(b).hexdigest()
def show(rev, path): return subprocess.check_output(['git', 'show', f'{rev}:{path}'], cwd=REPO)
nidx = json.loads(show(C273, P273+'native-index.json'))
archive = show(C273, P273+'native-receipts.tar.gz'); assert sha(archive) == nidx['archive_sha256']
pinned = json.loads(show(C273, P273+'fixture-MANIFEST.json'))
assert sha(show(C273, P273+'fixture-MANIFEST.json')) == lib.MANIFEST_SHA

fx = pathlib.Path(tempfile.mkdtemp(prefix='w4-fixtures-'))/'fx'
gen.generate(fx)
for case, c in pinned['cases'].items():
    for name, h in c['files'].items():
        assert gen.digest(fx/name) == h, name
from motion_field import read_mrc

def member(t, name):
    raw = t.extractfile(name).read(); assert sha(raw) == nidx['files'][name]['sha256'], name
    return raw

def global_rows(star):
    block = star.split('data_global_shift', 1)[1].split('data_', 1)[0]
    return [[float(v) for v in l.split()[1:]] for l in block.splitlines() if re.match(r'^\s*\d+\s+[-+.\deE]+\s+[-+.\deE]+\s*$', l)]

def coeffs(star):
    if 'data_local_motion_model' not in star: return None
    block = star.split('data_local_motion_model', 1)[1].split('data_', 1)[0]
    return [float(l.split()[1]) for l in block.splitlines() if re.match(r'^\s*\d+\s+[-+.\deE]+\s*$', l)]

def iterations(log):
    """Global block, then per-patch blocks: list of RMSD sequences."""
    blocks, cur = [], None
    for l in log.splitlines():
        if l.startswith('Global alignment') or l.startswith('Patch ('):
            cur = dict(name=l.split(':')[0] if l.startswith('Patch') else 'global', rmsd=[]); blocks.append(cur)
        m = re.match(r'\s*Iteration (\d+): RMSD = ([-+.\deE]+) px', l)
        if m and cur is not None: cur['rmsd'].append(float(m.group(2)))
    return blocks

ledger = []
with tarfile.open(fileobj=io.BytesIO(archive)) as t:
    for backend in ['cpu', 'cuda']:
        for case in gen.CASES:
            chk = json.loads(member(t, f'cases-{backend}/{case}.checker.json'))
            star = member(t, f'cases-{backend}/{case}/{case}.star').decode()
            log = member(t, f'cases-{backend}/{case}/{case}.log').decode()
            its = iterations(log)
            ledger.append(dict(backend=backend, case=case, role=chk['role'], accuracy_status=chk['accuracy_status'],
                sampling_status=chk['sampling_status'], identifiable=chk['identifiable'], field_px=chk['field_px'],
                field_angstrom=chk['field_angstrom'], global_mean_error_px=chk['global_mean_error_px'],
                local_error_px=chk['local_error_px'], signal=chk['signal'],
                star_global_xy=global_rows(star), local_coefficients=coeffs(star),
                log_alignment_blocks=its,
                patches_single_iteration=sum(1 for b in its if b['name'] != 'global' and len(b['rmsd']) == 1),
                patches=sum(1 for b in its if b['name'] != 'global')))

def first_iteration_map(case):
    """Double first-iteration global objective from regenerated fixture frames."""
    movie, _ = read_mrc(fx/f'{case}.mrcs'); F = np.fft.rfft2(movie.astype(np.float64))/(lib.NX*lib.NY)
    out = []
    for f in range(lib.NF):
        m = lib.ccf_map(F, f, False)
        win = np.array([[m[y % lib.NY, x % lib.NX] for x in range(-lib.SEARCH, lib.SEARCH+1)] for y in range(-lib.SEARCH, lib.SEARCH+1)])
        m32 = win.astype(np.float32)
        out.append(dict(frame=f, dc_term=float(np.real((F.sum(0)-F[f])[0, 0]*np.conj(F[f][0, 0]))),
                        peak=float(win.max()), window_range=float(win.max()-win.min()),
                        float32_ulp_at_peak=float(np.spacing(np.float32(win.max()))),
                        float32_distinct_values=int(np.unique(m32).size), float32_max_ties=int((m32 == m32.max()).sum())))
    return out
mechanisms = {case: first_iteration_map(case) for case in ['pedestal', 'flat', 'repeated', 'integer']}

# Global stage of affine/noisy from the bound #275 captures: specified objective in
# double and with an exact continuous maximum. Truth here is descriptive only:
# a global shift is not the affine field; the frame-centre displacement is shown.
committed = json.loads(show('6ae486785334fca635cfc9ad9e86026d656f3943', 'docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json'))
assert sha(INDEX.read_bytes()) == committed['array_product_index_sha256']
index = json.loads(INDEX.read_text())['files']
def load(rel):
    b = (RAW/rel).read_bytes(); assert sha(b) == index[rel]['sha256'], rel; return b
global_other = {}
for case in ['affine', 'noisy']:
    field = np.load(fx/f'{case}_field.npy'); centre = field[:, lib.NY//2, lib.NX//2, :]
    y0, y1, x0, x1 = pinned['cases'][case]['roi']; roi_mean = field[:, y0:y1, x0:x1].mean(axis=(1, 2))
    for backend in ['cpu', 'cuda']:
        base = f'runs/{backend}-{case}-on/capture/c1'
        meta = json.loads(load(base+'.json')); assert meta['tag'].endswith('global') and meta['patch_nxy'] == [lib.NX, lib.NY]
        F1 = np.frombuffer(load(base+'-i1-input.bin'), '<c8').reshape(lib.NF, lib.NY, lib.NFX)
        it = 1
        while (RAW/f'{base}-i{it+1}-after.bin').exists(): it += 1
        native = np.frombuffer(load(f'{base}-i{it}-after.bin'), '<f8').reshape(lib.NF, 2)
        rec = dict(native_final_xy=native.tolist(), native_iterations=it,
                   native_vs_centre=lib.err(native, centre), native_vs_roi_mean=lib.err(native, roi_mean))
        for label, est, tol, mi in (('specified_double', 'parabola', lib.TOL, 5), ('continuous_double', 'continuous', lib.TOL, 5),
                                    ('continuous_double_tol1e-9_max_iter50', 'continuous', 1e-9, 50)):
            acc, its, conv = lib.replay(F1, False, False, mi, tol, est, centre)
            rec[label] = dict(trajectory_xy=acc.tolist(), iterations=len(its), converged=conv,
                              vs_centre=lib.err(acc, centre), vs_roi_mean=lib.err(acc, roi_mean))
        global_other[f'{backend}-{case}'] = rec

OUT.write_text(json.dumps(dict(kind='offline ledger inputs; no MotionCorr execution', numpy=np.__version__,
    sources=dict(composition=C273, native='d751ff28594902eca75d665ff116e662653481aa', capture='6ae486785334fca635cfc9ad9e86026d656f3943'),
    fixtures_regenerated_hash_identical=True, ledger=ledger, first_iteration_global_objective=mechanisms,
    affine_noisy_global=global_other, script_sha256=sha(pathlib.Path(__file__).read_bytes()),
    lib_sha256=sha((here/'offline_stages_lib.py').read_bytes())), indent=1, allow_nan=False)+'\n')
for case, rows in mechanisms.items():
    print(case, [(r['window_range'], r['float32_ulp_at_peak'], r['float32_distinct_values']) for r in rows][:2])
for k, v in global_other.items():
    print(k, 'native', round(v['native_vs_centre']['rms_px'], 4), {l: round(v[l]['vs_centre']['rms_px'], 4) for l in ('specified_double', 'continuous_double', 'continuous_double_tol1e-9_max_iter50')})
print('single-iteration patches', [(r['backend'], r['case'], r['patches_single_iteration'], r['patches']) for r in ledger if r['patches']])
