"""Tests for release v5 and the minimal driver (criteria frozen in V5_PLAN.md, section 5). Scratch files only; a fake child stands in for the
binary; the real comparator and the pinned helper functions run on synthetic trees; no MotionCorr movie and no real MRC pixels.
Synthetic runs test consumer/driver logic only, not that the real binary obeys it.

usage: python -B tests/test_release_v5.py RESULT.json [group ...]   (real NumPy interpreter; threads <= 2)
"""
import copy, hashlib, json, os, shutil, sys, tempfile, traceback
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V5DIR = HERE.parent
PILOT = V5DIR.parent
REPO = Path(os.environ['V5_PIN_REPO_ROOT']) if os.environ.get('V5_PIN_REPO_ROOT') else PILOT.parents[4]
sys.path.insert(0, str(V5DIR)); sys.path.insert(0, str(HERE))
import pair_decision_v5 as P5
import driver_v5 as D5
import fake_products as fp

V3 = P5.V3
CONSUMER = Path('/tmp/mc-w8-common-mean-screen-20261026/src_4fa272f6')
PIN_PILOT = Path(os.environ.get('V5_PIN_PILOT_ROOT', str(PILOT)))
ROOTS = {'consumer_source': CONSUMER, 'repo': REPO, 'pilot': PIN_PILOT}
ADM_REAL = json.loads((V5DIR / 'ADMISSION_V5.json').read_text())
ORDER = ADM_REAL['case_order']
sha = lambda b: hashlib.sha256(b).hexdigest()
RESULTS = []


def record(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''), flush=True)


def expect_code(name, code, fn):
    try:
        fn()
    except (P5.PairError, V3.AdmissionError, D5.DriverStop) as e:
        record(name, e.code == code, 'code=%s' % e.code if e.code == code else 'wanted %s got %s: %s' % (code, e.code, e))
        return
    except Exception as e:
        record(name, False, 'wrong exception %s: %s' % (type(e).__name__, e))
        return
    record(name, False, 'ACCEPTED but wanted %s' % code)


def crafted(rms, p95, mx):
    a = {'rms': rms, 'p95': p95, 'max': mx}
    return {'runtime': {'angstrom': dict(a), 'px': dict(a)}, 'STAR': {'angstrom': dict(a), 'px': dict(a)}}


def crafted_scores():
    s = {}
    for c in ORDER:
        if c in P5.P1_CASES:
            s[c] = {'OFF': crafted(.1, .2, .3), 'ON': crafted(.1, .2, .3)}
        elif c == 'noisy':
            s[c] = {'OFF': crafted(1.6, 3.3, 7.2), 'ON': crafted(1.2, 2.9, 6.0)}
        else:
            s[c] = {'OFF': crafted(2.0, 4.0, 8.0), 'ON': crafted(2.0, 4.0, 8.0)}
    return s


class W5:
    """One scratch world: fake binary, fixtures, baselines, archive, build receipt and a test admission with those real pins."""
    def __init__(self, scratch, budget=16):
        self.s = Path(scratch).resolve()
        self.ev, self.base, self.fix, self.dec = self.s / 'evidence', self.s / 'baseline', self.s / 'fixtures', self.s / 'decision'
        self.binpath = self.s / 'bin' / 'motioncorr'
        (self.s / 'bin').mkdir()
        src = (HERE / 'fake_motioncorr.py').read_text().split('\n', 1)[1]
        self.binpath.write_text('#!%s\n' % sys.executable + src)
        self.binpath.chmod(0o755)
        shutil.copy(HERE / 'fake_products.py', self.s / 'bin' / 'fake_products.py')
        self.adm = copy.deepcopy(ADM_REAL)
        self.adm['fixture_files'] = {}
        self.fix.mkdir()
        for c in ORDER:
            for n in (c + '.star', c + '.mrcs'):
                b = ('fixture %s %s' % (c, n)).encode(); (self.fix / n).write_bytes(b)
                self.adm['fixture_files'][n] = {'bytes': len(b), 'sha256': sha(b)}
        for row in self.adm['rows']:
            c = row['case']; d = self.base / c / 'UP_only'
            fp.write_output(d / 'output', c, 'OFF')
            (d / 'runtime.json').write_bytes(fp.runtime_bytes(c, 'OFF')); (d / 'stdout.log').write_text(fp.stdout_text(c))
            for n in ('RUN.json', 'admission.json', 'checker.json', 'checker.stdout', 'metrics.json', 'occupancy-before.txt', 'time.txt'):
                (d / n).write_text('baseline %s %s\n' % (c, n))
            row['baseline_files'] = {str(p.relative_to(d)): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in sorted(d.rglob('*')) if p.is_file()}
        self.archive = self.s / 'archive.tar'; self.archive.write_bytes(b'fake archive bytes')
        self.commit, self.tree = '1' * 40, '2' * 40
        self.receipt_path = self.s / 'build_receipt.json'
        self.write_receipt()
        a = self.adm
        a['status'] = 'FROZEN_PENDING_OPUS_DELTA_REVIEW'
        a['evidence_root'], a['baseline_root'], a['fixture_dir'] = str(self.ev), str(self.base), str(self.fix)
        a['tool_roots'] = {k: str(v) for k, v in ROOTS.items()}
        a['native_producer_budget'] = budget
        a['compiler_and_config'] = {'t': 1}; a['shared_libraries'] = {'t': 1}; a['venue_identity'] = {'t': 1}; a['independent_source_clearance'] = {'t': 1}
        a['fresh_venue_resource_admission'] = {'cpus': '32-47', 'max_foreign_busy_cores': 1.5, 'min_available_mem_mb': 1, 'campaign_root': str(self.s), 'prior_scratch_bytes': 0, 'scratch_cap_bytes': 1 << 40}
        self.refresh_identity()
        self.sync()

    def write_receipt(self, **over):
        r = {'source_archive': {'path': str(self.archive), 'sha256': sha(self.archive.read_bytes()), 'commit': self.commit, 'tree': self.tree},
             'binary': {'path': str(self.binpath), 'sha256': sha(self.binpath.read_bytes())}}
        for k, v in over.items():
            r[k].update(v)
        self.receipt_path.write_text(json.dumps(r))

    def refresh_identity(self):
        a = self.adm
        a['candidate_binary'] = {'path': str(self.binpath), 'sha256': sha(self.binpath.read_bytes())}
        a['source_archive'] = {'path': str(self.archive), 'sha256': sha(self.archive.read_bytes()), 'commit': self.commit, 'tree': self.tree}
        a['candidate_source_commit'] = self.commit
        a['build_receipt'] = {'path': str(self.receipt_path), 'sha256': sha(self.receipt_path.read_bytes())}

    def sync(self):
        cmds = json.loads(P5.COMMANDS_PATH.read_text())
        if self.adm.get('candidate_binary'):  # kept as is while a test nulls the identity field
            self.adm['resolved_commands_sha256'] = {}
            for r in cmds:
                exp = V3.resolve_expected_row(cmds, self.adm, r['case'], r['arm'], str(self.ev), self.adm['candidate_binary']['path'], self.adm['candidate_binary']['sha256'])
                self.adm['resolved_commands_sha256']['%s/%s' % (r['case'], r['arm'])] = P5._h({k: exp[k] for k in ('argv', 'cwd', 'environment', 'input_files')})
        p = self.s / 'ADMISSION_TEST.json'
        p.write_text(json.dumps(self.adm, indent=1))
        P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256 = p, sha(p.read_bytes())

    def modes(self, d):
        (self.s / 'bin' / 'fake_modes.json').write_text(json.dumps(d))

    def release(self, **over):
        r = {'release_module_sha256': sha((V5DIR / 'pair_decision_v5.py').read_bytes()), 'driver_sha256': sha((V5DIR / 'driver_v5.py').read_bytes()),
             'admission_sha256': sha(P5.ADMISSION_PATH.read_bytes()), 'delta_review_report_sha256': 'a' * 64, 'approved_by': 'parent'}
        r.update(over)
        self.dec.mkdir(exist_ok=True)
        (self.dec / 'PARENT_RELEASE.json').write_text(json.dumps(r))

    def produce(self, case, arm):
        ctx = P5.context(self.dec)
        d = D5.stage_run(ctx, case, arm)
        return D5.launch(ctx, case, arm, d, ctx.expected(case, arm), cpus=None, timeout=30, guard_receipt={}), d

    def gate(self, case):
        return P5.pre_ON_gate(case, decision_dir=self.dec)

    def pair(self, case):
        return P5.admit_pair(case, decision_dir=self.dec)


def fresh(fn, **kw):
    saved = (P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256, P5.COMMANDS_PATH, P5.COMMANDS_V5_SHA256, P5._score_arm)
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v5-') as t:
        try:
            return fn(W5(t, **kw))
        except Exception as e:
            record('INFRA fault in %s' % fn.__name__, False, ''.join(traceback.format_exception_only(type(e), e)).strip())
        finally:
            P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256, P5.COMMANDS_PATH, P5.COMMANDS_V5_SHA256, P5._score_arm = saved


def guard_ok(step):
    return {'step': step}


def run_ok(w, **kw):
    return D5.run_campaign(w.dec, execute=True, guard=kw.pop('guard', guard_ok), cpus=None, timeout=kw.pop('timeout', 30))


# =============================== groups ===============================================================================================
def g_identity(w):
    ctx = P5.context(w.dec)
    record('control: the test admission passes identity, pins and resolved commands', ctx.binary_sha256 == sha(w.binpath.read_bytes()))
    for f in P5.LAUNCH_FIELDS:
        saved = w.adm[f]; w.adm[f] = None; w.sync()
        expect_code('null %s refused' % f, 'HELD', lambda: P5.context(w.dec))
        w.adm[f] = saved
    w.sync()
    w.adm['status'] = 'HELD_X'; w.sync(); expect_code('HELD status refused', 'HELD', lambda: P5.context(w.dec)); w.adm['status'] = 'FROZEN_PENDING_OPUS_DELTA_REVIEW'; w.sync()
    # anchors
    p = P5.ADMISSION_PATH
    alt = w.s / 'adm_alt.json'; alt.write_text(p.read_text() + ' '); P5.ADMISSION_PATH = alt
    expect_code('altered anchored admission refused', 'ANCHOR', lambda: P5.context(w.dec)); P5.ADMISSION_PATH = p
    cp = w.s / 'commands_alt.json'; cmds = json.loads(P5.COMMANDS_PATH.read_text()); cmds[0]['argv'][cmds[0]['argv'].index('--max_iter') + 1] = '9'; cp.write_text(json.dumps(cmds))
    real_c = P5.COMMANDS_PATH; P5.COMMANDS_PATH = cp
    expect_code('hand-edited commands refused by the anchor', 'ANCHOR', lambda: P5.context(w.dec)); P5.COMMANDS_PATH = real_c
    # resolved commands bound by the admission
    saved = dict(w.adm['resolved_commands_sha256']); w.adm['resolved_commands_sha256']['noisy/ON'] = '0' * 64
    q = w.s / 'adm_rc.json'; q.write_text(json.dumps(w.adm)); P5.ADMISSION_PATH, P5.ADMISSION_V5_SHA256 = q, sha(q.read_bytes())
    expect_code('resolved command row differs from the frozen admission', 'IDENTITY', lambda: P5.context(w.dec))
    w.adm['resolved_commands_sha256'] = saved; w.sync()
    # actual files
    orig = w.binpath.read_bytes()
    w.binpath.write_bytes(orig + b'#changed\n')
    expect_code('binary on disk differs from candidate_binary.sha256', 'IDENTITY', lambda: P5.context(w.dec)); w.binpath.write_bytes(orig)
    other = w.s / 'bin' / 'copy_of_binary'; other.write_bytes(orig); other.chmod(0o755)
    saved_cb = copy.deepcopy(w.adm['candidate_binary']); w.adm['candidate_binary']['path'] = str(other); w.sync()
    expect_code('binary path differs from the build receipt (same bytes)', 'IDENTITY', lambda: P5.context(w.dec))
    w.adm['candidate_binary'] = copy.deepcopy(saved_cb); w.sync()
    # a symlinked binary whose receipt and pin agree on the link path: only the symlink guard can reject it
    link = w.s / 'bin' / 'link'; os.symlink(w.binpath, link)
    w.adm['candidate_binary'] = {'path': str(link), 'sha256': saved_cb['sha256']}; w.write_receipt(binary={'path': str(link)})
    w.adm['build_receipt'] = {'path': str(w.receipt_path), 'sha256': sha(w.receipt_path.read_bytes())}; w.sync()
    expect_code('binary given as a symlink (pin and receipt agree on the link)', 'IDENTITY', lambda: P5.context(w.dec))
    w.write_receipt(); w.refresh_identity(); w.sync()
    record('control: restored identity passes after the path tests', P5.context(w.dec).binary_path == str(w.binpath))
    a0 = w.archive.read_bytes(); w.archive.write_bytes(a0 + b'x')
    expect_code('source archive changed after the pin', 'IDENTITY', lambda: P5.context(w.dec)); w.archive.write_bytes(a0)
    w.adm['candidate_source_commit'] = '3' * 40; w.sync()
    expect_code('candidate_source_commit differs from source_archive.commit', 'IDENTITY', lambda: P5.context(w.dec)); w.adm['candidate_source_commit'] = w.commit; w.sync()
    r0 = w.receipt_path.read_bytes(); w.receipt_path.write_bytes(r0 + b' ')
    expect_code('build receipt changed after the pin', 'IDENTITY', lambda: P5.context(w.dec)); w.receipt_path.write_bytes(r0)
    for label, over in [('archive sha256', {'source_archive': {'sha256': 'f' * 64}}), ('commit', {'source_archive': {'commit': '4' * 40}}), ('tree', {'source_archive': {'tree': '5' * 40}}),
                        ('binary sha256', {'binary': {'sha256': 'e' * 64}}), ('binary path', {'binary': {'path': '/elsewhere/motioncorr'}})]:
        w.write_receipt(**over); w.refresh_identity(); w.sync()
        expect_code('build receipt with the wrong %s (pin refreshed)' % label, 'IDENTITY', lambda: P5.context(w.dec))
    w.write_receipt(); w.refresh_identity(); w.sync()
    saved_tools = copy.deepcopy(w.adm['tools']); w.adm['tools'][0]['sha256'] = '0' * 64; w.sync()
    expect_code('altered tool pin refused', 'TOOL_PIN', lambda: P5.context(w.dec)); w.adm['tools'] = saved_tools; w.sync()
    record('control: restored identity passes again', P5.context(w.dec).binary_path == str(w.binpath))
    for kw, extra in [('binary_path', '/x'), ('binary_sha256', 'a' * 64), ('roots', {}), ('evidence_root', '/x'), ('expected', {}), ('admission', {}), ('commands', [])]:
        try:
            P5.pre_ON_gate('noisy', decision_dir=w.dec, **{kw: extra}); record('signature rejects caller argument %s' % kw, False, 'accepted')
        except TypeError:
            record('signature rejects caller argument %s' % kw, True)


def g_l3(w):
    cases = [('OFF zero global DC counters', 'dc_zero', 'noisy'), ('OFF missing DC line', 'no_dc', 'noisy'), ('global-only OFF with local work', 'local_work', 'flat')]
    for name, mode, case in cases:
        w.modes({'%s/OFF' % case: {mode: True}})
        r, d = w.produce(case, 'OFF')
        expect_code('L3 gate stops before ON: ' + name, 'MANIPULATION', lambda: w.gate(case))
        record('L3 no ON directory exists after the gate stop (%s)' % case, not (w.ev / case / 'ON').exists())
        shutil.rmtree(w.ev / case)
        shutil.rmtree(w.dec / 'pre_on', ignore_errors=True)
    w.modes({})
    r, d = w.produce('noisy', 'OFF')
    # 3x3 OFF with zero local counters
    (d / 'stdout.log').write_text(fp.stdout_text('noisy', l=(0, 0)).replace('peaks=40 guard_fired=0 (not_negative_definite=0, offset_gt_1px=0)', 'peaks=0 guard_fired=0 (not_negative_definite=0, offset_gt_1px=0)'))
    rr = json.loads((d / 'RUN.json').read_text()); b = (d / 'stdout.log').read_bytes(); rr['stdout'] = {'bytes': len(b), 'sha256': sha(b)}; (d / 'RUN.json').write_text(json.dumps(rr))
    expect_code('L3 gate: 3x3 OFF with local eligible 0', 'MANIPULATION', lambda: w.gate('noisy'))
    shutil.rmtree(w.ev / 'noisy')
    w.produce('noisy', 'OFF')
    record('control: a clean OFF passes the gate', w.gate('noisy')['status'] == 'PASS')


def g_l2(w):
    w.produce('noisy', 'OFF'); w.gate('noisy'); w.produce('noisy', 'ON')
    ctx = P5.context(w.dec)
    record('control: a normal pair admits', w.pair('noisy')['global_bits_equal'])
    # a self-consistent handwritten record over an OFF whose runtime differs from the retained bytes
    off = w.ev / 'noisy' / 'OFF'
    m = json.loads((off / 'runtime.json').read_text()); m['coeff_x'][1] += 1e-9; (off / 'runtime.json').write_text(json.dumps(m))
    rr = json.loads((off / 'RUN.json').read_text()); b = (off / 'runtime.json').read_bytes(); rr['runtime'] = {'bytes': len(b), 'sha256': sha(b)}; (off / 'RUN.json').write_text(json.dumps(rr))
    expect_code('gate refuses the changed OFF runtime', 'OFF_RAW', lambda: P5.pre_ON_gate('noisy', decision_dir=w.s / 'dec_other'))
    fns = P5._pinned_functions(ctx)
    cmp_dir = w.dec / 'pre_on' / 'noisy'
    shutil.rmtree(cmp_dir)
    cmp_info = P5._compare(ctx, ctx.baseline_dir('noisy') / 'output', off / 'output', cmp_dir)
    man = P5._manipulation_checked('noisy', 'OFF', off, fns, [3, 3])
    bound = P5._off_bound(ctx, 'noisy', off, ctx.baseline_dir('noisy'), cmp_info, man)
    (cmp_dir / 'pre_on.json').write_text(json.dumps({'schema': P5.PRE_ON_SCHEMA, 'status': 'PASS', 'bound': bound, 'binding_sha256': P5._h(bound)}))
    expect_code('L2 self-consistent handwritten record with a changed OFF runtime is rejected by admit_pair', 'OFF_RAW', lambda: w.pair('noisy'))


def g_l2b(w):
    w.produce('noisy', 'OFF'); w.gate('noisy'); w.produce('noisy', 'ON')
    bf = w.base / 'noisy' / 'UP_only' / 'output' / 'noisy.mrc'
    keep = bf.read_bytes(); bf.write_bytes(keep[:-1] + b'X')
    expect_code('L2 baseline byte changed after the gate', 'BASELINE', lambda: w.pair('noisy')); bf.write_bytes(keep)
    off = w.ev / 'noisy' / 'OFF'
    sp = off / 'output' / 'noisy.star'; sp.write_bytes(sp.read_bytes() + b'# edited\n')
    rr = json.loads((off / 'RUN.json').read_text()); rr['publication']['noisy.star'] = {'bytes': sp.stat().st_size, 'sha256': sha(sp.read_bytes())}; (off / 'RUN.json').write_text(json.dumps(rr))
    expect_code('L2 OFF STAR edited after the gate with a consistent receipt', 'OFF_RAW', lambda: w.pair('noisy'))


def g_record(w):
    w.produce('noisy', 'OFF'); w.produce('noisy', 'ON')
    expect_code('absent pre-ON record', 'PRE_ON', lambda: w.pair('noisy'))
    w.gate('noisy')
    rp = w.dec / 'pre_on' / 'noisy' / 'pre_on.json'; good = rp.read_text()
    j = json.loads(good); j['bound']['binary_sha256'] = 'ef' * 32; rp.write_text(json.dumps(j))
    expect_code('tampered pre-ON record', 'PRE_ON', lambda: w.pair('noisy'))
    j = json.loads(good); j['status'] = 'FAIL'; rp.write_text(json.dumps(j))
    expect_code('pre-ON record status not PASS', 'PRE_ON', lambda: w.pair('noisy'))
    rp.write_text(good)
    record('control: the restored record admits', w.pair('noisy')['global_bits_equal'])


def g_l1(w):
    crafted_all = crafted_scores()
    P5._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: crafted_all[case][arm]
    for c in ORDER:
        w.produce(c, 'OFF'); w.gate(c); w.produce(c, 'ON')
    for c in ORDER:
        w.pair(c)
    res = P5.decide_pilot(decision_dir=w.dec)
    record('L1 per-case admit_pair then decide_pilot in the same decision directory succeeds', res['prediction'] == 'SUPPORTED')
    for c in ('zero', 'flat'):
        runs = sorted(p.name for p in (w.dec / 'pair' / c).iterdir())
        record('L1 both global-only comparator outputs are retained for %s' % c, runs == ['run_1', 'run_2'] and all((w.dec / 'pair' / c / r / 'compare_products.json').is_file() for r in runs), str(runs))
    n_pair = sum(1 for p in (w.dec / 'pair').rglob('pair.json'))
    record('L1 one pair record per admit_pair call (8 + 8)', n_pair == 16, str(n_pair))
    expect_code('a repeated gate in the same decision directory is refused, not overwritten', 'DECISION_DIR', lambda: w.gate('noisy'))
    expect_code('cases parameter reordered', 'CASES', lambda: P5.decide_pilot(decision_dir=w.dec, cases=list(reversed(ORDER))))
    (w.ev / 'extra_case').mkdir()
    expect_code('unlisted extra case directory', 'CASES', lambda: P5.decide_pilot(decision_dir=w.dec))


def g_v4(w):
    # kept v4 behaviors under the v5 module
    w.modes({'noisy/ON': {'global_ulp': True}}); w.produce('noisy', 'OFF'); w.gate('noisy'); w.produce('noisy', 'ON')
    expect_code('ON global runtime 1 ulp different', 'GLOBAL_RUNTIME', lambda: w.pair('noisy'))
    w.modes({'flat/OFF': {'payload_bytes': 'zzzz'}}); w.produce('flat', 'OFF')
    expect_code('OFF product differing from the retained baseline (comparator)', 'COMPARATOR', lambda: w.gate('flat'))
    w.modes({}); w.produce('affine', 'OFF')
    lp = w.ev / 'affine' / 'OFF' / 'output' / 'affine.log'; lp.write_text(lp.read_text() + ' experimental local fullwidth weight x_norm = 42\n')
    rr = json.loads((w.ev / 'affine' / 'OFF' / 'RUN.json').read_text()); rr['publication']['affine.log'] = {'bytes': lp.stat().st_size, 'sha256': sha(lp.read_bytes())}; (w.ev / 'affine' / 'OFF' / 'RUN.json').write_text(json.dumps(rr))
    expect_code('witness spelling variant rejected', 'WITNESS_VARIANT', lambda: P5.admit_single('affine', 'OFF'))
    w.produce('zero', 'OFF'); w.gate('zero'); w.produce('zero', 'ON')
    record('control: a global-only pair admits with a whole-product comparator', w.pair('zero')['global_only_comparator'] is not None)


# ---- driver --------------------------------------------------------------------------------------------------------------------------
def g_driver_ok(w):
    P5._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: crafted_scores()[case][arm]
    dry = D5.run_campaign(w.dec, execute=False, guard=guard_ok)
    record('dry run plans 16 launches and creates nothing', dry['launches_planned'] == 16 and not w.ev.exists() and not w.dec.exists() and dry['created'] == [])
    w.dec.mkdir(exist_ok=True)
    expect_code('real launch refused without PARENT_RELEASE.json', 'RELEASE', lambda: D5.run_campaign(w.dec, execute=True, guard=guard_ok, cpus=None, timeout=30))
    for k, v in [('release_module_sha256', '0' * 64), ('driver_sha256', '0' * 64), ('admission_sha256', '0' * 64), ('delta_review_report_sha256', 'xyz'), ('approved_by', 'someone')]:
        w.release(**{k: v})
        expect_code('release file with a wrong %s' % k, 'RELEASE', lambda: D5.run_campaign(w.dec, execute=True, guard=guard_ok, cpus=None, timeout=30))
    record('refusals launched nothing', not w.ev.exists())
    w.release()
    res = run_ok(w)
    record('full 8-case campaign with the fake child ends in the decision', res['prediction'] == 'SUPPORTED' and res['acceptance'].startswith('NOT_ACCEPTED'))
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    launches = [e for e in led if e['event'] == 'launching']
    record('ledger holds exactly 16 launches in the frozen order', [(e['case'], e['arm']) for e in launches] == [(c, a) for c in ORDER for a in ('OFF', 'ON')] and led[-1]['event'] == 'DECIDED')
    staged = {c: sorted(os.listdir(w.ev / c / 'OFF' / 'input')) for c in ORDER}
    record('only the case STAR and MRCS are staged (no truth/target)', all(v == [c + '.mrcs', c + '.star'] for c, v in staged.items()))
    record('guard receipt retained for every launch', len(list((w.dec / 'guard').glob('*.json'))) == 16)
    r0 = json.loads((w.ev / 'noisy' / 'ON' / 'RUN.json').read_text())
    record('receipt records the actual child (argv[0] is the pinned binary, exit 0, observed env)', r0['argv'][0] == str(w.binpath) and r0['exit'] == 0 and r0['controlled_environment_observed']['OMP_NUM_THREADS'] == '2' and r0['extra_child_environment'] == {'PATH': '/usr/bin:/bin'})
    expect_code('a finished campaign is never restarted in place', 'EXISTS', lambda: run_ok(w))


def g_driver_fail(w):
    P5._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: crafted_scores()[case][arm]
    # guard failure before the first launch
    def bad_guard(step):
        raise D5.DriverStop('GUARD', 'foreign compute (test)')
    w.release()
    expect_code('guard failure before the first launch', 'GUARD', lambda: run_ok(w, guard=bad_guard))
    record('no run directory after a guard failure at validation', not w.ev.exists() or not any(w.ev.iterdir()))


def _fail_case(w, name, code, modes, last_launch, no_on=None, guard=guard_ok, timeout=30, retry_code='EXISTS'):
    w.modes(modes); w.release()
    expect_code(name, code, lambda: run_ok(w, guard=guard, timeout=timeout))
    led = [json.loads(l) for l in (w.dec / 'ledger.jsonl').read_text().splitlines()]
    n = sum(1 for e in led if e['event'] == 'launching')
    record(name + ' [launches stop at %d, STOP recorded]' % last_launch, n == last_launch and led[-1]['event'] == 'STOP' and led[-1]['code'] == code, 'launches=%d last=%s' % (n, led[-1]))
    if no_on:
        record(name + ' [no ON run directory for %s]' % no_on, not (w.ev / no_on / 'ON').exists())
    expect_code(name + ' [no retry: a second run in place is refused]', retry_code, lambda: run_ok(w))


def g_f1(w):
    _fail_case(w, 'fake child exits 1 on the first OFF', 'PRODUCER', {'noisy/OFF': {'exit': 1}}, 1, 'noisy')


def g_f2(w):
    _fail_case(w, 'fake child times out', 'PRODUCER', {'noisy/OFF': {'sleep': 5}}, 1, 'noisy', timeout=1)


def g_f3(w):
    _fail_case(w, 'child leaves no runtime.json', 'RUNTIME', {'noisy/OFF': {'no_runtime': True}}, 1, 'noisy')


def g_f4(w):
    _fail_case(w, 'child writes an unlisted extra output file', 'INVENTORY', {'noisy/OFF': {'extra_output': True}}, 1, 'noisy')


def g_f5(w):
    _fail_case(w, 'ON writes a wrong witness count', 'WITNESS', {'noisy/ON': {'witness_delta': -1}}, 2)


def g_f6(w):
    _fail_case(w, 'OFF differs from the retained baseline: STOP before ON', 'COMPARATOR', {'noisy/OFF': {'payload_bytes': 'zzzz'}}, 1, 'noisy')


def g_f7(w):
    _fail_case(w, 'OFF with zero DC counters stops before ON (L3)', 'MANIPULATION', {'noisy/OFF': {'dc_zero': True}}, 1, 'noisy')


def g_f8(w):
    state = {'n': 0}
    def guard(step):
        state['n'] += 1
        if step == 'noisy/ON':
            raise D5.DriverStop('GUARD', 'foreign compute before the ON launch (test)')
        return {}
    _fail_case(w, 'guard failure before an ON launch', 'GUARD', {}, 1, 'noisy', guard=guard)


def g_f11(w):
    def guard(step):
        if step == 'noisy/ON':
            w.binpath.write_bytes(w.binpath.read_bytes() + b'#swapped between launches\n')
        return {}
    _fail_case(w, 'binary changed between the OFF and ON launches', 'IDENTITY', {}, 1, 'noisy', guard=guard, retry_code='IDENTITY')


def g_f9(w):
    w.release()
    (w.ev / 'noisy').mkdir(parents=True)
    expect_code('evidence_root not empty at the start', 'EXISTS', lambda: run_ok(w))
    shutil.rmtree(w.ev)
    ctx = P5.context(w.dec)
    D5.stage_run(ctx, 'noisy', 'OFF')
    expect_code('run directory already exists', 'EXISTS', lambda: D5.stage_run(ctx, 'noisy', 'OFF'))
    real = D5.shutil.copyfile
    def leaky(src, dst, *a, **k):
        r = real(src, dst, *a, **k)
        (Path(dst).parent / 'noisy_field.npy').write_bytes(b'truth')
        return r
    D5.shutil.copyfile = leaky
    try:
        shutil.rmtree(w.ev / 'noisy')
        expect_code('a truth file in the staged cwd is refused', 'STAGING', lambda: D5.stage_run(ctx, 'noisy', 'ON'))
    finally:
        D5.shutil.copyfile = real
    w.adm['fixture_files']['noisy.mrcs']['sha256'] = '0' * 64; w.sync()
    shutil.rmtree(w.ev, ignore_errors=True)
    expect_code('fixture differing from its pin refuses the campaign', 'FIXTURE', lambda: D5.run_campaign(w.dec, execute=False, guard=guard_ok))


def g_f10(w):
    w.adm['native_producer_budget'] = 15; w.sync()
    expect_code('plan above the producer budget', 'BUDGET', lambda: D5.run_campaign(w.dec, execute=False, guard=guard_ok))
    w.adm['native_producer_budget'] = 16
    shutil.rmtree(w.base / 'zero' / 'UP_only' / 'output'); w.sync()
    expect_code('missing retained baseline refuses the campaign', 'BASELINE', lambda: D5.run_campaign(w.dec, execute=False, guard=guard_ok))


def g_guard(w):
    os.environ.pop('MOTIONCORR_HELD_LEASES', None)
    try:
        D5.real_guard(w.adm, 'test'); record('real guard without held leases', False, 'accepted')
    except D5.DriverStop as e:
        record('real guard refuses when the held-lease list is missing/different', e.code == 'GUARD', str(e)[:90])
    locks = D5.overlapping_locks('32-47')
    record('overlapping lock set always includes the bench and b2 locks', '/tmp/motioncorr-cpu64-bench.lock' in locks and '/tmp/motioncorr-b2-cpu32-47.lock' in locks)


GROUPS = {'identity': g_identity, 'l3': g_l3, 'l2': g_l2, 'l2b': g_l2b, 'l1': g_l1, 'v4': g_v4, 'driver_ok': g_driver_ok, 'driver_fail': g_driver_fail,
          'f1': g_f1, 'f2': g_f2, 'f3': g_f3, 'f4': g_f4, 'f5': g_f5, 'f6': g_f6, 'f7': g_f7, 'f8': g_f8, 'f9': g_f9, 'f10': g_f10, 'f11': g_f11, 'guard': g_guard, 'record': g_record}


def main(result_path, only=None):
    for name, fn in GROUPS.items():
        if only and name not in only:
            continue
        fresh(fn)
    failed = [r for r in RESULTS if not r['ok']]
    Path(result_path).write_text(json.dumps({'total': len(RESULTS), 'failed': len(failed), 'results': RESULTS}, indent=1, allow_nan=False) + '\n')
    print('TOTAL %d FAILED %d' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], set(sys.argv[2:]) or None))
