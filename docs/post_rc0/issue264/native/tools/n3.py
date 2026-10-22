# SPDX-License-Identifier: GPL-2.0-or-later
"""N3/N4: guard decisions through the real runner on TEST-ONLY overlay builds.

The overlay (../n3_observation_overlay.patch) replaces the measured patch shifts with a
known model at the measured positions/frames, so the real SVD fit, guard, reconstruction
and STAR publication run on known observations. Overlay builds are never production or
ordinary-movie qualification. Fixture: km_local_nonsquare (768x512x12), read in place.

  n3.py run cpu|gpu    every case on the arms of that backend (gpu: caller holds the GPU1 lock)
  n3.py grade          RESULTS.json against the frozen predictions
"""
import json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runlib as r  # noqa: E402

N3 = r.SCR / 'n3'
PRED = json.loads((r.SCR / 'src-cand/docs/post_rc0/issue264/native/predictions.json').read_text())['n3']
ARMS = {'cpu': {'ov-base-cpu': 'legacy', 'ov-cand-cpu': 'finite', 'ov-mut-cpu': 'uncentred'},
        'gpu': {'ov-base-cuda': 'legacy', 'ov-cand-cuda': 'finite'}}
CASES = list(PRED) + ['Z_no_overlay']
GUARD = re.compile(r'could not fit a reasonable local motion model \(delta > ([-+0-9.eE]+)\)')
OVERLAY = re.compile(r'MC264_N3 overlay applied n_obs=(\d+) nx=(\d+) ny=(\d+) n_frames=(\d+)')
MOVIE = Path(os.environ['G_KM_MOVIE'])
STAR = ('# version 30001\n\ndata_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n'
        '_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n'
        'opticsGroup1 1 0.885000 300.0 2.7 0.1\n\n\n# version 30001\n\ndata_movies\n\nloop_\n'
        '_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\nkm_local_nonsquare.mrcs 1\n')


def run(backend):
    assert r.sha256_file(MOVIE) == os.environ['G_KM_SHA256'], 'fixture hash mismatch'
    status = 0
    for arm in ARMS[backend]:
        binary = r.SCR / f'build-{arm}' / 'motioncorr'
        for case in CASES:
            d = N3 / arm / case; cwd = d / 'cwd'
            if d.exists():
                raise SystemExit(f'{d} exists; a new iteration needs a new directory')
            cwd.mkdir(parents=True); os.symlink(MOVIE, cwd / 'km_local_nonsquare.mrcs')
            (cwd / 'km_local_nonsquare.star').write_text(STAR)
            args = [binary, '--i', 'km_local_nonsquare.star', '--o', f'{d}/out/', '--use_own', '--j', '1',
                    '--patch_x', '4', '--patch_y', '4', '--bin_factor', '1', '--seed', '1', '--save_noDW', '--skip_defect']
            if backend == 'gpu':
                args += ['--gpu', '0']
            env = {}
            if case != 'Z_no_overlay':
                p = PRED[case]
                env['MC264_N3_COEFFS'] = ' '.join(repr(v) for v in p['coeffX_float'] + p['coeffY_float'])
            rec = r.run(f'{arm}-{case}', args, cwd, d / 'logs', backend == 'gpu', env)
            rec.update({'arm': arm, 'case': case, 'binary_sha256': r.sha256_file(binary)})
            (d / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
            print(arm, case, 'rc', rec['rc'], 'wall_s', rec['wall_s'], 'uuids', rec['gpu_uuids_witnessed'])
            status |= rec['rc'] != 0
    return status


def star_blocks(path):
    text = Path(path).read_text()
    coeffs = None
    if 'data_local_motion_model' in text:
        vals = {}
        for line in text.split('data_local_motion_model', 1)[1].splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit():
                vals[int(parts[0])] = float(parts[1])
        coeffs = [vals.get(i) for i in range(36)]
    glob = text.split('data_global_shift', 1)[1].split('data_', 1)[0] if 'data_global_shift' in text else None
    return coeffs, glob


def mrc_data(path):
    b = Path(path).read_bytes()
    ext = int.from_bytes(b[92:96], 'little')
    return b[1024 + ext:]


def grade():
    rows, problems = [], []
    for backend, arms in ARMS.items():
        for arm, algorithm in arms.items():
            for case in CASES:
                d = N3 / arm / case
                if not (d / 'RUN.json').exists():
                    rows.append({'arm': arm, 'case': case, 'status': 'UNRUN'}); continue
                rec = json.loads((d / 'RUN.json').read_text())
                out = (Path(rec['stdout']).read_text(errors='replace') + Path(rec['stderr']).read_text(errors='replace'))
                guards = [float(m) for m in GUARD.findall(out)]
                overlays = OVERLAY.findall(out)
                star = d / 'out/km_local_nonsquare.star'
                coeffs, glob = star_blocks(star) if star.exists() else (None, None)
                row = {'arm': arm, 'case': case, 'algorithm': algorithm, 'rc': rec['rc'], 'binary_sha256': rec['binary_sha256'],
                       'gpu_uuids': rec['gpu_uuids_witnessed'], 'overlay_lines': overlays, 'guard_values': guards,
                       'observed_reject': bool(guards), 'local_model_in_star': coeffs is not None}
                bad = []
                if rec['rc'] != 0: bad.append(f"rc {rec['rc']}")
                if backend == 'gpu':
                    if rec['gpu_uuids_witnessed'] != [r.UUID] or 'Using CUDA acceleration on GPU device 0' not in out:
                        bad.append('GPU1 not witnessed')
                elif rec['gpu_uuids_witnessed'] or '[CUDA' in out:
                    bad.append('CUDA activity in a CPU arm')
                if len(guards) > 1: bad.append('more than one guard line')
                if case == 'Z_no_overlay':
                    if overlays: bad.append('overlay applied without MC264_N3_COEFFS')
                else:
                    p = PRED[case][algorithm]
                    row.update({'predicted_reject': p['reject'], 'predicted_value': p['value']})
                    if len(overlays) != 1 or tuple(map(int, overlays[0][1:])) != (768, 512, 12) or int(overlays[0][0]) <= 18:
                        bad.append(f'overlay witness {overlays}')
                    if row['observed_reject'] != p['reject']: bad.append('decision differs from prediction')
                    if guards and abs(guards[0] - p['value']) > 2e-5 * p['value']: bad.append(f'guard value {guards[0]} vs {p["value"]}')
                    if row['local_model_in_star'] == p['reject']: bad.append('STAR local model presence contradicts decision')
                    if coeffs is not None:
                        inj = PRED[case]['coeffX_float'] + PRED[case]['coeffY_float']
                        err = max(abs(a - b) - 1e-7 * abs(b) for a, b in zip(coeffs, inj))
                        row['max_coeff_excess_over_1e-7rel'] = err
                        if err > 1e-5: bad.append(f'published coefficients differ from injected by {err}')
                if row['local_model_in_star'] == row['observed_reject']: bad.append('STAR model presence vs guard line')
                row['global_shift_block'] = glob
                row['problems'] = bad; row['status'] = 'PASS' if not bad else 'FAIL'
                rows.append(row)
    by = {(x['arm'], x['case']): x for x in rows}
    pairs = []
    for backend, (b, c) in {'cpu': ('ov-base-cpu', 'ov-cand-cpu'), 'gpu': ('ov-base-cuda', 'ov-cand-cuda')}.items():
        for case in CASES:
            x, y = by.get((b, case)), by.get((c, case))
            if not x or not y or x.get('status') == 'UNRUN' or y.get('status') == 'UNRUN':
                continue
            same_global = x['global_shift_block'] is not None and x['global_shift_block'] == y['global_shift_block']
            same_decision = x['observed_reject'] == y['observed_reject']
            img_equal = mrc_data(N3 / b / case / 'out/km_local_nonsquare.mrc') == mrc_data(N3 / c / case / 'out/km_local_nonsquare.mrc')
            ok = same_global and (img_equal if same_decision else not img_equal)
            pairs.append({'backend': backend, 'case': case, 'same_global_shifts': same_global, 'same_decision': same_decision,
                          'image_data_equal': img_equal, 'status': 'PASS' if ok else 'FAIL'})
    mut = [x for x in rows if x['arm'] == 'ov-mut-cpu' and x['case'] != 'Z_no_overlay' and x.get('status') != 'UNRUN']
    cand = {x['case']: x for x in rows if x['arm'] == 'ov-cand-cpu'}
    killed = [x['case'] for x in mut if x['case'] in cand and x['observed_reject'] != cand[x['case']].get('observed_reject')]
    n4 = {'mutant_rows_match_uncentred_predictions': all(x['status'] == 'PASS' for x in mut) and len(mut) == len(PRED),
          'cases_where_mutant_decision_differs_from_candidate': killed}
    n4['status'] = 'PASS' if n4['mutant_rows_match_uncentred_predictions'] and killed else 'FAIL'
    summary = {'runs': {s: sum(x['status'] == s for x in rows) for s in ('PASS', 'FAIL', 'UNRUN')},
               'pairs': {s: sum(x['status'] == s for x in pairs) for s in ('PASS', 'FAIL')}, 'n4': n4['status']}
    for x in rows: x.pop('global_shift_block', None)
    result = {'kind': 'TEST-ONLY overlay builds; not production or ordinary-movie qualification',
              'summary': summary, 'rows': rows, 'base_vs_candidate': pairs, 'n4_mutant': n4}
    (N3 / 'RESULTS.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(summary)); [print(x['arm'], x['case'], x['status'], x.get('problems')) for x in rows if x['status'] != 'PASS']
    return 0 if summary['runs']['FAIL'] == 0 and summary['runs']['UNRUN'] == 0 and summary['pairs']['FAIL'] == 0 and n4['status'] == 'PASS' else 1


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'run': sys.exit(run(sys.argv[2]))
    if c == 'grade': sys.exit(grade())
    raise SystemExit('unknown command')
