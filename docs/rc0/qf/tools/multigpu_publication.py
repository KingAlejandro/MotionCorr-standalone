#!/usr/bin/env python3
"""Item 5: 24 tutorial movies through tools/multi_gpu/run_dataset.py with 1, 2 and 4 workers.

Must be started by multigpu_step.sh, which already holds the four correctness locks and the
bench lock and has pinned this process to $QF_MG_CPU_A + $QF_MG_CPU_B. Per arm it checks the
documented publication contract (dataset_status/aggregate/worker status/shard ownership/joint
STAR/logfile.pdf/process cleanup) and compares the published per-movie products across
worker counts, and against a single-process single-GPU run, strictly.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(os.environ.get('QF_W', '/mnt/clathrin/alex-motioncorr-rc0/W-QF-PREP')) / 'src/tools/profiling'))
from qual_lib import *  # noqa: F401,F403
from lib import identity  # noqa: E402

UUID = {0: 'GPU-eddb42fe-4f9a-adde-76d3-b924e14add54', 1: 'GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d',
        2: 'GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598', 3: 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'}
DATA = Path.home() / 'motioncorr-validation-20261011-vm' / 'tutorial-data'
TOOLS = SRC / 'tools/multi_gpu'
OUT = W / 'multigpu'
TEXT = ('.star', '.eps', '.lst', '.log', '.txt')
# (name, devices, per-worker cpu masks, j)
# QF change: the fixed 16-CPU budget comes from QF_MG_CPU_A / QF_MG_CPU_B (two 8-CPU ranges
# 'lo-hi', default 96-103 and 104-111); the 1-worker arm and the s0 reference use QF_MG_W1_GPU
# (default 0). Q1 used 104-111 + 64-71 and GPU1.
def _split(r):
    lo, hi = map(int, r.split('-'))
    return f'{lo}-{lo + 3}', f'{lo + 4}-{hi}'


MG_A = os.environ.get('QF_MG_CPU_A', '96-103')
MG_B = os.environ.get('QF_MG_CPU_B', '104-111')
MG_ALL = f'{MG_A},{MG_B}'
W1_GPU = int(os.environ.get('QF_MG_W1_GPU', '0'))
W2_GPUS = [W1_GPU, (W1_GPU + 1) % 4]
ARMS = [
    ('w1', [W1_GPU], [MG_ALL], 16),
    ('w2', W2_GPUS, [MG_A, MG_B], 8),
    ('w4', [0, 1, 2, 3], [*_split(MG_A), *_split(MG_B)], 4),
]


def movie_list(star=None):
    txt = (star or DATA / 'movies.star').read_text()
    return re.findall(r'^(Movies/\S+\.(?:tiff|tif|eer))\s', txt, flags=re.M)


def star_rows(path):
    txt = Path(path).read_text()
    return re.findall(r'(\S+\.mrc)\s+(\S+\.star)', txt)


def pdf_pages(path):
    r = subprocess.run(['gs', '-q', '-dNODISPLAY', '-dNOSAFER', '-c',
                        f'({path}) (r) file runpdfbegin pdfpagecount = quit'], capture_output=True, text=True)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def filtered_copy(src: Path, dst: Path):
    """Hardlink copy of a published tree without _workers/, text products rewritten to dst's root.

    Rewritten: the tree's own root, the producing workers' output roots (<run>/workers/wK, which the
    per-movie EPS/log/.lst embed) and the private aggregate staging dir. `logfile.pdf.lst` (an
    aggregate-only leftover that a single-process run deletes, runner.cpp:1854) is not copied; this
    is declared in the report. MRC/STAR bytes are never rewritten except the root inside STARs.
    """
    if dst.exists():
        shutil.rmtree(dst)
    run = src.parent
    pats = [re.escape(str(r)) for r in {src, src.resolve()}]
    worker_re = re.compile('(?:' + '|'.join(re.escape(str(r)) + r'/workers/w\d+' for r in {run, run.resolve()}) + ')')
    stage_re = re.compile('(?:' + '|'.join(pats) + r')/\.aggregate-[A-Za-z0-9_]+')
    root_re = re.compile('(?:' + '|'.join(pats) + ')')
    for p in sorted(src.rglob('*')):
        rel = p.relative_to(src)
        if rel.parts[0] == '_workers' or p.is_dir() or rel.name == 'logfile.pdf.lst':
            continue
        q = dst / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in TEXT:
            t = p.read_bytes().decode('latin-1')
            t = stage_re.sub(str(dst), t)
            t = worker_re.sub(str(dst), t)
            t = root_re.sub(str(dst), t)
            q.write_bytes(t.encode('latin-1'))
        else:
            os.link(p, q)


def contract(name, run, movies, devices):
    c = {'checks': {}, 'problems': []}
    ds = json.loads((run / 'dataset_status.json').read_text())
    ag = json.loads((run / 'aggregate.json').read_text()) if (run / 'aggregate.json').exists() else {}
    ws = json.loads((run / 'workers/status.json').read_text())
    sm = json.loads((run / 'workers/shards/shard_manifest.json').read_text())
    c['dataset_status'] = {k: ds.get(k) for k in ('verdict', 'dataset_ready', 'workers_complete', 'ownership_mode',
                                                   'process_ownership_errors', 'cleanup', 'dataset_wall_s',
                                                   'worker_phase_wall_s', 'aggregate_phase_wall_s', 'aggregate_cpu_mask',
                                                   'failure', 'binary_sha256', 'input_star_sha256')}
    c['aggregate'] = {k: ag.get(k) for k in ('verdict', 'dataset_ready', 'input_type', 'row_order', 'problems', 'joint_star_problems')}
    c['workers_status'] = {k: ws.get(k) for k in ('verdict', 'n_workers', 'cpu_masks', 'cpu_budget_covered', 'devices', 'device_witness')
                           if k in ws}
    c['workers_status']['worker_records'] = [
        {k: w.get(k) for k in ('rc', 'return_code', 'device', 'uuid', 'gpu_uuid', 'witness', 'device_witness', 'cpu_mask',
                                'mask_witness', 'sampled_peak_gpu_memory_mib') if k in w}
        for w in ws.get('workers', [])] if isinstance(ws.get('workers'), list) else ws.get('workers')
    c['sampled_peak_gpu_memory_mib'] = ws.get('sampled_peak_gpu_memory_mib')
    chk = c['checks']
    chk['dataset_ready'] = bool(ds.get('verdict') == 'PASS' and ds.get('dataset_ready') and ds.get('workers_complete'))
    chk['aggregate_pass'] = bool(ag.get('verdict') == 'PASS' and ag.get('dataset_ready'))
    chk['workers_pass'] = ws.get('verdict') == 'PASS'
    # shard ownership: disjoint, covering, each worker's products == its shard
    n = len(devices)
    shards = None
    for key in ('shards', 'workers', 'assignments'):
        if isinstance(sm.get(key), list):
            shards = sm[key]
            break
    c['shard_manifest_keys'] = sorted(sm)
    stems = lambda names: sorted(Path(m).stem for m in names)
    owned = {}
    for k in range(n):
        wd = run / 'workers' / f'w{k}'
        owned[k] = sorted(p.stem for p in (wd / 'Movies').glob('*.mrc')) if (wd / 'Movies').exists() else []
    allowned = [s for v in owned.values() for s in v]
    want = stems(movies)
    chk['worker_products_partition_input'] = bool(sorted(allowned) == want and len(set(allowned)) == len(allowned))
    chk['every_worker_nonempty'] = all(owned[k] for k in owned)
    c['worker_movie_counts'] = {f'w{k}': len(v) for k, v in owned.items()}
    # shard files: star row names per shard
    shard_stars = sorted((run / 'workers/shards').glob('*.star'))
    shard_members = {}
    for s in shard_stars:
        shard_members[s.name] = sorted(Path(m).stem for m in re.findall(r'^(Movies/\S+\.(?:tiff|tif|eer))', s.read_text(), flags=re.M))
    c['shard_members_counts'] = {k: len(v) for k, v in shard_members.items()}
    if shard_members:
        mem = [x for v in shard_members.values() for x in v]
        chk['shards_disjoint_and_cover_input'] = bool(sorted(mem) == want and len(set(mem)) == len(mem))
        # worker k's published products must be exactly shard k's members, whatever the shard file order
        chk['worker_products_match_a_shard'] = sorted(map(tuple, owned.values())) == sorted(map(tuple, shard_members.values()))
    # merged tree
    merged = run / 'merged'
    mrcs = sorted(p.stem for p in merged.glob('Movies/*.mrc'))
    stars = sorted(p.stem for p in merged.glob('Movies/*.star'))
    chk['merged_inventory_24'] = bool(mrcs == want and stars == want)
    rows = star_rows(merged / 'corrected_micrographs.star') if (merged / 'corrected_micrographs.star').exists() else []
    chk['joint_star_row_order_equals_input'] = bool([Path(r[0]).stem for r in rows] == [Path(m).stem for m in movies])
    chk['joint_star_paths_inside_merged'] = all(str(Path(r[0]).resolve()).startswith(str(merged.resolve())) for r in rows)
    pdf = merged / 'logfile.pdf'
    c['logfile_pdf'] = {'exists': pdf.exists(), 'bytes': pdf.stat().st_size if pdf.exists() else None,
                        'pages': pdf_pages(pdf) if pdf.exists() else None}
    chk['logfile_pdf_present'] = bool(pdf.exists() and pdf.stat().st_size > 0)
    # worker aggregates are diverted, not published
    wk = {}
    for k in range(n):
        wj = merged / '_workers' / f'w{k}' / 'corrected_micrographs.star'
        wk[f'w{k}'] = len(star_rows(wj)) if wj.exists() else None
    c['worker_aggregate_rows_under__workers'] = wk
    chk['worker_aggregates_diverted_not_published'] = bool(len(rows) == len(movies) and
        all(v is not None and v < len(movies) for v in wk.values()) if n > 1 else True)
    # leftover owned processes
    ps = subprocess.run(['pgrep', '-u', str(os.getuid()), '-af', str(BIN['nvcomp'])], capture_output=True, text=True).stdout
    leftovers = [l for l in ps.splitlines() if 'pgrep' not in l]
    c['leftover_motioncorr_processes_after_run'] = leftovers
    chk['no_leftover_processes'] = not leftovers
    c['problems'] = [k for k, v in chk.items() if not v]
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='G,L')
    ap.add_argument('--mixed', action='store_true', help='mixed-format 2-worker dataset (coordinator steer 2)')
    ap.add_argument('--arms', default='w1,w2,w4', help='QF: subset of worker arms, e.g. w2 for a smoke run')
    ap.add_argument('--no-s0', action='store_true', help='QF: skip the single-process reference arm')
    ap.add_argument('--dry-run', action='store_true', help='QF: print the launcher commands and exit')
    a = ap.parse_args()
    global ARMS
    ARMS = [arm for arm in ARMS if arm[0] in a.arms.split(',')]
    if a.mixed:
        return main_mixed()
    movies = movie_list()
    assert len(movies) == 24, len(movies)
    summ = W / 'summaries' / 'multigpu'
    summ.mkdir(parents=True, exist_ok=True)
    star = DATA / 'movies.star'
    manifest = {'schema_version': 1, 'input_star_sha256': sha256_file(star), 'expected_shape_xyz': None,
                'joint_star': 'corrected_micrographs.star', 'movies': movies}
    all_res = {'movies': len(movies), 'input_star_sha256': manifest['input_star_sha256'],
               'binary': str(BIN['nvcomp']), 'binary_sha256': sha256_file(BIN['nvcomp']), 'configs': {}}
    for cfg in a.configs.split(','):
        res = {'arms': {}}
        base = OUT / cfg
        if base.exists() and not a.dry_run:
            shutil.rmtree(base)
        base.mkdir(parents=True, exist_ok=True)
        pa = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150', '--seed', '1',
              '--expected_frames', '24', '--gainref', 'Movies/gain.mrc', '--ingest', 'auto']
        if cfg == 'L':
            pa += ['--patch_x', '5', '--patch_y', '5']
        # single-process single-GPU reference (QF_MG_W1_GPU)
        s0 = base / 's0'
        if a.dry_run:
            print(f'{cfg} s0:', BIN['nvcomp'], '--i', star, '--o', f'{s0}/', '--j 8 --gpu 0', *pa,
                  f'(CUDA_VISIBLE_DEVICES={UUID[W1_GPU]})', flush=True)
        elif not a.no_s0:
            r = run_case(f'{cfg}-s0', BIN['nvcomp'], ['--i', star, '--o', f'{s0}/', '--j', '8', '--gpu', '0', *pa],
                         DATA, base / 'logs', gpu=False, extra_env={'CUDA_VISIBLE_DEVICES': UUID[W1_GPU], 'CUDA_DEVICE_ORDER': 'PCI_BUS_ID'},
                         witness=None)
            res['arms']['s0'] = {'run': r}
        for name, devs, masks, j in ARMS:
            run = base / name
            la = f"--devices {','.join(UUID[d] for d in devs)} --cpus '{';'.join(masks)}' --cpu-budget 16"
            cmd = ['taskset', '-c', MG_ALL, PY, str(TOOLS / 'run_dataset.py'), '--binary', str(BIN['nvcomp']),
                   '--star', str(star), '--out', str(run), f'--launcher-args={la}',
                   '--required-products=.mrc,.star,_shifts.eps', '--',
                   '--use_own', '--j', str(j), '--max_io_threads', str(j), *pa[1:]]
            if a.dry_run:
                print(f'{cfg} {name}:', ' '.join(map(str, cmd)), flush=True)
                continue
            env = base_env(False)
            env['PYTHONUNBUFFERED'] = '1'
            t0 = time.monotonic()
            p = subprocess.run(cmd, cwd=DATA, env=env, capture_output=True, text=True)
            wall = time.monotonic() - t0
            (base / 'logs').mkdir(exist_ok=True)
            (base / 'logs' / f'{name}.driver.log').write_text(p.stdout + '\n--stderr--\n' + p.stderr)
            arm = {'devices': devs, 'device_uuids': [UUID[d] for d in devs], 'cpu_masks': masks, 'j': j,
                   'argv': cmd[3:], 'rc': p.returncode, 'wall_s_outer': round(wall, 2)}
            if (run / 'dataset_status.json').exists():
                arm['contract'] = contract(name, run, movies, devs)
            res['arms'][name] = arm
            print(cfg, name, 'rc', p.returncode, 'problems', arm.get('contract', {}).get('problems'), f'{wall:.0f}s', flush=True)
        if a.dry_run:
            continue
        # strict comparisons across arms, on filtered copies
        cmpdir = base / 'cmp'
        trees = {}
        for name, *_ in ARMS:
            if (base / name / 'merged').exists():
                filtered_copy(base / name / 'merged', cmpdir / name)
                trees[name] = cmpdir / name
        if (base / 's0').exists() and not a.no_s0:
            filtered_copy(base / 's0', cmpdir / 's0')
            trees['s0'] = cmpdir / 's0'
        dims = None
        for t in trees.values():
            m = next(iter(sorted(t.glob('Movies/*.mrc'))), None)
            if m:
                import struct
                dims = list(struct.unpack('<3i', m.read_bytes()[:12]))
                break
        manifest['expected_shape_xyz'] = dims
        dump(manifest, base / 'manifest.json')
        res['comparisons'] = {}
        names = list(trees)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                x, y = names[i], names[j]
                key = f'{x}_vs_{y}'
                ident = identity.compare_trees(str(trees[x]), str(trees[y]))
                prod = run_tool([PY, COMPARE_TREES, trees[x], trees[y], '--manifest', base / 'manifest.json',
                                 '--input-star', star, '--products-only', '--json-out', base / f'cmp-{key}-products.json'])
                full = run_tool([PY, COMPARE_TREES, trees[x], trees[y], '--manifest', base / 'manifest.json',
                                 '--input-star', star, '--json-out', base / f'cmp-{key}-full.json'])
                fd = json.loads((base / f'cmp-{key}-full.json').read_text()) if (base / f'cmp-{key}-full.json').exists() else {}
                pd = json.loads((base / f'cmp-{key}-products.json').read_text()) if (base / f'cmp-{key}-products.json').exists() else {}
                res['comparisons'][key] = {
                    'identity_lib_status': ('PASS' if ident.get('identical') else 'FAIL'),
                    'identity_lib_detail': {k: v for k, v in ident.items() if k != 'files'},
                    'compare_output_trees_products_only_rc': prod['rc'], 'products_only_status': pd.get('status'),
                    'products_only_different': pd.get('different_products'),
                    'compare_output_trees_full_rc': full['rc'], 'full_status': fd.get('status'),
                    'full_different_files': fd.get('different_files'), 'full_tail': (full['stdout'] + full['stderr'])[-500:]}
                print(cfg, key, 'identity', ('PASS' if ident.get('identical') else 'FAIL'), 'products_only_rc', prod['rc'], 'full_rc', full['rc'], flush=True)
        # whole-file sha256 of published MRCs per arm (headers carry a clock label; payload via comparators above)
        res['mrc_sha256_whole_file_first3'] = {n: {p.name: sha256_file(p) for p in sorted(t.glob('Movies/*.mrc'))[:3]} for n, t in trees.items()}
        # controls that can discriminate: an untouched copy must PASS, a one-byte-mutated copy must FAIL
        if 'w1' in trees:
            pos = cmpdir / 'pos-w1'
            filtered_copy(base / 'w1' / 'merged', pos)
            neg = cmpdir / 'neg-w1'
            filtered_copy(base / 'w1' / 'merged', neg)
            victim = sorted(neg.glob('Movies/*.mrc'))[0]
            data = bytearray(victim.read_bytes())
            data[4096] ^= 0x01
            victim.unlink()
            victim.write_bytes(bytes(data))
            ctl = {}
            for nm, t in (('positive_untouched_copy', pos), ('negative_flipped_payload_byte', neg)):
                il = identity.compare_trees(str(trees['w1']), str(t))
                cr = run_tool([PY, COMPARE_TREES, trees['w1'], t, '--manifest', base / 'manifest.json', '--input-star', star])
                ctl[nm] = {'identity_lib': 'PASS' if il.get('identical') else 'FAIL', 'compare_output_trees_full_rc': cr['rc']}
            res['controls'] = ctl
            print(cfg, 'controls', ctl, flush=True)
        all_res['configs'][cfg] = res
        # delete bulk
        for p in list(base.rglob('*.mrc')) + list(base.rglob('*.pdf')):
            try:
                p.unlink()
            except OSError:
                pass
        shutil.rmtree(cmpdir, ignore_errors=True)
        dump(res, summ / f'multigpu-{cfg}.json')
    if not a.dry_run:
        dump(all_res, summ / 'all.json')


MIXED = [  # (movie source relative to the shared roots, optics group)
    ('tutorial', 'tutorial-data/Movies/20170629_00021_frameImage.tiff', 1),
    ('tutorial', 'tutorial-data/Movies/20170629_00022_frameImage.tiff', 1),
    ('e10641', 'corpus/data-https/EMPIAR-10641/data/Movies/Dataset/HM70-1_10-A-002_0002_Oct28_23.00.41.tif', 2),
    ('tutorial', 'tutorial-data/Movies/20170629_00023_frameImage.tiff', 1),
    ('tutorial', 'tutorial-data/Movies/20170629_00024_frameImage.tiff', 1),
    ('e10474f3', 'corpus/data-https/EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer', 3),
]
OPTICS = {1: (0.885, 200, 1.4), 2: (0.4, 300, 2.7), 3: (1.06, 300, 2.7)}
MARKERS = {'nvcomp': 'nvCOMP', 'native_staging': 'Staging this movie as native', 'converged_no': 'converged=no',
           'retry': 'etry', 'warning': 'WARNING'}


def build_mixed_inputs():
    d = W / 'inputs' / 'mixed'
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    v = Path.home() / 'motioncorr-validation-20261011-vm'
    names, ident = [], []
    for fam, rel, grp in MIXED:
        src = v / rel
        stem, dot, suffix = src.name.rpartition('.')
        lname = stem.replace('.', '_') + dot + suffix  # products use '.'->'_' stems; same bytes
        link = d / 'Movies' / lname
        if link.is_symlink() or link.exists():
            link.unlink()
        os.symlink(src, link)
        names.append((f'Movies/{lname}', grp))
        ident.append({'family': fam, 'movie': f'Movies/{lname}', 'optics_group': grp, 'sha256': sha256_file(src)})
    star = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
            '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5', '_rlnAmplitudeContrast #6']
    star += [f'opticsGroup{g} {g} {a} {kv} {cs} 0.1' for g, (a, kv, cs) in OPTICS.items()]
    star += ['', '# version 30001', '', 'data_movies', '', 'loop_', '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2']
    star += [f'{n} {g}' for n, g in names] + ['']
    (d / 'movies.star').write_text('\n'.join(star))
    return d, ident


def per_movie_markers(run, movies):
    out = {}
    for m in movies:
        stem = Path(m).stem
        logs = list((run / 'merged' / 'Movies').glob(f'{stem}.log'))
        txt = logs[0].read_text(errors='replace') if logs else ''
        out[m] = {k: txt.count(v) for k, v in MARKERS.items()} | {'log_found': bool(logs)}
        out[m]['native_staging_lines'] = [l.strip()[:160] for l in txt.splitlines() if 'Staging this movie as native' in l][:2]
        out[m]['nvcomp_lines'] = [l.strip()[:160] for l in txt.splitlines() if 'nvCOMP' in l][:2]
        out[m]['retry_lines'] = [l.strip()[:160] for l in txt.splitlines() if 'converged=no' in l][:2]
    return out


def main_mixed():
    d, ident = build_mixed_inputs()
    star = d / 'movies.star'
    movies = movie_list(star)
    assert len(movies) == 6, movies
    summ = W / 'summaries' / 'multigpu'
    summ.mkdir(parents=True, exist_ok=True)
    base = OUT / 'mixed'
    if base.exists():
        shutil.rmtree(base)
    (base / 'logs').mkdir(parents=True)
    res = {'inputs': ident, 'input_star_sha256': sha256_file(star), 'binary': str(BIN['nvcomp']),
           'binary_sha256': sha256_file(BIN['nvcomp']), 'arms': {}}
    arms = [arm for arm in ARMS if arm[0] in ('w1', 'w2')]
    trees = {}
    for name, devs, masks, j in arms:
        run = base / name
        wit = base / f'ingest-witness-{name}.txt'
        la = f"--devices {','.join(UUID[x] for x in devs)} --cpus '{';'.join(masks)}' --cpu-budget 16"
        cmd = ['taskset', '-c', MG_ALL, PY, str(TOOLS / 'run_dataset.py'), '--binary', str(BIN['nvcomp']),
               '--star', str(star), '--out', str(run), f'--launcher-args={la}',
               '--required-products=.mrc,.star,_shifts.eps', '--',
               '--use_own', '--j', str(j), '--max_io_threads', str(j), '--dose_weighting', '--dose_per_frame', '1.0',
               '--bfactor', '150', '--seed', '1', '--ingest', 'auto', '--ingest_witness', str(wit),
               '--patch_x', '5', '--patch_y', '5', '--eer_grouping', '40', '--eer_upsampling', '1']
        env = base_env(False)
        t0 = time.monotonic()
        p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True)
        wall = time.monotonic() - t0
        (base / 'logs' / f'{name}.driver.log').write_text(p.stdout + '\n--stderr--\n' + p.stderr)
        arm = {'devices': devs, 'device_uuids': [UUID[x] for x in devs], 'cpu_masks': masks, 'j': j, 'argv': cmd[3:],
               'rc': p.returncode, 'wall_s_outer': round(wall, 2),
               'ingest_witness_file': sorted(wit.read_text().splitlines()) if wit.exists() else None}
        if (run / 'dataset_status.json').exists():
            arm['contract'] = contract(name, run, movies, devs)
            arm['per_movie_markers'] = per_movie_markers(run, movies)
        res['arms'][name] = arm
        print('mixed', name, 'rc', p.returncode, 'problems', arm.get('contract', {}).get('problems'), f'{wall:.0f}s', flush=True)
        if (run / 'merged').exists():
            filtered_copy(run / 'merged', base / 'cmp' / name)
            trees[name] = base / 'cmp' / name
    if len(trees) == 2:
        ident_r = identity.compare_trees(str(trees['w1']), str(trees['w2']), expect_mrc=len(movies))
        res['w1_vs_w2'] = {'identity_lib_status': ('PASS' if ident_r.get('identical') else 'FAIL'), 'detail': {k: v for k, v in ident_r.items() if k != 'files'}}
        print('mixed identity w1 vs w2', ('PASS' if ident_r.get('identical') else 'FAIL'), flush=True)
        pos, neg = base / 'cmp' / 'pos', base / 'cmp' / 'neg'
        filtered_copy(base / 'w1' / 'merged', pos)
        filtered_copy(base / 'w1' / 'merged', neg)
        victim = sorted(neg.glob('Movies/*.mrc'))[0]
        data = bytearray(victim.read_bytes())
        data[4096] ^= 0x01
        victim.unlink()
        victim.write_bytes(bytes(data))
        res['controls'] = {'positive_untouched_copy': 'PASS' if identity.compare_trees(str(trees['w1']), str(pos)).get('identical') else 'FAIL',
                           'negative_flipped_payload_byte': 'PASS' if identity.compare_trees(str(trees['w1']), str(neg)).get('identical') else 'FAIL'}
    res['mrc_whole_file_sha256'] = {n: {p.name: sha256_file(p) for p in sorted(t.glob('Movies/*.mrc'))} for n, t in trees.items()}
    for p in list(base.rglob('*.mrc')) + list(base.rglob('*.pdf')):
        try:
            p.unlink()
        except OSError:
            pass
    shutil.rmtree(base / 'cmp', ignore_errors=True)
    dump(res, summ / 'multigpu-mixed.json')


if __name__ == '__main__':
    main()
