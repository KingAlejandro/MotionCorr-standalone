"""R3 reviewer probes for pair_decision_v4 (read-only on the package; scratch tempdirs only).

Reuses the author's PW world from tests/test_pair_decision_v4.py unchanged. Each probe states its prediction before running.
usage: python -B probes_r3.py PILOT_DIR OUT.json
"""
import json, shutil, sys, tempfile, traceback
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PILOT)); sys.path.insert(0, str(PILOT / 'tests'))
import test_pair_decision_v4 as T  # noqa: E402  (module import only; main() is not run)
P4, V3 = T.P4, T.V3
OUT = []


def outcome(fn):
    try:
        r = fn()
        return 'ACCEPTED', r
    except (P4.PairError, V3.AdmissionError) as e:
        return 'REJECTED:%s' % e.code, str(e)[:300]
    except Exception as e:
        return 'ERROR:%s' % type(e).__name__, ''.join(traceback.format_exception_only(type(e), e)).strip()[:300]


def probe(pid, desc, predicted, fn, cases=('noisy',)):
    real = (P4.ADMISSION_PATH, P4.ADMISSION_V3_SHA256, P4.COMMANDS_PATH, P4.COMMANDS_V3_SHA256)
    orig_score = P4._score_arm
    with tempfile.TemporaryDirectory(prefix='mc-lfw-r3-') as t:
        w = T.PW(Path(t).resolve())
        for c in cases:
            w.make(c)
        try:
            obs, detail = fn(w)
        except Exception as e:
            obs, detail = 'PROBE_ERROR:%s' % type(e).__name__, ''.join(traceback.format_exception_only(type(e), e)).strip()
        finally:
            P4.ADMISSION_PATH, P4.ADMISSION_V3_SHA256, P4.COMMANDS_PATH, P4.COMMANDS_V3_SHA256 = real
            P4._score_arm = orig_score
    row = {'id': pid, 'desc': desc, 'predicted': predicted, 'observed': obs, 'as_predicted': obs == predicted, 'detail': detail if isinstance(detail, str) else repr(detail)[:300]}
    OUT.append(row)
    print('%-4s %-70s predicted=%-26s observed=%s' % (pid, desc, predicted, obs), flush=True)


def off_runtime_edit(w):
    d, exp = w.cases['noisy']['OFF']
    m = json.loads((d / 'runtime.json').read_text()); m['coeff_x'][1] += 1e-9
    (d / 'runtime.json').write_text(json.dumps(m)); w.write_receipt(d, exp)


# Q1 control: honest gate rejects an OFF whose runtime differs from the retained bytes
def q1(w):
    off_runtime_edit(w)
    return outcome(lambda: w.gate('noisy'))


# Q2: same OFF defect, pre_ON_gate never run; a self-consistent pre-ON record is written from current disk.
# admit_pair verifies the record's integrity but does not re-derive the OFF_RAW byte check.
def q2(w):
    off_runtime_edit(w)
    w.sync()
    ctx = P4._Ctx(T.ROOTS, w.root, T.BIN, T.BINSHA, w.dec, True)
    off, base = w.root / 'noisy' / 'OFF', w.base_root / 'noisy'
    cmp_dir = w.dec / 'pre_on' / 'noisy'
    info = P4._compare(ctx, base / 'output', off / 'output', cmp_dir)  # the real comparator (output tree only)
    bound = P4._off_bound(ctx, 'noisy', off, base, cmp_dir, info)
    (cmp_dir / 'pre_on.json').write_text(json.dumps({'schema': P4.PRE_ON_SCHEMA, 'status': 'PASS', 'bound': bound, 'binding_sha256': P4._h(bound)}))
    return outcome(lambda: w.pair('noisy'))


# Q3: OFF stdout with zero global DC counters (manipulation failed) passes pre_ON_gate; caught only at admit_pair (after ON exists)
def q3(w):
    w.edit('noisy', 'OFF', 'stdout.log', lambda b: T.make_stdout(True, g=(0, 0), gpeaks=0).encode())
    return outcome(lambda: w.gate('noisy'))


# Q4: the admission's candidate_binary names a different sha256 than the caller's binary_sha256
def q4(w):
    w.adm['candidate_binary'] = {'path': '/venue/bin/motioncorr', 'sha256': 'cd' * 32}
    w.adm['candidate_source_commit'] = '0' * 40
    r = outcome(lambda: w.gate('noisy'))
    return r[0], 'caller binary_sha256=%s admission candidate_binary.sha256=%s; %s' % (T.BINSHA[:8], 'cd' * 4, r[1] if r[0] != 'ACCEPTED' else 'gate PASS')


# Q5/Q6: per-pair admit_pair (natural OFF->gate->ON->admit_pair flow), then decide_pilot in the same decision_dir
def build_all(w):
    for c in T.ALL_CASES:
        if c not in w.cases:
            w.make(c)
    for c in T.ALL_CASES:
        w.gate(c)


def crafted_scorer(w):
    s = T.crafted_scores()
    P4._score_arm = lambda case, arm, run_dir, expected, adm, ev, fx: s[case][arm]


def q5(w):
    build_all(w); w.sync(); crafted_scorer(w)
    return outcome(lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=T.FIX, roots=T.ROOTS,
                                           binary_path=T.BIN, binary_sha256=T.BINSHA, decision_dir=w.dec)['prediction'])


def q6(w):
    build_all(w)
    for c in T.ALL_CASES:
        w.pair(c)
    w.sync(); crafted_scorer(w)
    r = outcome(lambda: P4.decide_pilot(evidence_root=w.root, baseline_root=w.base_root, fixture_dir=T.FIX, roots=T.ROOTS,
                                        binary_path=T.BIN, binary_sha256=T.BINSHA, decision_dir=w.dec))
    stop = json.loads((w.dec / 'STOP.json').read_text()) if (w.dec / 'STOP.json').exists() else None
    return r[0], '%s | STOP.json=%s' % (r[1], stop)


# Q7-Q9: counter parser missing/foreign fields never become PASS
def q7(w):
    w.gate('noisy')
    w.edit('noisy', 'ON', 'stdout.log', lambda b: b.replace(b' cpu.local=360/360', b''))
    return outcome(lambda: w.pair('noisy'))


def q8(w):
    w.gate('noisy')
    w.edit('noisy', 'ON', 'stdout.log', lambda b: b + b'[coupled_peak] scope=other peaks=1 guard_fired=0 (not_negative_definite=0, offset_gt_1px=0)\n')
    return outcome(lambda: w.pair('noisy'))


def q9(w):
    w.gate('noisy')
    w.edit('noisy', 'ON', 'stdout.log', lambda b: b.replace(b'arm=both', b'arm=global'))
    return outcome(lambda: w.pair('noisy'))


probe('Q1', 'control: OFF runtime != retained bytes, honest pre_ON_gate', 'REJECTED:OFF_RAW', q1)
probe('Q2', 'same OFF defect, gate skipped, self-consistent pre_on.json forged', 'ACCEPTED', q2)
probe('Q3', 'OFF DC counters zero: pre_ON_gate result', 'ACCEPTED', q3)
probe('Q4', 'candidate_binary sha != caller binary_sha256: pre_ON_gate', 'ACCEPTED', q4)
probe('Q5', 'control: gates only, then decide_pilot (same decision_dir)', 'ACCEPTED', q5, cases=())
probe('Q6', 'gates + admit_pair x8, then decide_pilot (same decision_dir)', 'REJECTED:GLOBAL_ONLY', q6, cases=())
probe('Q7', 'ON DC line missing cpu.local field', 'REJECTED:MANIPULATION', q7)
probe('Q8', 'ON extra coupled line with unknown scope', 'REJECTED:MANIPULATION', q8)
probe('Q9', 'ON DC arm=global instead of both', 'REJECTED:MANIPULATION', q9)

Path(sys.argv[2]).write_text(json.dumps(OUT, indent=1) + '\n')
bad = [r['id'] for r in OUT if not r['as_predicted']]
print('PROBES %d, not as predicted: %s' % (len(OUT), bad or 'none'))
