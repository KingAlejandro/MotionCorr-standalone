#!/usr/bin/env python3
"""Item 4: execute the unweighted/even-odd CPU path changed by #178 inside CUDA builds.

Source analysis (src/motioncorr_runner.cpp, executeOwnMotionCorrection):
  pre_dw_sum_needed = !do_dose_weighting || save_noDW || even_odd_split.
  Then: movie_session (resident CUDA)  -> reconstructUnweighted(); on non-fatal false -> CPU
        use_gpu without session        -> cudaRealSpaceInterpolation(); on non-fatal false -> CPU
        neither (no --gpu)             -> CPU sumUnweightedFrames()      <- the #178 path
  CPU log witness: "Summing frames before dose weighting: " (no "(CUDA" suffix).

Arm A (primary): CUDA+nvCOMP build of main 1db86902 and CUDA+nvCOMP build of pre-#178 d7171b81,
both WITHOUT --gpu, same inputs/options; strict product identity (tools/profiling/lib/identity).
Arm B (contrast): the 1db86902 build WITH --gpu 0, to show the device path takes different lines.
Arm C (injected non-fatal device failure -> CPU fallback inside a --gpu run) is in
fallback178_injected.py.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path('/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/src/tools/profiling')))
from qual_lib import *  # noqa: F401,F403
from lib import identity  # noqa: E402
import product_campaign as pc  # noqa: E402

ROOT = W / 'fallback178'
CPU_LINE = 'Summing frames before dose weighting: '
CUDA_LINES = ('Summing frames before dose weighting (CUDA',)

# (case id, config, extra options, drop --dose_weighting?)
CASES = [
    ('noDW', 'G', ['--save_noDW'], False),
    ('noDW', 'L', ['--save_noDW'], False),
    ('evenodd', 'G', ['--save_noDW', '--even_odd_split'], False),
    ('evenodd', 'L', ['--save_noDW', '--even_odd_split'], False),
    ('evenodd-23fr', 'L', ['--save_noDW', '--even_odd_split', '--last_frame_sum', '23'], False),
    ('nodose', 'G', [], True),
]


def case_args(fam, cfg, out, extra, nodose):
    a = pc.family_args(fam, cfg, out)
    if nodose:
        i = a.index('--dose_weighting')
        del a[i:i + 1]
    return a + extra


def witness(out, stem, stdout_path):
    texts = []
    for p in (Path(out) / 'Movies' / f'{stem}.log', Path(stdout_path)):
        texts.append(p.read_text(errors='replace') if p.exists() else '')
    t = '\n'.join(texts)
    return {'cpu_line_count': t.count(CPU_LINE), 'cuda_line_count': sum(t.count(s) for s in CUDA_LINES),
            'cpu_line_example': next((l.strip()[:120] for l in t.splitlines() if CPU_LINE in l), None),
            'cuda_line_example': next((l.strip()[:120] for l in t.splitlines() if any(s in l for s in CUDA_LINES)), None)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-gpu-contrast', action='store_true')
    a = ap.parse_args()
    fams = pc.load_families()
    fam = fams['tutorial']
    droot = pc.data_root()
    inputs, ident = pc.setup_family(fam, droot, pc.parse_corpus_hashes())
    stem = Path(ident['movie']).stem
    summ = W / 'summaries' / 'fallback178'
    summ.mkdir(parents=True, exist_ok=True)
    results = []
    for cid, cfg, extra, nodose in CASES:
        name = f'{cid}-{cfg}'
        root = ROOT / name
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        rec = {'case': name, 'extra_options': extra, 'dose_weighting': not nodose, 'runs': {}}
        for arm, binkey in (('cur', 'nvcomp'), ('pre178', 'pre178')):
            out = root / f'out-{arm}'
            args = case_args(fam, cfg, out, extra, nodose)  # NO --gpu: CPU path of a CUDA build
            r = run_case(f'{name}-{arm}', BIN[binkey], args, inputs, root / 'logs', gpu=True)
            r['witness'] = witness(out, stem, r['stdout'])
            rec['runs'][arm] = r
        if not a.skip_gpu_contrast and cid in ('evenodd', 'noDW') and cfg == 'G':
            out = root / 'out-curgpu'
            args = case_args(fam, cfg, out, extra, nodose) + ['--gpu', '0']
            r = run_case(f'{name}-curgpu', BIN['nvcomp'], args, inputs, root / 'logs', gpu=True)
            r['witness'] = witness(out, stem, r['stdout'])
            rec['runs']['curgpu'] = r
        ok = all(rec['runs'][k].get('rc') == 0 for k in ('cur', 'pre178'))
        if ok:
            rep = identity.compare_trees(str(root / 'out-cur'), str(root / 'out-pre178'))
            rec['identity_cur_vs_pre178'] = {'status': ('PASS' if rep.get('identical') else 'FAIL'), 'detail': {k: v for k, v in rep.items() if k != 'files'}}
            rec['n_products'] = {'mrc': sorted(p.name for p in (root / 'out-cur').rglob('*.mrc'))}
        # delete bulk MRC after grading, retain whole-file hashes of the current arm
        rec['mrc_whole_file_sha256'] = {str(p.relative_to(root)): sha256_file(p) for p in sorted(root.rglob('*.mrc'))}
        for p in list(root.rglob('*.mrc')) + list(root.rglob('*.pdf')):
            p.unlink()
        dump(rec, summ / f'{name}.json')
        results.append(rec)
        print(name, 'ok' if ok else 'RUN-FAILED', rec.get('identity_cur_vs_pre178', {}).get('status'),
              {k: (v.get('rc'), v['witness']['cpu_line_count'], v['witness']['cuda_line_count']) for k, v in rec['runs'].items()}, flush=True)
    dump(results, summ / 'all.json')


if __name__ == '__main__':
    main()
