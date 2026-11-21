#!/usr/bin/env python3
"""Derive the i8 multi-device drivers with asserted replacements (originals untouched; diffs retained).

c1_item12_mg.py    from ../../tools-v2/c1_item12.py (the QF item 12 driver as already adapted for C1): the --dataset part now uses four devices by UUID
                   in the order GPU3, GPU0, GPU1, GPU2 (worker 0 is always the lane GPU3), two CPUs per worker out of 96-103, and adds the 4-worker arms:
                     d4        healthy, rules of d1/d2 (rc 0, PASS, 4 workers on 4 distinct witnessed UUIDs, cleanup, 4 MRC + 4 STAR + joint STAR,
                               merged tree identical to d1);
                     d4poison  UUID-selective poison on worker 3 (GPU2): the existing 'poison_one' rules of dpoison, with SHARDS[4] = one movie per worker.
                   The 2-worker poison now names worker 1 = GPU0 via QF_FAULT_UUID. grade_dataset() rules are unchanged; two structural edits only: (v3c) first_ret is looked up lazily for FAULTING workers
                   only (the first stage i8-mg-item12 crashed with StopIteration at d4poison because 4 workers give shard [0] = a tutorial movie with no 10641
                   movie; the crash was in the grader's bookkeeping, before any verdict), and `--arms/--regrade` select arms to run and retained arms to
                   regrade read-only from their files (rc recovered from dataset_status.json: PASS -> 0, 'Worker phase exited N' -> N).
c1_mg_publication.py from ../../../../rc0/qf/tools/multigpu_publication.py (QF item 8, G/L s0,w1,w2,w4): resources only. The driver hardcodes a 16-CPU
                   budget (w1 --j 16, w2 2x8 CPUs --j 8, w4 4x4 CPUs --j 4, --cpu-budget 16); i8 has 8 CPUs, so the arms keep their structure with
                   w1 --j 8 on 96-103, w2 two 4-CPU workers --j 4, w4 four 2-CPU workers --j 2 and --cpu-budget 8. s0 is already --j 8. The contract checks,
                   strict cross-arm comparisons and positive/negative controls are untouched. The bench lock is probed, not waited on (c1_lane.install).
"""
import difflib, re
from pathlib import Path
here = Path(__file__).resolve().parent
root = here.parents[3]


def derive(src, dst, edits):
    orig = src.read_text(); s = orig
    for e in edits:
        a, b = e[0], e[1]
        if len(e) == 3 and e[2] == 'rx':
            s, n = re.subn(a, b, s, flags=re.S); assert n == 1, (a, n)
        else:
            cnt = e[2] if len(e) == 3 else 1
            assert s.count(a) == cnt, (a, s.count(a)); s = s.replace(a, b)
    (here / dst).write_text(s)
    (here / (dst[:-3] + '.diff')).write_text(''.join(difflib.unified_diff(orig.splitlines(True), s.splitlines(True), str(src.relative_to(root)), dst)))


# ---- item 12 dataset, multi-device -------------------------------------------------------------------------------------------------
NEW_DATASET = '''def dataset(single_gpu=False, run=None, regrade=()):
    if single_gpu:  # GPU0 only: the 1-worker arms (healthy and poisoned); the 2-worker arms need the window
        gpus, masks = [LANE_GPU_UUID, None], [CPUS, None]
    else:           # i8: four devices by UUID, worker 0 is the lane GPU3; two CPUs per worker out of the granted 96-103
        gpus = [os.environ[f'C1_GPU{i}_UUID'] for i in (3, 0, 1, 2)]
        masks = ['96-97', '98-99', '100-101', '102-103']
    d = ROOT / 'inputs' / 'mixed'
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    for key, name, _ in MIXED:
        if (d / 'Movies' / name).is_symlink():
            (d / 'Movies' / name).unlink()
        os.symlink(INPUTS[key][0], d / 'Movies' / name)
    star = d / 'movies.star'
    star.write_text(star_text(['opticsGroupTut 1 0.885 200 1.4 0.1', 'opticsGroup10641 2 0.4 300 2.7 0.1'],
                              [(f'Movies/{n}', g) for _, n, g in MIXED]))
    # fault_worker must be a worker whose shard holds a 10641 movie (the resident retry only runs there): 1 or 3 of the 4-movie dataset
    fault2 = {'QF_FAULT_SHIM': str(SHIM), 'QF_FAULT_UUID': gpus[1], 'MC_RESIDENT_RETRY_COUNT': '1'}
    fault4 = {'QF_FAULT_SHIM': str(SHIM), 'QF_FAULT_UUID': gpus[3], 'MC_RESIDENT_RETRY_COUNT': '1'}
    arms = [('d1', BIN['nvcomp'], 1, {}, 'pass', None), ('d2', BIN['nvcomp'], 2, {}, 'pass', None),
            ('dshim', SHIM, 2, {'MC_PREPROCESS_FAULT': 'none', 'MC_RESIDENT_RETRY_COUNT': '1'}, 'pass', None),
            ('d4', BIN['nvcomp'], 4, {}, 'pass', None),
            # #207's case: only the worker on the second device faults (UUID-selective wrapper, see qf_fault_by_uuid.sh)
            ('dpoison', WRAPPER, 2, fault2, 'poison_one', 1),
            # i8 addition: the same rules with four workers, only the worker on GPU2 (worker 3) faults
            ('d4poison', WRAPPER, 4, fault4, 'poison_one', 3),
            # additional: both workers fault (the shim's own env, no wrapper)
            ('dpoison_both', SHIM, 2, {'MC_PREPROCESS_FAULT': 'resident-retry-fatal'}, 'poison_both', None)]
    if single_gpu:
        arms = [arms[0][:5] + (None,), ('dpoison_1w', SHIM, 1, {'MC_PREPROCESS_FAULT': 'resident-retry-fatal'}, 'poison_both', None)]
    res = {'gpus': gpus, 'cpu_masks': masks, 'wrapper_sha256': sha256_file(WRAPPER), 'shim_sha256': sha256_file(SHIM),
           'runs': {}, 'problems': []}
    retried = None
    for tag, binary, n, env, expect, fault_worker in arms:
        if run is not None and tag not in run and tag not in regrade:
            continue
        if tag in regrade:   # retained arm: graded read-only from its own files, never rerun
            out, leftovers = ROOT / 'dataset' / tag, []
            st0 = _load(out / 'dataset_status.json') or {}
            m = re.search(r'Worker phase exited (\\d+)', st0.get('failure') or '')
            rc = 0 if st0.get('verdict') == 'PASS' else (int(m[1]) if m else None)
        else:
            out, rc, leftovers = run_dataset_arm(tag, binary, n, env, gpus, masks, star, d)
        if tag == 'd1' and (out / 'merged').exists():
            retried = retry_accounting(out / 'merged')['retried']
        probs = grade_dataset(tag, out, rc, n, expect, gpus, fault_worker=fault_worker, retried=retried if tag == 'dshim' else None)
        if leftovers:
            probs.append(f'leftover processes {leftovers}')
        st = _load(out / 'dataset_status.json') or {}
        res['runs'][tag] = {'rc': rc, 'binary_sha256': sha256_file(binary), 'expect': expect, 'fault_worker': fault_worker,
                            'fault_uuid': env.get('QF_FAULT_UUID'), 'verdict': st.get('verdict'),
                            'dataset_ready': st.get('dataset_ready'), 'failure': st.get('failure'), 'problems': probs}
        res['problems'] += [f'{tag}: {x}' for x in probs]
        print(tag, 'rc', rc, 'verdict', st.get('verdict'), probs, flush=True)
    base = digest_tree(ROOT / 'dataset' / 'd1' / 'merged') if (ROOT / 'dataset' / 'd1' / 'merged').exists() else {}
    for tag in (() if single_gpu or (run is not None and 'd1' not in run and 'd1' not in regrade) else ('d2', 'dshim', 'd4')):
        m = ROOT / 'dataset' / tag / 'merged'
        other = digest_tree(m) if m.exists() else {}
        diff = sorted(k for k in set(base) | set(other) if base.get(k) != other.get(k))
        res[f'd1_vs_{tag}'] = {'files': len(base), 'differing': diff[:20]}
        if not base or diff:
            res['problems'].append(f'd1 vs {tag}: {len(diff)} differing files')
    for p in list((ROOT / 'dataset').rglob('*.mrc')) + list((ROOT / 'dataset').rglob('*.pdf')):
        p.unlink()
    res['verdict'] = 'PASS' if not res['problems'] else 'FAIL'
    dump(res, ROOT / 'results' / ('dataset-single-gpu.json' if single_gpu else ('dataset.json' if run is None else 'dataset-' + '_'.join(sorted(set(run) | set(regrade))) + '.json')))
    print('dataset:', res['verdict'], res['problems'])
    return res


def main():'''

derive(here.parents[1] / 'tools-v2/c1_item12.py', 'c1_item12_mg.py', [
    (r"def dataset\(single_gpu=False\):.*?\ndef main\(\):", NEW_DATASET.replace('\\', '\\\\'), 'rx'),
    ("    ap.add_argument('--dataset-single-gpu', action='store_true',",
     "    ap.add_argument('--arms', help='i8: comma list of dataset arms to RUN (default all)')\n    ap.add_argument('--regrade', default='', help='i8: comma list of retained dataset arms to grade read-only without rerunning')\n    ap.add_argument('--dataset-single-gpu', action='store_true',"),
    ("        return 0 if dataset(single_gpu=a.dataset_single_gpu)['verdict'] == 'PASS' else 1",
     "        run = a.arms.split(',') if a.arms else (None if not a.regrade else [])\n        return 0 if dataset(single_gpu=a.dataset_single_gpu, run=run, regrade=tuple(x for x in a.regrade.split(',') if x))['verdict'] == 'PASS' else 1"),
    ("        first_ret = next(j for j, i in enumerate(shard) if MIXED[i][0].startswith('10641'))\n",
     "        first_ret = next((j for j, i in enumerate(shard) if MIXED[i][0].startswith('10641')), None)   # i8: shards of the 4-worker arms may hold no 10641 movie\n"),
    ("        tut, ret = [_stem(i) for i in shard[:first_ret]], [_stem(shard[first_ret])]\n",
     "        if first_ret is None:\n            tut, ret = [_stem(i) for i in shard], []\n            if k in faulting:\n                problems.append(f'w{k}: no 10641 movie in its shard, so the retry fault cannot fire there')\n        else:\n            tut, ret = [_stem(i) for i in shard[:first_ret]], [_stem(shard[first_ret])]\n"),
    ("SHARDS = {1: [[0, 1, 2, 3]], 2: [[0, 1], [2, 3]]}", "SHARDS = {1: [[0, 1, 2, 3]], 2: [[0, 1], [2, 3]], 4: [[0], [1], [2], [3]]}   # i8: one movie per worker at n=4"),
])

# ---- QF item 8 multigpu publication, 8-CPU budget ----------------------------------------------------------------------------------
derive(root / 'rc0/qf/tools/multigpu_publication.py', 'c1_mg_publication.py', [
    ("sys.path.insert(0, str(Path(__file__).resolve().parent))\nsys.path.insert(0, str(Path(os.environ['QF_W']) / 'src/tools/profiling'))\nfrom qual_lib import *  # noqa: F401,F403\n",
     "# i8: QF helpers are read in place from the scratch checkout of the tested source; this derivative lives in the i8 tools packet.\n"
     "sys.path.insert(0, str(Path(os.environ['QF_W']) / 'src/docs/rc0/qf/tools'))\n"
     "sys.path.insert(0, str(Path(os.environ['QF_W']) / 'src/tools/profiling'))\n"
     "from qual_lib import *  # noqa: F401,F403\n"
     "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
     "import c1_lane; c1_lane.install()   # bench lock probed, not waited on (#198 policy)\n"),
    (r"def _split\(r\):.*?\n\]\n",
     """MG_ALL = os.environ['QF_MG_CPU_ALL']   # i8: one 8-CPU range 'lo-hi' (QF used two 8-CPU ranges, 16 CPUs)
W1_GPU = int(os.environ.get('QF_MG_W1_GPU', '0'))
W2_GPUS = [W1_GPU, (W1_GPU + 1) % 4]
_lo = int(MG_ALL.split('-')[0])
ARMS = [
    ('w1', [W1_GPU], [MG_ALL], 8),
    ('w2', W2_GPUS, [f'{_lo}-{_lo + 3}', f'{_lo + 4}-{_lo + 7}'], 4),
    ('w4', [0, 1, 2, 3], [f'{_lo}-{_lo + 1}', f'{_lo + 2}-{_lo + 3}', f'{_lo + 4}-{_lo + 5}', f'{_lo + 6}-{_lo + 7}'], 2),
]
""", 'rx'),
    ("--cpu-budget 16", "--cpu-budget 8", 2),
])
print('ok')
