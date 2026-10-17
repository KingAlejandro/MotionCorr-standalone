#!/usr/bin/env python3
"""QF item 2: route/product campaign (one movie per family, configs G and L).

Ported from Q1 (PR #209). Per (family, config):
  nvcomp build --ingest <arm> for each of --ingest-arms (default auto,compact,float)
                               -> trees A/K/F  (+ --ingest_witness)
  CPU-only build               -> tree C
  QF_REF_CPU_BIN, if set       -> tree R  (reference CPU build, e.g. Q1's 1db86902)
Checks:
  * every GPU arm witnessed on the lane GPU only, and the compact/float arms took the
    route they pin;
  * `--ingest compact` on a family whose auto route is float must be REFUSED (pinned
    refusal semantics); on any other family a refusal is a FAIL;
  * products-only identity (MRC header+payload, STAR) of every GPU arm against auto, plus
    the strict and declared-route-log-allowance verdicts for the record;
  * C vs R: products-only and strict all-files identity (same backend, valid input);
  * CPU-vs-CUDA `compare_motioncorr.py --gate backend`: DIAGNOSTIC ONLY.
Bulk MRC outputs are deleted after grading; logs/STAR/json stay.

Run:  taskset -c $QF_CPUS python3 product_campaign.py [--only fam[,fam]] [--configs G,L]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qual_lib import *  # noqa: F401,F403

FAMILIES = ['tutorial', 'e10361', 'e10474f3', 'e12963', 'e10216', 'e10028', 'e10164']
RUNS = W / 'campaign'
# Route-record log lines that legitimately differ between --ingest routes (memory:
# compare-output-trees-two-traps, item 4). Used only for the "declared allowance" verdict.
# QF: 'Released native int' added (#195 signed MRC routes, Q1 finding 4); the two native
# prefixes are generalised to every staged type.
ROUTE_LINE_PREFIXES = ['nvCOMP ingestion', 'Staging this movie as native', 'Released native ',
                       'Materialized native ']
COMPACT_REFUSAL = '--ingest compact was requested but the compact native staging did not apply'


def load_families():
    fams = json.loads((SRC / 'docs/workload_corpus/families.json').read_text())['families']
    return {f['id']: f for f in fams}


def parse_corpus_hashes():
    text = (SRC / 'docs/workload_corpus/corpus.md').read_text()
    out = {}
    for m in re.finditer(r'\|\s*(\w+)\s*\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`', text):
        out[m.group(2)] = {'bytes': int(m.group(3).replace(',', '')), 'sha256': m.group(4)}
    return out


def data_root():
    """A read-only symlink root: tutorial/, EMPIAR-*/ pointing at the shared assets."""
    root = W / 'dataroot'
    root.mkdir(exist_ok=True)
    v = Path.home() / 'motioncorr-validation-20261011-vm'
    links = {'tutorial': v / 'tutorial-data'}
    for acc in ('EMPIAR-10028', 'EMPIAR-10361', 'EMPIAR-10441', 'EMPIAR-10474', 'EMPIAR-10641', 'EMPIAR-12963'):
        links[acc] = v / 'corpus/data-https' / acc
    for acc in ('EMPIAR-10164', 'EMPIAR-10216'):
        # Q1 re-fetched these two from EBI (sizes and hashes verified against corpus.md).
        links[acc] = Q1 / 'data' / acc
    for name, target in links.items():
        link = root / name
        if link.is_symlink():
            link.unlink()
        os.symlink(target, link)
    return root


def setup_family(fam, droot, hashes):
    """One-movie run directory: inputs/<id>/{Movies/<movie>, gain, movies.star}; returns identity."""
    d = W / 'inputs' / fam['id']
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    rel = fam['movies'][0]
    src = droot / rel
    name = src.name
    if fam.get('link_rename') and name.endswith('.mrc'):
        name = name[:-4] + fam['link_rename']
    # MotionCorr writes products under the stem with '.' -> '_'; link under that spelling so the
    # input stem equals the product stem (same file bytes, only the symlink name differs).
    stem, dot, suffix = name.rpartition('.')
    name = stem.replace('.', '_') + dot + suffix
    link = d / 'Movies' / name
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(src.resolve(), link)
    ident = {'movie': 'Movies/' + name, 'movie_source': str(src.resolve()), 'movie_bytes': src.stat().st_size,
             'movie_sha256': sha256_file(src), 'gain': None}
    exp = hashes.get(rel)
    ident['movie_expected_sha256'] = exp['sha256'] if exp else None
    ident['movie_hash_matches_corpus_md'] = (exp['sha256'] == ident['movie_sha256']) if exp else None
    if fam.get('gain'):
        gsrc = droot / fam['gain']
        glink = d / fam['gain_link']
        if glink.is_symlink() or glink.exists():
            glink.unlink()
        os.symlink(gsrc.resolve(), glink)
        gexp = hashes.get(fam['gain'])
        ident['gain'] = {'link': fam['gain_link'], 'source': str(gsrc.resolve()), 'sha256': sha256_file(gsrc),
                         'expected_sha256': gexp['sha256'] if gexp else None}
        ident['gain']['matches_corpus_md'] = (gexp['sha256'] == ident['gain']['sha256']) if gexp else None
    star = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
            '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5',
            '_rlnAmplitudeContrast #6', 'opticsGroup1 1 %s %s %s 0.1' % (fam['angpix'], fam['voltage'], fam['cs']), '',
            '# version 30001', '', 'data_movies', '', 'loop_', '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2',
            '%s 1' % ident['movie'], '']
    (d / 'movies.star').write_text('\n'.join(star))
    ident['movies_star_sha256'] = sha256_file(d / 'movies.star')
    return d, ident


def family_args(fam, cfg, out):
    a = ['--use_own', '--dose_weighting', '--dose_per_frame', repr(fam['dose']), '--bfactor', '150', '--seed', '1',
         '--expected_frames', fam['frames'], '--i', 'movies.star', '--o', f'{out}/', '--j', '8']
    if fam.get('gain'):
        a += ['--gainref', fam['gain_link']]
    if fam.get('eer_grouping'):
        a += ['--eer_grouping', fam['eer_grouping'], '--eer_upsampling', '1']
    if cfg == 'L':
        a += ['--patch_x', '5', '--patch_y', '5']
    return a


def mrc_dims(path):
    import struct
    with open(path, 'rb') as f:
        h = f.read(1024)
    return list(struct.unpack_from('<3i', h, 0)), struct.unpack_from('<i', h, 12)[0]


def log_line_diff(a_root, b_root, movie_stem):
    """Lines present in only one arm's per-movie log (timing lines dropped), for the evidence record."""
    def lines(root):
        p = root / 'Movies' / f'{movie_stem}.log'
        txt = p.read_text(errors='replace') if p.exists() else ''
        drop = ('Full movie wall time', 'execution time:', 'transfer time:', 'Total GPU alignment time:', 'Kernel:', ' ms')
        return [l.strip() for l in txt.splitlines() if l.strip() and not any(m in l for m in drop)]
    la, lb = lines(a_root), lines(b_root)
    return {'only_in_A': [l for l in la if l not in lb], 'only_in_B': [l for l in lb if l not in la]}


def refusal_publications(out, stem):
    """Products a refused movie must not have: its corrected MRC (any suffix), its per-movie STAR,
    and a completion (joint) STAR row naming it."""
    found = []
    if out.exists():
        found += sorted(str(p.relative_to(out)) for p in out.rglob(f'{stem}*.mrc'))
        found += sorted(str(p.relative_to(out)) for p in out.rglob(f'{stem}*.star'))
        joint = out / 'corrected_micrographs.star'
        if joint.exists() and stem in joint.read_text(errors='replace'):
            found.append('corrected_micrographs.star (names the movie)')
    return found


def products_identity(root, a, b, star, prefixes=None, products_only=False, tag=''):
    tag = tag or f'{a}-vs-{b}'
    allow = []
    for p in prefixes or []:
        allow += ['--allow-added-log-line', p]
    out = root / f'identity-{tag}.json'
    r = run_tool([PY, COMPARE_TREES, root / f'out-{a}', root / f'out-{b}', '--manifest', root / 'manifest.json',
                  '--input-star', star, *(['--products-only'] if products_only else []), *allow, '--json-out', out])
    rec = {'rc': r['rc'], 'tail': (r['stdout'] + r['stderr'])[-600:]}
    if out.exists():
        d = json.loads(out.read_text())
        rec.update({'status': d.get('status'), 'different_files': d.get('different_files'),
                    'different_products': d.get('different_products')})
    return rec


def one_case(fam, cfg, inputs_dir, ident, summary_dir, ingest_arms):
    stem = Path(ident['movie']).stem
    root = RUNS / f"{fam['id']}-{cfg}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    logs = root / 'logs'
    arms = {}
    for arm in ingest_arms:
        out = root / f'out-{arm}'
        wit = root / f'witness-{arm}.txt'
        args = family_args(fam, cfg, out) + ['--gpu', '0', '--ingest', arm, '--ingest_witness', wit]
        arms[arm] = run_case(f"{fam['id']}-{cfg}-{arm}", BIN['nvcomp'], args, inputs_dir, logs, gpu=True, witness=wit)
    cpu_arms = ['cpu'] + (['ref_cpu'] if 'ref_cpu' in BIN else [])
    for arm in cpu_arms:
        out = root / f'out-{arm}'
        wit = root / f'witness-{arm}.txt'
        args = family_args(fam, cfg, out) + ['--ingest_witness', wit]
        arms[arm] = run_case(f"{fam['id']}-{cfg}-{arm}", BIN[arm], args, inputs_dir, logs, gpu=False, witness=wit)

    case = {'family': fam['id'], 'config': cfg, 'movie': ident['movie'], 'runs': arms, 'checks': {}, 'problems': []}
    ok_runs = {k for k, r in arms.items() if r.get('rc') == 0 and (root / f'out-{k}' / 'Movies' / f'{stem}.mrc').exists()}
    case['runs_ok'] = sorted(ok_runs)
    route = {k: (r.get('ingest_witness') or [''])[-1].split()[-1:] for k, r in arms.items()}
    route = {k: (v[0] if v else None) for k, v in route.items()}
    case['routes'] = route
    refused_arms = set()
    if 'compact' in ingest_arms:
        text = Path(arms['compact']['stdout']).read_text(errors='replace')
        published = refusal_publications(root / 'out-compact', stem)
        refused = arms['compact'].get('rc') not in (0, None) and COMPACT_REFUSAL in text
        expect_refusal = route.get('auto') == 'float'
        case['checks']['compact_refusal'] = {'refused': refused, 'expected': expect_refusal,
                                             'published_after_refusal': published}
        if refused != expect_refusal:
            case['problems'].append(f'compact arm refused={refused}, expected refusal={expect_refusal}')
        if refused and published:
            case['problems'].append(f'compact arm refused but published {published}')
        if refused:
            ok_runs.discard('compact')
            refused_arms.add('compact')
    # A refused arm exits during routing, before nvidia-smi can list it: its witness is recorded,
    # not required. Every arm that ran a movie must be seen on the lane GPU and nowhere else.
    for k in ingest_arms:
        w = arms[k].get('gpu_witness') or {}
        if k not in refused_arms and not w.get('on_lane_gpu_only'):
            case['problems'].append(f'{k}: GPU witness not on the lane GPU only ({w.get("uuids_seen_for_pid")})')
    for k in ingest_arms:
        if k in ('compact', 'float') and k in ok_runs and route.get(k) != k:
            case['problems'].append(f'{k} arm took route {route.get(k)}')
    for k in arms:
        if k not in ok_runs and not (k == 'compact' and case['checks'].get('compact_refusal', {}).get('refused')):
            case['problems'].append(f'{k} arm did not complete (rc={arms[k].get("rc")})')
    manifest = None
    if 'auto' in ok_runs:
        dims, mode = mrc_dims(root / 'out-auto' / 'Movies' / f'{stem}.mrc')
        case['output_dims_xyz'] = dims
        case['output_mode'] = mode
        case['dims_match_family_geometry'] = sorted(dims[:2]) == sorted([fam['nx'], fam['ny']]) and dims[2] == 1
        manifest = {'schema_version': 1, 'input_star_sha256': ident['movies_star_sha256'], 'expected_shape_xyz': dims,
                    'joint_star': 'corrected_micrographs.star', 'movies': [ident['movie']]}
        dump(manifest, root / 'manifest.json')
    star = str(inputs_dir / 'movies.star')
    if manifest:
        for k in ingest_arms:
            if k == 'auto' or k not in ok_runs:
                continue
            c = {'products_only': products_identity(root, 'auto', k, star, products_only=True),
                 'strict_all_files': products_identity(root, 'auto', k, star, tag=f'auto-vs-{k}-strict'),
                 'declared_route_log_allowance': products_identity(root, 'auto', k, star, ROUTE_LINE_PREFIXES,
                                                                   tag=f'auto-vs-{k}-declared'),
                 'allowance_prefixes': ROUTE_LINE_PREFIXES,
                 'log_line_diff': log_line_diff(root / 'out-auto', root / f'out-{k}', stem)}
            case['checks'][f'auto_vs_{k}'] = c
            if c['products_only']['rc'] != 0:
                case['problems'].append(f'auto vs {k}: products differ')
        if {'cpu', 'ref_cpu'} <= ok_runs:
            c = {'products_only': products_identity(root, 'ref_cpu', 'cpu', star, products_only=True),
                 'strict_all_files': products_identity(root, 'ref_cpu', 'cpu', star, tag='ref_cpu-vs-cpu-strict'),
                 'ref_cpu_binary_sha256': arms['ref_cpu']['binary_sha256'],
                 'log_line_diff': log_line_diff(root / 'out-ref_cpu', root / 'out-cpu', stem)}
            case['checks']['ref_cpu_vs_cpu'] = c
            if c['products_only']['rc'] != 0:
                case['problems'].append('ref_cpu vs cpu: products differ')
    # CPU vs CUDA auto: diagnostics only
    if {'auto', 'cpu'} <= ok_runs:
        gate = run_tool([PY, COMPARE_MC, '--gate', 'backend',
                         '--ref-mrc', root / 'out-cpu' / 'Movies' / f'{stem}.mrc',
                         '--test-mrc', root / 'out-auto' / 'Movies' / f'{stem}.mrc',
                         '--ref-star', root / 'out-cpu' / 'Movies' / f'{stem}.star',
                         '--test-star', root / 'out-auto' / 'Movies' / f'{stem}.star',
                         '--test-log', arms['auto']['time_log'], '--json-out', root / 'backend-gate.json'])
        g = {'rc': gate['rc'], 'tail': gate['stdout'][-1500:]}
        gj = root / 'backend-gate.json'
        if gj.exists():
            gd = json.loads(gj.read_text())
            g['json_checks'] = gd.get('checks', gd)
        case['checks']['cpu_vs_cuda_auto_backend_gate_DIAGNOSTIC_ONLY'] = g
    mrc_hashes = {}
    for k in ok_runs:
        p = root / f'out-{k}' / 'Movies' / f'{stem}.mrc'
        mrc_hashes[k] = {'size': p.stat().st_size, 'sha256_whole_file': sha256_file(p)}
    case['mrc_whole_file_sha256'] = mrc_hashes
    case['verdict'] = 'PASS' if not case['problems'] else 'FAIL'
    # delete bulk outputs; keep logs, STAR, json
    for p in root.rglob('*.mrc'):
        p.unlink()
    for p in root.rglob('*.pdf'):
        p.unlink()
    dump(case, summary_dir / f"{fam['id']}-{cfg}.json")
    return case


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--configs', default='G,L')
    ap.add_argument('--setup-only', action='store_true')
    ap.add_argument('--ingest-arms', default='auto,compact,float')
    a = ap.parse_args()
    fams = load_families()
    hashes = parse_corpus_hashes()
    droot = data_root()
    summary_dir = W / 'summaries' / 'campaign'
    summary_dir.mkdir(parents=True, exist_ok=True)
    chosen = [f for f in FAMILIES if not a.only or f in a.only.split(',')]
    idents = {}
    for fid in chosen:
        d, ident = setup_family(fams[fid], droot, hashes)
        idents[fid] = (d, ident)
        print(fid, ident['movie'], ident['movie_sha256'][:12], 'corpus-match=', ident['movie_hash_matches_corpus_md'],
              'gain=', (ident['gain'] or {}).get('matches_corpus_md'), flush=True)
    dump({k: v[1] for k, v in idents.items()}, summary_dir / 'inputs.json')
    if a.setup_only:
        return 0
    results = []
    for fid in chosen:
        for cfg in a.configs.split(','):
            t0 = time.time()
            case = one_case(fams[fid], cfg, idents[fid][0], idents[fid][1], summary_dir, a.ingest_arms.split(','))
            print(f"{fid}-{cfg}: {case['verdict']} ok={case['runs_ok']} routes={case['routes']} "
                  f"problems={case['problems']} ({time.time()-t0:.0f}s)", flush=True)
            results.append(case)
    dump(results, summary_dir / 'all.json')
    return 0 if all(c['verdict'] == 'PASS' for c in results) else 1


if __name__ == '__main__':
    sys.exit(main())
