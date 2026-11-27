# SPDX-License-Identifier: GPL-2.0-or-later
"""Controls for regrade_v2_1.py (AMENDMENT-1 A6). Local only; no MotionCorr, GPU or remote.

  test_regrade_v2_1.py build --ns NEW_DIR                      build immutable scenario inputs under NEW_DIR/inputs
  test_regrade_v2_1.py run --ns DIR --tag TAG [--grader PATH]  grade every scenario into DIR/run-TAG; CONTROLS.json

Inputs come from the real retained cpu1 evidence (real-writer STAR/RUN/log text). MRCs are generated fixtures
of the exact product geometry (768x512x1 float32, nsymbt 0). Live-precheck controls use small synthetic git trees.
"""
import argparse, hashlib, io, json, os, shutil, struct, subprocess, sys, tarfile

HERE = os.path.dirname(os.path.realpath(__file__))
NATIVE = os.path.dirname(HERE)
RAW = os.path.join(NATIVE, 'n3-cpu1-result/raw')
TAR, TAR_SHA = os.path.join(RAW, 'evidence.tar'), '3cc13020d35aaf7113fe16878e8eb63c11652863fd73c0da3974fc7fa09f2760'
PRED = os.path.join(NATIVE, 'n3-iter2/predictions_iter2.json')
MANIFEST = os.path.join(HERE, 'EVIDENCE_MANIFEST.json')
AMENDMENT = os.path.join(HERE, 'AMENDMENT-1.md')
PREDS = json.load(open(PRED))['n3']
CASES = list(PREDS) + ['Z_no_overlay']
AX, F_ = 'A_x_legacy_false_accept', 'F_mild_both_accept'
STAR = 'n3-cpu1/ov-cand-cpu/{}/out/km_local_nonsquare.star'
MRC = 'n3-cpu1/{}/{}/out/km_local_nonsquare.mrc'
ROOT = '/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1'
sha = lambda b: hashlib.sha256(b).hexdigest()
ENV = {'OMP_NUM_THREADS': '1', 'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'}

with tarfile.open(TAR, 'r:') as _t:
    ORIGINAL = [(m, _t.extractfile(m).read() if m.isfile() else None) for m in _t]
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
            if b is None:
                continue
            info = tarfile.TarInfo(name); info.size = len(b); info.mode = 0o644; t.addfile(info, io.BytesIO(b))
    return buf.getvalue()


def star_edit(case, old, new):
    s = FILES[STAR.format(case)].decode()
    assert old in s, (case, old)
    return {STAR.format(case): s.replace(old, new, 1).encode()}


def mrc(seed, nx=768, ny=512, nz=1, mode=2, nsymbt=0, map_word=b'MAP ', size=None):
    h = bytearray(1024)
    struct.pack_into('<4i', h, 0, nx, ny, nz, mode); struct.pack_into('<i', h, 92, nsymbt); h[208:212] = map_word
    unit = hashlib.sha256(seed.encode()).digest() * 2                    # 64 bytes
    body = unit * (768 * 512 * 4 // 64)
    b = bytes(h) + b'\0' * nsymbt + body
    return b if size is None else (b + b'\0' * max(0, size - len(b)))[:size]


def mrcs(override=None):
    out = {}
    for case in CASES:
        for arm, alg in (('ov-base-cpu', 'legacy'), ('ov-cand-cpu', 'finite')):
            reject = PREDS[case][alg]['reject'] if case in PREDS else False
            out[MRC.format(arm, case)] = mrc(f'{case}:{"G" if reject else "L"}')
    out.update(override or {})
    return out


def run_edit(rowpath, fn):
    rel = f'n3-cpu1/{rowpath}/RUN.json'; d = json.loads(FILES[rel]); fn(d); return {rel: json.dumps(d, indent=1).encode()}


ROW2, ROW1 = '           2     -1.70013     1.382446 ', '           1     0.000000     0.000000 '
CAND_BIN = FILES['build-ov-cand-cpu.binaries.sha256']
CAND_HASH = CAND_BIN.split()[0].decode()


def same_binary_edits():
    """Mutant arm takes the candidate's binary hash in its receipt and all its RUN records: only distinctness fails."""
    e = {'build-ov-mut-cpu.binaries.sha256': CAND_BIN}
    for c in CASES:
        e.update(run_edit(f'ov-mut-cpu/{c}', lambda d: d.update(binary_sha256=CAND_HASH)))
    return e


# name: (builder -> tar bytes, extra grade args, expected exit, needles that must all appear in the report)
TAR_SCENARIOS = {
    'real_evidence': (lambda: open(TAR, 'rb').read(), [], 2, []),
    'real_evidence_with_manifest': (lambda: open(TAR, 'rb').read(), ['manifest'], 2, []),
    'manifest_mismatch_after_edit': (lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.700130 ')), ['manifest'], 1, ['manifest mismatch']),
    'trailing_zero_equal': (lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.700130 ')), [], 2, []),
    'x_value_changed': (lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.700131 ')), [], 1, ['CPU pairs not 8']),
    'y_value_changed': (lambda: rebuild(star_edit(AX, '1.382446 ', '1.382447 ')), [], 1, ['CPU pairs not 8']),
    'x_signed_zero': (lambda: rebuild(star_edit(AX, ROW1, '           1    -0.000000     0.000000 ')), [], 1, ['CPU pairs not 8']),
    'y_signed_zero': (lambda: rebuild(star_edit(AX, ROW1, '           1     0.000000    -0.000000 ')), [], 1, ['CPU pairs not 8']),
    'missing_frame': (lambda: rebuild(star_edit(AX, ROW2 + '\n', '')), [], 1, ['frame token']),
    'duplicate_frame': (lambda: rebuild(star_edit(AX, ROW2 + '\n', ROW2 + '\n' + ROW2 + '\n')), [], 1, ['frame token']),
    'frame_leading_zero': (lambda: rebuild(star_edit(AX, ROW1, '           01     0.000000     0.000000 ')), [], 1, ['frame token']),
    'frame_superscript': (lambda: rebuild(star_edit(AX, ROW2, '           ²     -1.70013     1.382446 ')), [], 1, ['non-ASCII']),
    'value_arabic_indic_digit': (lambda: rebuild(star_edit(AX, '-1.70013 ', '-١.70013 ')), [], 1, ['non-ASCII']),
    'malformed_token': (lambda: rebuild(star_edit(AX, '-1.70013 ', '-1.7O013 ')), [], 1, ['malformed row']),
    'nan_token': (lambda: rebuild(star_edit(AX, '-1.70013 ', 'NaN ')), [], 1, ['malformed row']),
    'inf_token': (lambda: rebuild(star_edit(AX, '-1.70013 ', 'inf ')), [], 1, ['malformed row']),
    'wrong_label': (lambda: rebuild(star_edit(AX, '_rlnMicrographShiftX #2', '_rlnMicrographShiftZ #2')), [], 1, ['schema']),
    'missing_label': (lambda: rebuild(star_edit(AX, '_rlnMicrographShiftY #3 \n', '')), [], 1, ['schema']),
    'wrong_label_index': (lambda: rebuild(star_edit(AX, '_rlnMicrographShiftY #3', '_rlnMicrographShiftY #4')), [], 1, ['schema']),
    'second_global_block': (lambda: rebuild({STAR.format(AX): FILES[STAR.format(AX)] + b'\ndata_global_shift\n'}), [], 1, ['2 data_global_shift blocks']),
    'global_block_absent': (lambda: rebuild(star_edit(AX, 'data_global_shift', 'data_global_shiftless')), [], 1, ['0 data_global_shift blocks']),
    'binaries_not_distinct': (lambda: rebuild(same_binary_edits()), [], 1, ['not three distinct hashes']),
    'receipts_consistently_edited': (lambda: rebuild({'n3-cpu1/known-observations.json': FILES['n3-cpu1/known-observations.json'].replace(b'"overlay": true', b'"overlay": true ', 1)}), [], 1, ['known-observations.json missing or sha256']),
    'injected_spec_differs': (lambda: rebuild(run_edit('ov-base-cpu/B_x_legacy_false_reject', lambda d: d['env'].update(MC264_N3_COEFFS=d['env']['MC264_N3_COEFFS'] + ' 0'))), [], 1, ['injected spec differs']),
    'binary_differs_from_receipt': (lambda: rebuild(run_edit(f'ov-cand-cpu/{F_}', lambda d: d.update(binary_sha256='0' * 64))), [], 1, ['binary differs from build receipt']),
    'run_arm_case_cwd_argv_unbound': (lambda: rebuild(run_edit(f'ov-cand-cpu/{F_}', lambda d: d.update(arm='ov-base-cpu', case='G_large_both_reject', cwd='/elsewhere', argv=[a.replace('F_mild', 'G_large') for a in d['argv']]))), [], 1, ['RUN arm not bound', 'RUN case not bound', 'RUN cwd not bound', 'RUN argv not bound']),
    'run_argv_option_changed': (lambda: rebuild(run_edit(f'ov-mut-cpu/{F_}', lambda d: d['argv'].__setitem__(d['argv'].index('--j') + 1, '2'))), [], 1, ['RUN argv not bound']),
    'stdout_not_bound': (lambda: rebuild(run_edit('ov-mut-cpu/B_y_legacy_false_reject', lambda d: d.update(stdout=d['stdout'].replace('B_y', 'B_x')))), [], 1, ['stdout not bound']),
    'row_rule_absent_overlay': (lambda: rebuild({'n3-cpu1/ov-base-cpu/G_large_both_reject/logs/ov-base-cpu-G_large_both_reject.stderr':
                                                 FILES['n3-cpu1/ov-base-cpu/G_large_both_reject/logs/ov-base-cpu-G_large_both_reject.stderr'].replace(b'overlay applied', b'overlay skipped')}), [], 1, ['overlay witness']),
    'mutant_takes_candidate_decision': (lambda: rebuild({'n3-cpu1/ov-mut-cpu/A_x_legacy_false_accept/logs/ov-mut-cpu-A_x_legacy_false_accept.stderr':
                                                         FILES['n3-cpu1/ov-cand-cpu/A_x_legacy_false_accept/logs/ov-cand-cpu-A_x_legacy_false_accept.stderr']}), [], 1, ['N4 not PASS']),
    'missing_cpu_row': (lambda: rebuild({'n3-cpu1/ov-cand-cpu/E_xy_nonsquare_near_threshold/RUN.json': None}), [], 1, ['CPU rows not 24 PASS']),
    'cuda_artefact_present': (lambda: rebuild(add={'n3-cpu1/ov-cand-cuda/A_x_legacy_false_accept/note': b'x'}), [], 1, ['CUDA rows are not exactly 16 UNRUN']),
    'unsafe_member': (lambda: rebuild(add={'../escape': b'x'}), [], 1, ['unsafe member']),
    'mrc_full_pass': (lambda: rebuild(add=mrcs()), [], 0, []),
    'mrc_one_missing_unrun': (lambda: rebuild(add=mrcs({MRC.format('ov-base-cpu', 'Z_no_overlay'): None})), [], 2, []),
    'mrc_header_only_all': (lambda: rebuild(add={k: v[:1024] for k, v in mrcs().items()}), [], 1, ['MRC size 1024']),
    'mrc_truncated': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', F_): mrc(f'{F_}:L', size=1573884)})), [], 1, ['MRC size 1573884']),
    'mrc_oversize': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', F_): mrc(f'{F_}:L', size=1573889)})), [], 1, ['MRC size 1573889']),
    'mrc_wrong_mode': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', F_): mrc(f'{F_}:L', mode=1)})), [], 1, ['MRC descriptor']),
    'mrc_wrong_shape': (lambda: rebuild(add=mrcs({MRC.format('ov-base-cpu', F_): mrc(f'{F_}:L', nx=512, ny=768)})), [], 1, ['MRC descriptor']),
    'mrc_nonzero_nsymbt': (lambda: rebuild(add=mrcs({MRC.format('ov-base-cpu', F_): mrc(f'{F_}:L', nsymbt=8)})), [], 1, ['MRC size']),
    'mrc_map_word_missing': (lambda: rebuild(add=mrcs({MRC.format('ov-base-cpu', F_): mrc(f'{F_}:L', map_word=b'\0\0\0\0')})), [], 1, ['map word']),
    'mrc_wrong_payload_where_equal': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', F_): mrc('different')})), [], 1, ['image relation failed', 'contradicts original evidence']),
    'mrc_equal_where_flip': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', AX): mrc(f'{AX}:L')})), [], 1, ['image relation failed', 'contradicts original evidence']),
    'mrc_header_bytes_differ_payload_equal': (lambda: rebuild(add=mrcs({MRC.format('ov-cand-cpu', F_): (lambda b: b[:300] + b'LABEL-TIMESTAMP-2026' + b[320:])(mrc(f'{F_}:L'))})), [], 0, []),
}


def safe_extract(tarbytes, dest):
    with tarfile.open(fileobj=io.BytesIO(tarbytes), mode='r:') as t:
        for m in t:
            target = os.path.join(dest, m.name)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f:
                    f.write(t.extractfile(m).read())


def git(tree, *args, **kw):
    env = dict(ENV, GIT_AUTHOR_NAME='c', GIT_AUTHOR_EMAIL='c@x', GIT_COMMITTER_NAME='c', GIT_COMMITTER_EMAIL='c@x',
               GIT_AUTHOR_DATE='2026-10-23T00:00:00Z', GIT_COMMITTER_DATE='2026-10-23T00:00:00Z', HOME=tree, GIT_CONFIG_NOSYSTEM='1')
    return subprocess.run(['git', '-C', tree, *args], capture_output=True, check=True, env=env, **kw).stdout


def live_fixture(root, variant):
    trees = {'src-cand': (b'runner-cand', b'helper', None), 'src-base': (b'runner-base', None, None),
             'src-ov-base': (b'runner-base', None, b'runner-base+overlay'), 'src-ov-cand': (b'runner-cand', b'helper', b'runner-cand+overlay'),
             'src-ov-mut': (b'runner-cand', b'helper', b'runner-cand+overlay')}
    for name, (runner, helper, modified) in trees.items():
        t = os.path.join(root, name); os.makedirs(os.path.join(t, 'src'))
        open(os.path.join(t, 'src/motioncorr_runner.cpp'), 'wb').write(runner)
        if helper is not None: open(os.path.join(t, 'src/local_motion_guard.h'), 'wb').write(helper)
        git(t, 'init', '-q'); git(t, 'add', '-A'); git(t, 'commit', '-q', '-m', name)
        if modified: open(os.path.join(t, 'src/motioncorr_runner.cpp'), 'wb').write(modified)
        if name == 'src-ov-mut': open(os.path.join(t, 'src/local_motion_guard.h'), 'wb').write(b'helper-uncentred')
    binaries = {'ov-base-cpu': b'BIN-base', 'ov-cand-cpu': b'BIN-cand', 'ov-mut-cpu': b'BIN-mut'}
    if variant == 'binaries_not_distinct': binaries['ov-mut-cpu'] = b'BIN-cand'
    for arm, b in binaries.items():
        os.makedirs(os.path.join(root, f'build-{arm}'))
        open(os.path.join(root, f'build-{arm}/motioncorr'), 'wb').write(b)
        receipt = sha(b) if variant != 'binary_differs_from_receipt' or arm != 'ov-cand-cpu' else '0' * 64
        open(os.path.join(root, f'build-{arm}.binaries.sha256'), 'w').write(f'{receipt}  {ROOT}/build-{arm}/motioncorr\n')
    expect = {'trees': {}, 'binaries': {arm: sha(b) for arm, b in binaries.items()}}
    for name in trees:
        t = os.path.join(root, name)
        helper = os.path.join(t, 'src/local_motion_guard.h')
        expect['trees'][name] = {'head': git(t, 'rev-parse', 'HEAD').decode().strip(), 'diff_sha256': sha(git(t, 'diff')),
                                 'status': [l for l in git(t, 'status', '--porcelain').decode().split('\n') if l],
                                 'runner_sha256': sha(open(os.path.join(t, 'src/motioncorr_runner.cpp'), 'rb').read()),
                                 'helper_sha256': sha(open(helper, 'rb').read()) if os.path.exists(helper) else 'absent'}
    # Variants applied after EXPECT is recorded, so only the targeted check can differ.
    if variant == 'untracked_file': open(os.path.join(root, 'src-ov-cand/stray.txt'), 'w').write('x')
    if variant == 'runner_modified': open(os.path.join(root, 'src-ov-base/src/motioncorr_runner.cpp'), 'ab').write(b'!')
    if variant == 'head_differs': expect['trees']['src-cand']['head'] = '0' * 40
    if variant == 'symlink_component':
        os.rename(os.path.join(root, 'build-ov-base-cpu'), os.path.join(root, 'build-real')); os.symlink('build-real', os.path.join(root, 'build-ov-base-cpu'))
    if variant == 'stale_index_stat':      # tracked file touched, same bytes: status would normally refresh the index
        p = os.path.join(root, 'src-cand/src/motioncorr_runner.cpp'); st = os.stat(p); os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    return expect


LIVE_SCENARIOS = {  # variant: (expected exit, needles, proc variant)
    'live_pass': (0, [], 'empty'),
    'live_stale_index_stat_pass': (0, [], 'empty'),
    'live_head_differs': (1, ['src-cand: head'], 'empty'),
    'live_untracked_file': (1, ['src-ov-cand: status'], 'empty'),
    'live_runner_modified': (1, ['src-ov-base: diff_sha256', 'src-ov-base: runner_sha256'], 'empty'),
    'live_binary_differs_from_receipt': (1, ['ov-cand-cpu: live/receipt/expect'], 'empty'),
    'live_binaries_not_distinct': (1, ['live binaries are not distinct'], 'empty'),
    'live_symlink_component': (1, ['symlink or non-directory component'], 'empty'),
    'live_active_process': (1, ['active processes refer to the scratch'], 'active'),
    'live_proc_root_missing': (1, ['proc root missing'], 'missing'),
}

DIR_SCENARIOS = {  # name: (expected exit, needles)
    'dir_full_pass': (0, []),
    'dir_symlink_leaf_mrc': (1, ['symlink leaf']),
    'dir_symlink_dir_component': (1, ['symlink or non-directory component']),
    'dir_changed_after_precheck': (1, ['changed after precheck']),
    'dir_out_inside_scratch': (1, ['output inside the scratch root']),
    'dir_noncanonical_root': (1, ['non-canonical path']),
    'dir_precheck_header_only': (1, ['MRC size 1024']),
    'dir_precheck_star_edited': (1, ['missing or sha256 differs']),
}


def build(ns):
    ns = os.path.realpath(ns); inp = os.path.join(ns, 'inputs')
    os.makedirs(inp)
    record = {}
    for name, (builder, *_rest) in TAR_SCENARIOS.items():
        b = builder(); p = os.path.join(inp, name + '.tar'); open(p, 'wb').write(b); record[name] = sha(b)
    base = rebuild(add=mrcs())
    for name in DIR_SCENARIOS:
        s = os.path.join(inp, name, 'scratch'); os.makedirs(s)
        if name == 'dir_precheck_header_only':
            safe_extract(rebuild(add={k: v[:1024] for k, v in mrcs().items()}), s)
        elif name == 'dir_precheck_star_edited':
            safe_extract(rebuild(edits=star_edit(AX, '-1.70013 ', '-1.700130 '), add=mrcs()), s)
        else:
            safe_extract(base, s)
        if name == 'dir_symlink_leaf_mrc':
            p = os.path.join(s, MRC.format('ov-cand-cpu', F_)); os.rename(p, p + '.real'); os.symlink(os.path.basename(p) + '.real', p)
        if name == 'dir_symlink_dir_component':
            d = os.path.join(s, f'n3-cpu1/ov-cand-cpu/{F_}'); os.rename(os.path.join(d, 'out'), os.path.join(d, 'out2')); os.symlink('out2', os.path.join(d, 'out'))
        if name == 'dir_changed_after_precheck':
            alt = os.path.join(inp, name, 'replacement.mrc'); open(alt, 'wb').write(mrc(f'{F_}:L-but-changed'))
        if name == 'dir_noncanonical_root':
            os.symlink(s, os.path.join(inp, name, 'scratch-link'))
        record[name] = 'directory'
    for name, (_rc, _n, procv) in LIVE_SCENARIOS.items():
        d = os.path.join(inp, name); s = os.path.join(d, 'scratch'); os.makedirs(s)
        expect = live_fixture(s, name[len('live_'):])
        open(os.path.join(d, 'EXPECT.json'), 'w').write(json.dumps(expect, indent=1))
        proc = os.path.join(d, 'proc')
        if procv != 'missing':
            os.makedirs(os.path.join(proc, '999999'))
            cmd = f'python3\0worker.py\0{s}/n3-cpu1\0' if procv == 'active' else 'sleep\0100\0'
            open(os.path.join(proc, '999999/cmdline'), 'w').write(cmd)
        record[name] = 'synthetic'
    open(os.path.join(ns, 'BUILD.json'), 'w').write(json.dumps({'tar_scenarios_sha256': record,
                                                                'evidence_tar_sha256': TAR_SHA, 'mrc_size': len(mrc('x'))}, indent=1) + '\n')
    print('built', len(TAR_SCENARIOS), 'tar,', len(DIR_SCENARIOS), 'dir,', len(LIVE_SCENARIOS), 'live scenarios in', inp)
    return 0


def call(grader, *args):
    return subprocess.run([sys.executable, '-I', '-B', grader, *args], capture_output=True, text=True, env=ENV)


def run(ns, tag, grader):
    ns = os.path.realpath(ns); inp = os.path.join(ns, 'inputs'); out = os.path.join(ns, f'run-{tag}')
    os.makedirs(out)
    grader = os.path.realpath(grader)
    built = json.load(open(os.path.join(ns, 'BUILD.json')))
    results, ok = [], True

    def judge(name, p, report_path, want, needles):
        rep = json.load(open(report_path)) if os.path.exists(report_path) else None
        blob = json.dumps(rep) if rep else p.stdout + p.stderr
        good = p.returncode == want and all(n in blob for n in needles)
        if rep is not None and 'traceback' in rep and want == 1 and needles:
            good = False            # invalid input must not take the traceback path (A4)
        results.append({'control': name, 'exit': p.returncode, 'expected_exit': want, 'needles': needles,
                        'problems': (rep or {}).get('problems'), 'consumed_sha256': sha(json.dumps((rep or {}).get('consumed'), sort_keys=True).encode()) if rep and rep.get('consumed') else None,
                        'control_ok': good})
        print('ok ' if good else 'BAD', name, p.returncode, ((rep or {}).get('problems') or [p.stderr.strip()[-120:]])[:1], flush=True)
        return good

    for name, (_b, extra, want, needles) in TAR_SCENARIOS.items():
        tp = os.path.join(inp, name + '.tar'); o = os.path.join(out, name)
        args = ['grade', '--evidence-tar', tp, '--evidence-sha256', built['tar_scenarios_sha256'][name], '--predictions', PRED, '--out', o]
        if 'manifest' in extra: args += ['--manifest', MANIFEST]
        ok &= judge(name, call(grader, *args), os.path.join(o, 'REGRADE_V2_1.json'), want, needles)
    for name, (want, needles) in DIR_SCENARIOS.items():
        d = os.path.join(inp, name); s = os.path.join(d, 'scratch'); o = os.path.join(out, name); os.makedirs(o)
        pre = os.path.join(o, 'precheck.json')
        pp = call(grader, 'precheck-files', '--scratch-root', s, '--manifest', MANIFEST, '--out', pre)
        if name.startswith('dir_precheck_'):
            ok &= judge(name, pp, pre, want, needles); continue
        root = s
        if name == 'dir_changed_after_precheck':
            target = os.path.join(s, MRC.format('ov-cand-cpu', F_)); keep = target + '.before'
            os.rename(target, keep); shutil.copyfile(os.path.join(d, 'replacement.mrc'), target)
        gout = os.path.join(s, 'regrade-out') if name == 'dir_out_inside_scratch' else os.path.join(o, 'grade')
        if name == 'dir_noncanonical_root': root = os.path.join(d, 'scratch-link')
        p = call(grader, 'grade', '--scratch-root', root, '--manifest', MANIFEST, '--precheck', pre, '--predictions', PRED, '--out', gout)
        if name == 'dir_changed_after_precheck':
            os.replace(keep, target)                       # restore the built input
        report = os.path.join(gout, 'REGRADE_V2_1.json')
        if name in ('dir_out_inside_scratch', 'dir_noncanonical_root'):
            good = p.returncode == 1 and all(n in p.stderr for n in needles) and not os.path.exists(gout if name == 'dir_out_inside_scratch' else os.path.join(o, 'never'))
            results.append({'control': name, 'exit': p.returncode, 'expected_exit': 1, 'needles': needles, 'stderr': p.stderr.strip()[-200:], 'control_ok': good})
            print('ok ' if good else 'BAD', name, p.returncode, p.stderr.strip()[-120:], flush=True); ok &= good
        else:
            if name == 'dir_full_pass':
                ok &= judge(name + ':precheck', pp, pre, 0, [])
            ok &= judge(name, p, report, want, needles)
    for name, (want, needles, procv) in LIVE_SCENARIOS.items():
        d = os.path.join(inp, name); s = os.path.join(d, 'scratch'); o = os.path.join(out, name); os.makedirs(o)
        idx = os.path.join(s, 'src-cand/.git/index'); st0 = os.stat(idx)
        rep = os.path.join(o, 'live.json')
        p = call(grader, 'precheck-live', '--scratch-root', s, '--expect', os.path.join(d, 'EXPECT.json'), '--proc-root', os.path.join(d, 'proc'), '--out', rep)
        good = judge(name, p, rep, want, needles)
        if name == 'live_stale_index_stat_pass':
            st1 = os.stat(idx); same = (st0.st_size, st0.st_mtime_ns) == (st1.st_size, st1.st_mtime_ns)
            results[-1]['index_unchanged_witness'] = same; good &= same
            results[-1]['control_ok'] = good
        ok &= good
    # Refusal of an existing output directory (no report may be written over it).
    o = os.path.join(out, 'existing_out'); os.makedirs(o)
    p = call(grader, 'grade', '--evidence-tar', os.path.join(inp, 'real_evidence.tar'), '--evidence-sha256', TAR_SHA, '--predictions', PRED, '--out', o)
    good = p.returncode == 1 and 'output exists' in p.stderr and not os.listdir(o)
    results.append({'control': 'existing_out_refused', 'exit': p.returncode, 'control_ok': good}); ok &= good
    print('ok ' if good else 'BAD', 'existing_out_refused', flush=True)
    record = {'all_controls_ok': ok, 'n': len(results), 'grader': grader, 'grader_sha256': sha(open(grader, 'rb').read()),
              'amendment_sha256': sha(open(AMENDMENT, 'rb').read()), 'suite_sha256': sha(open(os.path.realpath(__file__), 'rb').read()),
              'build': built, 'results': results}
    open(os.path.join(out, 'CONTROLS.json'), 'w').write(json.dumps(record, indent=1) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('phase', choices=['build', 'run']); ap.add_argument('--ns', required=True)
    ap.add_argument('--tag'); ap.add_argument('--grader', default=os.path.join(HERE, 'regrade_v2_1.py'))
    a = ap.parse_args()
    sys.exit(build(a.ns) if a.phase == 'build' else run(a.ns, a.tag, a.grader))
