# SPDX-License-Identifier: GPL-2.0-or-later
"""Controls for regrade_v2.py built from the real retained cpu1 evidence (real-writer STARs).

Each control rebuilds the hash-pinned evidence tar in memory with one edit, writes it into its own
directory under --out, and runs the grader as a subprocess. MRC files are tiny generated fixtures
used only by these controls (the retained archive has none). Exit 0 iff every control behaves as
expected. usage: test_regrade_v2.py --out NEW_DIR
"""
import argparse, hashlib, io, json, pathlib, subprocess, sys, tarfile

HERE = pathlib.Path(__file__).resolve().parent
NATIVE = HERE.parent
RAW = NATIVE / 'n3-cpu1-result/raw'
TAR, TAR_SHA = RAW / 'evidence.tar', '3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760'
PRED = NATIVE / 'n3-iter2/predictions_iter2.json'
CASES = list(json.loads(PRED.read_text())['n3']) + ['Z_no_overlay']
sha = lambda b: hashlib.sha256(b).hexdigest()
STAR = 'n3-cpu1/ov-cand-cpu/{}/out/km_local_nonsquare.star'
AX = 'A_x_legacy_false_accept'


def members():
    with tarfile.open(TAR, 'r:') as t:
        return [(m, t.extractfile(m).read() if m.isfile() else None) for m in t]


ORIGINAL = members()
FILES = {m.name: b for m, b in ORIGINAL if b is not None}


def rebuild(edits=None, add=None):
    edits, add = edits or {}, add or {}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.PAX_FORMAT) as t:
        for m, b in ORIGINAL:
            if m.name in edits:
                b = edits[m.name]
                if b is None:
                    continue
            info = tarfile.TarInfo(m.name); info.type = m.type; info.mode = m.mode; info.mtime = m.mtime
            if b is not None:
                info.size = len(b); t.addfile(info, io.BytesIO(b))
            else:
                t.addfile(info)
        for name, b in add.items():
            info = tarfile.TarInfo(name); info.size = len(b); info.mode = 0o644
            t.addfile(info, io.BytesIO(b))
    return buf.getvalue()


def star_edit(case, old, new, count=1):
    s = FILES[STAR.format(case)].decode()
    assert s.count(old) >= 1, (case, old)
    return {STAR.format(case): s.replace(old, new, count).encode()}


def mrc(payload, ext=0, ext_bytes=b''):
    h = bytearray(1024); h[92:96] = ext.to_bytes(4, 'little')
    return bytes(h) + ext_bytes + payload


def mrcs(override=None):
    pred = json.loads(PRED.read_text())['n3']
    out = {}
    for case in CASES:
        for arm, alg in (('ov-base-cpu', 'legacy'), ('ov-cand-cpu', 'finite')):
            reject = pred[case][alg]['reject'] if case in pred else False
            out[f'n3-cpu1/{arm}/{case}/out/km_local_nonsquare.mrc'] = mrc(f'{case}:{"G" if reject else "L"}'.encode() * 16)
    out.update(override or {})
    return {k: v for k, v in out.items() if v is not None}


def run_edit(name, f, n, field, value):
    rel = f'n3-cpu1/{n}/RUN.json'; d = json.loads(FILES[rel]); f(d); return {rel: json.dumps(d).encode()}


ROW2, ROW1 = '           2     -1.70013     1.382446 ', '           1     0.000000     0.000000 '
CONTROLS = [
    # name, tar bytes builder, expected exit, expected text in report/stderr
    ('real_evidence_star_layer_pass_full_unrun', lambda: TAR.read_bytes(), 2, None),
    ('trailing_zero_representation_equal', lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.700130 ')), 2, None),
    ('full_pass_with_generated_mrcs', lambda: rebuild(add=mrcs()), 0, None),
    ('mrc_extended_header_ignored', lambda: rebuild(add=mrcs({f'n3-cpu1/ov-cand-cpu/F_mild_both_accept/out/km_local_nonsquare.mrc':
                                                              mrc(b'F_mild_both_accept:L' * 16, 8, b'EXTENDED')})), 0, None),
    ('value_changed_1e-6', lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.700131 ')), 1, 'CPU pairs not 8'),
    ('missing_frame', lambda: rebuild(star_edit(AX, ROW2 + '\n', '')), 1, 'frames'),
    ('duplicate_frame', lambda: rebuild(star_edit(AX, ROW2 + '\n', ROW2 + '\n' + ROW2 + '\n')), 1, 'frames'),
    ('malformed_token', lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.7O013 ')), 1, 'malformed row'),
    ('nan_token', lambda: rebuild(star_edit(AX, '-1.70013 ', 'NaN ')), 1, 'malformed row'),
    ('inf_token', lambda: rebuild(star_edit(AX, '-1.70013 ', 'inf ')), 1, 'malformed row'),
    ('negative_zero_sign', lambda: rebuild(star_edit(AX, ROW1, '           1    -0.000000     0.000000 ')), 1, 'CPU pairs not 8'),
    ('wrong_label', lambda: rebuild(star_edit(AX, '_rlnMicrographShiftX #2', '_rlnMicrographShiftZ #2')), 1, 'schema'),
    ('missing_label', lambda: rebuild(star_edit(AX, '_rlnMicrographShiftY #3 \n', '')), 1, 'schema'),
    ('wrong_label_index', lambda: rebuild(star_edit(AX, '_rlnMicrographShiftY #3', '_rlnMicrographShiftY #4')), 1, 'schema'),
    ('second_global_block', lambda: rebuild({STAR.format(AX): FILES[STAR.format(AX)] + b'\ndata_global_shift\n'}), 1, '2 data_global_shift blocks'),
    ('global_block_absent', lambda: rebuild(star_edit(AX, 'data_global_shift', 'data_global_shiftless')), 1, '0 data_global_shift blocks'),
    ('mrc_wrong_payload_where_equal_expected', lambda: rebuild(add=mrcs({f'n3-cpu1/ov-cand-cpu/F_mild_both_accept/out/km_local_nonsquare.mrc':
                                                                           mrc(b'different' * 16)})), 1, 'image relation failed'),
    ('mrc_equal_where_flip_expected', lambda: rebuild(add=mrcs({f'n3-cpu1/ov-cand-cpu/{AX}/out/km_local_nonsquare.mrc':
                                                                  mrc(f'{AX}:L'.encode() * 16)})), 1, 'image relation failed'),
    ('mrc_malformed_short', lambda: rebuild(add=mrcs({f'n3-cpu1/ov-cand-cpu/G_large_both_reject/out/km_local_nonsquare.mrc': b'short'})), 1, 'image relation failed'),
    ('mrc_one_missing_full_unrun', lambda: rebuild(add=mrcs({f'n3-cpu1/ov-base-cpu/Z_no_overlay/out/km_local_nonsquare.mrc': None})), 2, None),
    ('row_rule_absent_overlay', lambda: rebuild({'n3-cpu1/ov-base-cpu/G_large_both_reject/logs/ov-base-cpu-G_large_both_reject.stderr':
                                                 FILES['n3-cpu1/ov-base-cpu/G_large_both_reject/logs/ov-base-cpu-G_large_both_reject.stderr'].replace(b'MC264_N3 overlay applied', b'MC264_N3 overlay skipped')}), 1, 'CPU rows not 24 PASS'),
    ('mutant_takes_candidate_decision', lambda: rebuild({'n3-cpu1/ov-mut-cpu/A_x_legacy_false_accept/logs/ov-mut-cpu-A_x_legacy_false_accept.stderr':
                                                         FILES['n3-cpu1/ov-cand-cpu/A_x_legacy_false_accept/logs/ov-cand-cpu-A_x_legacy_false_accept.stderr']}), 1, 'N4 not PASS'),
    ('binary_differs_from_receipt', lambda: rebuild(run_edit('x', lambda d: d.update(binary_sha256='0' * 64), 'ov-cand-cpu/F_mild_both_accept', None, None)), 1, 'CPU rows not 24 PASS'),
    ('injected_spec_differs', lambda: rebuild(run_edit('x', lambda d: d['env'].update(MC264_N3_COEFFS=d['env']['MC264_N3_COEFFS'] + ' 0'), 'ov-base-cpu/B_x_legacy_false_reject', None, None)), 1, 'CPU rows not 24 PASS'),
    ('stdout_not_bound', lambda: rebuild(run_edit('x', lambda d: d.update(stdout=d['stdout'].replace('B_y', 'B_x')), 'ov-mut-cpu/B_y_legacy_false_reject', None, None)), 1, 'CPU rows not 24 PASS'),
    ('missing_cpu_row', lambda: rebuild({'n3-cpu1/ov-cand-cpu/E_xy_nonsquare_near_threshold/RUN.json': None}), 1, 'CPU rows not 24 PASS'),
    ('cuda_artefact_present', lambda: rebuild(add={'n3-cpu1/ov-cand-cuda/A_x_legacy_false_accept/note': b'x'}), 1, 'CUDA rows are not exactly 16 UNRUN'),
    ('unsafe_member', lambda: rebuild(add={'../escape': b'x'}), 1, 'unsafe member'),
]


def grade(d, tarbytes, tar_sha=None, predictions=PRED):
    tp = d / 'evidence.tar'; tp.write_bytes(tarbytes)
    p = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'regrade_v2.py'), '--evidence-tar', str(tp),
                        '--evidence-sha256', tar_sha or sha(tarbytes), '--predictions', str(predictions),
                        '--receipts', str(RAW / 'known-observations.json'), '--original-results', str(RAW / 'RESULTS.json'),
                        '--out', str(d / 'grade')], capture_output=True, text=True, env={'OMP_NUM_THREADS': '1', 'PATH': '/usr/bin:/bin'})
    rep = d / 'grade/REGRADE_V2.json'
    return p, (json.loads(rep.read_text()) if rep.exists() else None)


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    assert sha(TAR.read_bytes()) == TAR_SHA
    results, ok = [], True
    for name, build, want, needle in CONTROLS:
        d = out / name; d.mkdir()
        p, rep = grade(d, build())
        blob = json.dumps(rep) if rep else p.stdout + p.stderr
        good = p.returncode == want and (needle is None or needle in blob)
        if name == 'real_evidence_star_layer_pass_full_unrun':
            flips = [x for x in rep['pairs'] if not x['same_decision']]
            hist = {x['case']: x['same_global_shifts'] for x in rep['historical_original']['pairs']}
            good &= len(flips) == 5 and all(x['global_rows_equal'] and not hist[x['case']] for x in flips) \
                and rep['row_parity_problems'] == [] and rep['historical_original']['summary']['pairs'] == {'PASS': 3, 'FAIL': 5}
        ok &= good
        results.append({'control': name, 'exit': p.returncode, 'expected_exit': want, 'expected_text': needle,
                        'problems': (rep or {}).get('problems'), 'control_ok': good})
        print('ok ' if good else 'BAD', name, p.returncode, ((rep or {}).get('problems') or [''])[:1])
    # Invalid-input controls on the real archive.
    extra = []
    d = out / 'wrong_tar_hash'; d.mkdir(); p, rep = grade(d, TAR.read_bytes(), tar_sha='0' * 64)
    extra.append(('wrong_tar_hash', p.returncode == 1 and 'evidence tar sha256' in json.dumps(rep)))
    d = out / 'wrong_predictions'; d.mkdir()
    bad = d / 'predictions.json'; bad.write_text(PRED.read_text().replace('"reject": true', '"reject": false', 1))
    p, rep = grade(d, TAR.read_bytes(), predictions=bad)
    extra.append(('wrong_predictions_hash', p.returncode == 1 and 'predictions sha256' in json.dumps(rep)))
    d = out / 'out_dir_exists'; d.mkdir(); (d / 'grade').mkdir(); p, rep = grade(d, TAR.read_bytes())
    extra.append(('existing_out_refused', p.returncode == 1 and 'FileExistsError' in p.stderr and rep is None))
    # Directory input (the remote form): extracted real evidence grades like the tar; a symlinked STAR is refused.
    def grade_dir(root, outdir):
        return subprocess.run([sys.executable, '-I', '-B', str(HERE / 'regrade_v2.py'), '--scratch-root', str(root),
                               '--predictions', str(PRED), '--receipts', str(RAW / 'known-observations.json'),
                               '--original-results', str(RAW / 'RESULTS.json'), '--out', str(outdir)],
                              capture_output=True, text=True, env={'OMP_NUM_THREADS': '1', 'PATH': '/usr/bin:/bin'})
    d = out / 'directory_input'; d.mkdir()
    with tarfile.open(TAR, 'r:') as t:
        for m in t:
            target = d / 'scratch' / m.name
            if m.isdir(): target.mkdir(parents=True, exist_ok=True)
            elif m.isfile(): target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(t.extractfile(m).read())
    p = grade_dir(d / 'scratch', d / 'grade')
    extra.append(('directory_input_star_layer_pass_full_unrun', p.returncode == 2))
    star = d / 'scratch' / STAR.format('F_mild_both_accept'); moved = d / 'outside.star'
    star.rename(moved); star.symlink_to(moved)
    p = grade_dir(d / 'scratch', d / 'grade-symlink')
    extra.append(('directory_input_symlink_refused', p.returncode == 1 and 'path escapes root' in (d / 'grade-symlink/REGRADE_V2.json').read_text()))
    for name, good in extra:
        ok &= good; results.append({'control': name, 'control_ok': good}); print('ok ' if good else 'BAD', name)
    (out / 'CONTROLS.json').write_text(json.dumps({'all_controls_ok': ok, 'n': len(results), 'results': results}, indent=1) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=pathlib.Path, required=True)
    sys.exit(main(ap.parse_args().out))
