# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only diagnosis of the cpu1 base/candidate global-shift pair failures.

Uses the unchanged grader extraction (tools/n3.py star_blocks) on the retained native STARs,
then compares the numeric global-shift rows separately from the text that follows them.
Harm controls show the row comparison is sensitive and reproduce the extraction mechanism
on synthetic STARs. Nothing here changes or re-runs the grade.
usage: diagnose_pairs.py EVIDENCE_DIR --out diagnosis.json
"""
import argparse, json, os, pathlib, re, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / 'src-cand').symlink_to(REPO)
os.environ.update(G_SCR=str(tmp), G_CPUS='14-15', G_GPU_UUID='none', G_KM_MOVIE='/dev/null')
sys.path.insert(0, str(HERE.parent / 'tools'))
import n3  # noqa: E402  (unchanged grader module; only star_blocks is called)

ROW = re.compile(r'^\s*(\d+)\s+(\S+)\s+(\S+)\s*$')
CASES = ['A_x_legacy_false_accept', 'B_x_legacy_false_reject', 'A_y_legacy_false_accept', 'B_y_legacy_false_reject',
         'E_xy_nonsquare_near_threshold', 'F_mild_both_accept', 'G_large_both_reject', 'Z_no_overlay']
ARMS = ['ov-base-cpu', 'ov-cand-cpu', 'ov-mut-cpu']


def rows_and_tail(block):
    rows = [m.groups() for m in map(ROW.match, block.splitlines()) if m]
    last = block.rstrip().splitlines()[-1] if block.strip() else ''
    tail = block[block.rindex(last) + len(last):] if last else block
    return rows, tail


def main(ev, out):
    result, ok = {'pairs': [], 'arms_all_equal_rows': {}}, True
    for case in CASES:
        blocks = {}
        for arm in ARMS:
            text = (ev / 'n3-cpu1' / arm / case / 'out/km_local_nonsquare.star').read_text()
            coeffs, glob = n3.star_blocks(ev / 'n3-cpu1' / arm / case / 'out/km_local_nonsquare.star')
            rows, tail = rows_and_tail(glob)
            blocks[arm] = {'rows': rows, 'tail': tail, 'model': coeffs is not None, 'raw': glob,
                           'next_block': (re.findall(r'^data_(\w+)', text.split('data_global_shift', 1)[1], re.M) or ['<end of file>'])[0]}
        b, c = blocks['ov-base-cpu'], blocks['ov-cand-cpu']
        pair = {'case': case, 'grader_same_global_shifts': b['raw'] == c['raw'],
                'numeric_rows_identical': b['rows'] == c['rows'], 'n_rows': len(b['rows']),
                'base_model_published': b['model'], 'cand_model_published': c['model'],
                'base_next_block': b['next_block'], 'cand_next_block': c['next_block'],
                'base_tail': b['tail'], 'cand_tail': c['tail']}
        pair['explained_by_tail_only'] = pair['numeric_rows_identical'] and (pair['grader_same_global_shifts'] or b['tail'] != c['tail'])
        result['pairs'].append(pair)
        result['arms_all_equal_rows'][case] = all(blocks[a]['rows'] == b['rows'] for a in ARMS)
        ok &= pair['numeric_rows_identical'] and pair['n_rows'] == 12
    # Harm control 1: the row comparison detects a 1e-6 change in one shift value.
    p = ev / 'n3-cpu1/ov-cand-cpu/A_x_legacy_false_accept/out/km_local_nonsquare.star'
    _, glob = n3.star_blocks(p)
    rows, _ = rows_and_tail(glob)
    bumped = glob.replace(rows[5][1], f'{float(rows[5][1]) + 1e-6:.6f}', 1)
    h1 = rows_and_tail(bumped)[0] != rows
    # Harm control 2: identical rows, one STAR followed by a local model block, one ending: the
    # unchanged extraction differs; rows equal. Reproduces the mechanism without a native run.
    head = '# version 50001\n\ndata_global_shift\n\nloop_ \n_rlnMicrographFrameNumber #1 \n' \
           '_rlnMicrographShiftX #2 \n_rlnMicrographShiftY #3 \n           1     0.000000     0.000000 \n \n'
    with tempfile.TemporaryDirectory() as d:
        a, r = pathlib.Path(d, 'a.star'), pathlib.Path(d, 'r.star')
        a.write_text(head + '\n# version 50001\n\ndata_local_motion_model\n\nloop_ \n_rlnMotionModelCoeffsIdx #1 \n'
                     '_rlnMotionModelCoeff #2 \n' + ''.join(f'{i:12d}     0.000000 \n' for i in range(36)))
        r.write_text(head)
        ga, gr = n3.star_blocks(a)[1], n3.star_blocks(r)[1]
        h2 = ga != gr and rows_and_tail(ga)[0] == rows_and_tail(gr)[0]
    result['harm_controls'] = {'row_compare_detects_1e-6_change': h1, 'extraction_differs_on_identical_rows_by_following_block': h2}
    result['all_pairs_numeric_rows_identical'] = ok
    for x in result['pairs']:
        print(x['case'], 'grader_same' if x['grader_same_global_shifts'] else 'grader_DIFF',
              'rows_identical' if x['numeric_rows_identical'] else 'ROWS_DIFFER',
              x['base_next_block'], '|', x['cand_next_block'], repr(x['base_tail']), repr(x['cand_tail']))
    print('harm controls', result['harm_controls'], 'all arms equal rows', all(result['arms_all_equal_rows'].values()))
    out.write_text(json.dumps(result, indent=1) + '\n')
    return 0 if ok and h1 and h2 else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('evidence', type=pathlib.Path); ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args(); sys.exit(main(a.evidence, a.out))
