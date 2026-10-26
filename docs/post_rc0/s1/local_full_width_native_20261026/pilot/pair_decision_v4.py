"""Pair and decision layer v4 for the HELD local full-width pilot (criteria: PAIR_V4_PLAN.md).

Pure consumer layer. It launches no producer, reads no movie or real image intensities and adds no estimator or numerical
operator. The pinned compare_products.py is executed as a subprocess; the pinned factorial_common.star_blocks and
manipulation are extracted by AST (that module has top-level venue-path side effects) and executed unchanged with only
`check` replaced by a function that raises PairError. A gate here is a condition for a parent driver, not permission.
"""
from pathlib import Path
import ast, hashlib, json, os, re, subprocess, sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
# Hashes of the unchanged v3 files: the trust root of this module (no circular self-hash).
ADMISSION_V3_SHA256 = '80f796393c1fa40f6e77855576b58439fcecf661057782c0c9a1ad56abb1b42b'
COMMANDS_V3_SHA256 = '2bd36face2fed6f6a92398eb0402a63e6c6ea3624832e45c823f289a061b8081'
V3_MODULE_SHA256 = 'bd685429028d6b5d7ce1665355dd120cde163966b5abb11fb51be4d8937bdccc'
ADMISSION_PATH = HERE / 'ADMISSION_DRAFT_v3.json'
COMMANDS_PATH = HERE / 'COMMANDS_DRAFT_v3.json'
LAUNCH_FIELDS = ('candidate_binary', 'source_archive', 'compiler_and_config', 'shared_libraries', 'venue_identity',
                 'fresh_venue_resource_admission', 'independent_source_clearance')
P1_CASES = ('affine', 'pedestal', 'zero', 'integer', 'fractional')
UNIDENTIFIABLE = ('flat', 'repeated')
METRICS = ('rms', 'p95', 'max')
PRE_ON_SCHEMA = 'local-full-width-pre-on-v4'
PAIR_SCHEMA = 'local-full-width-pair-v4'


class PairError(ValueError):
    def __init__(self, code, message=''):
        super().__init__(code + (': ' + message if message else ''))
        self.code = code


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha_file(p):
    return _sha_bytes(Path(p).read_bytes())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _h(obj):
    return _sha_bytes(_canon(obj))


def _strict(text, what):
    def bad(c):
        raise ValueError('non-finite constant ' + c)
    try:
        return json.loads(text, parse_constant=bad)
    except ValueError as e:
        raise PairError('NONFINITE' if 'non-finite' in str(e) else 'JSON', what + ': ' + str(e))


# ---- trust root ---------------------------------------------------------------------------------------------------------
if _sha_file(HERE / 'score_fields_v3.py') != V3_MODULE_SHA256:
    raise PairError('ANCHOR', 'score_fields_v3.py differs from its pin')
sys.path.insert(0, str(HERE))
import score_fields_v3 as V3  # noqa: E402


def _load_anchored():
    ab, cb = ADMISSION_PATH.read_bytes(), COMMANDS_PATH.read_bytes()
    if _sha_bytes(ab) != ADMISSION_V3_SHA256:
        raise PairError('ANCHOR', 'admission file differs from its anchored hash')
    if _sha_bytes(cb) != COMMANDS_V3_SHA256:
        raise PairError('ANCHOR', 'commands file differs from its anchored hash')
    return _strict(ab.decode(), 'admission'), _strict(cb.decode(), 'commands')


class _Ctx:
    def __init__(self, roots, evidence_root, binary_path, binary_sha256, decision_dir, need_launch):
        self.adm, self.cmd = _load_anchored()
        self.roots, self.evidence_root = roots, str(evidence_root)
        self.binary_path, self.binary_sha256 = binary_path, binary_sha256
        self.decision_dir = Path(decision_dir) if decision_dir is not None else None
        if need_launch:
            if str(self.adm.get('status', '')).startswith('HELD_') or any(self.adm.get(k) is None for k in LAUNCH_FIELDS) \
                    or not isinstance(self.adm.get('candidate_source_commit'), str):
                raise PairError('HELD', 'admission is HELD or a launch field (binary/source/venue/lease/clearance) is null')
        try:
            V3.verify_tool_pins(self.adm, roots)
        except V3.AdmissionError as e:
            raise PairError('TOOL_PIN', str(e))
        self.identity = {k: self.adm.get(k) for k in LAUNCH_FIELDS + ('candidate_source_commit',)}

    def tool(self, suffix):
        t = [e for e in self.adm['tools'] if e['path'].endswith(suffix)]
        if len(t) != 1:
            raise PairError('TOOL_PIN', 'tool %s not pinned exactly once' % suffix)
        p = Path(self.roots[t[0]['root']]) / t[0]['path']
        if _sha_file(p) != t[0]['sha256']:
            raise PairError('TOOL_PIN', suffix + ' changed')
        return p

    def expected(self, case, arm):
        try:
            return V3.resolve_expected_row(self.cmd, self.adm, case, arm, self.evidence_root, self.binary_path, self.binary_sha256)
        except V3.AdmissionError as e:
            raise PairError(e.code, str(e))


def _check_decision_dir(decision_dir, *others):
    d = Path(decision_dir).resolve()
    for o in others:
        o = Path(o).resolve()
        if d == o or d.is_relative_to(o) or o.is_relative_to(d):
            raise PairError('DECISION_DIR', 'decision_dir overlaps %s' % o)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stop(decision_dir, e):
    try:
        d = Path(decision_dir)
        rec = {'code': getattr(e, 'code', type(e).__name__), 'message': str(e)}
        with (d / 'STOP_LOG.jsonl').open('a') as f:
            f.write(json.dumps(rec) + '\n')
        if not (d / 'STOP.json').exists():
            (d / 'STOP.json').write_text(json.dumps(rec, indent=1) + '\n')
    except OSError:
        pass


def _guarded(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (PairError, V3.AdmissionError) as e:
            dd = kw.get('decision_dir')
            if dd is not None and Path(dd).is_dir():
                _stop(dd, e)
            raise
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ---- single-run admission (v3 unchanged) + R2 W1 prescan ------------------------------------------------------------------
VARIANT = re.compile(r'local[\W_]*full[\W_]*width', re.I)


def _admit(ctx, case, arm, run_dir):
    exp = ctx.expected(case, arm)
    adm = V3.admit_producer(run_dir, exp, ctx.adm, ctx.evidence_root)
    text = (Path(run_dir) / 'output' / (case + '.log')).read_text()
    for ln in text.split('\n'):
        if VARIANT.search(ln) and ln != V3.WITNESS_LINE:
            raise PairError('WITNESS_VARIANT', 'non-exact local full-width line: %r' % ln[:100])
    return exp, adm


@_guarded
def admit_single(case, arm, run_dir, *, evidence_root, roots, binary_path, binary_sha256, decision_dir=None):
    ctx = _Ctx(roots, evidence_root, binary_path, binary_sha256, decision_dir, need_launch=False)
    return _admit(ctx, case, arm, run_dir)[1]


# ---- retained pieces -------------------------------------------------------------------------------------------------------
def _tree_hashes(root, code):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise PairError(code, '%s is not a real directory' % root)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for n in dirnames + filenames:
            if (Path(dirpath) / n).is_symlink():
                raise PairError(code, 'symlink under %s: %s' % (root, n))
        for n in filenames:
            p = Path(dirpath) / n
            out[p.relative_to(root).as_posix()] = (p.stat().st_size, _sha_file(p))
    return out


def _baseline_pins(ctx, case):
    rows = [r for r in ctx.adm['rows'] if r['case'] == case]
    if len(rows) != 1:
        raise PairError('CASES', 'case not in admission rows')
    return {k: (v['bytes'], v['sha256']) for k, v in rows[0]['baseline_files'].items()}


def _verify_baseline(ctx, case, baseline_dir):
    pins = _baseline_pins(ctx, case)
    disk = _tree_hashes(baseline_dir, 'BASELINE')
    if set(disk) != set(pins):
        raise PairError('BASELINE', 'inventory differs: only-disk %s, only-pin %s' % (sorted(set(disk) - set(pins)), sorted(set(pins) - set(disk))))
    for k in sorted(pins):
        if disk[k] != pins[k]:
            raise PairError('BASELINE', 'bytes/sha256 differ from the pin: ' + k)
    return pins


def _compare(ctx, a_root, b_root, out_dir):
    """Run the pinned comparator as a subprocess; retain command, rc, stdout, stderr and JSON in out_dir."""
    comparator = ctx.tool('compare_products.py')
    out_dir = Path(out_dir)
    if (out_dir / 'compare_products.json').exists():
        raise PairError('DECISION_DIR', 'retained comparator output already exists: %s' % out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / 'compare_products.json'
    cmd = [sys.executable, '-B', str(comparator), str(a_root), str(b_root), str(jp)]
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'}
    cp = subprocess.run(cmd, cwd=out_dir, env=env, capture_output=True, text=True, timeout=600)
    (out_dir / 'command.json').write_text(json.dumps({'argv': cmd, 'cwd': str(out_dir), 'env': env, 'returncode': cp.returncode, 'comparator_sha256': _sha_file(comparator)}, indent=1) + '\n')
    (out_dir / 'stdout.txt').write_text(cp.stdout)
    (out_dir / 'stderr.txt').write_text(cp.stderr)
    return _read_comparison(out_dir, a_root, b_root)


def _read_comparison(out_dir, a_root, b_root):
    out_dir = Path(out_dir)
    cmdj = _strict((out_dir / 'command.json').read_text(), 'command.json')
    jp = out_dir / 'compare_products.json'
    if cmdj['returncode'] != 0 or not jp.is_file():
        raise PairError('COMPARATOR', 'comparator rc=%s, json present=%s' % (cmdj['returncode'], jp.is_file()))
    j = _strict(jp.read_text(), 'compare_products.json')
    if j.get('verdict') != 'IDENTICAL' or j.get('n_gated_differing') != 0 or j.get('root_a') != str(Path(a_root).resolve()) or j.get('root_b') != str(Path(b_root).resolve()):
        raise PairError('COMPARATOR', 'verdict %r, differing %r' % (j.get('verdict'), j.get('n_gated_differing')))
    return {'command_sha256': _sha_file(out_dir / 'command.json'), 'json_sha256': _sha_file(jp), 'comparator_sha256': cmdj['comparator_sha256'],
            'n_files': j['n_files'], 'n_gated': j['n_gated']}


def _off_bound(ctx, case, off_dir, baseline_dir, cmp_dir, cmp_info):
    off = Path(off_dir)
    pins = _baseline_pins(ctx, case)
    return {
        'case': case,
        'off_receipt_sha256': _sha_file(off / 'RUN.json'),
        'off_runtime_sha256': _sha_file(off / 'runtime.json'),
        'off_output_inventory_sha256': _h(_tree_hashes(off / 'output', 'INVENTORY')),
        'baseline_inventory_sha256': _h(pins),
        'baseline_dir_inventory_sha256': _h(_tree_hashes(baseline_dir, 'BASELINE')),
        'comparator': cmp_info,
        'admission_sha256': _sha_bytes(ADMISSION_PATH.read_bytes()), 'commands_sha256': _sha_bytes(COMMANDS_PATH.read_bytes()),
        'tool_pins_sha256': _h(ctx.adm['tools']),
        'binary_path': ctx.binary_path, 'binary_sha256': ctx.binary_sha256, 'identity': ctx.identity,
    }


# ---- pre-ON gate -------------------------------------------------------------------------------------------------------------
@_guarded
def pre_ON_gate(case, off_dir, baseline_dir, *, evidence_root, roots, binary_path, binary_sha256, decision_dir):
    """Derive OFF compatibility from the admitted OFF run and the pinned retained baseline; return a hash-bound record."""
    decision_dir = _check_decision_dir(decision_dir, evidence_root, off_dir, baseline_dir)
    ctx = _Ctx(roots, evidence_root, binary_path, binary_sha256, decision_dir, need_launch=True)
    exp, _ = _admit(ctx, case, 'OFF', off_dir)
    if Path(off_dir).resolve() != Path(exp['cwd']).parent.resolve():
        raise PairError('RUN_DIR', 'OFF directory is not the resolved slot')
    _verify_baseline(ctx, case, baseline_dir)
    pins = _baseline_pins(ctx, case)
    off = Path(off_dir)
    for rel in ('runtime.json', 'output/%s.star' % case):
        if (off / rel).stat().st_size != pins[rel][0] or _sha_file(off / rel) != pins[rel][1]:
            raise PairError('OFF_RAW', 'OFF %s differs from the retained baseline bytes' % rel)
    cmp_dir = decision_dir / 'pre_on' / case
    cmp_info = _compare(ctx, Path(baseline_dir) / 'output', off / 'output', cmp_dir)
    bound = _off_bound(ctx, case, off_dir, baseline_dir, cmp_dir, cmp_info)
    rec = {'schema': PRE_ON_SCHEMA, 'status': 'PASS', 'bound': bound, 'binding_sha256': _h(bound),
           'note': 'condition for a parent driver; not a launch permission'}
    (cmp_dir / 'pre_on.json').write_text(json.dumps(rec, indent=1, allow_nan=False) + '\n')
    return rec


def _verify_pre_on(ctx, case, off_dir, baseline_dir, decision_dir):
    cmp_dir = Path(decision_dir) / 'pre_on' / case
    rp = cmp_dir / 'pre_on.json'
    if not rp.is_file():
        raise PairError('PRE_ON', 'pre-ON record absent for ' + case)
    rec = _strict(rp.read_text(), 'pre_on.json')
    if rec.get('schema') != PRE_ON_SCHEMA or rec.get('status') != 'PASS':
        raise PairError('PRE_ON', 'record schema/status')
    _verify_baseline(ctx, case, baseline_dir)
    cmp_info = _read_comparison(cmp_dir, Path(baseline_dir) / 'output', Path(off_dir) / 'output')
    bound = _off_bound(ctx, case, off_dir, baseline_dir, cmp_dir, cmp_info)
    if rec.get('bound') != bound or rec.get('binding_sha256') != _h(bound) or _h(rec['bound']) != rec['binding_sha256']:
        diff = sorted(k for k in set(bound) | set(rec.get('bound', {})) if bound.get(k) != rec.get('bound', {}).get(k))
        raise PairError('PRE_ON', 'record no longer binds the current OFF/baseline/pins: ' + ','.join(diff))
    return rec


# ---- pinned helpers by AST ---------------------------------------------------------------------------------------------------
def _pinned_functions(ctx):
    path = ctx.tool('factorial_common.py')
    src = path.read_text()
    tree = ast.parse(src)
    want = ('star_blocks', 'manipulation')
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in want]
    if sorted(n.name for n in nodes) != sorted(want):
        raise PairError('TOOL_PIN', 'factorial_common.py does not define exactly the expected functions once')

    def check(ok, message):
        if not ok:
            raise PairError('MANIPULATION', message)
    ns = {'re': re, 'Path': Path, 'check': check}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    seg = {n.name: _sha_bytes(ast.get_source_segment(src, n).encode()) for n in nodes}
    return ns['star_blocks'], ns['manipulation'], seg


# ---- pair --------------------------------------------------------------------------------------------------------------------
def _global_bits(run_dir):
    import numpy as np
    model = _strict((Path(run_dir) / 'runtime.json').read_text(), 'runtime.json')
    g = np.asarray(model['global'], dtype=np.float64)
    if g.shape != (5, 2):
        raise PairError('GLOBAL_RUNTIME', 'global shape %r' % (g.shape,))
    return g.view(np.uint64).tolist(), model['local_enabled']


def _arm_facts(ctx, case, arm, run_dir, fns):
    star_blocks, manipulation, _ = fns
    d = Path(run_dir)
    bits, local_enabled = _global_bits(d)
    blocks = star_blocks(d / 'output' / (case + '.star'))
    if 'global_shift' not in blocks:
        raise PairError('GLOBAL_STAR', 'no global_shift block in %s STAR' % arm)
    man = manipulation(d / 'stdout.log')
    try:
        conv = V3.V2.R.convergence(d / 'output' / (case + '.log'))
    except Exception as e:
        raise PairError('CONVERGENCE', '%s: %s' % (type(e).__name__, e))
    return {'global_bits': bits, 'global_star_block': blocks['global_shift'], 'manipulation': man, 'convergence': conv, 'local_enabled': local_enabled}


@_guarded
def admit_pair(case, off_dir, on_dir, baseline_dir, *, evidence_root, roots, binary_path, binary_sha256, decision_dir):
    decision_dir = _check_decision_dir(decision_dir, evidence_root, off_dir, on_dir, baseline_dir)
    ctx = _Ctx(roots, evidence_root, binary_path, binary_sha256, decision_dir, need_launch=True)
    _verify_pre_on(ctx, case, off_dir, baseline_dir, decision_dir)
    eo, _ = _admit(ctx, case, 'OFF', off_dir)
    en, _ = _admit(ctx, case, 'ON', on_dir)
    ro = _strict((Path(off_dir) / 'RUN.json').read_text(), 'OFF receipt'); rn = _strict((Path(on_dir) / 'RUN.json').read_text(), 'ON receipt')
    if ro['binary_sha256'] != rn['binary_sha256'] or ro['argv'][0] != rn['argv'][0] or ro['binary_sha256'] != binary_sha256:
        raise PairError('PAIR_BINARY', 'OFF and ON do not share one binary')
    fns = _pinned_functions(ctx)
    fo, fn_ = _arm_facts(ctx, case, 'OFF', off_dir, fns), _arm_facts(ctx, case, 'ON', on_dir, fns)
    if fo['global_bits'] != fn_['global_bits']:
        raise PairError('GLOBAL_RUNTIME', 'full-precision global trajectory differs between OFF and ON (float64 bit patterns)')
    if fo['global_star_block'] != fn_['global_star_block']:
        raise PairError('GLOBAL_STAR', 'serialised global block differs between OFF and ON')
    grid = eo['patch_grid']
    local3 = grid == [3, 3]
    mo, mn = fo['manipulation'], fn_['manipulation']
    for arm, m in (('OFF', mo), ('ON', mn)):
        le = m['dc']['local_eligible']
        if m['dc']['global_eligible'] <= 0:
            raise PairError('MANIPULATION', '%s global DC eligible is 0' % arm)
        if local3 and le <= 0:
            raise PairError('MANIPULATION', '%s 3x3 local DC eligible is 0' % arm)
        if not local3 and (le != 0 or m['coupled']['patch']['peaks'] != 0):
            raise PairError('MANIPULATION', '%s global-only case has local DC/coupled work' % arm)
    for key in ('global_zeroed', 'global_eligible'):
        if mo['dc'][key] != mn['dc'][key]:
            raise PairError('COUNTERS', 'global DC %s drifted: %s vs %s' % (key, mo['dc'][key], mn['dc'][key]))
    if mo['coupled']['global'] != mn['coupled']['global']:
        raise PairError('COUNTERS', 'global coupled counters drifted')
    pair_dir = decision_dir / 'pair' / case
    global_only = None
    if not local3:
        for rel in ('runtime.json', 'output/%s.star' % case):
            if (Path(off_dir) / rel).read_bytes() != (Path(on_dir) / rel).read_bytes():
                raise PairError('GLOBAL_ONLY', 'global-only OFF/ON %s bytes differ' % rel)
        try:
            global_only = _compare(ctx, Path(off_dir) / 'output', Path(on_dir) / 'output', pair_dir)
        except PairError as e:
            raise PairError('GLOBAL_ONLY', 'whole-product comparator: ' + str(e))
    rec = {'schema': PAIR_SCHEMA, 'case': case, 'patch_grid': grid, 'binary_sha256': binary_sha256,
           'off_receipt_sha256': _sha_file(Path(off_dir) / 'RUN.json'), 'on_receipt_sha256': _sha_file(Path(on_dir) / 'RUN.json'),
           'global_bits_equal': True, 'global_star_block_equal': True, 'global_only_comparator': global_only,
           'witness_lines': {'OFF': eo['expected_witness_lines'], 'ON': en['expected_witness_lines']},
           'counters': {'OFF': mo, 'ON': mn}, 'local_enabled': {'OFF': fo['local_enabled'], 'ON': fn_['local_enabled']},
           'convergence': {'OFF': fo['convergence'], 'ON': fn_['convergence']},
           'pinned_function_segments_sha256': fns[2],
           'note': 'local_enabled/convergence are recorded separately and are not truth surrogates'}
    pair_dir.mkdir(parents=True, exist_ok=True)
    (pair_dir / 'pair.json').write_text(json.dumps(rec, indent=1, allow_nan=False) + '\n')
    return rec


# ---- decision ----------------------------------------------------------------------------------------------------------------
def _score_arm(case, arm, run_dir, expected, adm, evidence_root, fixture_dir):
    return V3.score_admitted(run_dir, expected, adm, evidence_root, fixture_dir)


@_guarded
def decide_pilot(*, evidence_root, baseline_root, fixture_dir, roots, binary_path, binary_sha256, decision_dir, cases=None):
    decision_dir = _check_decision_dir(decision_dir, evidence_root, baseline_root)
    ctx = _Ctx(roots, evidence_root, binary_path, binary_sha256, decision_dir, need_launch=True)
    order = list(ctx.adm['case_order'])
    if cases is not None and list(cases) != order:
        raise PairError('CASES', 'cases must be exactly %s in order, got %s' % (order, list(cases)))
    ev = Path(evidence_root)
    present = sorted(p.name for p in ev.iterdir()) if ev.is_dir() else []
    if present != sorted(order):
        raise PairError('CASES', 'evidence_root entries %s differ from the 8 admitted cases' % present)
    for case in order:  # structure first: every case must be a complete OFF/ON pair before anything is admitted
        cd = ev / case
        if not cd.is_dir() or sorted(p.name for p in cd.iterdir()) != ['OFF', 'ON'] or not ((cd / 'OFF').is_dir() and (cd / 'ON').is_dir()):
            raise PairError('CASES', 'case %s lacks a complete OFF/ON pair' % case)
    scores, pairs = {}, {}
    for case in order:
        off, on = ev / case / 'OFF', ev / case / 'ON'
        base = Path(baseline_root) / case
        pairs[case] = admit_pair(case, off, on, base, evidence_root=evidence_root, roots=roots, binary_path=binary_path,
                                 binary_sha256=binary_sha256, decision_dir=decision_dir)
        scores[case] = {arm: _score_arm(case, arm, d, ctx.expected(case, arm), ctx.adm, ctx.evidence_root, fixture_dir) for arm, d in (('OFF', off), ('ON', on))}
    result = _decide(scores)
    result['pair_record_sha256'] = {c: _h(p) for c, p in pairs.items()}
    (decision_dir / 'DECISION.json').write_text(json.dumps(result, indent=1, allow_nan=False) + '\n')
    return result


def _decide(scores):
    """Pure rule evaluation over already admitted and scored arms."""
    lim = {'rms': .20, 'p95': .40, 'max': .80}

    def gate(a):
        return 'PASS' if all(a[k] <= v for k, v in lim.items()) else 'FAIL'
    p1 = {}
    for c in P1_CASES:
        p1[c] = {'OFF': {f: gate(scores[c]['OFF'][f]['angstrom']) for f in ('runtime', 'STAR')},
                 'ON': {f: gate(scores[c]['ON'][f]['angstrom']) for f in ('runtime', 'STAR')}}
    p1_ok = all(v['ON'][f] == 'PASS' for v in p1.values() for f in ('runtime', 'STAR'))
    n = scores['noisy']
    p2_detail = {f: {k: {'OFF': n['OFF'][f]['angstrom'][k], 'ON': n['ON'][f]['angstrom'][k], 'strictly_lower': n['ON'][f]['angstrom'][k] < n['OFF'][f]['angstrom'][k]} for k in METRICS} for f in ('runtime', 'STAR')}
    p2_ok = all(p2_detail[f][k]['strictly_lower'] for f in p2_detail for k in METRICS)
    noisy_gate = {f: gate(n['ON'][f]['angstrom']) for f in ('runtime', 'STAR')}
    increases = []
    for c, arms in scores.items():
        for f in ('runtime', 'STAR'):
            for k in METRICS:
                off, on = arms['OFF'][f]['angstrom'][k], arms['ON'][f]['angstrom'][k]
                if on > off:
                    increases.append({'case': c, 'field': f, 'metric': k, 'OFF': off, 'ON': on,
                                      'gate_transition': '%s->%s' % (gate(arms['OFF'][f]['angstrom']), gate(arms['ON'][f]['angstrom']))})
    return {
        'schema': 'local-full-width-decision-v4',
        'P1': {'ok': p1_ok, 'cases': p1},
        'P2': {'ok': p2_ok, 'noisy': p2_detail},
        'noisy_raw_gate': 'PASS' if all(v == 'PASS' for v in noisy_gate.values()) else 'FAIL', 'noisy_raw_gate_by_field': noisy_gate,
        'increases': increases,
        'unidentifiable': {c: {'status': 'UNIDENTIFIABLE', 'raw_distances_angstrom': {arm: {f: scores[c][arm][f]['angstrom'] for f in ('runtime', 'STAR')} for arm in ('OFF', 'ON')},
                               'raw_distances_px': {arm: {f: scores[c][arm][f]['px'] for f in ('runtime', 'STAR')} for arm in ('OFF', 'ON')}} for c in UNIDENTIFIABLE},
        'prediction': 'SUPPORTED' if (p1_ok and p2_ok) else 'NOT_SUPPORTED',
        'acceptance': 'NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE',
        'scope': 'no full100, adoption, image or CUDA meaning; synthetic tests establish consumer logic only',
    }
