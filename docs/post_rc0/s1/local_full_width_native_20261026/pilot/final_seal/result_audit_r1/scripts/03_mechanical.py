"""Mechanical checks over the audit bundle bytes: receipts/ledgers/launch budget, argv/env/witness, global pair equality,
global-only whole-product identity (receipt hashes + saved comparator), convergence markers, resource receipts.
Usage: python3 -I -B 03_mechanical.py BUNDLE OUT.json"""
import hashlib, json, re, struct, sys
from pathlib import Path
B, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
GRID3 = {'noisy', 'affine', 'pedestal'}
BIN = 'bb92e06116f434219ae3f94c4317ea9b0ea63ee9c5169fd03c28bc00de4d19bd'
FLAG = '--experimental_local_full_width_weight'
WIT = ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22'
def sha(b): return hashlib.sha256(b).hexdigest()
def fsha(p): return sha(Path(p).read_bytes())
def jl(p): return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
out = {'runs': {}, 'pairs': {}, 'ledger': {}, 'convergence': {}, 'resource': {}, 'problems': []}
P = out['problems']

# ---------------- ledgers / budget / terminal state
l1, l2 = jl(B / 'decision_r1/ledger.jsonl'), jl(B / 'decision_r2/ledger.jsonl')
fin1 = [e for e in l1 if e['event'] == 'finished']; fin2 = [e for e in l2 if e['event'] == 'finished']
lau1 = [e for e in l1 if e['event'] == 'launching']; lau2 = [e for e in l2 if e['event'] == 'launching']
receipts = {(e['case'], e['arm']): e['receipt_sha256'] for e in fin1 + fin2}
reused = [e for e in l2 if e['event'] == 'REUSED']
out['ledger'] = {
    'r1_events': [e['event'] for e in l1], 'r2_first_event': l2[0]['event'], 'r2_last_event': l2[-1],
    'r1_launches': len(lau1), 'r2_launches': len(lau2), 'total_launches': len(lau1) + len(lau2),
    'finished_total': len(fin1) + len(fin2), 'all_exit_0': all(e['exit'] == 0 and e['timed_out'] is False for e in fin1 + fin2),
    'unique_receipts': len(set(receipts.values())), 'unique_case_arm': len(receipts),
    'r2_has_STOP_event': any(e['event'] == 'STOP' for e in l2), 'r2_STOP_json_present': (B / 'decision_r2/STOP.json').exists(),
    'r1_ends_STOP': l1[-1]['event'] == 'STOP' and l1[-1]['code'] == 'COMPARATOR',
    'reused_event': reused[0] if reused else None,
    'reused_r1_ledger_sha_matches_bundle': bool(reused) and reused[0]['r1_ledger_sha256'] == fsha(B / 'decision_r1/ledger.jsonl'),
    'reused_r1_stop_sha_matches_bundle': bool(reused) and reused[0]['r1_stop_sha256'] == fsha(B / 'decision_r1/STOP.json'),
    'reused_receipt_equals_r1_finished': bool(reused) and reused[0]['run_json_sha256'] == fin1[0]['receipt_sha256'],
    'reused_off_index_receipt': json.loads((B / 'pins/REUSED_OFF_INDEX.json').read_text())['run_json_sha256'],
    'noisy_OFF_not_relaunched_in_r2': not any(e['case'] == 'noisy' and e['arm'] == 'OFF' for e in lau2),
    'r2_indices': [e['index'] for e in lau2],
    'decided_counts': {k: l2[-1].get(k) for k in ('launches', 'global_launches', 'prediction', 'acceptance')},
    'driver_rc': {p: (B / p).read_text().strip() for p in ('native_run_r1/driver.rc', 'native_run_r1/lane.rc', 'native_run_r2/driver.rc', 'native_run_r2/lane.rc')},
    'RESULT_equals_DECISION_bytes': (B / 'native_run_r2/RESULT.json').read_bytes() == (B / 'decision_r2/DECISION.json').read_bytes(),
    'RESULT_equals_DECISION_json': json.loads((B / 'native_run_r2/RESULT.json').read_text()) == json.loads((B / 'decision_r2/DECISION.json').read_text()),
}
L = out['ledger']
if not (L['total_launches'] == 16 and L['unique_receipts'] == 16 and L['all_exit_0'] and L['r2_last_event']['event'] == 'DECIDED' and not L['r2_has_STOP_event']): P.append('ledger/budget')

dec = json.loads((B / 'decision_r2/DECISION.json').read_text())
pair_sha_ok = {c: fsha(next((B / 'decision_r2/pair' / c).glob('run_*/pair.json'))) == dec['pair_record_sha256'][c] for c in CASES}
out['ledger']['decision_pair_record_sha_ok'] = pair_sha_ok

# ---------------- per run
cmds = json.loads((B / 'pins/COMMANDS_V5_2.json').read_text())
crow = {(r['case'], r['arm']): r for r in cmds}
envs = {}
for c in CASES:
    for a in ('OFF', 'ON'):
        d = B / 'runs' / c / a
        rb = (d / 'RUN.json').read_bytes(); r = json.loads(rb); inv = json.loads((d / 'products_inventory.json').read_text())
        row = {'receipt_sha_matches_ledger': sha(rb) == receipts[(c, a)], 'case_arm_ok': (r['case'], r['arm']) == (c, a), 'exit': r['exit'], 'timed_out': r['timed_out'],
               'binary_sha_ok': r['binary_sha256'] == BIN, 'inventory_RUN_sha_ok': inv['RUN.json']['sha256'] == sha(rb)}
        # copied file hashes vs inventory and receipt
        cop = {}
        for rel, e in inv.items():
            if e.get('copied_into_bundle'):
                local = d / (rel if rel in ('RUN.json', 'runtime.json', 'stdout.log') or rel.startswith('input/') else Path(rel).name)
                cop[rel] = local.exists() and fsha(local) == e['sha256']
        row['copied_files_match_inventory'] = cop
        pub = r['publication']; invout = {k[len('output/'):]: v for k, v in inv.items() if k.startswith('output/')}
        row['inventory_outputs_equal_receipt_publication'] = set(invout) == set(pub) and all(invout[k]['sha256'] == pub[k]['sha256'] and invout[k]['bytes'] == pub[k]['bytes'] for k in pub)
        row['runtime_sha_ok'] = fsha(d / 'runtime.json') == r['runtime']['sha256']; row['stdout_sha_ok'] = fsha(d / 'stdout.log') == r['stdout']['sha256']
        row['case_star_sha_ok'] = fsha(d / f'{c}.star') == pub[f'{c}.star']['sha256']; row['case_log_sha_ok'] = fsha(d / f'{c}.log') == pub[f'{c}.log']['sha256']
        row['ledger_input_sha_eq_admission_pins'] = None
        argv = r['argv']
        row['flag_count'] = argv.count(FLAG); row['flag_ok'] = row['flag_count'] == (1 if a == 'ON' else 0)
        row['argv0'] = argv[0]
        exp = crow[(c, a)]; root_exp, root_act = '/tmp/motioncorr-local-full-width-native-20261026', '/tmp/motioncorr-lfw-v5-20261026'
        ea = [argv[0] if t == '<PINNED_LINUX_BINARY>' else t.replace(root_exp, root_act) for t in exp['argv']]
        row['argv_equals_COMMANDS_V5_2_after_root_and_binary_substitution'] = ea == argv
        row['env_equals_COMMANDS_V5_2_after_root_substitution'] = {k: v.replace(root_exp, root_act) for k, v in exp['environment'].items()} == r['environment']
        row['cwd_ok'] = r['cwd'] == exp['cwd'].replace(root_exp, root_act)
        row['controlled_env_observed'] = r['controlled_environment_observed']
        row['extra_child_env'] = r.get('extra_child_environment')
        argv_sha_candidates = {'json_compact': sha(json.dumps(argv, separators=(',', ':')).encode()), 'json_default': sha(json.dumps(argv).encode()), 'nul_join': sha('\0'.join(argv).encode())}
        ledger_argv = next((e['argv_sha256'] for e in lau1 + lau2 if (e['case'], e['arm']) == (c, a)), None)
        row['ledger_argv_sha_reproduced_by'] = [k for k, v in argv_sha_candidates.items() if v == ledger_argv]
        log = (d / f'{c}.log').read_text().splitlines()
        row['log_first_line_ok'] = log[0] == f'Working on {c}.mrcs with 2 thread(s).'
        wl = [l for l in log if 'EXPERIMENTAL local full-width weight' in l]
        row['witness_lines'] = len(wl); row['witness_exact'] = all(l == WIT for l in wl)
        row['witness_expected'] = 9 if (a == 'ON' and c in GRID3) else 0
        rt = json.loads((d / 'runtime.json').read_text()); row['local_enabled'] = rt['local_enabled']
        # STAR patch coverage
        st = (d / f'{c}.star').read_text()
        m = re.search(r'data_local_shift\s+loop_\s+((?:_\S+ #\d+\s+)+)(.*?)(?:\n\s*\n|\Z)', st, re.S)
        rows = [l.split() for l in m.group(2).strip().splitlines()] if m else []
        row['star_local_shift_rows'] = len(rows); row['star_patch_centres'] = sorted({(float(x[1]), float(x[2])) for x in rows})
        out['runs'][f'{c}/{a}'] = row
        envs[(c, a)] = {k: v for k, v in r['environment'].items() if k != 'MC_DIAG_MODEL_OUT'}
        bad = [k for k, v in row.items() if v is False] + [k for k, v in cop.items() if not v]
        if bad or row['witness_lines'] != row['witness_expected'] or row['exit'] != 0: P.append((c, a, bad))
out['env_identical_except_model_out_path'] = len({json.dumps(v, sort_keys=True) for v in envs.values()}) == 1

# ---------------- convergence (native markers)
tol_re = re.compile(r'\[align\] scope=global iterations=(\d+) max_iter=(\d+) converged=(\d) last_rmsd_px=(\S+) tolerance_px=(\S+)')
for c in CASES:
    pr = json.loads(next((B / 'decision_r2/pair' / c).glob('run_*/pair.json')).read_text())
    for a in ('OFF', 'ON'):
        d = B / 'runs' / c / a
        so = (d / 'stdout.log').read_text().splitlines()
        marks = [(i + 1, tol_re.search(l)) for i, l in enumerate(so) if '[align]' in l]
        g = {'stdout_align_markers': len(marks)}
        if len(marks) == 1 and marks[0][1]:
            ln, mm = marks[0]; it, mx, cv, last, tol = int(mm[1]), int(mm[2]), int(mm[3]), float(mm[4]), float(mm[5])
            g.update(file=f'runs/{c}/{a}/stdout.log', line=ln, iterations=it, max_iter=mx, converged_marker=cv, last_rmsd=last, tol=tol,
                     marker_consistent_with_rmsd=(cv == 1) == (last < tol))
            g['global_status'] = 'TRUE' if cv == 1 else 'FALSE'
        else: g['global_status'] = 'MISSING' if not marks else 'AMBIGUOUS'
        # log blocks
        lg = (d / f'{c}.log').read_text().splitlines()
        blocks, cur = [], None
        for i, l in enumerate(lg):
            if l.startswith('Global alignment:'): cur = {'name': 'global', 'start': i + 1, 'rmsd': []}; blocks.append(cur)
            elif l.startswith('Patch ('): cur = {'name': l.split(':')[0], 'start': i + 1, 'rmsd': []}; blocks.append(cur)
            elif cur is not None:
                mm = re.match(r'\s*Iteration (\d+): RMSD = (\S+) px', l)
                if mm: cur['rmsd'].append(float(mm[2]))
        glog = blocks[0]
        g['log_global_iterations'] = len(glog['rmsd']); g['log_global_last'] = glog['rmsd'][-1]
        g['log_vs_marker_agree'] = g.get('iterations') == len(glog['rmsd']) and abs(g.get('last_rmsd', -1) - glog['rmsd'][-1]) < 1e-12
        pats = []
        for b in blocks[1:]:
            last = b['rmsd'][-1] if b['rmsd'] else None
            st = 'MISSING' if last is None else ('AMBIGUOUS' if last == 0.5 else ('TRUE' if last < 0.5 else 'FALSE'))
            pats.append({'patch': b['name'], 'log_line': b['start'], 'iterations': len(b['rmsd']), 'last_rmsd': last, 'derived_status': st})
        g['patches'] = pats
        g['patch_counts'] = {s: sum(p['derived_status'] == s for p in pats) for s in ('TRUE', 'FALSE', 'AMBIGUOUS', 'MISSING')}
        pc = pr['convergence'][a]
        g['pair_json'] = {'global_converged': pc['global_converged'], 'global_converged_type': type(pc['global_converged']).__name__, 'iterations': pc['global_iterations'],
                          'patch_converged': [p['converged'] for p in pc['patches']], 'patch_types': sorted({type(p['converged']).__name__ for p in pc['patches']}), 'source': pc.get('source')}
        g['pair_json_agrees'] = (pc['global_converged'] is (g['global_status'] == 'TRUE')) and [p['converged'] for p in pc['patches']] == [p['derived_status'] == 'TRUE' for p in pats] \
            and [p['final_increment_px'] for p in pc['patches']] == [p['last_rmsd'] for p in pats]
        out['convergence'][f'{c}/{a}'] = g
        if not g['pair_json_agrees'] or not g.get('marker_consistent_with_rmsd') or not g['log_vs_marker_agree']: P.append(('convergence', c, a))

# ---------------- pairs
def star_block(text, name):
    i = text.index(name); j = text.find('# version', i); return text[i:j if j > 0 else None]
cnt_re = re.compile(r'\[coupled_peak\] scope=global peaks=(\d+) guard_fired=(\d+) \(not_negative_definite=(\d+), offset_gt_1px=(\d+)\)')
dc_re = re.compile(r'MC_EXPERIMENT_CCF_DC arm=(\S+) cpu\.global=(\d+)/(\d+) cpu\.local=(\d+)/(\d+)')
for c in CASES:
    o, n = B / 'runs' / c / 'OFF', B / 'runs' / c / 'ON'
    ro, rn = json.loads((o / 'runtime.json').read_text()), json.loads((n / 'runtime.json').read_text())
    gb = lambda r: b''.join(struct.pack('<d', float(x)) for row in r['global'] for x in row)
    so, sn = (o / f'{c}.star').read_text(), (n / f'{c}.star').read_text()
    to, tn = (o / 'stdout.log').read_text(), (n / 'stdout.log').read_text()
    RO, RN = json.loads((o / 'RUN.json').read_text()), json.loads((n / 'RUN.json').read_text())
    pr = json.loads(next((B / 'decision_r2/pair' / c).glob('run_*/pair.json')).read_text())
    rec = {'global_float64_bits_equal': gb(ro) == gb(rn), 'star_global_block_bytes_equal': star_block(so, 'data_global_shift') == star_block(sn, 'data_global_shift'),
           'star_general_block_equal': star_block(so, 'data_general') == star_block(sn, 'data_general'),
           'coupled_global_counters': [cnt_re.findall(to), cnt_re.findall(tn)], 'dc_counters': [dc_re.findall(to), dc_re.findall(tn)]}
    rec['coupled_global_equal'] = rec['coupled_global_counters'][0] == rec['coupled_global_counters'][1] and len(rec['coupled_global_counters'][0]) == 1
    dco, dcn = rec['dc_counters'][0][0], rec['dc_counters'][1][0]
    rec['dc_global_equal'] = dco[1:3] == dcn[1:3]; rec['dc_local_equal'] = dco[3:5] == dcn[3:5]
    rec['pair_json_claims'] = {k: pr[k] for k in ('global_bits_equal', 'global_star_block_equal', 'local_enabled', 'witness_lines')}
    rec['pair_json_agrees'] = pr['global_bits_equal'] == rec['global_float64_bits_equal'] and pr['global_star_block_equal'] == rec['star_global_block_bytes_equal']
    if c not in GRID3:
        rec['runtime_bytes_equal'] = (o / 'runtime.json').read_bytes() == (n / 'runtime.json').read_bytes()
        rec['case_star_bytes_equal'] = so == sn
        po, pn = RO['publication'], RN['publication']
        rec['publication_names_equal'] = set(po) == set(pn)
        rec['publication_sha_differs'] = sorted(k for k in po if po[k]['sha256'] != pn.get(k, {}).get('sha256'))
        cdir = next((B / 'decision_r2/pair' / c).glob('run_*'))
        cj = json.loads((cdir / 'compare_products.json').read_text())
        rec['comparator_stdout'] = (cdir / 'stdout.txt').read_text().strip(); rec['comparator_stderr_bytes'] = (cdir / 'stderr.txt').stat().st_size
        rec['comparator_json_sha_matches_pair'] = fsha(cdir / 'compare_products.json') == pr['global_only_comparator']['json_sha256']
        rec['comparator_command_sha_matches_pair'] = fsha(cdir / 'command.json') == pr['global_only_comparator']['command_sha256']
        rec['comparator_json_top'] = {k: v for k, v in cj.items() if not isinstance(v, (list, dict))}
    else:
        rec['runtime_coeffs_equal'] = ro['coeff_x'] == rn['coeff_x'] and ro['coeff_y'] == rn['coeff_y']
    out['pairs'][c] = rec

# ---------------- pre-ON
out['pre_on'] = {c: {'status': json.loads((B / 'decision_r2/pre_on' / c / 'pre_on.json').read_text())['status'],
                     'stdout': (B / 'decision_r2/pre_on' / c / 'stdout.txt').read_text().strip(),
                     'json_sha_bound': fsha(B / 'decision_r2/pre_on' / c / 'compare_products.json') == json.loads((B / 'decision_r2/pre_on' / c / 'pre_on.json').read_text())['bound']['comparator']['json_sha256']}
                 for c in CASES}
out['pre_on_r1_noisy_stdout'] = (B / 'decision_r1/pre_on/noisy/stdout.txt').read_text().strip() if (B / 'decision_r1/pre_on/noisy/stdout.txt').exists() else None

# ---------------- resources (recompute summaries from stored samples)
for c in CASES:
    for a in ('OFF', 'ON'):
        r = json.loads((B / 'runs' / c / a / 'RUN.json').read_text()); rs = r['resource_samples']; ss = rs['samples']
        procs = [p for s in ss for p in s['procs']]
        rec = {'status': rs['status'], 'n_samples': rs['n_samples'], 'stored': len(ss), 'truncated': rs['truncated'], 'read_failures': rs['read_failures'], 'first_errors': rs['first_errors'],
               'vanished': rs['vanished_reads'], 'children_missing': rs['children_file_missing_reads'],
               'recomputed_max_threads': max(p['threads'] for p in procs), 'recomputed_max_tasks': max(p['tasks'] for p in procs),
               'recomputed_masks': sorted({p['cpus_allowed_list'] for p in procs}), 'recomputed_pids': sorted({p['pid'] for p in procs}),
               'recomputed_span_ms': [ss[0]['t_ms'], ss[-1]['t_ms']], 'proc_names': sorted({p['name'] for p in procs}),
               'max_procs_in_one_sample': max(len(s['procs']) for s in ss), 'wall_s': r['wall_seconds_receipt_only']}
        sm = rs['summary']
        rec['summary_agrees'] = (sm['max_threads'], sm['max_tasks'], sorted(sm['distinct_cpus_allowed_lists']), sorted(sm['processes_seen']), [sm['first_ms'], sm['last_ms']]) == \
            (rec['recomputed_max_threads'], rec['recomputed_max_tasks'], rec['recomputed_masks'], rec['recomputed_pids'], rec['recomputed_span_ms'])
        out['resource'][f'{c}/{a}'] = rec
        if not rec['summary_agrees'] or rec['status'] != 'OBSERVED': P.append(('resource', c, a))

OUT.write_text(json.dumps(out, indent=1, default=str) + '\n')
print('problems:', P)
print(json.dumps(out['ledger'], indent=1, default=str)[:3000])
