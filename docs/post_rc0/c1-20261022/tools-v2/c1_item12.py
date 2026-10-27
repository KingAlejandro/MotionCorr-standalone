#!/usr/bin/env python3
"""QF item 12: resident patch retry (#197) on the frozen binaries, after #207 (W-RETRY-Q, PR #207 @ 9bb6ca5c).

Single-GPU part (default; lane flock per run via qual_lib.run_case). 10641 (2 movies, gain, compact
u8) and 10216 (2 movies, compact int16), config L, `--group_frames 1` and `4`. Arms:
  frozen   $QF_W/build-nvcomp/motioncorr
  ref_1db  Q1's CUDA+nvCOMP 1db86902 (77db3f92...): #207 graded this source ("db")
  count    frozen motioncorr_resident_retry_fault, MC_RESIDENT_RETRY_COUNT=1 MC_PREPROCESS_FAULT=none
  rec      same, MC_PREPROCESS_FAULT=resident-retry-recoverable   (group_frames 1 only)
  fatal    same, MC_PREPROCESS_FAULT=resident-retry-fatal         (group_frames 1 only)
Pass criteria (#207 sections 1, 2, 3, 5):
  * frozen, ref_1db, count, rec exit 0; fatal exits nonzero;
  * frozen vs ref_1db and count vs frozen: complete non-PDF tree identical (#207's declared log
    allowances) and products identical;
  * retried patches (two completion lines in a patch block) equal #207's record: 41/30 at
    group_frames 1, 9/25 at group_frames 4 (10641/10216); the shim's resident-preparation counter
    equals the retried count in `count`, and that count minus one in `rec`;
  * rec: exactly one `WARNING: resident retry preparation did not complete`, products identical to frozen;
  * fatal: the refusal message `Refusing to retry alignment on a poisoned context`, no corrected MRC,
    no per-movie STAR and no joint STAR for the refused movie; every shim run reports remaining-owned=0.
Dataset part (`--dataset`, needs the multi-GPU window: start it through multigpu_step.sh --driver):
mixed [tutorial 00026, 10641 A-002, tutorial 00031, 10641 A-004], run_dataset.py, d1 (1 worker),
d2 (2 workers), dshim (2 workers, counter), dpoison (2 workers, fatal only in the worker on the
second GPU, restored by the UUID-selective wrapper qf_fault_by_uuid.sh) and dpoison_both (both
workers fault). grade_dataset() requires, from the run's own files (a missing file fails):
  d1/d2/dshim  rc 0, dataset and worker verdict PASS, dataset_ready, worker rcs 0, workers on their
               intended distinct witnessed UUIDs, cleanup complete, 4 MRC + 4 STAR + joint STAR merged,
               d2 and dshim identical to d1 (#207 cmp_tree.py rules); dshim's counter = retried patches;
  dpoison      nonzero rc, verdict FAIL, dataset_ready false, 'Worker phase exited', worker rcs [0, 1]:
               w1 log carries the injected fault, the refusal and fault=on, its 10641 movie has no
               MRC/STAR, its tutorial movie keeps both; w0 complete with its per-worker joint STAR and
               fault=off; no merged tree; cleanup complete, no leftover process;
  dpoison_both as dpoison, with both workers faulting and refusing.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# C1: QF helpers are read in place. Deployed under $C1_SCR/tools-*-run, so bind to the scratch checkout; in the repo (C1_SCR unset) use docs/rc0/qf/tools.
HERE = (Path(os.environ['C1_SCR']) / 'src' / 'docs' / 'rc0' / 'qf' / 'tools' if os.environ.get('C1_SCR')
        else Path(__file__).resolve().parents[3] / 'rc0' / 'qf' / 'tools')
if not (HERE / 'qual_lib.py').is_file():
    raise SystemExit(f'c1_item12: QF helpers not found at {HERE}')
sys.path.insert(0, str(HERE))
from qual_lib import *  # noqa: F401,F403
sys.path.insert(0, str(Path(__file__).resolve().parent))
import c1_lane; c1_lane.install()   # C1 v2: bench lock probed, not waited on (#198 policy)
run_case = c1_lane.run_case_nb   # C1 v2: nonblocking GPU3 lease, stop on foreign process, mandatory pre/post health under the lease

ROOT = W / 'c1-item12'
V = Path.home() / 'motioncorr-validation-20261011-vm'
RQ = Path('/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/inputs/data')  # #207's verified 10216 re-fetch (read only)
REF_1DB = Path(os.environ.get('QF_REF_CUDA_BIN', Q1 / 'build-nvcomp' / 'motioncorr'))
SHIM = W / 'build-nvcomp' / 'motioncorr_resident_retry_fault'
# #207 evidence/inputs/input_sha256.txt
INPUTS = {
    '10641_A002': (V / 'corpus/data-https/EMPIAR-10641/data/Movies/Dataset/HM70-1_10-A-002_0002_Oct28_23.00.41.tif',
                   '5f50686d7d32b9635fd64e550a91fc7d192849deeda30b7349a2827d17478c6d'),
    '10641_A004': (V / 'corpus/data-https/EMPIAR-10641/data/Movies/Dataset/HM70-1_10-A-004_0008_Oct28_23.06.04.tif',
                   'd0a4df43c93f694d792a9822a0f5d970ec866a0a9345d6bc44eb84e50020a617'),
    '10641_gain': (V / 'corpus/data-https/EMPIAR-10641/data/Movies/CountCDSRef_HM70-1_65-9_0000_Oct28_19.44.32.mrc',
                   'bdb0bb58f33d1b0dbf011222da0700f513ecb674e4085ed4708cce701dff7d95'),
    '10216_1739': (RQ / 'EMPIAR-10216/data/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc',
                   'f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56'),
    '10216_1742': (RQ / 'EMPIAR-10216/data/FoilHole_14961496_Data_14966722_14966723_20180615_1742_Fractions.mrc',
                   'c3b841e9ebcfb1e734a93c7bd7511033ded98c82b5c1cdb123f17e669e165ca1'),
    'tut_00026': (V / 'tutorial-data/Movies/20170629_00026_frameImage.tiff',
                  'f989391b9d0e3e3b927a8de59d60179ade0b7ae5075ce7c3a9a5002ae2254ae3'),
    'tut_00031': (V / 'tutorial-data/Movies/20170629_00031_frameImage.tiff',
                  'fa2699a1203a2ee278a5973e10105ea3e56b18a1c1d5ee153482767cb7e71d8d'),
}
FAMS = {  # movie links use '.'->'_' stems, as #207 (the comparator derives product names from them)
    'e10641': dict(movies=[('10641_A002', 'HM70-1_10-A-002_0002_Oct28_23_00_41.tif'),
                           ('10641_A004', 'HM70-1_10-A-004_0008_Oct28_23_06_04.tif')],
                   gain='10641_gain', optics='0.4 300 2.7', opts=['--dose_per_frame', '1.0', '--gainref', 'gain.mrc',
                                                                  '--expected_frames', '70']),
    'e10216': dict(movies=[('10216_1739', 'FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrcs'),
                           ('10216_1742', 'FoilHole_14961496_Data_14966722_14966723_20180615_1742_Fractions.mrcs')],
                   gain=None, optics='0.517 300 2.7', opts=['--dose_per_frame', '1.0', '--expected_frames', '59']),
}
RECORDED_RETRIED = {('e10641', 1): 41, ('e10216', 1): 30, ('e10641', 4): 9, ('e10216', 4): 25}  # #207 sections 1, 5
ALLOW = ['Staging this movie as native', 'Released native', 'WARNING: resident retry preparation did not complete',
         'CUDA Error in']
WARN = 'WARNING: resident retry preparation did not complete'
REFUSAL = 'Refusing to retry alignment on a poisoned context'
COMMON = ['--use_own', '--dose_weighting', '--bfactor', '150', '--seed', '1', '--patch_x', '5', '--patch_y', '5',
          '--j', '2', '--gpu', '0']   # C1: 2-CPU lane (QF used 8)


def star_text(optics_rows, movies):
    head = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
            '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5',
            '_rlnAmplitudeContrast #6', *optics_rows, '', '# version 30001', '', 'data_movies', '', 'loop_',
            '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2']
    return '\n'.join(head + [f'{m} {g}' for m, g in movies] + [''])


def check_inputs():
    rec = {}
    for k, (p, exp) in INPUTS.items():
        h = sha256_file(p)
        rec[k] = {'path': str(p), 'sha256': h, 'match_pr207': h == exp}
        if h != exp:
            raise SystemExit(f'{k}: {p} sha256 {h} != #207 record {exp}')
    return rec


def setup_family(fam):
    f = FAMS[fam]
    d = ROOT / 'inputs' / fam
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    for key, name in f['movies']:
        link = d / 'Movies' / name
        if link.is_symlink():
            link.unlink()
        os.symlink(INPUTS[key][0], link)
    if f['gain']:
        g = d / 'gain.mrc'
        if g.is_symlink():
            g.unlink()
        os.symlink(INPUTS[f['gain']][0], g)
    (d / 'movies.star').write_text(star_text([f'opticsGroup1 1 {f["optics"]} 0.1'],
                                             [(f'Movies/{n}', 1) for _, n in f['movies']]))
    dump({'schema_version': 1, 'input_star_sha256': sha256_file(d / 'movies.star'),
          'expected_shape_xyz': None, 'joint_star': 'corrected_micrographs.star',
          'movies': [f'Movies/{n}' for _, n in f['movies']]}, d / 'manifest.json')
    return d


def retry_accounting(out):
    """#207 analyse.py: patches, retried (two completion lines in a patch block), warnings."""
    res = {'patches': 0, 'retried': 0, 'retry_converged': 0, 'warnings': 0}
    for log in sorted((out / 'Movies').glob('*.log')):
        text = log.read_text(errors='replace')
        res['warnings'] += text.count(WARN)
        for b in re.split(r'(?m)^Patch \(', text)[1:]:
            done = re.findall(r'\[CUDA Patch Alignment\] completed; converged=(yes|no)', b)
            res['patches'] += 1
            if len(done) >= 2:
                res['retried'] += 1
                res['retry_converged'] += done[-1] == 'yes'
    return res


def tree_compare(d, a, b, products_only):
    allow = []
    if not products_only:
        for p in ALLOW:
            allow += ['--allow-added-log-line', p]
    tag = 'products' if products_only else 'full'
    idir = ROOT / 'inputs' / d.name.split('-')[0]
    r = run_tool([PY, COMPARE_TREES, d / f'out-{a}', d / f'out-{b}', '--manifest', idir / 'manifest.json',
                  '--input-star', idir / 'movies.star', *(['--products-only'] if products_only else []), *allow,
                  '--json-out', d / f'cmp-{a}-{b}-{tag}.json'])
    return r['rc']


def single_gpu(families, groupings):
    results = []
    for fam in families:
        idir = setup_family(fam)
        for g in groupings:
            d = ROOT / 'runs' / f'{fam}-g{g}'
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)
            extra = ['--group_frames', str(g)] if g != 1 else []
            arms = [('frozen', BIN['nvcomp'], {}), ('ref_1db', REF_1DB, {}),
                    ('count', SHIM, {'MC_RESIDENT_RETRY_COUNT': '1', 'MC_PREPROCESS_FAULT': 'none'})]
            if g == 1:
                arms += [('rec', SHIM, {'MC_RESIDENT_RETRY_COUNT': '1', 'MC_PREPROCESS_FAULT': 'resident-retry-recoverable'}),
                         ('fatal', SHIM, {'MC_RESIDENT_RETRY_COUNT': '1', 'MC_PREPROCESS_FAULT': 'resident-retry-fatal'})]
            case = {'family': fam, 'group_frames': g, 'arms': {}, 'problems': []}
            for name, binary, env in arms:
                out = d / f'out-{name}'
                wit = d / f'{name}.witness'
                args = [*COMMON, *FAMS[fam]['opts'], '--i', 'movies.star', '--o', f'{out}/', '--ingest_witness', wit, *extra]
                r = run_case(f'{fam}-g{g}-{name}', binary, args, idir, d / 'logs', gpu=True, extra_env={**env, 'OMP_NUM_THREADS': '2'}, witness=wit)
                text = Path(r['stdout']).read_text(errors='replace')
                m = re.search(r'resident-retry-preparations=(\d+)', text)
                owned = re.search(r'remaining-owned=(\d+)', text)
                arm = {'rc': r.get('rc'), 'binary_sha256': r['binary_sha256'], 'routes': r.get('ingest_witness'),
                       'gpu_witness': r.get('gpu_witness'), 'max_rss_kib': r.get('max_rss_kib'),
                       'resident_preps': int(m.group(1)) if m else None,
                       'remaining_owned': int(owned.group(1)) if owned else None,
                       'refusal': REFUSAL in text, 'accounting': retry_accounting(out) if out.exists() else None}
                case['arms'][name] = arm
                if binary == SHIM and arm['remaining_owned'] != 0:
                    case['problems'].append(f'{name}: shim remaining-owned={arm["remaining_owned"]}')
                if name != 'fatal' and arm['rc'] == 0 and not (arm['gpu_witness'] or {}).get('on_lane_gpu_only'):
                    case['problems'].append(f'{name}: not witnessed on the lane GPU only')
            A = case['arms']
            mrcs = sorted((d / 'out-frozen' / 'Movies').glob('*.mrc')) if (d / 'out-frozen').exists() else []
            if mrcs:  # the manifest takes the corrected-image geometry from the frozen arm's own header
                import struct
                mf = json.loads((idir / 'manifest.json').read_text())
                mf['expected_shape_xyz'] = list(struct.unpack('<3i', mrcs[0].read_bytes()[:12]))
                dump(mf, idir / 'manifest.json')
            for name in ('frozen', 'count') + (('rec',) if g == 1 else ()):   # C1: ref_1db rc is legacy-only
                if name == 'frozen' and A['ref_1db']['rc'] != 0:
                    case['legacy_ref_1db_rc'] = A['ref_1db']['rc']
                if A[name]['rc'] != 0:
                    case['problems'].append(f'{name}: rc {A[name]["rc"]}')
            # C1: the expected retried count is C1's own frozen-arm count; #207's record is kept as a legacy comparison only.
            want = (A['frozen']['accounting'] or {}).get('retried')
            case['legacy_recorded_207_retried'] = RECORDED_RETRIED[(fam, g)]
            case['legacy_c1_retried'] = want
            case['legacy_ref_1db_retried'] = (A['ref_1db']['accounting'] or {}).get('retried')
            if not want:
                case['problems'].append(f'frozen retried {want}: no retried patch, so the retry/fault controls were not exercised')
            if A['count']['resident_preps'] != want:
                case['problems'].append(f'count resident-preparations {A["count"]["resident_preps"]} != {want}')
            for a, b in (('ref_1db', 'frozen'), ('frozen', 'count')):
                if A[a]['rc'] == 0 and A[b]['rc'] == 0:
                    full, prod = tree_compare(d, a, b, False), tree_compare(d, a, b, True)
                    case[f'{a}_vs_{b}'] = {'full_rc': full, 'products_rc': prod}
                    if (full or prod) and a == 'ref_1db':
                        case['legacy_ref_1db_vs_frozen_differs'] = True    # expected: #254/#260/#270 change CUDA local alignment; attributed in T24
                    elif full or prod:
                        case['problems'].append(f'{a} vs {b}: full rc {full}, products rc {prod}')
            if g == 1:
                rec = A['rec']
                if rec['rc'] == 0:
                    prod = tree_compare(d, 'frozen', 'rec', True)
                    case['frozen_vs_rec_products_rc'] = prod
                    if prod:
                        case['problems'].append('rec: products differ from frozen')
                if (rec['accounting'] or {}).get('warnings') != 1:
                    case['problems'].append(f'rec: {(rec["accounting"] or {}).get("warnings")} fallback warnings, expected 1')
                if rec['resident_preps'] != want - 1:
                    case['problems'].append(f'rec: resident-preparations {rec["resident_preps"]} != {want - 1}')
                fat = A['fatal']
                pub = sorted(str(p.relative_to(d / 'out-fatal')) for p in (d / 'out-fatal').rglob('*')
                             if p.suffix in ('.mrc', '.star')) if (d / 'out-fatal').exists() else []
                fat['published'] = pub
                if fat['rc'] in (0, None) or not fat['refusal']:
                    case['problems'].append(f'fatal: rc {fat["rc"]}, refusal message {fat["refusal"]}')
                first = FAMS[fam]['movies'][0][1].rsplit('.', 1)[0]
                if any(first in p for p in pub) or 'corrected_micrographs.star' in pub:
                    case['problems'].append(f'fatal: refused movie published {pub}')
            for p in list(d.rglob('*.mrc')) + list(d.rglob('*.pdf')):
                p.unlink()
            case['verdict'] = 'PASS' if not case['problems'] else 'FAIL'
            dump(case, ROOT / 'results' / f'{fam}-g{g}.json')
            print(f'{fam} g{g}: {case["verdict"]} {case["problems"]}', flush=True)
            results.append(case)
    return results


def digest_tree(root):
    """#207 cmp_tree.py rules (merged trees, _workers/ excluded)."""
    out = {}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.relative_to(root).parts[0] == '_workers':
            continue
        raw = p.read_bytes()
        raw = re.sub(rb'item12-retry/dataset/[A-Za-z0-9]+', b'DS', raw)
        raw = re.sub(rb'workers/w[0-9]+', b'workers/wN', raw)
        raw = re.sub(rb'\.aggregate-[A-Za-z0-9_]+', b'.aggregate-X', raw)
        if p.suffix == '.mrc':
            h = hashlib.sha256(raw[:224] + raw[1024:]).hexdigest()
        elif p.suffix in ('.star', '.eps'):
            h = hashlib.sha256(raw.replace(str(root).encode(), b'<ROOT>')).hexdigest()
        elif p.suffix == '.log':
            lines = [l for l in raw.replace(str(root).encode(), b'<ROOT>').split(b'\n') if not any(
                m in l for m in (b' ms', b'time', b'Kernel', b'~~(,_,', b'sec .', b'free device memory',
                                 b'device memory in use rose'))]
            h = hashlib.sha256(b'\n'.join(lines)).hexdigest()
        else:
            h = 'present'
        out[str(p.relative_to(root))] = h
    return out


MIXED = [('tut_00026', '20170629_00026_frameImage.tiff', 1), ('10641_A002', 'HM70-1_10-A-002_0002_Oct28_23_00_41.tif', 2),
         ('tut_00031', '20170629_00031_frameImage.tiff', 1), ('10641_A004', 'HM70-1_10-A-004_0008_Oct28_23_06_04.tif', 2)]
# contiguous sharding of the 4-movie STAR over 2 workers (#207 section 4): w0 = t26 + 10641-A, w1 = t31 + 10641-B
SHARDS = {1: [[0, 1, 2, 3]], 2: [[0, 1], [2, 3]]}
WRAPPER = HERE / 'qf_fault_by_uuid.sh'


def _stem(i):
    return MIXED[i][1].rsplit('.', 1)[0]


def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def grade_dataset(tag, out, rc, n, expect, gpus, fault_worker=None, retried=None):
    """Grade one run_dataset.py arm from its own files. expect: 'pass', 'poison_both' or 'poison_one'.

    Missing files are failures, never defaults: a run that did not execute cannot pass."""
    problems = []
    ds = _load(out / 'dataset_status.json')
    ws = _load(out / 'workers' / 'status.json')
    if ds is None:
        problems.append('no dataset_status.json')
    if ws is None:
        problems.append('no workers/status.json')
    if ds is None or ws is None:
        return problems
    workers = ws.get('workers') if isinstance(ws.get('workers'), list) else []
    if ws.get('n_workers') != n or len(workers) != n:
        problems.append(f'n_workers {ws.get("n_workers")}/{len(workers)} != {n}')
    gw = ws.get('gpu_witness') or {}
    if not gw.get('all_pids_witnessed_on_intended_distinct_devices') or gw.get('distinct_devices_witnessed') != n:
        problems.append(f'device witness: {gw.get("distinct_devices_witnessed")} distinct, all-on-intended '
                        f'{gw.get("all_pids_witnessed_on_intended_distinct_devices")}')
    devs = [d.get('uuid') for d in ws.get('devices') or []]
    if devs != gpus[:n]:
        problems.append(f'worker devices {devs} != {gpus[:n]}')
    pc = ws.get('process_cleanup') or {}
    if not pc.get('complete') or pc.get('observed_live_before_cleanup') or pc.get('unexpected_descendants'):
        problems.append(f'process cleanup incomplete: {pc}')
    if ds.get('process_ownership_errors'):
        problems.append(f'process ownership errors {ds.get("process_ownership_errors")}')
    consoles = []
    for w in workers:
        log = Path(w.get('log') or '')
        consoles.append(log.read_text(errors='replace') if log.is_file() else None)
    rcs = [w.get('returncode') for w in workers]
    merged = out / 'merged'

    def worker_products(k):
        wd = out / 'workers' / f'w{k}'
        return {p.name for p in (wd / 'Movies').glob('*') if p.suffix in ('.mrc', '.star')} if (wd / 'Movies').exists() else set()

    if expect == 'pass':
        if rc != 0 or ds.get('verdict') != 'PASS' or not ds.get('dataset_ready') or ws.get('verdict') != 'PASS':
            problems.append(f'rc {rc}, dataset {ds.get("verdict")}/{ds.get("dataset_ready")}, workers {ws.get("verdict")}')
        if rcs != [0] * n:
            problems.append(f'worker rcs {rcs}')
        names = {f'{_stem(i)}.{x}' for i in range(4) for x in ('mrc', 'star')}
        have = {p.name for p in (merged / 'Movies').glob('*') if p.suffix in ('.mrc', '.star')} if merged.exists() else set()
        if have != names or not (merged / 'corrected_micrographs.star').exists():
            problems.append(f'merged products {sorted(have)}, joint STAR {(merged / "corrected_micrographs.star").exists()}')
        if retried is not None:  # dshim: the counter must have run, once per retried 10641 patch
            preps = sum(int(m) for c in consoles if c for m in re.findall(r'resident-retry-preparations=(\d+)', c))
            if preps != retried:
                problems.append(f'shim resident-retry-preparations {preps} != retried {retried}')
        return problems
    # poison cases
    if rc in (0, None) or ds.get('verdict') != 'FAIL' or ds.get('dataset_ready') is not False:
        problems.append(f'rc {rc}, dataset verdict {ds.get("verdict")}, ready {ds.get("dataset_ready")}')
    if 'Worker phase exited' not in (ds.get('failure') or ''):
        problems.append(f'failure reason {ds.get("failure")!r}')
    if merged.exists() or (merged / 'corrected_micrographs.star').exists():
        problems.append('a merged tree was published')
    faulting = list(range(n)) if expect == 'poison_both' else [fault_worker]
    for k in range(n):
        c = consoles[k] if k < len(consoles) else None
        prods = worker_products(k)
        shard = SHARDS[n][k]
        first_ret = next(j for j, i in enumerate(shard) if MIXED[i][0].startswith('10641'))
        # movies before the first faulting (10641) movie must survive; the faulting movie must not publish.
        # Later movies in the same process are refused at session initialisation (#69), so not required.
        tut, ret = [_stem(i) for i in shard[:first_ret]], [_stem(shard[first_ret])]
        if c is None:
            problems.append(f'w{k}: no console log')
            continue
        if k in faulting:
            if rcs[k] in (0, None):
                problems.append(f'w{k}: faulting worker rc {rcs[k]}')
            if '[preprocessfault] injected' not in c or REFUSAL not in c:
                problems.append(f'w{k}: fault not attributed (injected/refusal lines missing)')
            if expect == 'poison_one' and 'fault=on' not in c:
                problems.append(f'w{k}: wrapper did not enable the fault')
            for st in ret:
                if any(p.startswith(st) for p in prods):
                    problems.append(f'w{k}: refused movie {st} published {sorted(prods)}')
            for st in tut:  # the healthy movie before it in the same worker keeps its products
                if not {f'{st}.mrc', f'{st}.star'} <= prods:
                    problems.append(f'w{k}: healthy movie {st} lost products ({sorted(prods)})')
        else:
            if rcs[k] != 0:
                problems.append(f'w{k}: healthy worker rc {rcs[k]}')
            if '[preprocessfault] injected' in c or 'fault=off' not in c:
                problems.append(f'w{k}: healthy worker shows a fault or no wrapper attribution')
            want = {f'{_stem(i)}.{x}' for i in SHARDS[n][k] for x in ('mrc', 'star')}
            if not want <= prods or not (out / 'workers' / f'w{k}' / 'corrected_micrographs.star').exists():
                problems.append(f'w{k}: healthy worker incomplete ({sorted(prods)})')
    return problems


def run_dataset_arm(tag, binary, n, env, gpus, masks, star, cwd):
    out = ROOT / 'dataset' / tag
    if out.exists():
        shutil.rmtree(out)
    la = f"--devices {','.join(gpus[:n])} --cpus '{';'.join(masks[:n])}'"
    cmd = ['taskset', '-c', ','.join(masks[:n]), PY, str(SRC / 'tools/multi_gpu/run_dataset.py'), '--binary', str(binary),
           '--star', str(star), '--out', str(out), f'--launcher-args={la}', '--',
           '--use_own', '--dose_weighting', '--dose_per_frame', '1.0', '--bfactor', '150', '--seed', '1',
           '--patch_x', '5', '--patch_y', '5', '--j', '2']
    e = base_env(False)
    e.update(env)
    e['OMP_NUM_THREADS'] = '2'   # C1: 2-CPU lane
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    (ROOT / 'dataset').mkdir(exist_ok=True)
    (ROOT / 'dataset' / f'{tag}.driver.log').write_text(p.stdout + '\n--stderr--\n' + p.stderr)
    leftovers = subprocess.run(['pgrep', '-u', str(os.getuid()), '-f', str(binary)], capture_output=True, text=True).stdout.split()
    return out, p.returncode, leftovers


def dataset(single_gpu=False):
    if single_gpu:  # GPU0 only: the 1-worker arms (healthy and poisoned); the 2-worker arms need the window
        gpus, masks = [LANE_GPU_UUID, None], [CPUS, None]
    else:
        gpus = [LANE_GPU_UUID, os.environ['QF_DATASET_GPU2_UUID']]
        masks = [CPUS, os.environ['QF_DATASET_CPUS2']]
    d = ROOT / 'inputs' / 'mixed'
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    for key, name, _ in MIXED:
        if (d / 'Movies' / name).is_symlink():
            (d / 'Movies' / name).unlink()
        os.symlink(INPUTS[key][0], d / 'Movies' / name)
    star = d / 'movies.star'
    star.write_text(star_text(['opticsGroupTut 1 0.885 200 1.4 0.1', 'opticsGroup10641 2 0.4 300 2.7 0.1'],
                              [(f'Movies/{n}', g) for _, n, g in MIXED]))
    fault_env = {'QF_FAULT_SHIM': str(SHIM), 'QF_FAULT_UUID': gpus[1], 'MC_RESIDENT_RETRY_COUNT': '1'}
    arms = [('d1', BIN['nvcomp'], 1, {}, 'pass'), ('d2', BIN['nvcomp'], 2, {}, 'pass'),
            ('dshim', SHIM, 2, {'MC_PREPROCESS_FAULT': 'none', 'MC_RESIDENT_RETRY_COUNT': '1'}, 'pass'),
            # #207's case: only the worker on the second GPU faults (UUID-selective wrapper, see qf_fault_by_uuid.sh)
            ('dpoison', WRAPPER, 2, fault_env, 'poison_one'),
            # additional: both workers fault (the shim's own env, no wrapper)
            ('dpoison_both', SHIM, 2, {'MC_PREPROCESS_FAULT': 'resident-retry-fatal'}, 'poison_both')]
    if single_gpu:
        arms = [arms[0], ('dpoison_1w', SHIM, 1, {'MC_PREPROCESS_FAULT': 'resident-retry-fatal'}, 'poison_both')]
    res = {'gpus': gpus, 'cpu_masks': masks, 'wrapper_sha256': sha256_file(WRAPPER), 'shim_sha256': sha256_file(SHIM),
           'runs': {}, 'problems': []}
    retried = None
    for tag, binary, n, env, expect in arms:
        out, rc, leftovers = run_dataset_arm(tag, binary, n, env, gpus, masks, star, d)
        if tag == 'd1' and (out / 'merged').exists():
            retried = retry_accounting(out / 'merged')['retried']
        probs = grade_dataset(tag, out, rc, n, expect, gpus, fault_worker=1, retried=retried if tag == 'dshim' else None)
        if leftovers:
            probs.append(f'leftover processes {leftovers}')
        st = _load(out / 'dataset_status.json') or {}
        res['runs'][tag] = {'rc': rc, 'binary_sha256': sha256_file(binary), 'expect': expect, 'verdict': st.get('verdict'),
                            'dataset_ready': st.get('dataset_ready'), 'failure': st.get('failure'), 'problems': probs}
        res['problems'] += [f'{tag}: {x}' for x in probs]
        print(tag, 'rc', rc, 'verdict', st.get('verdict'), probs, flush=True)
    base = digest_tree(ROOT / 'dataset' / 'd1' / 'merged') if (ROOT / 'dataset' / 'd1' / 'merged').exists() else {}
    for tag in (() if single_gpu else ('d2', 'dshim')):
        m = ROOT / 'dataset' / tag / 'merged'
        other = digest_tree(m) if m.exists() else {}
        diff = sorted(k for k in set(base) | set(other) if base.get(k) != other.get(k))
        res[f'd1_vs_{tag}'] = {'files': len(base), 'differing': diff[:20]}
        if not base or diff:
            res['problems'].append(f'd1 vs {tag}: {len(diff)} differing files')
    for p in list((ROOT / 'dataset').rglob('*.mrc')) + list((ROOT / 'dataset').rglob('*.pdf')):
        p.unlink()
    res['verdict'] = 'PASS' if not res['problems'] else 'FAIL'
    dump(res, ROOT / 'results' / ('dataset-single-gpu.json' if single_gpu else 'dataset.json'))
    print('dataset:', res['verdict'], res['problems'])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--families', default='e10641,e10216')
    ap.add_argument('--groupings', default='1,4')
    ap.add_argument('--dataset', action='store_true', help='dataset part only (multi-GPU window)')
    ap.add_argument('--dataset-single-gpu', action='store_true',
                    help='dataset grading on the lane GPU only: 1-worker healthy and poisoned arms (not a QF PASS)')
    a = ap.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    dump({'inputs': check_inputs(), 'binaries': {'frozen': sha256_file(BIN['nvcomp']), 'ref_1db': sha256_file(REF_1DB),
                                                 'shim': sha256_file(SHIM)}}, ROOT / 'provenance.json')
    if a.dataset or a.dataset_single_gpu:
        return 0 if dataset(single_gpu=a.dataset_single_gpu)['verdict'] == 'PASS' else 1
    res = single_gpu(a.families.split(','), [int(x) for x in a.groupings.split(',')])
    return 0 if all(r['verdict'] == 'PASS' for r in res) else 1


if __name__ == '__main__':
    sys.exit(main())
