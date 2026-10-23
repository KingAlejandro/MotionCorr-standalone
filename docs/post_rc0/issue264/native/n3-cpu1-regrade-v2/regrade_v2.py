# SPDX-License-Identifier: GPL-2.0-or-later
"""cpu1 regrade v2 (CONTRACT.md): the original row/pair/N4 rules with exact parsed global-shift rows.

Read-only. Inputs come only from arguments; nothing is imported from the old tools, no environment
variable is read, nothing is extracted or executed. Exit 0 FULL PASS, 2 STAR-layer PASS with FULL
UNRUN (no MRC payloads), 1 any FAIL or invalid input.

  regrade_v2.py (--evidence-tar TAR --evidence-sha256 HEX | --scratch-root DIR)
                --predictions P --receipts R --original-results O --out NEW_DIR
"""
import argparse, hashlib, io, json, re, sys, tarfile, traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath

PRED_SHA256 = '6ff11cb5145f3c9f3f0c6380de26b27913eb9da7ccb6652a783c777b205c859e'
RECEIPTS_SHA256 = 'e178e99fa232a785c4758fa25acfae4c43d6266c2609d02570942310fdaabf33'
ORIGINAL_RESULTS_SHA256 = '1e027cef5950721b3d8299182f279abb314bde9e8d2353df1f7be252b6f18052'
CPU_ARMS = {'ov-base-cpu': 'legacy', 'ov-cand-cpu': 'finite', 'ov-mut-cpu': 'uncentred'}
GPU_ARMS = {'ov-base-cuda': 'legacy', 'ov-cand-cuda': 'finite'}
GUARD = re.compile(r'could not fit a reasonable local motion model \(delta > ([-+0-9.eE]+)\)')       # as tools/n3.py
OVERLAY = re.compile(r'MC264_N3 overlay applied n_obs=(\d+) nx=(\d+) ny=(\d+) n_frames=(\d+)')     # as tools/n3.py
LABELS = [('_rlnMicrographFrameNumber', '#1'), ('_rlnMicrographShiftX', '#2'), ('_rlnMicrographShiftY', '#3')]
DECIMAL = re.compile(r'^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$')
sha = lambda b: hashlib.sha256(b).hexdigest()


class Invalid(Exception):
    pass


class TarSource:
    def __init__(self, path, expected):
        raw = Path(path).read_bytes()
        if sha(raw) != expected:
            raise Invalid(f'evidence tar sha256 {sha(raw)} != {expected}')
        self.files, self.dirs = {}, set()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
            for m in tar:
                p = PurePosixPath(m.name)
                if p.is_absolute() or '..' in p.parts:
                    raise Invalid(f'unsafe member {m.name}')
                for parent in p.parents:
                    self.dirs.add(str(parent))
                if m.isdir():
                    self.dirs.add(str(p))
                elif m.isfile():
                    if str(p) in self.files:
                        raise Invalid(f'duplicate member {m.name}')
                    self.files[str(p)] = tar.extractfile(m).read()
        self.identity = {'kind': 'tar', 'path': str(path), 'sha256': expected}

    def read(self, rel):
        return self.files.get(rel)

    def exists(self, rel):
        return rel in self.files or rel in self.dirs


class DirSource:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.identity = {'kind': 'directory', 'path': str(self.root)}

    def _path(self, rel):
        p = (self.root / rel)
        if self.root not in p.resolve().parents and p.resolve() != self.root:
            raise Invalid(f'path escapes root: {rel}')
        return p

    def read(self, rel):
        p = self._path(rel)
        return p.read_bytes() if p.is_file() and not p.is_symlink() else None

    def exists(self, rel):
        return self._path(rel).exists()


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
    """Exact parse of the single data_global_shift block (CONTRACT.md). Raises Invalid."""
    lines = star.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == 'data_global_shift']
    if len(starts) != 1:
        raise Invalid(f'{len(starts)} data_global_shift blocks')
    labels, rows, loop = [], [], False
    for line in lines[starts[0] + 1:]:
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
        if len(tok) != 3 or not tok[0].isdigit() or not DECIMAL.match(tok[1]) or not DECIMAL.match(tok[2]):
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
    if [r[0] for r in rows] != list(range(1, 13)):
        raise Invalid(f'frames {[r[0] for r in rows]}')
    return rows


def rows_equal(a, b):
    return len(a) == len(b) and all(fa == fb and xa == xb and ya == yb and xa.is_signed() == xb.is_signed()
                                    and ya.is_signed() == yb.is_signed() for (fa, xa, ya), (fb, xb, yb) in zip(a, b))


def mrc_payload(b):
    if len(b) < 1024:
        raise Invalid('MRC shorter than its header')
    ext = int.from_bytes(b[92:96], 'little', signed=True)
    if ext < 0 or len(b) < 1024 + ext:
        raise Invalid('MRC extended header inconsistent')
    return b[1024 + ext:]


def grade(src, pred, receipts, original, out):
    cases = list(pred) + ['Z_no_overlay']
    report = {'kind': 'cpu1 regrade v2 (exact global rows); TEST-ONLY overlay builds; not CPU+CUDA qualification',
              'source': src.identity, 'problems': []}
    P = report['problems']
    # Bindings: build receipts, RUN binaries, injected observations.
    arm_bin = {}
    for arm in CPU_ARMS:
        b = src.read(f'build-{arm}.binaries.sha256')
        arm_bin[arm] = b.split()[0].decode() if b else None
    if None in arm_bin.values() or len(set(arm_bin.values())) != 3:
        P.append(f'build receipts {arm_bin}')
    rec_rows = receipts['rows']
    rows, stars = [], {}
    for arm, algorithm in {**CPU_ARMS, **GPU_ARMS}.items():
        for case in cases:
            base = f'n3-cpu1/{arm}/{case}'
            raw = src.read(f'{base}/RUN.json')
            if raw is None:
                rows.append({'arm': arm, 'case': case, 'status': 'UNRUN'})
                continue
            rec = json.loads(raw)
            label, bad = f'{arm}-{case}', []
            outs = []
            for kind in ('stdout', 'stderr'):
                rel = f'{base}/logs/{label}.{kind}'
                if not str(rec.get(kind, '')).endswith('/' + rel) or src.read(rel) is None:
                    bad.append(f'{kind} not bound to this row'); outs.append('')
                else:
                    outs.append(text(src.read(rel)))
            log = outs[0] + outs[1]
            guards = [float(m) for m in GUARD.findall(log)]
            overlays = [list(t) for t in OVERLAY.findall(log)]
            sb = src.read(f'{base}/out/km_local_nonsquare.star')
            star = text(sb) if sb is not None else None
            coeffs = coefficients(star) if star is not None else None
            stars[(arm, case)] = star
            row = {'arm': arm, 'case': case, 'algorithm': algorithm, 'rc': rec['rc'], 'binary_sha256': rec['binary_sha256'],
                   'gpu_uuids': rec['gpu_uuids_witnessed'], 'overlay_lines': overlays, 'guard_values': guards,
                   'observed_reject': bool(guards), 'local_model_in_star': coeffs is not None}
            if rec['rc'] != 0: bad.append(f"rc {rec['rc']}")
            if arm in GPU_ARMS: bad.append('CUDA row present in a CPU-only campaign')
            elif rec['gpu_uuids_witnessed'] or '[CUDA' in log: bad.append('CUDA activity in a CPU arm')
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
            # v2 bindings (not in the original row rule; reported separately so row parity stays comparable).
            binding = []
            if arm in CPU_ARMS and rec['binary_sha256'] != arm_bin.get(arm): binding.append('binary differs from build receipt')
            r = rec_rows.get(f'{arm}/{case}')
            env = rec.get('env', {})
            if arm in CPU_ARMS:
                if r is None: binding.append('no receipt')
                elif r['overlay'] and (env.get('MC264_N3_COEFFS') != r['MC264_N3_COEFFS'] or sha(r['MC264_N3_COEFFS'].encode()) != r['spec_sha256']):
                    binding.append('injected spec differs from receipt')
                elif not r['overlay'] and 'MC264_N3_COEFFS' in env: binding.append('spec on a no-overlay row')
            row['problems'], row['binding_problems'] = bad, binding
            row['status'] = 'PASS' if not bad and not binding else 'FAIL'
            rows.append(row)
    # Receipts must equal the predictions they were frozen from.
    for case in pred:
        spec = ' '.join(repr(v) for v in pred[case]['coeffX_float'] + pred[case]['coeffY_float'])
        for arm in CPU_ARMS:
            if rec_rows.get(f'{arm}/{case}', {}).get('MC264_N3_COEFFS') != spec: P.append(f'receipt {arm}/{case} not from predictions')
    by = {(x['arm'], x['case']): x for x in rows}
    # Pairs: exact global rows; image relation from payload bytes when every pair MRC is present.
    pairs, images_available = [], True
    for case in cases:
        x, y = by[('ov-base-cpu', case)], by[('ov-cand-cpu', case)]
        if 'UNRUN' in (x['status'], y['status']):
            continue
        pr = {'backend': 'cpu', 'case': case, 'same_decision': x['observed_reject'] == y['observed_reject']}
        try:
            pr['global_rows_equal'] = rows_equal(global_rows(stars[('ov-base-cpu', case)] or ''), global_rows(stars[('ov-cand-cpu', case)] or ''))
        except Invalid as e:
            pr['global_rows_equal'], pr['global_rows_error'] = False, str(e)
        mb, mc = (src.read(f'n3-cpu1/{a}/{case}/out/km_local_nonsquare.mrc') for a in ('ov-base-cpu', 'ov-cand-cpu'))
        pr['status_star_layer'] = 'PASS' if pr['global_rows_equal'] else 'FAIL'
        if mb is None or mc is None:
            images_available = False
            pr['image_data_equal'], pr['status_full'] = None, 'UNRUN'
        else:
            try:
                pr['image_data_equal'] = mrc_payload(mb) == mrc_payload(mc)
                pr['mrc_payload_sha256'] = [sha(mrc_payload(mb)), sha(mrc_payload(mc))]
                ok = pr['global_rows_equal'] and (pr['image_data_equal'] if pr['same_decision'] else not pr['image_data_equal'])
                pr['status_full'] = 'PASS' if ok else 'FAIL'
            except Invalid as e:
                pr['image_data_equal'], pr['image_error'], pr['status_full'] = None, str(e), 'FAIL'
        pairs.append(pr)
    expected_kills = sorted(c for c in pred if pred[c]['uncentred']['reject'] != pred[c]['finite']['reject'])
    mut = [x for x in rows if x['arm'] == 'ov-mut-cpu' and x['case'] != 'Z_no_overlay' and x['status'] != 'UNRUN']
    cand = {x['case']: x for x in rows if x['arm'] == 'ov-cand-cpu'}
    kills = sorted(x['case'] for x in mut if x['case'] in cand and x['observed_reject'] != cand[x['case']].get('observed_reject'))
    n4 = {'mutant_rows_pass': len(mut) == len(pred) and all(x['status'] == 'PASS' for x in mut), 'kills': kills, 'expected_kills': expected_kills}
    n4['status'] = 'PASS' if n4['mutant_rows_pass'] and kills == expected_kills else 'FAIL'
    # Row parity with the original grader on the same inputs (port check).
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
    if len(cpu) != 24 or any(x['status'] != 'PASS' for x in cpu): P.append('CPU rows not 24 PASS: ' + str(sorted(f"{x['arm']}/{x['case']}:{x['status']}" for x in cpu if x['status'] != 'PASS')))
    if len(gpu) != 16 or any(x['status'] != 'UNRUN' for x in gpu) or any(src.exists(f'n3-cpu1/{a}') for a in GPU_ARMS): P.append('CUDA rows are not exactly 16 UNRUN with no artefact')
    if len(pairs) != 8 or any(p['status_star_layer'] != 'PASS' for p in pairs): P.append('CPU pairs not 8 with equal global rows')
    if n4['status'] != 'PASS': P.append('N4 not PASS on the expected kills')
    if parity: P.append('row parity with the original grader failed')
    star_ok = not P
    full_bad = [p['case'] for p in pairs if p['status_full'] == 'FAIL']
    if full_bad: P.append(f'image relation failed: {full_bad}')
    report.update({'rows': rows, 'pairs': pairs, 'n4': n4, 'row_parity_problems': parity, 'build_receipts': arm_bin,
                   'star_layer_verdict': 'PASS' if star_ok else 'FAIL',
                   'full_verdict': 'FAIL' if (not star_ok or full_bad) else ('PASS' if images_available else 'UNRUN'),
                   'full_n3_n4_aggregate': 'INCOMPLETE: 16 CUDA rows UNRUN',
                   'historical_original': {'summary': original['summary'], 'n4': original['n4_mutant']['status'],
                                           'pairs': [{k: p[k] for k in ('case', 'same_global_shifts', 'same_decision', 'image_data_equal', 'status')}
                                                     for p in original['base_vs_candidate']],
                                           'subset': 'FAIL (unchanged)'}})
    return report


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--evidence-tar', type=Path); g.add_argument('--scratch-root', type=Path)
    ap.add_argument('--evidence-sha256'); ap.add_argument('--predictions', type=Path, required=True)
    ap.add_argument('--receipts', type=Path, required=True); ap.add_argument('--original-results', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    inputs, report = {}, None
    try:
        for name, path, want in (('predictions', a.predictions, PRED_SHA256), ('receipts', a.receipts, RECEIPTS_SHA256),
                                 ('original_results', a.original_results, ORIGINAL_RESULTS_SHA256)):
            raw = path.read_bytes(); inputs[name] = {'path': str(path), 'sha256': sha(raw)}
            if sha(raw) != want: raise Invalid(f'{name} sha256 {sha(raw)} != {want}')
        if a.evidence_tar and not a.evidence_sha256: raise Invalid('--evidence-sha256 is required with --evidence-tar')
        src = TarSource(a.evidence_tar, a.evidence_sha256) if a.evidence_tar else DirSource(a.scratch_root)
        report = grade(src, json.loads(a.predictions.read_bytes())['n3'], json.loads(a.receipts.read_bytes()),
                       json.loads(a.original_results.read_bytes()), a.out)
    except Exception as e:
        report = {'kind': 'cpu1 regrade v2', 'star_layer_verdict': 'FAIL', 'full_verdict': 'FAIL',
                  'problems': [f'invalid input: {e}'], 'traceback': traceback.format_exc()}
    report['inputs'] = inputs
    report['grader_sha256'] = sha(Path(__file__).read_bytes())
    (a.out / 'REGRADE_V2.json').write_text(json.dumps(report, indent=1, default=str) + '\n')
    print('star_layer', report['star_layer_verdict'], 'full', report['full_verdict'], report['problems'])
    return 0 if report['full_verdict'] == 'PASS' else 2 if report['star_layer_verdict'] == 'PASS' and report['full_verdict'] == 'UNRUN' else 1


if __name__ == '__main__':
    sys.exit(main())
