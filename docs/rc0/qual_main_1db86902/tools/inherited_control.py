#!/usr/bin/env python3
"""Control for the CPU-vs-CUDA backend-gate diagnostics (item 3): are the large L-config divergences
inherited? Runs e10216-L and e12963-L (movie 1) with the 1db86902 and pre-#178 d7171b81 builds, on CPU
and on GPU1 (--ingest auto), and compares current vs pre-#178 strictly per backend."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path('/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/src/tools/profiling')))
from qual_lib import *  # noqa
from lib import identity
import product_campaign as pc

BIN['pre178cpu'] = W / 'build-pre178-cpu' / 'motioncorr'
fams = pc.load_families()
droot = pc.data_root()
hashes = pc.parse_corpus_hashes()
out_all = []
for fid in ('e10216', 'e12963'):
    fam = fams[fid]
    inputs, ident = pc.setup_family(fam, droot, hashes)
    root = W / 'inherited-control' / f'{fid}-L'
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    runs = {}
    for arm, key, gpu in (('cur-cpu', 'cpu', False), ('pre-cpu', 'pre178cpu', False),
                          ('cur-gpu', 'nvcomp', True), ('pre-gpu', 'pre178', True)):
        out = root / f'out-{arm}'
        args = pc.family_args(fam, 'L', out) + (['--gpu', '0', '--ingest', 'auto'] if gpu else [])
        runs[arm] = run_case(f'{fid}-L-{arm}', BIN[key], args, inputs, root / 'logs', gpu=gpu)
        print(fid, arm, runs[arm].get('rc'), flush=True)
    rec = {'family': fid, 'runs': runs}
    for backend in ('cpu', 'gpu'):
        if runs[f'cur-{backend}'].get('rc') == 0 and runs[f'pre-{backend}'].get('rc') == 0:
            rep = identity.compare_trees(str(root / f'out-cur-{backend}'), str(root / f'out-pre-{backend}'))
            rec[f'identity_cur_vs_pre178_{backend}'] = {'identical': rep['identical'], 'mrc_compared': rep['mrc_compared'],
                                                         'problems': rep['problems']}
            print(fid, backend, 'identical', rep['identical'], flush=True)
    for p in list(root.rglob('*.mrc')) + list(root.rglob('*.pdf')):
        p.unlink()
    out_all.append(rec)
dump(out_all, W / 'summaries' / 'inherited_control.json')
