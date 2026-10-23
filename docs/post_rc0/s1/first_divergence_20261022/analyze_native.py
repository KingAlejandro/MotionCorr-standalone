#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Evaluate the collected W4 native campaign against its frozen expectations.

usage: analyze_native.py COLLECTED RAW275 FILE_INDEX275 REPO OUT.json
COLLECTED is a local copy of the remote task scratch (runs/, run-logs/, logs/,
fixtures/MANIFEST.json, campaign-manifest.json, truth-*.txt). An expectation
outcome is a diagnostic statement about this campaign, not an accuracy PASS.
"""
import hashlib, json, pathlib, re, subprocess, sys
import numpy as np

C, RAW, INDEX, REPO, OUT = (pathlib.Path(a) for a in sys.argv[1:6])
def sha(b): return hashlib.sha256(b).hexdigest()
M = json.loads((C/'campaign-manifest.json').read_text())
committed_manifest = subprocess.check_output(['git', 'show', 'daaa2217:docs/post_rc0/s1/first_divergence_20261022/campaign-manifest.json'], cwd=REPO)
assert (C/'campaign-manifest.json').read_bytes() == committed_manifest, 'campaign manifest differs from the frozen commit'
r275 = json.loads(subprocess.check_output(['git', 'show', '6ae486785334fca635cfc9ad9e86026d656f3943:docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json'], cwd=REPO))
assert sha(INDEX.read_bytes()) == r275['array_product_index_sha256']
index = json.loads(INDEX.read_text())['files']
def load275(rel):
    b = (RAW/rel).read_bytes(); assert sha(b) == index[rel]['sha256'], rel; return b

def star_global(text):
    block = text.split('data_global_shift', 1)[1].split('data_', 1)[0]
    return np.array([[float(v) for v in l.split()[1:]] for l in block.splitlines() if re.match(r'^\s*\d+\s+[-+.\deE]+\s+[-+.\deE]+\s*$', l)])

def state(path):
    rows = [l.split() for l in path.read_text().splitlines()]
    return np.array([[float(r[2]), float(r[3])] for r in rows]), [int(r[0]) for r in rows]

def mrc_parts(b):
    nsymbt = int.from_bytes(b[92:96], 'little')
    labels = re.sub(rb'\d{2,4}[-/:]\d{2}[-/:]\d{2,4}|\d{2}:\d{2}:\d{2}', b'T', b[224:1024])
    return b[:224], labels, b[1024+nsymbt:]

def err(t, truth):
    v = np.linalg.norm(t-truth, axis=1); return dict(rms_px=float(np.sqrt(np.mean(v*v))), max_px=float(v.max()))

truth_files = {n: np.array([[float(v) for v in l.split()] for l in (C/n).read_text().splitlines()]) for n in
               ['truth-integer.txt', 'truth-fractional.txt', 'truth-integer-perturbed.txt']}
arms = {}
for arm in M['arms']:
    lab, case, be = arm['label'], arm['case'], arm['backend']
    d = C/'runs'/lab
    log = (d/'out'/f'{case}.log').read_text()
    exitcode = int((C/'run-logs'/f'{lab}.exit').read_text())
    check_exit = int((C/'run-logs'/f'check-{lab}.exit').read_text())
    chk = json.loads((d/'checker.json').read_text())
    final, _ = state(d/'state'/'global-final.txt')
    iters, inum = state(d/'state'/'global-iterations.txt')
    star = star_global((d/'out'/f'{case}.star').read_text())
    truth = truth_files[f'truth-{case}.txt']
    rec = dict(backend=be, case=case, env=arm['env'], exit=exitcode, checker_exit=check_exit,
               witness_injected=log.count('W4 injected global shifts'), witness_fixed=log.count('W4 fixed frame-0 reference'),
               global_rmsd_log=[float(x) for x in re.findall(r'Iteration \d+: RMSD = ([-+.\deE]+) px', log.split('Global alignment', 1)[1])],
               runtime_global_xy=final.tolist(), iterations_recorded=sorted(set(inum)),
               runtime_vs_truth=err(final, truth), star_vs_runtime_max_px=float(np.max(np.linalg.norm(star-final, axis=1))),
               checker=dict(accuracy=chk['accuracy_status'], sampling=chk['sampling_status'], field_px=chk['field_px'],
                            field_angstrom=chk['field_angstrom'], published_sum=chk['signal'].get('published_sum_divided_by_frames'),
                            true_motion_bilinear=chk['signal']['true_motion_bilinear'], uncorrected=chk['signal']['uncorrected']),
               files={str(p.relative_to(C)): sha(p.read_bytes()) for p in sorted(d.rglob('*')) if p.is_file()})
    arms[lab] = rec

def expect(lab):
    a = arms[lab]; e = []
    kind = lab.split('-')[0]
    e.append(('exit 0', a['exit'] == 0))
    if kind == 'neutral':
        e.append(('no witness', a['witness_injected'] == a['witness_fixed'] == 0))
        base = f"runs/{a['backend']}-integer-off/"
        ref = np.array([[float(v) for v in l.split()[1:]] for l in load275(base+'state/global.txt').decode().splitlines()])
        e.append(('runtime trajectory equals #275 capture-off exactly', bool(np.array_equal(ref, np.array(a['runtime_global_xy'])))))
        mine = (C/'runs'/lab/'out'/'integer.star').read_bytes(); theirs = load275(base+'out/integer.star')
        e.append(('STAR equal after output-prefix normalization', mine.replace(str(C/'runs'/lab/'out').encode(), b'OUT') == theirs.replace(b'/mnt/clathrin/alex-motioncorr-residual-ccf-20261022-805d9de2/runs/'+f"{a['backend']}-integer-off/out".encode(), b'OUT')))
        e.append(('MRC equal except timestamp label', mrc_parts((C/'runs'/lab/'out'/'integer.mrc').read_bytes()) == mrc_parts(load275(base+'out/integer.mrc'))))
        e.append(('checker accuracy FAIL (historical)', a['checker']['accuracy'] == 'FAIL'))
    elif kind in ('truth', 'perturbed'):
        f = 'truth-integer-perturbed.txt' if kind == 'perturbed' else f"truth-{a['case']}.txt"
        e.append(('witness once', a['witness_injected'] == 1 and a['witness_fixed'] == 0))
        e.append(('runtime equals injected file exactly', bool(np.array_equal(np.array(a['runtime_global_xy']), truth_files[f]))))
        e.append(('STAR vs runtime <= 5e-6 px', a['star_vs_runtime_max_px'] <= 5e-6))
        ps = a['checker']['published_sum']['contrast_normalized_rmse']
        if kind == 'truth':
            e.append(('checker accuracy PASS by construction', a['checker']['accuracy'] == 'PASS'))
            e.append(('published sum contrast-normalized RMSE <= 1e-3', ps <= 1e-3))
        else:
            e.append(('checker accuracy FAIL', a['checker']['accuracy'] == 'FAIL'))
            ref = arms[lab.replace('perturbed', 'truth')]['checker']['published_sum']['contrast_normalized_rmse']
            e.append(('published sum error >= 10x truth arm', ps >= 10*ref))
    elif kind == 'fixedref':
        e.append(('witness once', a['witness_fixed'] == 1 and a['witness_injected'] == 0))
        if a['case'] == 'integer':
            e.append(('runtime trajectory equals truth (0 px)', a['runtime_vs_truth']['max_px'] == 0.0))
        else:
            e.append(('checker accuracy FAIL', a['checker']['accuracy'] == 'FAIL'))
            e.append(('field rms within 0.2-0.45 px (prediction 0.26-0.34)', 0.2 <= a['checker']['field_px']['rms'] <= 0.45))
    return [dict(expectation=n, met=bool(v)) for n, v in e]

for lab in arms: arms[lab]['expectations'] = expect(lab)
summary = {lab: dict(all_met=all(x['met'] for x in a['expectations']), runtime_rms_px=a['runtime_vs_truth']['rms_px'],
                     checker=a['checker']['accuracy'], field_rms_px=a['checker']['field_px']['rms'],
                     published_sum_cnrmse=(a['checker']['published_sum'] or {}).get('contrast_normalized_rmse'))
           for lab, a in arms.items()}
OUT.write_text(json.dumps(dict(kind='W4 native campaign evaluation', summary=summary, arms=arms,
    inputs=json.loads((C/'run-logs'/'inputs.json').read_text()), build=json.loads((C/'logs'/'binary-hashes.json').read_text()),
    source_identity=json.loads((C/'logs'/'source-identity.json').read_text()),
    script_sha256=sha(pathlib.Path(__file__).read_bytes())), indent=1, allow_nan=False)+'\n')
for lab, s in summary.items(): print(lab, s)
for lab, a in arms.items():
    for x in a['expectations']:
        if not x['met']: print('NOT MET', lab, x['expectation'])
