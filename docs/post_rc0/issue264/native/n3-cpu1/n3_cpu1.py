# SPDX-License-Identifier: GPL-2.0-or-later
"""N3/N4 CPU subset (FROZEN-CPU1.md): the original runner and row grader (../tools/n3.py) with the
R3-reviewed iteration-2 predictions, CPU arms only, output n3-cpu1/. TEST-ONLY overlay builds.

  n3_cpu1.py receipts    write the injected known observations of all 24 CPU rows before any run
  n3_cpu1.py run cpu     run the 24 CPU rows (refuses gpu; needs matching receipts)
  n3_cpu1.py grade       original grade (all 40 rows, the 16 CUDA rows stay UNRUN), then the
                         separate CPU-subset verdict CPU_SUBSET.json; exit 0 only on subset PASS
"""
import hashlib, json, os, sys, traceback
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / 'tools'
sys.path.insert(0, str(TOOLS))
import runlib  # noqa: E402
import n3  # noqa: E402

PRED_SHA256 = '6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e'
PRED_PATH = runlib.SCR / 'src-cand/docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json'
raw = PRED_PATH.read_bytes()
if hashlib.sha256(raw).hexdigest() != PRED_SHA256:
    raise SystemExit(f'predictions_iter2.json hash mismatch at {PRED_PATH}; refusing')
n3.PRED = json.loads(raw)['n3']
n3.CASES = list(n3.PRED) + ['Z_no_overlay']
n3.N3 = runlib.SCR / 'n3-cpu1'
CPU_ARMS, GPU_ARMS = n3.ARMS['cpu'], n3.ARMS['gpu']      # ARMS is not edited: grade still lists the CUDA rows
RECEIPTS = n3.N3 / 'known-observations.json'


def receipts_record():
    rows = {}
    for arm, algorithm in CPU_ARMS.items():
        for case in n3.CASES:
            if case == 'Z_no_overlay':
                rows[f'{arm}/{case}'] = {'overlay': False}
                continue
            p = n3.PRED[case]
            spec = ' '.join(repr(v) for v in p['coeffX_float'] + p['coeffY_float'])   # exactly what n3.run exports
            rows[f'{arm}/{case}'] = {'overlay': True, 'MC264_N3_COEFFS': spec,
                                     'spec_sha256': hashlib.sha256(spec.encode()).hexdigest(),
                                     'coeffX': p['coeffX'], 'coeffY': p['coeffY'],
                                     'predicted': p[algorithm], 'algorithm': algorithm}
    return {'kind': 'injected known observations, recorded before fit/guard/reconstruction',
            'predictions_sha256': PRED_SHA256, 'fixture_sha256_required': os.environ.get('G_KM_SHA256'),
            'overlay': 'patch observation i := model(patch_frames[i], patch_xs[i]/nx-0.5, patch_ys[i]/ny-0.5)',
            'rows': rows}


def receipts():
    if RECEIPTS.exists():
        raise SystemExit(f'{RECEIPTS} exists; refusing')
    n3.N3.mkdir(parents=True, exist_ok=True)
    RECEIPTS.write_text(json.dumps(receipts_record(), indent=1) + '\n')
    print('receipts', len(receipts_record()['rows']))
    return 0


def run(backend):
    if backend != 'cpu':
        raise SystemExit('CPU subset only; CUDA rows stay UNRUN')
    if not RECEIPTS.exists() or json.loads(RECEIPTS.read_text()) != receipts_record():
        raise SystemExit('known-observation receipts missing or different; refusing')
    return n3.run('cpu')


def grade():
    problems, rc_original, error = [], None, None
    try:
        rc_original = n3.grade()
    except Exception:
        error = traceback.format_exc()
        problems.append('original grader raised (fail closed)')
    res = json.loads((n3.N3 / 'RESULTS.json').read_text()) if (n3.N3 / 'RESULTS.json').exists() and error is None else None
    expected_cpu = {(a, c) for a in CPU_ARMS for c in n3.CASES}
    expected_gpu = {(a, c) for a in GPU_ARMS for c in n3.CASES}
    cpu_rows = gpu_rows = {}
    if res is not None:
        rows = [(x['arm'], x['case'], x['status']) for x in res['rows']]
        if len(rows) != len(set((a, c) for a, c, _ in rows)): problems.append('duplicate rows')
        cpu_rows = {(a, c): s for a, c, s in rows if a in CPU_ARMS}
        gpu_rows = {(a, c): s for a, c, s in rows if a in GPU_ARMS}
        if set(cpu_rows) != expected_cpu or len(expected_cpu) != 24: problems.append('CPU rows are not the expected 24')
        bad = sorted(f'{a}/{c}:{s}' for (a, c), s in cpu_rows.items() if s != 'PASS')
        if bad: problems.append(f'CPU rows not PASS: {bad}')
        if set(gpu_rows) != expected_gpu or len(expected_gpu) != 16 or any(s != 'UNRUN' for s in gpu_rows.values()):
            problems.append('CUDA rows are not exactly 16 UNRUN')
        if any((n3.N3 / a).exists() for a in GPU_ARMS): problems.append('a CUDA arm directory exists in a CPU-only campaign')
        cpu_pairs = [p for p in res['base_vs_candidate'] if p['backend'] == 'cpu']
        if len(cpu_pairs) != 8 or any(p['status'] != 'PASS' for p in cpu_pairs): problems.append('CPU base/candidate pairs not 8 PASS')
        if any(p['backend'] != 'cpu' for p in res['base_vs_candidate']): problems.append('a CUDA pair was graded')
        expected_kills = sorted(c for c in n3.PRED if n3.PRED[c]['uncentred']['reject'] != n3.PRED[c]['finite']['reject'])
        if res['n4_mutant']['status'] != 'PASS' or sorted(res['n4_mutant']['cases_where_mutant_decision_differs_from_candidate']) != expected_kills:
            problems.append(f'N4 not PASS on exactly {expected_kills}')
        s = res['summary']
        if s['runs'] != {'PASS': 24, 'FAIL': 0, 'UNRUN': 16} or rc_original != 1:
            problems.append(f'original summary {s} rc {rc_original}; expected 24 PASS / 0 FAIL / 16 UNRUN and rc 1')
    elif error is None:
        problems.append('RESULTS.json missing')
    verdict = 'PASS' if not problems else 'FAIL'
    report = {'kind': 'CPU subset of N3/N4 (TEST-ONLY overlay builds); not CPU+CUDA qualification',
              'predictions_sha256': PRED_SHA256, 'cpu_subset_expected_rows': 24, 'cuda_rows_pending_unrun': 16,
              'cpu_subset_verdict': verdict,
              'full_n3_n4_aggregate': 'INCOMPLETE: 16 CUDA rows UNRUN',
              'original_grade_exit': rc_original, 'original_grade_error': error, 'problems': problems}
    n3.N3.mkdir(parents=True, exist_ok=True)
    (n3.N3 / 'CPU_SUBSET.json').write_text(json.dumps(report, indent=1) + '\n')
    print('CPU subset', verdict, problems)
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'receipts': sys.exit(receipts())
    if c == 'run': sys.exit(run(sys.argv[2]))
    if c == 'grade': sys.exit(grade())
    raise SystemExit('unknown command')
