#!/usr/bin/env python3
"""Closes the evidence gap in the first harness version: its nvidia-smi sampler matched the pid of
/usr/bin/time, not of the forked payload, so no run recorded a physical-GPU witness. This reruns two
campaign cases through the same run_case path (descendant-aware sampler) and records the UUID seen."""
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qual_lib import *  # noqa
import product_campaign as pc

fams = pc.load_families()
droot, hashes = pc.data_root(), pc.parse_corpus_hashes()
res = []
for fid, cfg in (('e12963', 'L'), ('e10361', 'G'), ('tutorial', 'L')):
    fam = fams[fid]
    inputs, ident = pc.setup_family(fam, droot, hashes)
    root = W / 'gpu-witness' / f'{fid}-{cfg}'
    if root.exists():
        shutil.rmtree(root)
    out = root / 'out'
    args = pc.family_args(fam, cfg, out) + ['--gpu', '0', '--ingest', 'auto']
    r = run_case(f'witness-{fid}-{cfg}', BIN['nvcomp'], args, inputs, root / 'logs', gpu=True)
    print(fid, cfg, r.get('rc'), r.get('gpu_witness'), flush=True)
    res.append({k: r.get(k) for k in ('label', 'rc', 'wall_s', 'gpu_witness', 'bench_gate', 'binary_sha256', 'args')})
    shutil.rmtree(root / 'out', ignore_errors=True)
dump(res, W / 'summaries' / 'gpu_witness_check.json')
