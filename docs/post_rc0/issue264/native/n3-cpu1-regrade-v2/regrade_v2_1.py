# SPDX-License-Identifier: GPL-2.0-or-later
"""cpu1 regrade v2.1 (CONTRACT.md + AMENDMENT-1.md). Read-only; inputs only from arguments; stdlib only.

  regrade_v2_1.py grade (--evidence-tar TAR --evidence-sha256 HEX | --scratch-root DIR --manifest M --precheck P)
                        [--manifest M] --predictions PRED --out NEW_DIR
  regrade_v2_1.py precheck-files --scratch-root DIR --manifest M --out NEW_FILE
  regrade_v2_1.py precheck-live  --scratch-root DIR --expect EXPECT_LIVE.json --proc-root /proc --out NEW_FILE

grade exit: 0 FULL PASS, 2 STAR layer PASS with FULL UNRUN, 1 FAIL or invalid input. Prechecks: 0 PASS, 1 otherwise.
Nothing is written below the scratch root; every read below it refuses symlinks (O_NOFOLLOW per component).
"""
import argparse, errno, hashlib, io, json, os, re, stat, struct, subprocess, sys, tarfile, traceback
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

AMENDMENT_SHA256 = 'e556f54c551b0fb656d55967fccabda89ce7335246204620b9e1e21fe0b11af5'
PRED_SHA256 = '6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e'
RECEIPTS_SHA256 = 'e178e99fa232a785c4758fa25acfae4c43d6266c2609d02570942310fdaabf33'
ORIGINAL_RESULTS_SHA256 = '1e027cef5950721b3d8299182f279abb314bde9e8d2353df1f7be252b6f18052'
MANIFEST_SHA256 = '6bdc14cc25a6361d8ab86f1c0e7edbb05be2099a9c7ed78a337ee8dda5992ed6'
RECORDED_ROOT = '/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1'
CPU_ARMS = {'ov-base-cpu': 'legacy', 'ov-cand-cpu': 'finite', 'ov-mut-cpu': 'uncentred'}
GPU_ARMS = {'ov-base-cuda': 'legacy', 'ov-cand-cuda': 'finite'}
PAIR_ARMS = ('ov-base-cpu', 'ov-cand-cpu')
MRC_DESCRIPTOR = (768, 512, 1, 2, 0)          # nx, ny, nz, mode, nsymbt (AMENDMENT-1 A1)
MRC_SIZE = 1024 + 768 * 512 * 4
READ_CAP = 16 << 20
TAR_CAP = 64 << 20                             # local evidence archives only
GUARD = re.compile(r'could not fit a reasonable local motion model \(delta > ([-+0-9.eE]+)\)')       # as tools/n3.py
OVERLAY = re.compile(r'MC264_N3 overlay applied n_obs=(\d+) nx=(\d+) ny=(\d+) n_frames=(\d+)')     # as tools/n3.py
LABELS = [('_rlnMicrographFrameNumber', '#1'), ('_rlnMicrographShiftX', '#2'), ('_rlnMicrographShiftY', '#3')]
VALUE = re.compile(r'^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$', re.ASCII)
ARGV_TAIL = ['--use_own', '--j', '1', '--patch_x', '4', '--patch_y', '4', '--bin_factor', '1', '--seed', '1', '--save_noDW', '--skip_defect']
sha = lambda b: hashlib.sha256(b).hexdigest()


class Invalid(Exception):
    pass


def canonical(path, must_exist=True):
    p = os.path.abspath(path)
    if must_exist and not os.path.exists(p):
        raise Invalid(f'missing input {p}')
    target = p if must_exist else os.path.dirname(p)
    if os.path.realpath(target) != target:
        raise Invalid(f'non-canonical path (symlink component): {target}')
    return p


def outside(path, root):
    return os.path.commonpath([os.path.abspath(path), root]) != root


def read_file(path, cap=READ_CAP):
    p = canonical(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Invalid(f'not a regular file: {p}')
        return _read_fd(fd, p, cap)
    finally:
        os.close(fd)


def _read_fd(fd, name, cap=READ_CAP):
    size = os.fstat(fd).st_size
    if size > cap:
        raise Invalid(f'{name} exceeds {cap} bytes')
    chunks, total = [], 0
    while True:
        b = os.read(fd, 1 << 20)
        if not b:
            break
        total += len(b)
        if total > cap:
            raise Invalid(f'{name} grew past {cap} bytes')
        chunks.append(b)
    return b''.join(chunks)


class TarReader:
    def __init__(self, path, expected):
        self.path = canonical(path)
        raw = read_file(self.path, TAR_CAP)
        if sha(raw) != expected:
            raise Invalid(f'evidence tar sha256 {sha(raw)} != {expected}')
        self.expected, self.files, self.dirs = expected, {}, set()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
            for m in tar:
                p = PurePosixPath(m.name)
                if p.is_absolute() or '..' in p.parts:
                    raise Invalid(f'unsafe member {m.name}')
                if not (m.isfile() or m.isdir()):
                    raise Invalid(f'link or special member {m.name}')
                for parent in p.parents:
                    self.dirs.add(str(parent))
                if m.isdir():
                    self.dirs.add(str(p))
                else:
                    if str(p) in self.files:
                        raise Invalid(f'duplicate member {m.name}')
                    self.files[str(p)] = tar.extractfile(m).read()
        self.identity = {'kind': 'tar', 'path': self.path, 'sha256': expected}

    def read(self, rel):
        return self.files.get(rel)

    def exists(self, rel):
        return rel in self.files or rel in self.dirs

    def unchanged(self):
        return sha(read_file(self.path, TAR_CAP)) == self.expected


class DirReader:
    """Every component below the canonical root is opened with O_NOFOLLOW; a symlink anywhere is invalid."""

    def __init__(self, root):
        self.root = canonical(root)
        if not os.path.isdir(self.root):
            raise Invalid(f'scratch root is not a directory: {self.root}')
        self.identity = {'kind': 'directory', 'path': self.root}

    def _walk(self, rel):
        parts = PurePosixPath(rel).parts
        if not parts or any(p in ('', '.', '..') for p in parts) or PurePosixPath(rel).is_absolute():
            raise Invalid(f'bad relative path {rel}')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for comp in parts[:-1]:
                try:
                    nfd = os.open(comp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    os.close(fd); return None, None
                except OSError as e:
                    os.close(fd)
                    if e.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise Invalid(f'symlink or non-directory component in {rel}')
                    raise
                os.close(fd); fd = nfd
            return fd, parts[-1]
        except BaseException:
            raise

    def read(self, rel, cap=READ_CAP):
        fd, leaf = self._walk(rel)
        if fd is None:
            return None
        try:
            try:
                lfd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                return None
            except OSError as e:
                if e.errno in (errno.ELOOP, errno.EMLINK):
                    raise Invalid(f'symlink leaf {rel}')
                raise
            try:
                if not stat.S_ISREG(os.fstat(lfd).st_mode):
                    raise Invalid(f'not a regular file: {rel}')
                return _read_fd(lfd, rel, cap)
            finally:
                os.close(lfd)
        finally:
            os.close(fd)

    def hash_stream(self, rel, cap=1 << 30):
        fd, leaf = self._walk(rel)
        if fd is None:
            return None
        try:
            try:
                lfd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                return None
            except OSError as e:
                if e.errno in (errno.ELOOP, errno.EMLINK):
                    raise Invalid(f'symlink leaf {rel}')
                raise
            try:
                st = os.fstat(lfd)
                if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
                    raise Invalid(f'not a bounded regular file: {rel}')
                h, n = hashlib.sha256(), 0
                while True:
                    b = os.read(lfd, 1 << 20)
                    if not b:
                        break
                    n += len(b); h.update(b)
                return {'size': n, 'sha256': h.hexdigest()}
            finally:
                os.close(lfd)
        finally:
            os.close(fd)

    def exists(self, rel):
        fd, leaf = self._walk(rel)
        if fd is None:
            return False
        try:
            st = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        finally:
            os.close(fd)
        if stat.S_ISLNK(st.st_mode):
            raise Invalid(f'symlink leaf {rel}')
        return True


def consumed(cases):
    rels = [f'build-{a}.binaries.sha256' for a in CPU_ARMS] + ['n3-cpu1/known-observations.json', 'n3-cpu1/RESULTS.json']
    for a in CPU_ARMS:
        for c in cases:
            b = f'n3-cpu1/{a}/{c}'
            rels += [f'{b}/RUN.json', f'{b}/logs/{a}-{c}.stdout', f'{b}/logs/{a}-{c}.stderr', f'{b}/out/km_local_nonsquare.star']
    mrcs = [f'n3-cpu1/{a}/{c}/out/km_local_nonsquare.mrc' for c in cases for a in PAIR_ARMS]
    return rels, mrcs


def snapshot(reader, cases):
    rels, mrcs = consumed(cases)
    files = {rel: reader.read(rel) for rel in rels + mrcs}
    presence = {f'n3-cpu1/{a}': reader.exists(f'n3-cpu1/{a}') for a in GPU_ARMS}
    return files, presence


def identity(files, presence):
    return {'files': {k: ({'size': len(v), 'sha256': sha(v)} if v is not None else 'absent') for k, v in sorted(files.items())},
            'presence': presence}


def text(b):
    return b.decode('utf-8', 'replace').replace('\r\n', '\n').replace('\r', '\n')   # Path.read_text(errors='replace')


def coefficients(star):
    """tools/n3.py star_blocks, coefficient half, unchanged."""
    if 'data_local_motion_model' not in star:
        return None
    vals = {}
    for line in star.split('data_local_motion_model', 1)[1].splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            vals[int(parts[0])] = float(parts[1])
    return [vals.get(i) for i in range(36)]


def global_rows(star):
    lines = star.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == 'data_global_shift']
    if len(starts) != 1:
        raise Invalid(f'{len(starts)} data_global_shift blocks')
    labels, rows, loop = [], [], False
    for line in lines[starts[0] + 1:]:
        if not line.isascii():
            raise Invalid(f'non-ASCII line in global block: {line!r}')
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('data_'):
            break
        if s == 'loop_':
            if loop:
                raise Invalid('second loop_')
            loop = True
            continue
        if s.startswith('_'):
            if not loop or rows:
                raise Invalid('label outside loop header')
            labels.append(tuple(s.split()))
            continue
        if not loop or labels != LABELS:
            raise Invalid(f'schema {labels}')
        tok = s.split()
        if len(tok) != 3:
            raise Invalid(f'malformed row {s!r}')
        expected = str(len(rows) + 1)
        if tok[0] != expected:
            raise Invalid(f'frame token {tok[0]!r} where {expected!r} expected')
        if not VALUE.match(tok[1]) or not VALUE.match(tok[2]):
            raise Invalid(f'malformed row {s!r}')
        try:
            x, y = Decimal(tok[1]), Decimal(tok[2])
        except InvalidOperation:
            raise Invalid(f'malformed row {s!r}')
        if not (x.is_finite() and y.is_finite()):
            raise Invalid(f'nonfinite row {s!r}')
        rows.append((int(tok[0]), x, y))
    if labels != LABELS:
        raise Invalid(f'schema {labels}')
    if len(rows) != 12:
        raise Invalid(f'{len(rows)} frames')
    return rows


def rows_equal(a, b):
    return len(a) == len(b) and all(fa == fb and xa == xb and ya == yb and xa.is_signed() == xb.is_signed()
                                    and ya.is_signed() == yb.is_signed() for (fa, xa, ya), (fb, xb, yb) in zip(a, b))


def mrc_check(b):
    """AMENDMENT-1 A1. Returns (descriptor, payload) or raises Invalid."""
    if len(b) != MRC_SIZE:
        raise Invalid(f'MRC size {len(b)} != {MRC_SIZE}')
    nx, ny, nz, mode = struct.unpack_from('<4i', b, 0)
    nsymbt = struct.unpack_from('<i', b, 92)[0]
    desc = (nx, ny, nz, mode, nsymbt)
    if desc != MRC_DESCRIPTOR:
        raise Invalid(f'MRC descriptor {desc} != {MRC_DESCRIPTOR}')
    if b[208:212] != b'MAP ':
        raise Invalid('MRC map word missing')
    return desc, b[1024:]


def grade(files, presence, pred):
    cases = list(pred) + ['Z_no_overlay']
    P = []
    receipts = json.loads(files['n3-cpu1/known-observations.json'])
    original = json.loads(files['n3-cpu1/RESULTS.json'])
    arm_bin = {}
    for arm in CPU_ARMS:
        b = files[f'build-{arm}.binaries.sha256']
        arm_bin[arm] = b.split()[0].decode('ascii', 'replace') if b else None
    if None in arm_bin.values() or len(set(arm_bin.values())) != 3:
        P.append(f'build receipts not three distinct hashes {arm_bin}')
    rec_rows = receipts['rows']
    rows, stars = [], {}
    for arm, algorithm in {**CPU_ARMS, **GPU_ARMS}.items():
        for case in cases:
            base = f'n3-cpu1/{arm}/{case}'
            raw = files.get(f'{base}/RUN.json')
            if raw is None:
                rows.append({'arm': arm, 'case': case, 'status': 'UNRUN'})
                continue
            rec = json.loads(raw)
            label, bad, binding = f'{arm}-{case}', [], []
            outs = []
            for kind in ('stdout', 'stderr'):
                rel = f'{base}/logs/{label}.{kind}'
                if rec.get(kind) != f'{RECORDED_ROOT}/{rel}' or files.get(rel) is None:
                    binding.append(f'{kind} not bound to this row'); outs.append('')
                else:
                    outs.append(text(files[rel]))
            log = outs[0] + outs[1]
            guards = [float(m) for m in GUARD.findall(log)]
            overlays = [list(t) for t in OVERLAY.findall(log)]
            sb = files.get(f'{base}/out/km_local_nonsquare.star')
            star = text(sb) if sb is not None else None
            coeffs = coefficients(star) if star is not None else None
            stars[(arm, case)] = star
            row = {'arm': arm, 'case': case, 'algorithm': algorithm, 'rc': rec.get('rc'), 'binary_sha256': rec.get('binary_sha256'),
                   'gpu_uuids': rec.get('gpu_uuids_witnessed'), 'overlay_lines': overlays, 'guard_values': guards,
                   'observed_reject': bool(guards), 'local_model_in_star': coeffs is not None}
            if rec.get('rc') != 0: bad.append(f"rc {rec.get('rc')}")
            if arm in GPU_ARMS: bad.append('CUDA row present in a CPU-only campaign')
            elif rec.get('gpu_uuids_witnessed') or '[CUDA' in log: bad.append('CUDA activity in a CPU arm')
            if len(guards) > 1: bad.append('more than one guard line')
            if case == 'Z_no_overlay':
                if overlays: bad.append('overlay applied without MC264_N3_COEFFS')
            else:
                p = pred[case][algorithm]
                row.update({'predicted_reject': p['reject'], 'predicted_value': p['value']})
                if len(overlays) != 1 or tuple(map(int, overlays[0][1:])) != (768, 512, 12) or int(overlays[0][0]) <= 18:
                    bad.append(f'overlay witness {overlays}')
                if row['observed_reject'] != p['reject']: bad.append('decision differs from prediction')
                if guards and abs(guards[0] - p['value']) > 2e-5 * p['value']: bad.append(f'guard value {guards[0]} vs {p["value"]}')
                if row['local_model_in_star'] == p['reject']: bad.append('STAR local model presence contradicts decision')
                if coeffs is not None:
                    if None in coeffs:
                        bad.append('published coefficient index missing')
                    else:
                        inj = pred[case]['coeffX_float'] + pred[case]['coeffY_float']
                        err = max(abs(a - b) - 1e-7 * abs(b) for a, b in zip(coeffs, inj))
                        row['max_coeff_excess_over_1e-7rel'] = err
                        if err > 1e-5: bad.append(f'published coefficients differ from injected by {err}')
            if row['local_model_in_star'] == row['observed_reject']: bad.append('STAR model presence vs guard line')
            if arm in CPU_ARMS:
                if rec.get('binary_sha256') != arm_bin.get(arm): binding.append('binary differs from build receipt')
                want_argv = ['taskset', '-c', '14-15', f'{RECORDED_ROOT}/build-{arm}/motioncorr', '--i', 'km_local_nonsquare.star',
                             '--o', f'{RECORDED_ROOT}/{base}/out/'] + ARGV_TAIL
                for field, want in (('label', label), ('arm', arm), ('case', case), ('gpu', False),
                                    ('cwd', f'{RECORDED_ROOT}/{base}/cwd'), ('argv', want_argv)):
                    if rec.get(field) != want: binding.append(f'RUN {field} not bound')
                r = rec_rows.get(f'{arm}/{case}')
                env = rec.get('env', {})
                if r is None: binding.append('no receipt')
                elif r['overlay'] and (env.get('MC264_N3_COEFFS') != r['MC264_N3_COEFFS'] or sha(r['MC264_N3_COEFFS'].encode()) != r['spec_sha256']):
                    binding.append('injected spec differs from receipt')
                elif not r['overlay'] and 'MC264_N3_COEFFS' in env: binding.append('spec on a no-overlay row')
            row['problems'], row['binding_problems'] = bad, binding
            row['status'] = 'PASS' if not bad and not binding else 'FAIL'
            rows.append(row)
    for case in pred:
        spec = ' '.join(repr(v) for v in pred[case]['coeffX_float'] + pred[case]['coeffY_float'])
        for arm in CPU_ARMS:
            if rec_rows.get(f'{arm}/{case}', {}).get('MC264_N3_COEFFS') != spec: P.append(f'receipt {arm}/{case} not from predictions')
    by = {(x['arm'], x['case']): x for x in rows}
    orig_pairs = {p['case']: p for p in original['base_vs_candidate']}
    pairs, images_available = [], True
    for case in cases:
        x, y = by[PAIR_ARMS[0], case], by[PAIR_ARMS[1], case]
        if 'UNRUN' in (x['status'], y['status']):
            continue
        pr = {'backend': 'cpu', 'case': case, 'same_decision': x['observed_reject'] == y['observed_reject']}
        try:
            pr['global_rows_equal'] = rows_equal(global_rows(stars[PAIR_ARMS[0], case] or ''), global_rows(stars[PAIR_ARMS[1], case] or ''))
        except Invalid as e:
            pr['global_rows_equal'], pr['global_rows_error'] = False, str(e)
        pr['status_star_layer'] = 'PASS' if pr['global_rows_equal'] else 'FAIL'
        mb, mc = (files.get(f'n3-cpu1/{a}/{case}/out/km_local_nonsquare.mrc') for a in PAIR_ARMS)
        try:
            checked = [mrc_check(m) if m is not None else None for m in (mb, mc)]
        except Invalid as e:
            pr.update(image_data_equal=None, image_error=str(e), status_full='FAIL'); pairs.append(pr); continue
        if None in checked:
            images_available = False
            pr.update(image_data_equal=None, status_full='UNRUN'); pairs.append(pr); continue
        (db, pb), (dc, pc) = checked
        pr['descriptors_equal'] = db == dc
        pr['image_data_equal'] = pb == pc
        pr['payload_sha256'] = [sha(pb), sha(pc)]
        ok = pr['global_rows_equal'] and pr['descriptors_equal'] and (pr['image_data_equal'] if pr['same_decision'] else not pr['image_data_equal'])
        hist = orig_pairs.get(case, {}).get('image_data_equal')
        pr['original_image_data_equal'] = hist
        if hist is not pr['image_data_equal']:
            pr['contradicts_original'] = True
            ok = False
        pr['status_full'] = 'PASS' if ok else 'FAIL'
        pairs.append(pr)
    expected_kills = sorted(c for c in pred if pred[c]['uncentred']['reject'] != pred[c]['finite']['reject'])
    mut = [x for x in rows if x['arm'] == 'ov-mut-cpu' and x['case'] != 'Z_no_overlay' and x['status'] != 'UNRUN']
    cand = {x['case']: x for x in rows if x['arm'] == 'ov-cand-cpu'}
    kills = sorted(x['case'] for x in mut if x['case'] in cand and x['observed_reject'] != cand[x['case']].get('observed_reject'))
    n4 = {'mutant_rows_pass': len(mut) == len(pred) and all(x['status'] == 'PASS' for x in mut), 'kills': kills, 'expected_kills': expected_kills}
    n4['status'] = 'PASS' if n4['mutant_rows_pass'] and kills == expected_kills else 'FAIL'
    parity = []
    orig_rows = {(x['arm'], x['case']): x for x in original['rows']}
    keys = ('status', 'observed_reject', 'guard_values', 'overlay_lines', 'local_model_in_star', 'predicted_reject',
            'predicted_value', 'max_coeff_excess_over_1e-7rel', 'binary_sha256', 'problems')
    for k, x in by.items():
        o = orig_rows.get(k)
        if o is None: parity.append(f'{k} absent from original'); continue
        mine = dict(x, status='PASS' if x['status'] == 'PASS' or (x['status'] == 'FAIL' and not x['problems']) else x['status'])
        diff = [f for f in keys if (f in o or f in mine) and o.get(f) != mine.get(f)]
        if diff: parity.append(f'{k}: {diff}')
    cpu = [x for x in rows if x['arm'] in CPU_ARMS]
    gpu = [x for x in rows if x['arm'] in GPU_ARMS]
    if len(cpu) != 24 or any(x['status'] != 'PASS' for x in cpu):
        P.append('CPU rows not 24 PASS: ' + str(sorted(f"{x['arm']}/{x['case']}:{x['status']}" for x in cpu if x['status'] != 'PASS')))
    if len(gpu) != 16 or any(x['status'] != 'UNRUN' for x in gpu) or any(presence.values()):
        P.append('CUDA rows are not exactly 16 UNRUN with no artefact')
    if len(pairs) != 8 or any(p['status_star_layer'] != 'PASS' for p in pairs): P.append('CPU pairs not 8 with equal global rows')
    if n4['status'] != 'PASS': P.append('N4 not PASS on the expected kills')
    if parity: P.append('row parity with the original grader failed')
    star_ok = not P
    full_bad = [p['case'] for p in pairs if p['status_full'] == 'FAIL']
    if full_bad: P.append(f'image relation failed: {full_bad}')
    if any(p.get('contradicts_original') for p in pairs):
        P.append('recomputed image relation contradicts original evidence; stop')
    return {'rows': rows, 'pairs': pairs, 'n4': n4, 'row_parity_problems': parity, 'build_receipts': arm_bin, 'problems': P,
            'star_layer_verdict': 'PASS' if star_ok else 'FAIL',
            'full_verdict': 'FAIL' if (not star_ok or full_bad) else ('PASS' if images_available else 'UNRUN'),
            'full_n3_n4_aggregate': 'INCOMPLETE: 16 CUDA rows UNRUN',
            'historical_original': {'summary': original['summary'], 'n4': original['n4_mutant']['status'],
                                    'pairs': [{k: p[k] for k in ('case', 'same_global_shifts', 'same_decision', 'image_data_equal', 'status')}
                                              for p in original['base_vs_candidate']], 'subset': 'FAIL (unchanged)'}}


def new_out_dir(path, root=None):
    p = canonical(path, must_exist=False)
    if os.path.lexists(p):
        raise Invalid(f'output exists: {p}')
    if root is not None and not outside(p, root):
        raise Invalid('output inside the scratch root')
    os.mkdir(p)
    return p


def publish(path, record):
    tmp = path + '.partial'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(record, indent=1, default=str) + '\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def self_identity():
    return {'grader_sha256': sha(read_file(os.path.realpath(__file__))), 'amendment_sha256': AMENDMENT_SHA256,
            'python': sys.version.split()[0]}


def cmd_grade(a):
    report = {'kind': 'cpu1 regrade v2.1 (AMENDMENT-1); TEST-ONLY overlay builds; not CPU+CUDA qualification', **self_identity()}
    out = None
    try:
        root = canonical(a.scratch_root) if a.scratch_root else None
        out = new_out_dir(a.out, root)
        inputs = {}
        pred_raw = read_file(a.predictions); inputs['predictions'] = {'path': canonical(a.predictions), 'sha256': sha(pred_raw)}
        if sha(pred_raw) != PRED_SHA256: raise Invalid(f'predictions sha256 {sha(pred_raw)} != {PRED_SHA256}')
        manifest = precheck = None
        if a.manifest:
            mraw = read_file(a.manifest); inputs['manifest'] = {'path': canonical(a.manifest), 'sha256': sha(mraw)}
            if sha(mraw) != MANIFEST_SHA256: raise Invalid(f'manifest sha256 {sha(mraw)} != {MANIFEST_SHA256}')
            manifest = json.loads(mraw)
        if a.evidence_tar:
            if not a.evidence_sha256: raise Invalid('--evidence-sha256 is required with --evidence-tar')
            reader = TarReader(a.evidence_tar, a.evidence_sha256)
        else:
            if not (a.manifest and a.precheck): raise Invalid('directory mode requires --manifest and --precheck')
            praw = read_file(a.precheck); inputs['precheck'] = {'path': canonical(a.precheck), 'sha256': sha(praw)}
            precheck = json.loads(praw)
            reader = DirReader(root)
        report['source'] = reader.identity; report['inputs'] = inputs
        pred = json.loads(pred_raw)['n3']
        cases = list(pred) + ['Z_no_overlay']
        files, presence = snapshot(reader, cases)
        ident = identity(files, presence)
        report['consumed'] = ident
        for rel, want in (('n3-cpu1/known-observations.json', RECEIPTS_SHA256), ('n3-cpu1/RESULTS.json', ORIGINAL_RESULTS_SHA256)):
            if files.get(rel) is None or sha(files[rel]) != want: raise Invalid(f'{rel} missing or sha256 != pinned {want}')
        binding = []
        if manifest is not None:
            for rel, want in manifest['files'].items():
                got = ident['files'].get(rel)
                if got == 'absent' or got is None or got['sha256'] != want: binding.append(f'manifest mismatch {rel}')
        if precheck is not None:
            if precheck.get('verdict') != 'PASS' or precheck.get('scratch_root') != root or precheck.get('manifest_sha256') != MANIFEST_SHA256:
                binding.append('precheck report not a PASS for this root and manifest')
            for rel, rec in (precheck.get('pair_mrcs') or {}).items():
                if ident['files'].get(rel) != rec: binding.append(f'changed after precheck {rel}')
            if sorted(precheck.get('pair_mrcs') or {}) != sorted(consumed(cases)[1]): binding.append('precheck MRC set incomplete')
        result = grade(files, presence, pred)
        # Re-read every consumed input and require the same identity (A2).
        files2, presence2 = snapshot(reader, cases)
        if identity(files2, presence2) != ident: binding.append('input changed during grading')
        if isinstance(reader, TarReader) and not reader.unchanged(): binding.append('evidence tar changed during grading')
        report.update(result)
        if binding:
            report['problems'] = report['problems'] + binding
            report['input_binding_problems'] = binding
            report['star_layer_verdict'] = report['full_verdict'] = 'FAIL'
    except Invalid as e:
        report.update(star_layer_verdict='FAIL', full_verdict='FAIL', problems=[f'invalid input: {e}'])
    except Exception as e:
        report.update(star_layer_verdict='FAIL', full_verdict='FAIL', problems=[f'unexpected error: {e!r}'], traceback=traceback.format_exc())
    if out is None:
        print('refused:', report['problems'], file=sys.stderr)
        return 1
    publish(os.path.join(out, 'REGRADE_V2_1.json'), report)
    print('star_layer', report['star_layer_verdict'], 'full', report['full_verdict'], report['problems'][:3])
    return 0 if report['full_verdict'] == 'PASS' else 2 if report['star_layer_verdict'] == 'PASS' and report['full_verdict'] == 'UNRUN' else 1


def new_out_file(path, root):
    p = canonical(path, must_exist=False)
    if os.path.lexists(p): raise Invalid(f'output exists: {p}')
    if not outside(p, root): raise Invalid('output inside the scratch root')
    return p


def cmd_precheck_files(a):
    rec = {'kind': 'cpu1 regrade v2.1 precheck-files', **self_identity(), 'problems': []}
    out = None
    try:
        root = canonical(a.scratch_root); out = new_out_file(a.out, root)
        mraw = read_file(a.manifest)
        if sha(mraw) != MANIFEST_SHA256: raise Invalid('manifest sha256 differs from the pinned value')
        m = json.loads(mraw); reader = DirReader(root)
        rec.update(scratch_root=root, manifest_sha256=sha(mraw), pair_mrcs={})
        for rel, want in m['files'].items():
            b = reader.read(rel)
            if b is None or sha(b) != want: rec['problems'].append(f'{rel} missing or sha256 differs')
        for rel in m['pair_mrcs']:
            b = reader.read(rel)
            if b is None: rec['problems'].append(f'{rel} missing'); continue
            try: mrc_check(b)
            except Invalid as e: rec['problems'].append(f'{rel}: {e}')
            rec['pair_mrcs'][rel] = {'size': len(b), 'sha256': sha(b)}
    except Invalid as e:
        rec['problems'].append(f'invalid input: {e}')
    rec['verdict'] = 'PASS' if not rec['problems'] else 'FAIL'
    if out is None:
        print('refused:', rec['problems'], file=sys.stderr); return 1
    publish(out, rec); print('precheck-files', rec['verdict'], rec['problems'][:3])
    return 0 if rec['verdict'] == 'PASS' else 1


def _git(tree, *args):
    env = {'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C', 'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
    if 'HOME' in os.environ: env['HOME'] = os.environ['HOME']
    p = subprocess.run(['git', '-C', tree, *args], capture_output=True, env=env)
    if p.returncode != 0: raise Invalid(f'git {args[0]} failed in {tree}: {p.stderr.decode(errors="replace")[:200]}')
    return p.stdout


def _scan_processes(proc_root, root):
    if not os.path.isdir(proc_root): raise Invalid(f'proc root missing: {proc_root}')
    skip = {os.getpid()}
    pid = os.getppid()
    while pid > 1 and pid not in skip:
        skip.add(pid)
        try:
            pid = int(open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    refers = lambda s: s == root or s.startswith(root + '/')
    hits, unreadable = [], 0
    for d in os.listdir(proc_root):
        if not d.isdigit() or int(d) in skip: continue
        base = os.path.join(proc_root, d)
        try:
            cmd = open(os.path.join(base, 'cmdline'), 'rb').read().split(b'\0')
            if any(refers(c.decode(errors='replace')) or (root in c.decode(errors='replace')) for c in cmd if c): hits.append((d, 'cmdline')); continue
            try:
                if refers(os.readlink(os.path.join(base, 'cwd'))): hits.append((d, 'cwd')); continue
            except FileNotFoundError:
                pass
            fdd = os.path.join(base, 'fd')
            if os.path.isdir(fdd):
                for fd in os.listdir(fdd):
                    try:
                        if refers(os.readlink(os.path.join(fdd, fd))): hits.append((d, 'fd')); break
                    except OSError:
                        pass
        except PermissionError:
            unreadable += 1
        except (FileNotFoundError, ProcessLookupError):
            pass
    return hits, unreadable


def cmd_precheck_live(a):
    rec = {'kind': 'cpu1 regrade v2.1 precheck-live (read-only, GIT_OPTIONAL_LOCKS=0)', **self_identity(), 'problems': []}
    P = rec['problems']; out = None
    try:
        root = canonical(a.scratch_root); out = new_out_file(a.out, root)
        eraw = read_file(a.expect); expect = json.loads(eraw)
        rec.update(scratch_root=root, expect_sha256=sha(eraw), trees={}, binaries={})
        reader = DirReader(root)
        proc_root = os.path.abspath(a.proc_root)
        if not os.path.isdir(proc_root): raise Invalid(f'proc root missing: {proc_root}')
        hits, unreadable = _scan_processes(canonical(proc_root), root)
        rec['processes'] = {'referring_to_scratch': hits, 'unreadable': unreadable}
        if hits: P.append(f'active processes refer to the scratch: {hits}')
        for name, want in expect['trees'].items():
            tree = os.path.join(root, name)
            if not reader.exists(f'{name}/.git/index'): raise Invalid(f'{name}: no git index')
            canonical(tree)
            idx = os.path.join(tree, '.git', 'index')
            st0 = os.stat(idx, follow_symlinks=False)
            got = {'head': _git(tree, 'rev-parse', 'HEAD').decode().strip(),
                   'diff_sha256': sha(_git(tree, 'diff')),
                   'status': [l for l in _git(tree, 'status', '--porcelain').decode().split('\n') if l],
                   'runner_sha256': sha(reader.read(f'{name}/src/motioncorr_runner.cpp') or b''),
                   'helper_sha256': (lambda b: sha(b) if b is not None else 'absent')(reader.read(f'{name}/src/local_motion_guard.h'))}
            st1 = os.stat(idx, follow_symlinks=False)
            got['index_unchanged'] = (st0.st_size, st0.st_mtime_ns, st0.st_ino) == (st1.st_size, st1.st_mtime_ns, st1.st_ino)
            rec['trees'][name] = got
            if not got['index_unchanged']: P.append(f'{name}: .git/index changed during the check')
            for k, v in want.items():
                if got.get(k) != v: P.append(f'{name}: {k} {got.get(k)!r} != {v!r}')
        for arm, want in expect['binaries'].items():
            live = reader.hash_stream(f'build-{arm}/motioncorr')
            r = reader.read(f'build-{arm}.binaries.sha256')
            receipt = r.split()[0].decode('ascii', 'replace') if r else None
            rec['binaries'][arm] = {'live': live, 'receipt': receipt, 'expect': want}
            if live is None or live['sha256'] != want or receipt != want: P.append(f'{arm}: live/receipt/expect binary hashes differ')
        if len({v['live']['sha256'] for v in rec['binaries'].values() if v['live']}) != len(expect['binaries']):
            P.append('live binaries are not distinct')
    except Invalid as e:
        P.append(f'invalid input: {e}')
    rec['verdict'] = 'PASS' if not P else 'FAIL'
    if out is None:
        print('refused:', P, file=sys.stderr); return 1
    publish(out, rec); print('precheck-live', rec['verdict'], P[:3])
    return 0 if rec['verdict'] == 'PASS' else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('grade')
    src = g.add_mutually_exclusive_group(required=True)
    src.add_argument('--evidence-tar'); src.add_argument('--scratch-root')
    g.add_argument('--evidence-sha256'); g.add_argument('--manifest'); g.add_argument('--precheck')
    g.add_argument('--predictions', required=True); g.add_argument('--out', required=True)
    f = sub.add_parser('precheck-files')
    for k in ('--scratch-root', '--manifest', '--out'): f.add_argument(k, required=True)
    l = sub.add_parser('precheck-live')
    for k in ('--scratch-root', '--expect', '--proc-root', '--out'): l.add_argument(k, required=True)
    a = ap.parse_args()
    return {'grade': cmd_grade, 'precheck-files': cmd_precheck_files, 'precheck-live': cmd_precheck_live}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
