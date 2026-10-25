# SPDX-License-Identifier: GPL-2.0-or-later
"""Mutant pass for regrade_v2_1.py against the built control inputs (AMENDMENT-1 A6).

Each mutant is a one-site source edit. The classification is declared here, before running:
  killed      - at least one control must fail;
  equivalent  - cannot change any outcome on this evidence (reason given);
  redundant   - another guard fires on every input that would trip it (reason given);
  untested    - no control can trigger it (reason given; a known limit, not coverage).
The pass fails if a declared 'killed' mutant survives or a non-'killed' one is killed (the reason would be wrong).
usage: mutants_v2_1.py --ns BUILT_SUITE_NS --out NEW_DIR
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.realpath(__file__))
SRC = open(os.path.join(HERE, 'regrade_v2_1.py')).read()
K, E, R, U = 'killed', 'equivalent', 'redundant', 'untested'
M = [
    ('y_ignored', "xa == xb and ya == yb", "xa == xb", K, ''),
    ('sign_removed', "and xa.is_signed() == xb.is_signed()\n                                    and ya.is_signed() == yb.is_signed() ", "", K, ''),
    ('frame_token_numeric_only', "if tok[0] != expected:", "if int(tok[0]) != int(expected):", K, ''),
    ('ascii_line_check_removed', "if not line.isascii():", "if False:", K, ''),
    ('value_regex_unicode', "re.ASCII)", "0)", E, 'every non-ASCII digit is rejected first by the ASCII line check'),
    ('row_count_check_removed', "if len(rows) != 12:", "if False:", U, 'no control truncates the last frame; frames 1..k still pass the token check'),
    ('nonfinite_check_removed', "if not (x.is_finite() and y.is_finite()):", "if False:", E, 'the ASCII value grammar admits no NaN/inf token'),
    ('mrc_size_check_removed', "if len(b) != MRC_SIZE:", "if False:", K, ''),
    ('mrc_descriptor_check_removed', "if desc != MRC_DESCRIPTOR:", "if False:", K, ''),
    ('mrc_map_word_removed', "if b[208:212] != b'MAP ':", "if False:", K, ''),
    ('pair_descriptor_equality_removed', "pr['descriptors_equal'] = db == dc", "pr['descriptors_equal'] = True", E,
     'every accepted MRC has exactly MRC_DESCRIPTOR, so two accepted descriptors are always equal'),
    ('contradiction_gate_removed', "if hist is not pr['image_data_equal']:", "if False:", R,
     'the original booleans equal the decision relation on this evidence, so the relation rule fails on the same inputs'),
    ('relation_rule_removed', "(pr['image_data_equal'] if pr['same_decision'] else not pr['image_data_equal'])", "True", R,
     'the contradiction gate fails on the same inputs (same reason, reversed)'),
    ('reread_check_removed', "if identity(files2, presence2) != ident: binding.append('input changed during grading')", "pass", U,
     'no control can change an input between the two reads without a test hook; the hook was deliberately not added'),
    ('precheck_binding_removed', "if ident['files'].get(rel) != rec: binding.append(f'changed after precheck {rel}')", "pass", K, ''),
    ('manifest_binding_removed', "if got == 'absent' or got is None or got['sha256'] != want: binding.append(f'manifest mismatch {rel}')", "pass", K, ''),
    ('symlink_leaf_read_as_missing', "                    raise Invalid(f'symlink leaf {rel}')\n                raise\n            try:\n                if not stat.S_ISREG(os.fstat(lfd).st_mode):",
     "                    return None\n                raise\n            try:\n                if not stat.S_ISREG(os.fstat(lfd).st_mode):", K, ''),
    ('dir_component_followed', "nfd = os.open(comp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)", "nfd = os.open(comp, os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)", K, ''),
    ('out_inside_scratch_allowed', "if root is not None and not outside(p, root):", "if False:", K, ''),
    ('noncanonical_root_allowed', "    if os.path.realpath(target) != target:\n        raise", "    if False:\n        raise", K, ''),
    ('run_argv_binding_removed', "('cwd', f'{RECORDED_ROOT}/{base}/cwd'), ('argv', want_argv)", "('cwd', f'{RECORDED_ROOT}/{base}/cwd')", K, ''),
    ('run_arm_binding_removed', "('label', label), ('arm', arm), ('case', case)", "('label', label), ('case', case)", K, ''),
    ('distinct_receipts_removed', "if None in arm_bin.values() or len(set(arm_bin.values())) != 3:", "if None in arm_bin.values():", K, ''),
    ('spec_hash_check_removed', " or sha(r['MC264_N3_COEFFS'].encode()) != r['spec_sha256']", "", R, 'the receipts file is sha256-pinned, so its spec_sha256 field cannot disagree'),
    ('receipt_vs_prediction_removed', "if rec_rows.get(f'{arm}/{case}', {}).get('MC264_N3_COEFFS') != spec: P.append", "if False: P.append", R,
     'receipts and predictions are both sha256-pinned and consistent'),
    ('parity_check_removed', "if parity: P.append('row parity with the original grader failed')", "pass", R,
     'a regression guard for the port; every control that changes a row also trips a row rule or binding'),
    ('n4_exact_kills_removed', "kills == expected_kills", "bool(kills)", E, 'mutant rows must match the uncentred predictions, which fixes the kill set'),
    ('pair_count_removed', "if len(pairs) != 8 or any(", "if any(", E, 'eight pairs exist whenever 24 CPU rows PASS'),
    ('live_index_check_removed', "if not got['index_unchanged']: P.append", "if False: P.append", U,
     'with GIT_OPTIONAL_LOCKS=0 git does not write the index, so no control can make this fire'),
    ('live_optional_locks_enabled', "env = {'GIT_OPTIONAL_LOCKS': '0',", "env = {'GIT_OPTIONAL_LOCKS': '1',", K,
     'the stale-index control must then see git rewrite the index'),
    ('live_distinct_removed', "if len({v['live']['sha256'] for v in rec['binaries'].values() if v['live']}) != len(expect['binaries']):", "if False:", K, ''),
    ('live_process_scan_ignored', "if hits: P.append", "if False: P.append", K, ''),
    ('live_receipt_ignored', "if live is None or live['sha256'] != want or receipt != want:", "if live is None or live['sha256'] != want:", K, ''),
]


def main(ns, out):
    os.makedirs(out)
    results, ok = [], True
    for name, old, new, kind, why in M:
        assert SRC.count(old) == 1, (name, SRC.count(old))
        d = os.path.join(out, name); os.makedirs(d)
        g = os.path.join(d, 'regrade_v2_1.py'); open(g, 'w').write(SRC.replace(old, new))
        p = subprocess.run([sys.executable, '-B', os.path.join(HERE, 'test_regrade_v2_1.py'), 'run', '--ns', ns, '--tag', f'mut-{name}', '--grader', g],
                           capture_output=True, text=True, env={'OMP_NUM_THREADS': '1', 'PATH': os.environ['PATH']})
        killed_by = [l.split()[1] for l in p.stdout.splitlines() if l.startswith('BAD')]
        killed = bool(killed_by)
        consistent = killed == (kind == K)
        if kind == 'killed' and name == 'live_optional_locks_enabled':
            consistent = killed and 'live_stale_index_stat_pass' in killed_by
        ok &= consistent
        results.append({'mutant': name, 'declared': kind, 'reason': why, 'killed': killed, 'killed_by': killed_by, 'consistent_with_declaration': consistent})
        print('ok ' if consistent else 'BAD', name, kind, killed_by[:4], flush=True)
    summary = {k: sum(r['declared'] == k for r in results) for k in (K, E, R, U)}
    open(os.path.join(out, 'MUTANTS.json'), 'w').write(json.dumps({'all_consistent': ok, 'declared': summary, 'results': results}, indent=1) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--ns', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); sys.exit(main(os.path.realpath(a.ns), os.path.realpath(a.out)))
