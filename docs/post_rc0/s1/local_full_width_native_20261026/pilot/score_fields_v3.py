"""Producer admission and field scoring v3 for the HELD local full-width pilot.

Pure consumer layer: launches nothing and reads no movie or image intensities. The numerical field operators, dense ROI,
limits and recipes are those of score_fields_v2 (imported by pinned hash, unchanged). Criteria: SCORER_V3_PLAN.md.
field_metrics_lowlevel is v2's metadata-only calculation and is NOT producer admission; use admit_producer/score_admitted.
"""
from pathlib import Path
import hashlib, json, os, re, sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
V2_SHA256 = 'e0ef769c665dce1368738a327dc5a15efb0280462750709f0db99d164186a03b'  # score_fields_v2.py exactly as retained
_V2_PIN_FILE = HERE / 'score_fields_v2.py'

MANIFEST_SHA256 = '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
FIXED_ROI = [12, 84, 12, 116]
FIXED_RECIPE = (5, 96, 128)
PLACEHOLDER_BINARY = '<PINNED_LINUX_BINARY>'
DRAFT_ROOT = '/tmp/motioncorr-local-full-width-native-20261026/evidence'
FLAG = '--experimental_local_full_width_weight'
RECEIPT_SCHEMA = 'local-full-width-run-receipt-v3'
CONTROLLED_PREFIXES = ('MC_', 'OMP_', 'GOMP_', 'KMP_', 'OPENBLAS_', 'MKL_', 'BLIS_', 'VECLIB_', 'NUMEXPR_')
WITNESS_MARKER = 'EXPERIMENTAL local full-width weight'
WITNESS_LINE = ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22'
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class AdmissionError(ValueError):
    def __init__(self, code, message=''):
        super().__init__(code + (': ' + message if message else ''))
        self.code = code


def _fail(code, message=''):
    raise AdmissionError(code, message)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _strict_json(text, what):
    def bad(c):
        raise ValueError('non-finite constant ' + c)
    try:
        return json.loads(text, parse_constant=bad)
    except ValueError as e:
        _fail('NONFINITE' if 'non-finite' in str(e) else 'SCHEMA', what + ': ' + str(e))


def _is_int(v):
    return type(v) is int


def _hex(v):
    return isinstance(v, str) and HEX64.match(v) is not None


# ---- numerical consumers: v2 unchanged, imported by pinned hash --------------------------------------------------------
def _import_v2(expected_sha256):
    if sha(_V2_PIN_FILE) != expected_sha256:
        _fail('TOOL_PIN', 'score_fields_v2.py differs from the pinned hash')
    sys.path.insert(0, str(HERE))
    import score_fields_v2 as v2
    if Path(v2.__file__).resolve() != _V2_PIN_FILE:
        _fail('TOOL_PIN', 'foreign score_fields_v2 module')
    return v2


V2 = _import_v2(V2_SHA256)
field_metrics_lowlevel = V2.field_metrics  # metadata-only; never producer admission
LIMITS = V2.LIMITS


# ---- tool pins ----------------------------------------------------------------------------------------------------------
def verify_tool_pins(admission, roots):
    """Every admission tool pin must match the bytes at the caller-supplied root."""
    for entry in admission['tools']:
        root = roots.get(entry['root'])
        if root is None:
            _fail('TOOL_PIN', 'no root supplied for ' + entry['root'])
        p = Path(root) / entry['path']
        if not p.is_file() or not _hex(entry['sha256']) or sha(p) != entry['sha256']:
            _fail('TOOL_PIN', entry['root'] + ':' + entry['path'])
    return True


# ---- expected-row resolution -------------------------------------------------------------------------------------------
def _reroot(value, evidence_root):
    if isinstance(value, str) and value.startswith(DRAFT_ROOT):
        return str(evidence_root) + value[len(DRAFT_ROOT):]
    return value


def witness_expected(arm, patch_grid):
    return 9 if (arm == 'ON' and list(patch_grid) == [3, 3]) else 0


def resolve_expected_row(commands, admission, case, arm, evidence_root, binary_path, binary_sha256):
    """Resolve one draft command row for an explicitly supplied binary; the draft placeholder is never admissible itself."""
    if not isinstance(binary_path, str) or not binary_path.startswith('/') or '<' in binary_path:
        _fail('PLACEHOLDER', 'binary path must be an explicit absolute path')
    if not _hex(binary_sha256):
        _fail('BINARY', 'binary sha256 must be 64 lowercase hex')
    rows = [r for r in commands if r.get('case') == case and r.get('arm') == arm]
    if len(rows) != 1:
        _fail('CASE', 'expected exactly one draft row for %r/%r' % (case, arm))
    row = rows[0]
    if row['argv'][0] != PLACEHOLDER_BINARY or row.get('status') != 'UNRUN_HELD':
        _fail('PLACEHOLDER', 'draft row is not an unresolved HELD draft')
    arows = [r for r in admission['rows'] if r['case'] == case]
    if len(arows) != 1:
        _fail('CASE', 'case absent from the admission rows')
    grid = arows[0]['patch_grid']
    count = witness_expected(arm, grid)
    if row['expected_local_weight_witness_lines'] != count:
        _fail('WITNESS', 'draft witness count disagrees with arm and patch grid')
    root = str(evidence_root)
    return {
        'case': case, 'arm': arm, 'binary_path': binary_path, 'binary_sha256': binary_sha256,
        'argv': [binary_path] + [_reroot(a, root) for a in row['argv'][1:]],
        'cwd': _reroot(row['cwd'], root),
        'environment': {k: _reroot(v, root) for k, v in row['environment'].items()},
        'input_files': list(row['input_files']),
        'patch_grid': list(grid), 'expected_witness_lines': count,
        'expected_output_names': sorted(k[len('output/'):] for k in arows[0]['baseline_files'] if k.startswith('output/')),
    }


# ---- admission ---------------------------------------------------------------------------------------------------------
def _walk_output(out):
    if out.is_symlink() or not out.is_dir():
        _fail('INVENTORY', 'output is not a real directory')
    found = {}
    for dirpath, dirnames, filenames in os.walk(out, followlinks=False):
        for name in list(dirnames) + filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                _fail('INVENTORY', 'symlink under output: ' + name)
        for name in filenames:
            p = Path(dirpath) / name
            if not p.is_file():
                _fail('INVENTORY', 'special file under output: ' + name)
            found[p.relative_to(out).as_posix()] = p
    return found


def _bound_file(run_dir, name, pin, code):
    p = run_dir / name
    if p.is_symlink() or not p.is_file():
        _fail(code, name + ' missing')
    if not (isinstance(pin, dict) and _is_int(pin.get('bytes')) and _hex(pin.get('sha256'))):
        _fail('SCHEMA', name + ' receipt pin malformed')
    data = p.read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        _fail(code, name + ' differs from the receipt')
    return data


def admit_producer(run_dir, expected, admission, evidence_root):
    """Bind receipt, argv, env, cwd, inputs, complete publication, runtime/stdout bytes and the log witness to `expected`."""
    d = Path(run_dir)
    case, arm = expected['case'], expected['arm']
    if any(isinstance(a, str) and a.startswith('<') and a.endswith('>') for a in expected['argv']) or not _hex(expected.get('binary_sha256')):
        _fail('PLACEHOLDER', 'expected row is not resolved')
    if case not in admission['case_order']:
        _fail('CASE', 'case not admitted')
    if arm not in ('OFF', 'ON'):
        _fail('ARM', 'expected arm invalid')
    if d.resolve() != (Path(evidence_root) / case / arm).resolve():
        _fail('RUN_DIR', 'run directory is not evidence_root/case/arm')
    rp = d / 'RUN.json'
    if rp.is_symlink() or not rp.is_file():
        _fail('SCHEMA', 'RUN.json missing')
    r = _strict_json(rp.read_text(), 'RUN.json')
    if not isinstance(r, dict) or r.get('schema') != RECEIPT_SCHEMA:
        _fail('SCHEMA', 'receipt schema')
    if r.get('case') != case:
        _fail('CASE', 'receipt case %r' % (r.get('case'),))
    if r.get('arm') != arm:  # missing arm is None, which also fails
        _fail('ARM', 'receipt arm %r, expected %r' % (r.get('arm'), arm))
    if not _is_int(r.get('exit')) or r['exit'] != 0:
        _fail('EXIT', 'producer exit %r' % (r.get('exit'),))
    if r.get('run_dir') != str(d.resolve()):
        _fail('RUN_DIR', 'receipt run_dir differs')
    argv = r.get('argv')
    if not (isinstance(argv, list) and all(isinstance(a, str) for a in argv)):
        _fail('SCHEMA', 'argv type')
    if argv.count(FLAG) != (1 if arm == 'ON' else 0):
        _fail('FLAG_COUNT', '%s occurs %d times for %s' % (FLAG, argv.count(FLAG), arm))
    if r.get('binary_sha256') != expected['binary_sha256'] or not _hex(r.get('binary_sha256')):
        _fail('BINARY', 'binary sha256')
    if argv != expected['argv']:
        _fail('ARGV', 'argv differs from the resolved row')
    if r.get('cwd') != expected['cwd'] or Path(expected['cwd']).resolve() != (d / 'input').resolve():
        _fail('CWD', 'cwd differs from run_dir/input row value')
    inp = d / 'input'
    if inp.is_symlink() or not inp.is_dir():
        _fail('INPUT', 'input directory missing')
    names = sorted(p.name for p in inp.iterdir())
    if names != sorted(expected['input_files']):
        _fail('INPUT', 'input directory must hold exactly %s, found %s' % (sorted(expected['input_files']), names))
    for n in names:
        p = inp / n
        pin = admission['fixture_files'].get(n)
        if p.is_symlink() or not p.is_file() or pin is None or p.stat().st_size != pin['bytes'] or sha(p) != pin['sha256']:
            _fail('INPUT', n + ' differs from the fixture pin')
    env = r.get('environment')
    if env != expected['environment']:
        _fail('ENV', 'environment differs from the declared row')
    observed = r.get('controlled_environment_observed')
    want = {k: v for k, v in expected['environment'].items() if k.startswith(CONTROLLED_PREFIXES)}
    if observed != want:
        _fail('ENV_OBSERVED', 'controlled child environment %r differs from %r' % (observed, want))
    pub = r.get('publication')
    if not isinstance(pub, dict) or not all(isinstance(k, str) for k in pub):
        _fail('SCHEMA', 'publication type')
    for k in pub:
        if k.startswith('/') or '..' in Path(k).parts:
            _fail('INVENTORY', 'publication path escapes output: ' + k)
    found = _walk_output(d / 'output')
    if set(pub) != set(found):
        _fail('INVENTORY', 'receipt differs from the output tree: only-receipt %s, only-disk %s' % (sorted(set(pub) - set(found)), sorted(set(found) - set(pub))))
    if sorted(pub) != expected['expected_output_names']:
        _fail('INVENTORY', 'output names differ from the baseline names of the case')
    for rel in sorted(pub):
        _bound_file(d / 'output', rel, pub[rel], 'PUBLICATION_HASH')
    rt = _bound_file(d, 'runtime.json', r.get('runtime'), 'RUNTIME')
    model = _strict_json(rt.decode('utf-8'), 'runtime.json')
    import numpy as np
    try:
        g = np.asarray(model['global'], dtype=float); cx = np.asarray(model['coeff_x'], dtype=float); cy = np.asarray(model['coeff_y'], dtype=float)
    except (KeyError, TypeError, ValueError):
        _fail('RUNTIME', 'runtime model malformed')
    if type(model.get('local_enabled')) is not bool or g.shape != (FIXED_RECIPE[0], 2) or cx.shape != (18,) or cy.shape != (18,):
        _fail('RUNTIME', 'runtime geometry')
    if not all(np.isfinite(a).all() for a in (g, cx, cy)):
        _fail('NONFINITE', 'runtime model')
    _bound_file(d, 'stdout.log', r.get('stdout'), 'STDOUT')
    # log witness (L1): written to output/<case>.log by the per-movie log stream, not to stdout
    try:
        text = (d / 'output' / (case + '.log')).read_bytes().decode('utf-8')
    except UnicodeDecodeError:
        _fail('LOG_CASE', 'log is not utf-8')
    lines = text.split('\n')
    if lines[0] != 'Working on %s.mrcs with 2 thread(s).' % case:
        _fail('LOG_CASE', 'log does not belong to this case: %r' % lines[0][:80])
    marked = [ln for ln in lines if WITNESS_MARKER in ln]
    for ln in marked:
        if ln != WITNESS_LINE:
            _fail('WITNESS', 'malformed witness line %r' % ln)
    if len(marked) != expected['expected_witness_lines'] or expected['expected_witness_lines'] != witness_expected(arm, expected['patch_grid']):
        _fail('WITNESS', '%d witness lines, expected %d for %s %s' % (len(marked), witness_expected(arm, expected['patch_grid']), arm, expected['patch_grid']))
    return {'receipt': r, 'case': case, 'arm': arm, 'witness_lines': len(marked)}


# ---- scoring -----------------------------------------------------------------------------------------------------------
def _star_movie_stem(star_path):
    m = re.search(r'^_rlnMicrographMovieName\s+(\S+)\s*$', Path(star_path).read_text(), re.M)
    return None if m is None else Path(m.group(1)).stem


def field_metrics_bound(case, runtime_path, star_path, truth_path, fixture_dir):
    """Field metrics bound to the pinned manifest, fixed ROI and one case. Still metadata-only (no producer admission)."""
    fx = Path(fixture_dir)
    if sha(fx / 'MANIFEST.json') != MANIFEST_SHA256:
        _fail('MANIFEST', 'manifest sha256 differs from the pin')
    manifest = json.loads((fx / 'MANIFEST.json').read_text())
    if case not in manifest['cases']:
        _fail('CASE', 'case not in manifest')
    meta = manifest['cases'][case]
    r = meta['recipe']
    if list(meta['roi']) != FIXED_ROI:
        _fail('ROI', 'ROI %r is not the fixed %r' % (meta['roi'], FIXED_ROI))
    if (r['frames'], r['ny'], r['nx']) != FIXED_RECIPE:
        _fail('ROI', 'recipe geometry')
    tname = case + '_field.npy'
    if Path(truth_path).name != tname:
        _fail('TRUTH', 'truth file %r does not belong to case %r' % (Path(truth_path).name, case))
    if Path(star_path).name != case + '.star':
        _fail('STAR_CASE', 'STAR file name does not belong to the case')
    if _star_movie_stem(star_path) != case:
        _fail('STAR_CASE', 'STAR movie name %r is not %r' % (_star_movie_stem(star_path), case))
    out = V2.field_metrics(runtime_path, star_path, truth_path, meta, meta['files'][tname])
    out['binding'] = {'case': case, 'manifest_sha256': MANIFEST_SHA256, 'roi': FIXED_ROI}
    return out


def score_admitted(run_dir, expected, admission, evidence_root, fixture_dir):
    """Admission first; scoring paths come only from the admitted run directory."""
    adm = admit_producer(run_dir, expected, admission, evidence_root)
    d = Path(run_dir)
    case = expected['case']
    m = field_metrics_bound(case, d / 'runtime.json', d / 'output' / (case + '.star'), Path(fixture_dir) / (case + '_field.npy'), fixture_dir)
    m['admission'] = {'arm': adm['arm'], 'witness_lines': adm['witness_lines']}
    return m


def on_launch_permitted(off_compatibility, source_identity):
    """OFF compatibility and source identity must both be PASS before any ON producer is launched."""
    return off_compatibility == 'PASS' and source_identity == 'PASS'
