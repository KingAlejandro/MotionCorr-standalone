#!/usr/bin/env python3
"""QF item 11: replay #208's EER compact matrix (W-EER-Q, PR #208 @ a5fa5429) on the frozen binaries.

Every case recorded in item_records/eer_208.json (from #208's evidence/cases + evidence/results) is
re-run with the recorded options and arms, in the QF lane (qual_lib.run_case: lane GPU flock per run,
bench-lock probe, UUID pin, nvidia-smi witness, /usr/bin/time -v). Binaries: $QF_W/build-nvcomp
(CUDA cases) and $QF_W/build-cpu vs Q1's CPU 1db86902 (#208's three CPU cases compared 0ac2726a
with 1db86902; the frozen CPU build must equal 1db86902). Not replayed: o1n_NOGUARD (a mutant build
used as #208's negative control) and the s00 smoke runs (no recorded result).

Inputs: corpus movies are hash-checked against docs/workload_corpus/corpus.md; the damaged copies
are regenerated with #208's eer_corrupt.py and must equal #208's recorded SHA-256. #208 did not
record eer_synth.py parameters, so the synthetic movies use the parameters declared in SYNTH and
their hashes are recorded here (not compared with #208's files).

Grading per case, against #208's record: every arm's exit status equals the recorded one; every
arm's --ingest_witness route list equals the recorded one; where #208 compared two arms, the
complete-tree comparison (main's compare_output_trees.py, #208's declared log allowances) passes
iff it passed then; every GPU arm that processed a movie (rc 0) is seen on the lane GPU only.
PASS = every replayed case passes. Run:
  QF_W=... QF_CPUS=... QF_GPU_UUID=... QF_GPU_LOCK=... \
    taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/item11_eer.py [--only c01,c02] [--skip-heavy]
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from qual_lib import *  # noqa: F401,F403
import product_campaign as pc  # noqa: E402

RECORD = json.loads((HERE / 'item_records' / 'eer_208.json').read_text())
ROOT = W / 'item11-eer'
D = Path.home() / 'motioncorr-validation-20261011-vm' / 'corpus' / 'data-https'
CORPUS = {
    'f3': 'EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer',
    'f4': 'EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer',
    'g': 'EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer',
    'g_gain': 'EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain',
}
# eer_corrupt.py arguments and #208's recorded output hash (evidence/fixture-sha256.txt)
CORRUPT = {
    'f3_trunc60': (['truncate', '0.6'], 'e23cd25ef3bb3600a057e36ddd3a091ceb20693fedaaf4fd910f4e2ed12ed8f7'),
    'f3_rand': (['random', '500', '4096'], 'e0cfbe1c7542de3a161ebe2ff139443c446fb33a4f166bd75f48470d602047da'),
    'f3_ff': (['ff', '700'], 'ebdb0e12dea7be0f059b230c7b6434ad62e9137f0cec6e9f0246f0e5aaf4099a'),
    'f3_zero': (['zero', '900'], 'c7cf6747e2b3d17c018ece718aff242ce8e765720da93a85bc816d052910ee54'),
}
# Declared eer_synth.py parameters (QF choice; #208's are unrecorded). Overflow movies carry hot pixels
# so that one output pixel counts g (or 4g at -1) per group; the codec movies carry random electrons.
SYNTH = {
    'n65000_4k_n240': (4096, ['--det', '4096', '--nfrac', '240', '--codec', '65000', '--bg', '20000']),
    'n65001_2k_n240': (2048, ['--det', '2048', '--nfrac', '240', '--codec', '65001', '--bg', '20000']),
    'n65002_2k_n240': (2048, ['--det', '2048', '--nfrac', '240', '--codec', '65002', '--bg', '20000']),
    'ovf4k_n49152': (4096, ['--det', '4096', '--nfrac', '49152', '--hot', '4', '--bg', '2000']),
    'ovf2k_n196608': (2048, ['--det', '2048', '--nfrac', '196608', '--hot', '1', '--bg', '2000']),
    'ovf4k_n196608': (4096, ['--det', '4096', '--nfrac', '196608', '--hot', '1', '--bg', '2000']),
}
ANGPIX = {'f3': 1.06, 'f4': 1.64, 'g': 0.97}  # #208 mkcase.py FAM
BATCH = {'b1': 'f3_trunc60', 'b5': 'f3_trunc60', 'b2': 'f3_rand', 'b3': 'f3_ff', 'b4': 'f3_zero'}
SYN_FOR = {'o1': 'ovf4k_n49152', 'o2': 'ovf4k_n49152', 'o3': 'ovf2k_n196608', 'o4': 'ovf2k_n196608',
           'o5': 'ovf4k_n196608', 'x1': 'n65000_4k_n240', 'x2': 'n65000_4k_n240', 'x3': 'n65002_2k_n240',
           'x4': 'n65002_2k_n240', 'x5': 'n65001_2k_n240'}
SKIP = {'o1n_NOGUARD_upm1_g16384': 'negative control on a mutant (guard-removed) build; not a frozen-binary case'}
HEAVY = {'m1_f4_g40_up2_full', 'm2_f4_g40_up2_100groups', 'c15_f3_g200_up3', 'c16_g_g150_up3'}
ALLOW = ['Staging this movie as native', 'Released native uint', 'Materialized native uint', 'EER grouping']
Q1_CPU = Path(os.environ.get('QF_REF_CPU_BIN', Q1 / 'build-cpu' / 'motioncorr'))


def ensure_inputs(log):
    """Corpus links (hash-checked), damaged copies (hash-checked against #208), synthetic movies (declared)."""
    inp = ROOT / 'inputs'
    inp.mkdir(parents=True, exist_ok=True)
    hashes = pc.parse_corpus_hashes()
    info = {}
    for key, rel in CORPUS.items():
        h = sha256_file(D / rel)
        exp = (hashes.get(rel) or {}).get('sha256')
        info[key] = {'path': str(D / rel), 'sha256': h, 'corpus_md': exp, 'match': h == exp}
        if exp and h != exp:
            raise SystemExit(f'{rel}: sha256 {h} != corpus.md {exp}')
    for name, (args, exp) in CORRUPT.items():
        dst = inp / f'{name}.eer'
        if not dst.exists():
            subprocess.run([PY, str(HERE / 'harness_eer' / 'eer_corrupt.py'), str(D / CORPUS['f3']), str(dst), *args], check=True)
        h = sha256_file(dst)
        info[name] = {'args': args, 'sha256': h, 'pr208_sha256': exp, 'match': h == exp}
        if h != exp:
            raise SystemExit(f'{name}: regenerated damaged movie differs from #208 ({h})')
    for name, (_, args) in SYNTH.items():
        dst = inp / f'{name}.eer'
        if not dst.exists():
            subprocess.run([PY, str(HERE / 'harness_eer' / 'eer_synth.py'), str(dst), *args], check=True,
                           capture_output=True)
        info[name] = {'args': args, 'sha256': sha256_file(dst), 'pr208_sha256': None}
    wrong = inp / 'gain_wrong_2048.mrc'
    if not wrong.exists():
        hdr = bytearray(1024)
        struct.pack_into('<4i', hdr, 0, 2048, 2048, 1, 2)
        struct.pack_into('<3i', hdr, 28, 2048, 2048, 1)
        hdr[208:212] = b'MAP '
        struct.pack_into('<i', hdr, 212, 0x00004144)
        wrong.write_bytes(bytes(hdr) + struct.pack('<f', 1.0) * (2048 * 2048))
    info['gain_wrong_2048'] = {'sha256': sha256_file(wrong), 'note': 'QF-written 2048x2048 float32 ones'}
    dump(info, log)
    return inp, info


def case_inputs(name, opts, inp):
    """Movie sources, gain/defect files and detector size for a recorded case name."""
    tag = name.split('_')[0]
    gain = None
    if tag in BATCH:
        fam, movies, det = 'f3', [D / CORPUS['f3'], inp / f'{BATCH[tag]}.eer', D / CORPUS['f3']], 4096
    elif tag == 'b6':
        fam, movies, det, gain = 'g', [D / CORPUS['g'], D / CORPUS['g']], 4096, inp / 'gain_wrong_2048.mrc'
    elif tag in SYN_FOR:
        fam, movies, det = None, [inp / f'{SYN_FOR[tag]}.eer'], SYNTH[SYN_FOR[tag]][0]
    else:  # c*, cc*, d*, m*: family token in the name
        fam = next(t for t in name.split('_')[1:] if t in ('f3', 'f4', 'g'))
        movies, det = [D / CORPUS[fam]], 4096
    if '--gainref' in opts and gain is None:
        gain = D / CORPUS['g_gain']
    defect = HERE / 'item_records' / 'eer_defects' / f'defect_{name}.txt' if '--defect_file' in opts else None
    up = int(opts[opts.index('--eer_upsampling') + 1])
    side = det // 2 if up == -1 else det << (up - 1)
    base = ANGPIX.get(fam, 1.0)  # as #208's mkcase.py: family pixel size scaled by the upsampling
    angpix = base / (2 ** (up - 1)) if up > 0 else base * 2
    return movies, gain, defect, side, angpix


def setup(name, rec, inp):
    opts = list(rec['options'])
    movies, gain, defect, side, angpix = case_inputs(name, opts, inp)
    d = ROOT / 'runs' / name
    if d.exists():
        shutil.rmtree(d)
    (d / 'in' / 'Movies').mkdir(parents=True)
    names = ['Movies/movie.eer'] if len(movies) == 1 else [f'Movies/movie{i + 1}.eer' for i in range(len(movies))]
    for n, src in zip(names, movies):
        os.symlink(Path(src).resolve(), d / 'in' / n)
    if gain:
        os.symlink(Path(gain).resolve(), d / 'in' / opts[opts.index('--gainref') + 1])
    if defect:
        shutil.copy(defect, d / 'in' / opts[opts.index('--defect_file') + 1])
    star = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
            '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5', '_rlnAmplitudeContrast #6',
            f'opticsGroup1 1 {angpix} 300 2.7 0.1', '', '# version 30001', '', 'data_movies', '', 'loop_',
            '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2'] + [f'{n} 1' for n in names] + ['']
    (d / 'in' / 'movies.star').write_text('\n'.join(star))
    dump({'schema_version': 1, 'expected_shape_xyz': [side, side, 1], 'joint_star': 'corrected_micrographs.star',
          'movies': names, 'input_star_sha256': sha256_file(d / 'in' / 'movies.star')}, d / 'in' / 'manifest.json')
    return d, opts


def compare(d, a, b):
    allow = []
    for p in ALLOW:
        allow += ['--allow-added-log-line', p]
    out = d / f'compare-{a}-vs-{b}.json'
    r = run_tool([PY, COMPARE_TREES, d / f'out-{a}', d / f'out-{b}', '--manifest', d / 'in' / 'manifest.json',
                  '--input-star', d / 'in' / 'movies.star', *allow, '--json-out', out])
    return {'rc': r['rc'], 'tail': (r['stdout'] + r['stderr'])[-500:]}


def run_one(name, rec, inp):
    d, opts = setup(name, rec, inp)
    res = {'case': name, 'desc': rec['desc'], 'recorded': rec['recorded'],
           'recorded_compare_rc': rec['recorded_compare_rc'], 'arms': {}, 'problems': []}
    if rec['binary_kind'] == 'cpu':
        i = opts.index('--gpu')
        del opts[i:i + 2]  # as #208's eer_cpu_compare.py: the CPU build has no GPU
        arms = [('ref_cpu_1db86902', Q1_CPU, None, 'base0ac2726a'), ('cpu', BIN['cpu'], None, 'cand1db86902')]
    else:
        arms = [(a, BIN['nvcomp'], rec['arm_ingest'][a], a) for a in rec['arms']]
    for arm, binary, ingest, rec_arm in arms:
        out = d / f'out-{arm}'
        out.mkdir()
        wit = d / f'{arm}.witness'
        args = ['--i', 'movies.star', '--o', f'{out}/', *opts]
        if ingest:
            args += ['--ingest', ingest, '--ingest_witness', wit]
        r = run_case(f'{name}-{arm}', binary, args, d / 'in', d / 'logs', gpu=rec['binary_kind'] != 'cpu', witness=wit)
        routes = [l.split()[-1] for l in (r.get('ingest_witness') or [])]
        res['arms'][arm] = {'rc': r.get('rc'), 'routes': routes, 'binary_sha256': r['binary_sha256'],
                            'gpu_witness': r.get('gpu_witness'), 'max_rss_kib': r.get('max_rss_kib'), 'wall_s': r.get('wall_s')}
        want = rec['recorded'][rec_arm]
        if r.get('rc') != want['rc']:
            res['problems'].append(f'{arm}: rc {r.get("rc")} != recorded {want["rc"]}')
        if routes != want['routes']:
            res['problems'].append(f'{arm}: routes {routes} != recorded {want["routes"]}')
        w = r.get('gpu_witness') or {}
        if rec['binary_kind'] != 'cpu' and r.get('rc') == 0 and not w.get('on_lane_gpu_only'):
            res['problems'].append(f'{arm}: not witnessed on the lane GPU only ({w.get("uuids_seen_for_pid")})')
    pair = rec['compare'] or (['ref_cpu_1db86902', 'cpu'] if rec['binary_kind'] == 'cpu' else None)
    if pair and rec['recorded_compare_rc'] is not None:
        if all(res['arms'][x]['rc'] == 0 for x in pair):
            res['compare'] = compare(d, *pair)
            if (res['compare']['rc'] == 0) != (rec['recorded_compare_rc'] == 0):
                res['problems'].append(f'compare {pair}: rc {res["compare"]["rc"]}, recorded {rec["recorded_compare_rc"]}')
        else:
            res['problems'].append(f'compare {pair} not run: an arm failed')
    for p in list(d.rglob('*.mrc')) + list(d.rglob('*.pdf')):
        if p.is_file() and not p.is_symlink():
            p.unlink()
    res['verdict'] = 'PASS' if not res['problems'] else 'FAIL'
    dump(res, ROOT / 'results' / f'{name}.json')
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='', help='comma-separated case-name prefixes')
    ap.add_argument('--skip-heavy', action='store_true', help='skip up2-F4 and up3 cases (reported UNRUN)')
    a = ap.parse_args()
    inp, info = ensure_inputs(ROOT / 'inputs.json')
    summary = {'record': RECORD['source'], 'binaries': {'nvcomp': sha256_file(BIN['nvcomp']), 'cpu': sha256_file(BIN['cpu']),
                                                       'ref_cpu_1db86902': sha256_file(Q1_CPU)}, 'cases': {}}
    for name, rec in RECORD['cases'].items():
        if name in SKIP:
            summary['cases'][name] = {'verdict': 'N/A', 'reason': SKIP[name]}
            continue
        if a.only and not any(name.startswith(p) for p in a.only.split(',')):
            continue
        if a.skip_heavy and name in HEAVY:
            summary['cases'][name] = {'verdict': 'UNRUN', 'reason': '--skip-heavy'}
            continue
        t0 = time.time()
        r = run_one(name, rec, inp)
        summary['cases'][name] = {'verdict': r['verdict'], 'problems': r['problems']}
        print(f'{name}: {r["verdict"]} {r["problems"]} ({time.time() - t0:.0f}s)', flush=True)
        dump(summary, ROOT / 'summary.json')
    v = [c['verdict'] for c in summary['cases'].values()]
    summary['totals'] = {k: v.count(k) for k in ('PASS', 'FAIL', 'UNRUN', 'N/A')}
    dump(summary, ROOT / 'summary.json')
    print('item 11:', summary['totals'])
    return 0 if v.count('FAIL') == 0 and v.count('UNRUN') == 0 and not a.only else (1 if v.count('FAIL') else 2)


if __name__ == '__main__':
    sys.exit(main())
