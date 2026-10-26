"""Reviewer probes of score_fields_v3 admission behaviour beyond the author's tests. Scratch only; no producer, no pixels.

Each probe states the outcome the reviewer predicts and records the observed outcome. ADMITTED outcomes are gaps or
honest limits, REJECTED outcomes are confirmations; neither changes the author's criteria.
usage: python -B -I gap_probes.py PILOT_DIR OUT.json
"""
import copy, json, shutil, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
PILOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PILOT / 'tests'))
sys.path.insert(0, str(PILOT))
import test_score_fields_v3 as T  # reuse the author's World fixture builder unchanged
V3 = T.V3
OUT = []


def outcome(fn):
    try:
        fn()
        return 'ADMITTED'
    except V3.AdmissionError as e:
        return 'REJECTED:' + e.code
    except Exception as e:
        return 'ERROR:%s:%s' % (type(e).__name__, e)


def probe(name, predicted, fn, note):
    got = outcome(fn)
    OUT.append({'probe': name, 'predicted': predicted, 'observed': got, 'as_predicted': got == predicted, 'note': note})
    print('%-58s predicted=%-18s observed=%s' % (name, predicted, got), flush=True)


def forge_into(w, case, src_arm, dst_arm):
    """Producer-side forgery: dst slot holds src products; the receipt is rewritten to be self-consistent for dst."""
    w.build(case, src_arm)
    src = w.root / case / src_arm
    dst = w.root / case / dst_arm
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    exp = V3.resolve_expected_row(T.CMD, w.adm, case, dst_arm, w.root, T.BIN, T.BINSHA)
    w.write_receipt(dst, exp)
    return dst, exp


with tempfile.TemporaryDirectory(prefix='mc-lfw-r2-probe-') as scratch:
    w = T.World(scratch)
    d, exp = forge_into(w, 'noisy', 'ON', 'OFF')
    probe('P1 forged: 3x3 ON products in OFF slot, receipt rewritten', 'REJECTED:WITNESS', lambda: w.admit(d, exp),
          'product witness is the only check independent of the self-reported receipt')
    d, exp = forge_into(w, 'noisy', 'OFF', 'ON')
    probe('P2 forged: 3x3 OFF products in ON slot, receipt rewritten', 'REJECTED:WITNESS', lambda: w.admit(d, exp), '')
    d, exp = forge_into(w, 'flat', 'ON', 'OFF')
    probe('P3 forged: global-only ON products in OFF slot', 'ADMITTED', lambda: w.admit(d, exp),
          'honest limit: global-only arms have no product-level arm witness')

    # near-miss witness forms that do not contain the exact marker substring are invisible to the parser
    d, exp = w.build('noisy', 'OFF')
    lp = d / 'output' / 'noisy.log'
    lp.write_text(lp.read_text() + ' EXPERIMENTAL local full width weight: x_norm = 42, pnx = 42, nfx = 22\n')
    w.write_receipt(d, exp)
    probe('P4 OFF log with marker-variant line (no hyphen)', 'ADMITTED', lambda: w.admit(d, exp),
          'WITNESS_MARKER substring match; a variant spelling is neither counted nor rejected')
    d, exp = w.build('noisy', 'OFF')
    lp = d / 'output' / 'noisy.log'
    lp.write_text(lp.read_text() + ' experimental local full-width weight: x_norm = 42, pnx = 42, nfx = 22\n')
    w.write_receipt(d, exp)
    probe('P5 OFF log with lower-case witness line', 'ADMITTED', lambda: w.admit(d, exp), 'case-sensitive marker')

    # admit_producer trusts the caller's expected dict for patch grid and output names
    d, exp = w.build('noisy', 'ON', log_witness=0)
    bad = dict(exp, patch_grid=[1, 1], expected_witness_lines=0)
    probe('P6 noisy ON, 0 witnesses, caller expected patch_grid [1,1]', 'ADMITTED', lambda: w.admit(d, bad),
          'admit_producer does not re-derive patch_grid from admission rows; resolve_expected_row would refuse')
    probe('P6b same run with resolved expected', 'REJECTED:WITNESS', lambda: w.admit(d, exp), 'control')

    # COMMANDS file is a caller-supplied list without a hash anchor in the consumer
    cmd2 = copy.deepcopy(T.CMD)
    for r in cmd2:
        if r['case'] == 'noisy':
            r['argv'][r['argv'].index('--max_iter') + 1] = '9'
            r['environment']['OMP_NUM_THREADS'] = '8'
    exp2 = V3.resolve_expected_row(cmd2, w.adm, 'noisy', 'ON', w.root, T.BIN, T.BINSHA)
    d, _ = w.build('noisy', 'ON')
    w.write_receipt(d, exp2)
    probe('P7 altered COMMANDS (max_iter 9, OMP 8), receipt matches it', 'ADMITTED', lambda: w.admit(d, exp2),
          'no COMMANDS_DRAFT_v3 hash or regeneration check in resolve_expected_row/admit_producer')

    # pair layer: OFF and ON resolved with different binaries both admit
    d_off, e_off = w.build('noisy', 'OFF')
    e_on = V3.resolve_expected_row(T.CMD, w.adm, 'noisy', 'ON', w.root, T.BIN, 'cd' * 32)
    d_on, _ = w.build('noisy', 'ON')
    w.write_receipt(d_on, e_on, lambda r: r.__setitem__('binary_sha256', 'cd' * 32))
    a = outcome(lambda: w.admit(d_off, e_off)); b = outcome(lambda: w.admit(d_on, e_on))
    OUT.append({'probe': 'P8 OFF binary ab.., ON binary cd..: both admit', 'predicted': 'ADMITTED/ADMITTED', 'observed': a + '/' + b,
                'as_predicted': (a, b) == ('ADMITTED', 'ADMITTED'), 'note': 'no pair-level same-binary check exists'})
    print('P8 pair different binaries:', a, b)

    # unconstrained files beside RUN.json
    d, exp = w.build('noisy', 'ON'); (d / 'stderr.log').write_text('segfault?'); (d / 'extra_dir').mkdir()
    probe('P9 extra files in run_dir outside output/ and input/', 'ADMITTED', lambda: w.admit(d, exp),
          'stderr is neither required nor bound; run_dir top level is not inventoried')

    # receipt listing a symlink with the target's hash: second line of defence after the symlink guard
    d, exp = w.build('noisy', 'ON')
    (d / 'output' / 'logfile.pdf').unlink(); (d / 'output' / 'logfile.pdf').symlink_to('/etc/hosts')
    hb = Path('/etc/hosts').read_bytes()
    w.write_receipt(d, exp, lambda r: r['publication'].__setitem__('logfile.pdf', {'bytes': len(hb), 'sha256': T.sha(hb)}))
    probe('P10 output symlink listed in receipt with target hash', 'REJECTED:INVENTORY', lambda: w.admit(d, exp), '')

    # symlinked canonical slot pointing at another tree: receipt run_dir must be the resolved target
    d, exp = w.build('noisy', 'OFF')
    real = Path(scratch) / 'real_off'; shutil.move(str(d), real); d.symlink_to(real)
    probe('P11 canonical slot is a symlink to a tree elsewhere', 'REJECTED:RUN_DIR', lambda: w.admit(d, exp),
          'receipt run_dir was written for the canonical path; resolve() follows the link')

    # admission-level witness constant agrees with source line format R1 quoted
    OUT.append({'probe': 'P12 WITNESS_LINE constant', 'observed': V3.WITNESS_LINE,
                'as_predicted': V3.WITNESS_LINE == ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22'})

Path(sys.argv[2]).write_text(json.dumps(OUT, indent=1) + '\n')
print('probes', len(OUT), 'not as predicted:', [o['probe'] for o in OUT if not o['as_predicted']])
