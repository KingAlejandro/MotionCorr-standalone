# SPDX-License-Identifier: GPL-2.0-or-later
"""Host mock controls for the CPU-subset grader (no MotionCorr, no GPU, no remote).

Each scenario builds a fake scratch whose 24 CPU rows are synthesised from the frozen
predictions as the real runner would leave them (RUN.json, stdout/stderr, STAR, MRC), then
runs `n3_cpu1.py grade` as a subprocess. The positive must exit 0 with the subset PASS;
every negative must exit 1 and name the expected problem.
usage: python3 test_cpu1_controls.py --out NEW_DIR
"""
import argparse, json, os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
NATIVE = HERE.parent
ITER2 = NATIVE / 'n3-iter2/predictions_iter2.json'
PRED = json.loads(ITER2.read_text())['n3']
V1 = json.loads((NATIVE / 'predictions.json').read_text())['n3']
ARMS = {'ov-base-cpu': 'legacy', 'ov-cand-cpu': 'finite', 'ov-mut-cpu': 'uncentred'}
CASES = list(PRED) + ['Z_no_overlay']
OVERLAY = 'MC264_N3 overlay applied n_obs=192 nx=768 ny=512 n_frames=12\n'
GLOBAL = 'data_global_shift\n\nloop_\n_rlnMicrographFrameNumber #1\n_rlnMicrographShiftX #2\n_rlnMicrographShiftY #3\n' + \
         ''.join(f'{i + 1} {0.1 * i:.6f} {-0.05 * i:.6f}\n' for i in range(12)) + '\n'


def row_files(d, case, algorithm, *, value=None, overlay=True, guard=None, model=None, stdout='mock cpu run\n', rc=0, mrc=True):
    p = PRED.get(case)
    reject = p[algorithm]['reject'] if guard is None and p else bool(guard)
    (d / 'logs').mkdir(parents=True); (d / 'out').mkdir()
    err = OVERLAY if overlay and case != 'Z_no_overlay' else ''
    if reject:
        err += f'km_local_nonsquare.mrcs: could not fit a reasonable local motion model (delta > {value if value is not None else p[algorithm]["value"]:g}). Global trajectory alone is used.\n'
    (d / 'logs/run.stdout').write_text(stdout); (d / 'logs/run.stderr').write_text(err)
    star = 'data_general\n\n' + GLOBAL
    keep_model = (not reject) if model is None else model
    if keep_model:
        coeffs = p['coeffX_float'] + p['coeffY_float'] if p else [0.001 * i for i in range(36)]
        star += 'data_local_motion_model\n\nloop_\n_rlnMotionModelCoeffsIdx #1\n_rlnMotionModelCoeff #2\n' + \
                ''.join(f'{i:12d} {c:12.6f}\n' for i, c in enumerate(coeffs)) + '\n'
    (d / 'out/km_local_nonsquare.star').write_text(star)
    if mrc:
        (d / 'out/km_local_nonsquare.mrc').write_bytes(bytes(1024) + f'{case}:{"G" if reject else "L"}'.encode() * 64)
    (d / 'RUN.json').write_text(json.dumps({'rc': rc, 'stdout': str(d / 'logs/run.stdout'), 'stderr': str(d / 'logs/run.stderr'),
                                            'gpu_uuids_witnessed': [], 'binary_sha256': 'mock'}))


def scratch(root, mutate=None):
    s = root; src = s / 'src-cand/docs/post_rc0/issue264/native'
    (src / 'n3-iter2').mkdir(parents=True)
    shutil.copy(NATIVE / 'predictions.json', src / 'predictions.json')
    shutil.copy(ITER2, src / 'n3-iter2/predictions_iter2.json')
    for arm, algorithm in ARMS.items():
        for case in CASES:
            kw = mutate(arm, case) if mutate else {}
            if kw is None:
                continue
            row_files(s / 'n3-cpu1' / arm / case, case, kw.pop('algorithm', algorithm), **kw)
    return s


def grade(s):
    env = dict(os.environ, G_SCR=str(s), G_CPUS='14-15', G_GPU_UUID='GPU-mock', G_KM_MOVIE='/dev/null', OMP_NUM_THREADS='1')
    p = subprocess.run([sys.executable, '-B', str(HERE / 'n3_cpu1.py'), 'grade'], env=env, capture_output=True, text=True)
    rep = s / 'n3-cpu1/CPU_SUBSET.json'
    report = json.loads(rep.read_text()) if rep.exists() else None
    return p, report


def old33(arm, case):
    return {'value': float(V1[case]['finite']['value'])} if arm == 'ov-cand-cpu' and case.startswith('A_') else {}


SCENARIOS = {
    'positive': (None, 0, None),
    'missing_row': (lambda a, c: None if (a, c) == ('ov-cand-cpu', 'E_xy_nonsquare_near_threshold') else {}, 1, 'CPU rows not PASS'),
    'wrong_case': (lambda a, c: {'value': PRED['B_x_legacy_false_reject']['finite']['value'], 'guard': False}
                   if (a, c) == ('ov-cand-cpu', 'A_x_legacy_false_accept') else {}, 1, 'CPU rows not PASS'),
    'old_3p3_value': (old33, 1, 'CPU rows not PASS'),
    'absent_overlay': (lambda a, c: {'overlay': False} if (a, c) == ('ov-base-cpu', 'G_large_both_reject') else {}, 1, 'CPU rows not PASS'),
    'star_model_on_reject': (lambda a, c: {'model': True} if (a, c) == ('ov-cand-cpu', 'A_y_legacy_false_accept') else {}, 1, 'CPU rows not PASS'),
    'star_model_missing_on_accept': (lambda a, c: {'model': False} if (a, c) == ('ov-cand-cpu', 'B_x_legacy_false_reject') else {}, 1, 'CPU rows not PASS'),
    'mutant_behaves_like_candidate': (lambda a, c: {'algorithm': 'finite'} if a == 'ov-mut-cpu' else {}, 1, 'N4 not PASS'),
    'cuda_marker_in_cpu_arm': (lambda a, c: {'stdout': '[CUDA Global Alignment] completed;\n'} if (a, c) == ('ov-base-cpu', 'F_mild_both_accept') else {}, 1, 'CPU rows not PASS'),
    'nonzero_rc': (lambda a, c: {'rc': 1} if (a, c) == ('ov-mut-cpu', 'B_y_legacy_false_reject') else {}, 1, 'CPU rows not PASS'),
    'missing_mrc': (lambda a, c: {'mrc': False} if (a, c) == ('ov-cand-cpu', 'F_mild_both_accept') else {}, 1, 'original grader raised'),
    'overlay_on_no_overlay_row': (lambda a, c: {} , 1, 'CPU rows not PASS'),   # edited after synthesis below
    'pair_image_mismatch': (None, 1, 'CPU base/candidate pairs not 8 PASS'),     # edited after synthesis below
    'cuda_arm_present': (None, 1, 'CUDA rows are not exactly 16 UNRUN'),         # edited after synthesis below
    'wrong_predictions_file': (None, 1, 'hash mismatch'),                        # edited after synthesis below
}


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    results, ok = [], True
    for name, (mutate, want_rc, want_problem) in SCENARIOS.items():
        s = scratch(out / name, mutate)
        if name == 'overlay_on_no_overlay_row':
            f = s / 'n3-cpu1/ov-cand-cpu/Z_no_overlay/logs/run.stderr'; f.write_text(OVERLAY + f.read_text())
        if name == 'pair_image_mismatch':
            (s / 'n3-cpu1/ov-cand-cpu/F_mild_both_accept/out/km_local_nonsquare.mrc').write_bytes(bytes(1024) + b'different')
        if name == 'cuda_arm_present':
            row_files(s / 'n3-cpu1/ov-cand-cuda/A_x_legacy_false_accept', 'A_x_legacy_false_accept', 'finite')
        if name == 'wrong_predictions_file':
            f = s / 'src-cand/docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json'
            d = json.loads(f.read_text()); d['n3']['A_x_legacy_false_accept']['finite']['value'] = 3.3; f.write_text(json.dumps(d))
        p, report = grade(s)
        text = json.dumps(report) if report else p.stdout + p.stderr
        passed = p.returncode == want_rc and (want_problem is None or want_problem in text) and \
            (want_rc != 0 or (report and report['cpu_subset_verdict'] == 'PASS' and report['full_n3_n4_aggregate'].startswith('INCOMPLETE')))
        ok &= passed
        results.append({'scenario': name, 'exit': p.returncode, 'expected_exit': want_rc, 'expected_problem': want_problem,
                        'problems': report['problems'] if report else (p.stderr.strip().splitlines() or [''])[-1], 'control_ok': passed})
        print('ok ' if passed else 'BAD', name, p.returncode, (report or {}).get('problems', (p.stderr.strip().splitlines() or [''])[-1]))
    # Receipt and refusal controls: no MotionCorr binary is reached in any of them.
    s = out / 'receipts'; scratch(s, lambda a, c: None)
    env = dict(os.environ, G_SCR=str(s), G_CPUS='14-15', G_GPU_UUID='GPU-mock', G_KM_MOVIE='/dev/null', OMP_NUM_THREADS='1')
    cmd = lambda *a: subprocess.run([sys.executable, '-B', str(HERE / 'n3_cpu1.py'), *a], env=env, capture_output=True, text=True)
    first, again, gpu = cmd('receipts'), cmd('receipts'), cmd('run', 'gpu')
    rec = json.loads((s / 'n3-cpu1/known-observations.json').read_text())
    rec['rows']['ov-cand-cpu/A_x_legacy_false_accept']['MC264_N3_COEFFS'] += ' 0'
    (s / 'n3-cpu1/known-observations.json').write_text(json.dumps(rec))
    tampered = cmd('run', 'cpu')
    checks = {'receipts_written_24_rows': first.returncode == 0 and len(rec['rows']) == 24
                  and sum(r['overlay'] for r in rec['rows'].values()) == 21,
              'receipts_refuse_overwrite': again.returncode != 0 and 'exists; refusing' in again.stderr,
              'run_gpu_refused': gpu.returncode != 0 and 'CPU subset only' in gpu.stderr,
              'tampered_receipts_refused': tampered.returncode != 0 and 'receipts missing or different' in tampered.stderr,
              'no_run_directory_created': not any((s / 'n3-cpu1').glob('ov-*'))}
    for k, v in checks.items():
        print('ok ' if v else 'BAD', k); ok &= v
        results.append({'scenario': k, 'control_ok': v})
    # Source-binding controls: SOURCES.txt lines recorded by the iteration-1 setup (same src trees), with
    # src-cand pointing at this checkout; one altered helper hash must be rejected.
    repo = HERE.parents[4]
    lines = (HERE / 'iteration1_SOURCES.txt').read_text()
    for name, text, want in (('sources_bound', lines, 0),
                             ('sources_wrong_helper', lines.replace('helper=d531871f', 'helper=00000000'), 1)):
        s = out / name; s.mkdir(); (s / 'SOURCES.txt').write_text(text); os.symlink(repo, s / 'src-cand')
        env = dict(os.environ, G_SCR=str(s), G_SHA='0a1f64ab3e192c3ebad57b35149d872b21331730')
        p = subprocess.run([sys.executable, '-B', str(HERE / 'check_sources.py')], env=env, capture_output=True, text=True)
        v = p.returncode == want
        print('ok ' if v else 'BAD', name, p.returncode, p.stdout.strip().splitlines()[-1][:160]); ok &= v
        results.append({'scenario': name, 'exit': p.returncode, 'expected_exit': want, 'control_ok': v})
    (out / 'CONTROLS.json').write_text(json.dumps({'all_controls_ok': ok, 'results': results}, indent=1) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=pathlib.Path, required=True)
    sys.exit(main(ap.parse_args().out))
