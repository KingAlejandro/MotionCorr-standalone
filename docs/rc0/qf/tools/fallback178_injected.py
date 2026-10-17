#!/usr/bin/env python3
"""Item 4, arm C: CUDA -> CPU unweighted fallback inside a --gpu run, via the repo's own
link-time fault shim (tests/cuda_fault_inject_shim.cpp, binary motioncorr_faultinject).

The shim returns an injected cudaErrorMemoryAllocation (a recoverable class) for the k-th
cudaMalloc. Sweep k until the per-movie log shows the device reconstruction announced and then
the CPU line ("Summing frames before dose weighting: ") -- that is the #178 path reached from a
device run. The same k is then run with a faultinject build of pre-#178 d7171b81 and the two
product trees are compared strictly. The injected status is a code returned by an interposed
call, not a real out-of-memory condition.
"""
from __future__ import annotations

import shutil
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(os.environ['QF_W']) / 'src/tools/profiling'))
from qual_lib import *  # noqa: F401,F403
from lib import identity  # noqa: E402
import product_campaign as pc  # noqa: E402
from fallback178 import CPU_LINE, witness  # noqa: E402

FI_CUR = W / 'build-nvcomp' / 'motioncorr_faultinject'
FI_PRE = Path(os.environ.get('QF_PRE178_FI_BIN', Q1 / 'build-pre178-fi' / 'motioncorr_faultinject'))  # Q1's d7171b81 build
ROOT = W / 'fallback178-injected'
EXTRA = ['--save_noDW', '--even_odd_split']


def attempt(label, binary, fam, inputs, k, tag):
    out = ROOT / f'out-{tag}-{label}'
    args = pc.family_args(fam, 'G', out) + EXTRA + ['--gpu', '0']
    env = {'MC_FAULT_ORDINAL': str(k), 'MC_FAULT_CODE': 'alloc'}
    r = run_case(f'{tag}-{label}', binary, args, inputs, ROOT / 'logs', gpu=True, extra_env=env)
    r['witness'] = witness(out, 'ign', r['stdout'])
    r['witness_cuda_then_cpu'] = r['witness']['cuda_line_count'] > 0 and r['witness']['cpu_line_count'] > 0
    r['fault_ordinal'] = k
    r['out'] = str(out)
    txt = Path(r['stdout']).read_text(errors='replace')
    r['injected_line'] = next((l.strip()[:160] for l in txt.splitlines() if 'INJECT' in l.upper()), None)
    return r


def main():
    fams = pc.load_families()
    fam = fams['tutorial']
    inputs, ident = pc.setup_family(fam, pc.data_root(), pc.parse_corpus_hashes())
    stem = Path(ident['movie']).stem
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    summ = W / 'summaries' / 'fallback178'
    summ.mkdir(parents=True, exist_ok=True)
    # trace run: how many cudaMalloc calls?
    args = pc.family_args(fam, 'G', ROOT / 'out-trace') + EXTRA + ['--gpu', '0']
    tr = run_case('trace', FI_CUR, args, inputs, ROOT / 'logs', gpu=True, extra_env={'MC_FAULT_TRACE': '1'})
    txt = Path(tr['stdout']).read_text(errors='replace')
    import re
    ords = [int(m.group(1)) for m in re.finditer(r'cudaMalloc #(\d+)', txt)]
    n = max(ords) if ords else 0
    print('trace rc', tr.get('rc'), 'cudaMalloc calls', n, flush=True)
    sweep = []
    found = None
    for k in range(1, n + 1):
        r = attempt('cur', FI_CUR, fam, inputs, k, f'k{k}')
        # discovery needs the real stem for the per-movie log
        out = Path(r['out'])
        r['witness'] = witness(out, stem, r['stdout'])
        r['witness_cuda_then_cpu'] = r['witness']['cuda_line_count'] > 0 and r['witness']['cpu_line_count'] > 0
        sweep.append({kk: r.get(kk) for kk in ('fault_ordinal', 'rc', 'witness_cuda_then_cpu', 'injected_line')})
        print('k', k, 'rc', r.get('rc'), 'cuda->cpu', r['witness_cuda_then_cpu'], flush=True)
        if r['witness_cuda_then_cpu'] and r.get('rc') == 0:
            found = (k, r)
            break
        shutil.rmtree(out, ignore_errors=True)
    rec = {'cudaMalloc_calls_in_trace_run': n, 'sweep': sweep, 'found_ordinal': found[0] if found else None}
    if found:
        k, cur = found
        pre = attempt('pre', FI_PRE, fam, inputs, k, f'k{k}')
        pre['witness'] = witness(Path(pre['out']), stem, pre['stdout'])
        pre['witness_cuda_then_cpu'] = pre['witness']['cuda_line_count'] > 0 and pre['witness']['cpu_line_count'] > 0
        rec['cur'], rec['pre178'] = cur, pre
        if pre.get('rc') == 0:
            rep = identity.compare_trees(cur['out'], pre['out'])
            rec['identity_cur_vs_pre178'] = {'status': ('PASS' if rep.get('identical') else 'FAIL'), 'detail': {kk: v for kk, v in rep.items() if kk != 'files'}}
        rec['mrc_whole_file_sha256'] = {str(p.relative_to(ROOT)): sha256_file(p) for p in sorted(ROOT.rglob('*.mrc'))}
    for p in list(ROOT.rglob('*.mrc')) + list(ROOT.rglob('*.pdf')):
        p.unlink()
    dump(rec, summ / 'injected.json')
    print('found', rec['found_ordinal'], rec.get('identity_cur_vs_pre178', {}).get('status'))


if __name__ == '__main__':
    main()
