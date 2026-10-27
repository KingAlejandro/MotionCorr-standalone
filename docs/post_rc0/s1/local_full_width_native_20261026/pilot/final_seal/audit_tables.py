"""Read-only audit tables from this bundle only (no producers, no fits). Recomputes the frozen runtime/actual-STAR metrics with the pinned v3 field operator on the bundled runtime.json, case STAR and truth,
and compares them with the retained DECISION.json. Usage: python -B audit_tables.py BUNDLE_DIR PILOT_DIR OUT_PREFIX  (PILOT_DIR holds score_fields_v2/v3; the pinned consumer sources must be at their pinned path)."""
import json, re, sys, glob
from pathlib import Path
sys.dont_write_bytecode = True
B, PILOT, OUT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(PILOT))
import score_fields_v3 as V3
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
dec = json.loads((B / 'decision_r2' / 'DECISION.json').read_text())
rows, maxdiff = {}, 0.0
for c in CASES:
    for a in ('OFF', 'ON'):
        d = B / 'runs' / c / a
        m = V3.field_metrics_bound(c, d / 'runtime.json', d / f'{c}.star', B / 'truth' / f'{c}_field.npy', B / 'truth')
        rows[(c, a)] = m
        log = (d / f'{c}.log').read_text()
        m['poly_fit_rmsd_px'] = [float(x) for x in re.findall(r'Polynomial fit RMSD: X = (\S+) px Y = (\S+) px', log)[0]] if 'Polynomial fit RMSD' in log else None
# compare with the retained decision
chk = []
for f in ('runtime', 'STAR'):
    for k in ('rms', 'p95', 'max'):
        for a in ('OFF', 'ON'):
            chk.append(abs(rows[('noisy', a)][f]['angstrom'][k] - dec['P2']['noisy'][f][k][a]))
for c in ('affine', 'pedestal', 'zero', 'integer', 'fractional'):
    for a in ('OFF', 'ON'):
        for f in ('runtime', 'STAR'):
            g = rows[(c, a)][f]['gate']
            assert g == dec['P1']['cases'][c][a][f], (c, a, f, g)
for c in ('flat', 'repeated'):
    for a in ('OFF', 'ON'):
        for f in ('runtime', 'STAR'):
            for k in ('rms', 'p95', 'max'):
                chk.append(abs(rows[(c, a)][f]['angstrom'][k] - dec['unidentifiable'][c]['raw_distances_angstrom'][a][f][k]))
maxdiff = max(chk)
out = {'recomputed_vs_DECISION_max_abs_difference_A': maxdiff, 'p1_gates_equal_decision': True, 'metrics': {}, 'resource': {}, 'pairs': {}, 'decision_scope_verbatim': dec['scope'], 'decision_acceptance': dec['acceptance'], 'increases': dec['increases'],
       'noisy_raw_gate': dec['noisy_raw_gate'], 'prediction': dec['prediction']}
for (c, a), m in rows.items():
    out['metrics'][f'{c}/{a}'] = {'runtime_A': m['runtime']['angstrom'], 'STAR_A': m['STAR']['angstrom'], 'runtime_gate': m['runtime']['gate'], 'STAR_gate': m['STAR']['gate'], 'runtime_px': m['runtime']['px'], 'STAR_px': m['STAR']['px'],
                                   'star_runtime_roundtrip_max_px': m['roundtrip_vector_max_px'], 'local_enabled': m['local_enabled'], 'poly_fit_rmsd_px': m['poly_fit_rmsd_px']}
    r = json.loads((B / 'runs' / c / a / 'RUN.json').read_text()); rs = r['resource_samples']; s = rs['summary']
    out['resource'][f'{c}/{a}'] = {'exit': r['exit'], 'timed_out': r['timed_out'], 'status': rs['status'], 'n_samples': rs['n_samples'], 'stored': rs['stored_samples'], 'truncated': rs['truncated'], 'read_failures': rs['read_failures'],
                                    'vanished_reads': rs['vanished_reads'], 'children_file_missing_reads': rs['children_file_missing_reads'], 'max_threads': s['max_threads'], 'max_tasks': s['max_tasks'], 'masks': s['distinct_cpus_allowed_lists'],
                                    'processes_seen': len(s['processes_seen']), 'span_ms': [s['first_ms'], s['last_ms']], 'wall_s': r['wall_seconds_receipt_only']}
for c in CASES:
    p = json.loads(Path(glob.glob(str(B / 'decision_r2' / 'pair' / c / 'run_*' / 'pair.json'))[0]).read_text())
    cv = p['convergence']
    pre = json.loads((B / 'decision_r2' / 'pre_on' / c / 'pre_on.json').read_text())
    def pat(a):
        ps = cv[a]['patches']
        return {'patches': len(ps), 'converged_true': sum(x['converged'] is True for x in ps), 'converged_false': sum(x['converged'] is False for x in ps), 'converged_none': sum(x['converged'] is None for x in ps), 'final_increment_px': [x['final_increment_px'] for x in ps]}
    ct = p['counters']
    out['pairs'][c] = {'patch_grid': p['patch_grid'], 'global_bits_equal': p['global_bits_equal'], 'global_star_block_equal': p['global_star_block_equal'], 'local_enabled': p['local_enabled'], 'witness_lines': p['witness_lines'],
                       'global_converged': {a: cv[a]['global_converged'] for a in ('OFF', 'ON')}, 'global_iterations': {a: cv[a]['global_iterations'] for a in ('OFF', 'ON')}, 'global_final_increment_px': {a: cv[a]['global_increment_px'][-1] for a in ('OFF', 'ON')},
                       'patch_convergence': {a: pat(a) for a in ('OFF', 'ON')}, 'dc_global_equal': ct['OFF']['dc']['global_eligible'] == ct['ON']['dc']['global_eligible'] and ct['OFF']['dc']['global_zeroed'] == ct['ON']['dc']['global_zeroed'],
                       'dc': {a: ct[a]['dc'] for a in ('OFF', 'ON')}, 'coupled_global_equal': ct['OFF']['coupled']['global'] == ct['ON']['coupled']['global'], 'coupled': {a: ct[a]['coupled'] for a in ('OFF', 'ON')},
                       'global_only_comparator': p['global_only_comparator'], 'pre_on_status': pre['status'], 'pre_on_comparator': pre['bound']['comparator']}
out['rejection_counts'] = 'NOT RECORDED as such in the saved logs/receipts (only per-patch convergence and the polynomial-fit RMSD are saved); not derived here'
Path(OUT + '.json').write_text(json.dumps(out, indent=1, allow_nan=False) + '\n')
print('recomputed vs DECISION max abs diff (A): %.3e' % maxdiff)
