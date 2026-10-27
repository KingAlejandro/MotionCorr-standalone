#!/usr/bin/env python3
"""Offline controls for the C1 i8 multi-device grader fixes (review of PR #282). Read-only on the evidence.

usage: python3 -I grader_controls.py EXTRACTED_TGZ_DIR C1_TOOLS_DIR OUT.json

EXTRACTED_TGZ_DIR  c1-i8-evidence.tgz extracted into a fresh directory
C1_TOOLS_DIR       docs/post_rc0/c1-20261022/native-final-20261025/tools (fixed grader, i8d_redigest.py)

The grader functions are lifted by AST from the fixed c1_item12_mg.py (grade_dataset, digest_tree and the
constants they read) and from the first-stage tools-v3-run copy, so no QF/lane code is imported or run.
Each control works on a private copy of the retained dataset tree in which the VM scratch prefix is
rewritten to the local copy (worker console paths in status.json, product paths inside logs/STARs).
MRC payloads were not retained; a 0-byte placeholder is created for every MRC the worker's own log says
it wrote ('Written aligned and dose-weighted sum to ...mrc'), and in merged/ for pass arms whose worker
wrote it. The MRC presence/absence the grader checks is therefore reconstructed from the logs.
"""
import ast, copy, hashlib, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

EV, TOOLS, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
VM = '/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-i8-20261025'
WANT_FN = {'grade_dataset', 'digest_tree', '_stem', '_load'}
WANT_AS = {'MIXED', 'SHARDS', 'REFUSAL'}


def lift(path):
    tree = ast.parse(Path(path).read_text())
    body = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in WANT_FN)
            or (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in WANT_AS for t in n.targets))]
    ns = {'re': re, 'hashlib': hashlib, 'json': json, 'Path': Path}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), ns)
    assert WANT_FN | WANT_AS <= set(ns), sorted(WANT_FN | WANT_AS - set(ns))
    return ns


NEW = lift(TOOLS / 'c1_item12_mg.py')                     # = tools-v3c/-v3d (sha256 6e6ba987...)
OLD = lift(EV / 'tools-v3-run' / 'c1_item12_mg.py')       # first stage i8-mg-item12 (a72b7871...)
reg = json.loads((TOOLS.parent / 'summary' / 'item12-dataset-regrade.json').read_text())
GPUS = reg['gpus']
ARMS = {  # tag: (n, expect, fault_worker), exactly as c1_item12_mg.dataset() passes them
    'd1': (1, 'pass', None), 'd2': (2, 'pass', None), 'dshim': (2, 'pass', None), 'd4': (4, 'pass', None),
    'dpoison': (2, 'poison_one', 1), 'd4poison': (4, 'poison_one', 3), 'dpoison_both': (2, 'poison_both', None)}


def stage(tmp):
    """Private, path-rewritten copy of the retained c1-item12/dataset tree with log-witnessed MRC placeholders."""
    root = tmp / 'c1-item12'
    shutil.copytree(EV / 'c1-item12', root)
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in ('.json', '.log', '.star'):
            b = p.read_bytes()
            if VM.encode() in b:
                p.write_bytes(b.replace(VM.encode(), str(tmp).encode()))
    for arm in ARMS:
        for wlog in (root / 'dataset' / arm / 'workers').glob('w*/Movies/*.log'):
            if re.search(rb'Written aligned and dose-weighted sum to \S+\.mrc', wlog.read_bytes()):
                (wlog.parent / (wlog.stem + '.mrc')).touch()
                m = root / 'dataset' / arm / 'merged' / 'Movies'
                if m.is_dir():
                    (m / (wlog.stem + '.mrc')).touch()
    return root


def rc_of(ds_dir):  # the regrade's rc recovery (c1_item12_mg.py dataset(): PASS -> 0, 'Worker phase exited N' -> N)
    st = json.loads((ds_dir / 'dataset_status.json').read_text())
    m = re.search(r'Worker phase exited (\d+)', st.get('failure') or '')
    return 0 if st.get('verdict') == 'PASS' else (int(m[1]) if m else None)


def retried_of(merged):
    res = 0
    for log in sorted((merged / 'Movies').glob('*.log')):
        for b in re.split(r'(?m)^Patch \(', log.read_text(errors='replace'))[1:]:
            res += len(re.findall(r'\[CUDA Patch Alignment\] completed; converged=(yes|no)', b)) >= 2
    return res


def grade(ns, root, tag, **over):
    n, expect, fw = ARMS[tag]
    d = root / 'dataset' / tag
    kw = dict(rc=rc_of(d), n=n, expect=expect, gpus=GPUS, fault_worker=fw,
              retried=retried_of(root / 'dataset' / 'd1' / 'merged') if tag == 'dshim' else None)
    kw.update(over)
    try:
        return ns['grade_dataset'](tag, d, kw['rc'], kw['n'], kw['expect'], kw['gpus'],
                                   fault_worker=kw['fault_worker'], retried=kw['retried'])
    except StopIteration:
        return 'StopIteration'


def edit_json(p, fn):
    j = json.loads(p.read_text()); fn(j); p.write_text(json.dumps(j))


def sub_file(p, a, b, count=1):
    t = p.read_bytes(); assert t.count(a) >= 1, (p, a); p.write_bytes(t.replace(a, b, count))


res = {'baseline_new': {}, 'baseline_old': {}, 'grader_mutants': {}, 'digest': {}}
with tempfile.TemporaryDirectory() as t:
    root = stage(Path(t))
    for tag in ARMS:
        res['baseline_new'][tag] = grade(NEW, root, tag)
        res['baseline_old'][tag] = grade(OLD, root, tag)

# ---- grader mutants: each must yield >= 1 problem under the FIXED grader ----------------------------------
D = lambda r, a: r / 'dataset' / a
W = lambda r, a, k: r / 'dataset' / a / 'workers' / f'w{k}'
MUT = {
    'd4poison: healthy w1 (10641 A002) STAR deleted':
        ('d4poison', lambda r: (W(r, 'd4poison', 1) / 'Movies' / 'HM70-1_10-A-002_0002_Oct28_23_00_41.star').unlink(), {}),
    'd4poison: healthy w2 per-worker joint STAR deleted':
        ('d4poison', lambda r: (W(r, 'd4poison', 2) / 'corrected_micrographs.star').unlink(), {}),
    'd4poison: refusal line removed from faulting w3 console':
        ('d4poison', lambda r: sub_file(W(r, 'd4poison', 3) / 'launcher.console.log',
                                        b'Refusing to retry alignment on a poisoned context', b'Retrying', 10), {}),
    'd4poison: faulting w3 published its refused movie (STAR+MRC)':
        ('d4poison', lambda r: [(W(r, 'd4poison', 3) / 'Movies' / f'HM70-1_10-A-004_0008_Oct28_23_06_04.{x}').touch() for x in ('star', 'mrc')], {}),
    'd4poison: fault also fired on healthy w1 (injected line in console)':
        ('d4poison', lambda r: sub_file(W(r, 'd4poison', 1) / 'launcher.console.log', b'fault=off',
                                        b'fault=off\n[preprocessfault] injected cudaErrorIllegalAddress'), {}),
    'd4poison: wrapper did not enable the fault on w3 (fault=on -> fault=off)':
        ('d4poison', lambda r: sub_file(W(r, 'd4poison', 3) / 'launcher.console.log', b'fault=on', b'fault=off'), {}),
    'd4poison: healthy w2 returncode 1':
        ('d4poison', lambda r: edit_json(D(r, 'd4poison') / 'workers' / 'status.json',
                                         lambda j: j['workers'][2].__setitem__('returncode', 1)), {}),
    'd4poison: faulting w3 returncode 0':
        ('d4poison', lambda r: edit_json(D(r, 'd4poison') / 'workers' / 'status.json',
                                         lambda j: j['workers'][3].__setitem__('returncode', 0)), {}),
    'd4poison: a merged joint STAR was published':
        ('d4poison', lambda r: ((D(r, 'd4poison') / 'merged').mkdir(), (D(r, 'd4poison') / 'merged' / 'corrected_micrographs.star').touch()), {}),
    'd4poison: dataset_ready true / verdict PASS':
        ('d4poison', lambda r: edit_json(D(r, 'd4poison') / 'dataset_status.json',
                                         lambda j: j.update(verdict='PASS', dataset_ready=True)), {}),
    'd4poison: graded with fault_worker=0 (shard holds no 10641 movie)':
        ('d4poison', lambda r: None, {'fault_worker': 0}),
    'd4poison: worker devices out of intended UUID order':
        ('d4poison', lambda r: edit_json(D(r, 'd4poison') / 'workers' / 'status.json',
                                         lambda j: j['devices'].reverse()), {}),
    'd4poison: w3 console log missing':
        ('d4poison', lambda r: (W(r, 'd4poison', 3) / 'launcher.console.log').unlink(), {}),
    'dpoison: healthy tutorial movie before the 10641 movie in faulting w1 lost its STAR':
        ('dpoison', lambda r: (W(r, 'dpoison', 1) / 'Movies' / '20170629_00031_frameImage.star').unlink(), {}),
    'dpoison: healthy w0 lost its 10641 MRC':
        ('dpoison', lambda r: (W(r, 'dpoison', 0) / 'Movies' / 'HM70-1_10-A-002_0002_Oct28_23_00_41.mrc').unlink(), {}),
    'dpoison_both: refusal removed from w1':
        ('dpoison_both', lambda r: sub_file(W(r, 'dpoison_both', 1) / 'launcher.console.log',
                                            b'Refusing to retry alignment on a poisoned context', b'Retrying', 10), {}),
    'dpoison_both: rc 0 (dataset verdict PASS)':
        ('dpoison_both', lambda r: edit_json(D(r, 'dpoison_both') / 'dataset_status.json',
                                             lambda j: j.update(verdict='PASS', failure=None)), {}),
    'd4: merged STAR of one movie deleted':
        ('d4', lambda r: (D(r, 'd4') / 'merged' / 'Movies' / '20170629_00031_frameImage.star').unlink(), {}),
    'd4: gpu witness reports 3 distinct devices':
        ('d4', lambda r: edit_json(D(r, 'd4') / 'workers' / 'status.json',
                                   lambda j: j['gpu_witness'].__setitem__('distinct_devices_witnessed', 3)), {}),
    'd4: worker 1 returncode 1':
        ('d4', lambda r: edit_json(D(r, 'd4') / 'workers' / 'status.json',
                                   lambda j: j['workers'][1].__setitem__('returncode', 1)), {}),
    'dshim: counter does not match retried patches':
        ('dshim', lambda r: None, {'retried': 10 ** 6}),
}
for name, (tag, fn, over) in MUT.items():
    with tempfile.TemporaryDirectory() as t:
        root = stage(Path(t)); fn(root)
        res['grader_mutants'][name] = grade(NEW, root, tag, **over)

# ---- digest: exact lines that differ before/after normalisation, and digest mutants ------------------------
OLD_RX, NEW_RX = rb'item12-retry/dataset/[A-Za-z0-9]+', rb'(?:item12-retry|c1-item12)/dataset/[A-Za-z0-9]+'
FILTER = (b' ms', b'time', b'Kernel', b'~~(,_,', b'sec .', b'free device memory', b'device memory in use rose')


def norm_lines(p, rx):
    raw = re.sub(rx, b'DS', p.read_bytes())
    raw = re.sub(rb'workers/w[0-9]+', b'workers/wN', raw)
    raw = re.sub(rb'\.aggregate-[A-Za-z0-9_]+', b'.aggregate-X', raw)
    return raw.split(b'\n')


with tempfile.TemporaryDirectory() as t:
    root = stage(Path(t))
    base = root / 'dataset' / 'd1' / 'merged'
    lines = {}
    for tag in ('d2', 'dshim', 'd4'):
        m = root / 'dataset' / tag / 'merged'
        for log in sorted((base / 'Movies').glob('*.log')):
            for label, rx in (('old_rx', OLD_RX), ('new_rx', NEW_RX)):
                a = [l for l in norm_lines(log, rx) if not any(f in l for f in FILTER)]
                b = [l for l in norm_lines(m / 'Movies' / log.name, rx) if not any(f in l for f in FILTER)]
                diff = [(x.decode(errors='replace'), y.decode(errors='replace')) for x, y in zip(a, b) if x != y]
                lines.setdefault(f'{tag}/{log.name}', {})[label] = {'n_lines': [len(a), len(b)], 'differing': diff}
            # lines the inherited filter drops that are NOT time/kernel noise (masked content differences)
            ra = set(log.read_bytes().split(b'\n')); rb_ = set((m / 'Movies' / log.name).read_bytes().split(b'\n'))
            masked = sorted(l.decode() for l in ra ^ rb_ if any(f in l for f in FILTER) and b' ms' not in l)
            if masked:
                lines[f'{tag}/{log.name}']['filtered_only_lines'] = masked
    res['digest']['line_diff_d1_vs'] = lines
    # i8d_redigest.py as committed, on the retained (eps/mrc-less) trees
    def redigest(r):
        o = Path(t) / 'rd.json'
        p = subprocess.run([sys.executable, '-I', str(TOOLS / 'i8d_redigest.py'), str(r), str(o)], capture_output=True, text=True)
        return {'rc': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()[-300:],
                **({k: v for k, v in json.loads(o.read_text()).items() if k in ('files_in_d1_merged', 'verdict')} if o.exists() else {})}
    res['digest']['redigest_retained'] = redigest(root)

DMUT = {
    'd2 log: one fitted shift digit changed in a non-filtered line':
        lambda r: _flip_shift(r / 'dataset' / 'd2' / 'merged' / 'Movies' / '20170629_00026_frameImage.log'),
    'd4 log: product path names a different movie in the normalised line':
        lambda r: sub_file(r / 'dataset' / 'd4' / 'merged' / 'Movies' / 'HM70-1_10-A-004_0008_Oct28_23_06_04.log',
                           b'Movies/HM70-1_10-A-004_0008_Oct28_23_06_04.mrc', b'Movies/HM70-1_10-A-002_0002_Oct28_23_00_41.mrc'),
    'dshim STAR: one value changed':
        lambda r: _flip_shift(r / 'dataset' / 'dshim' / 'merged' / 'Movies' / 'HM70-1_10-A-002_0002_Oct28_23_00_41.star'),
    'd2 joint STAR: one row dropped':
        lambda r: _drop_last_row(r / 'dataset' / 'd2' / 'merged' / 'corrected_micrographs.star'),
    'd2 log: writes into d1\'s directory (EXPECTED masked: tag is normalised away)':
        lambda r: sub_file(r / 'dataset' / 'd2' / 'merged' / 'Movies' / '20170629_00026_frameImage.log',
                           b'c1-item12/dataset/d2/', b'c1-item12/dataset/d1/'),
}


def _flip_shift(p):
    t = p.read_bytes()
    m = None
    for m in re.finditer(rb'(?m)^[^\n]*?(-?\d+\.\d{3,})', t):
        if not any(f in m.group(0) for f in FILTER):
            break
    i = m.start(1) + len(m.group(1)) - 1
    p.write_bytes(t[:i] + (b'1' if t[i:i + 1] != b'1' else b'2') + t[i + 1:])


def _drop_last_row(p):
    rows = p.read_bytes().rstrip(b'\n').split(b'\n')
    p.write_bytes(b'\n'.join(rows[:-1]) + b'\n')


res['digest']['redigest_mutants'] = {}
for name, fn in DMUT.items():
    with tempfile.TemporaryDirectory() as t:
        root = stage(Path(t)); fn(root)
        o = Path(t) / 'rd.json'
        p = subprocess.run([sys.executable, '-I', str(TOOLS / 'i8d_redigest.py'), str(root), str(o)], capture_output=True, text=True)
        j = json.loads(o.read_text()) if o.exists() else {}
        res['digest']['redigest_mutants'][name] = {'rc': p.returncode, 'verdict': j.get('verdict'),
                                                   'differing': {k: v['differing'] for k, v in j.get('cmp', {}).items() if v['differing']}}

OUT.write_text(json.dumps(res, indent=1) + '\n')
ok_base = all(v == [] for v in res['baseline_new'].values())
ok_mut = all(isinstance(v, list) and v for v in res['grader_mutants'].values())
print('baseline (fixed grader) all PASS:', ok_base, {k: v for k, v in res['baseline_new'].items() if v})
print('baseline (first-stage grader):', {k: ('ok' if v == [] else v) for k, v in res['baseline_old'].items()})
print('grader mutants detected:', sum(bool(v) and isinstance(v, list) for v in res['grader_mutants'].values()), '/', len(res['grader_mutants']))
for k, v in res['grader_mutants'].items():
    print(' ', 'DETECTED' if isinstance(v, list) and v else 'MISSED  ', k, '->', v if not isinstance(v, list) else v[:2])
print('redigest on retained trees:', res['digest']['redigest_retained'])
for k, v in res['digest']['redigest_mutants'].items():
    print(' ', v['verdict'], k, v['differing'])
