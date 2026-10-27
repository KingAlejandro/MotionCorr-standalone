"""Independent witnesses for the future full-width capture-ON job (static checks of the produced files; no native code, no truth).
Mandatory for admission: (1) session schema/mode/selected coordinates, (2) recorded actual weight_x_norm, (3) captured float weight map equal to the frozen
native-order oracle at x_norm 42, (4) the per-patch native log witness (x_norm = 42) for all 9 patches of the 3x3 grid, plus complete coverage of the selected patches.
Any mismatch raises Stop(name); nothing is relaxed after an outcome."""
import json, re
from pathlib import Path
import numpy as np

SELECTED = [[104, 15], [62, 79]]
LOG_WITNESS = ' EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22'
PAYLOAD_LIMIT = 67108864
FRAMES = 5

class Stop(Exception):
    def __init__(self, name, why):
        super().__init__(f'{name}: {why}'); self.name, self.why = name, why

def need(ok, name, why):
    if not ok: raise Stop(name, why)

def _json(path, name):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e: raise Stop(name, f'unreadable {path}: {e}')

def expected_patch_files(n_iter):
    """File names one selected patch writes for n_iter executed iterations (writer order of local_ccf_capture.h; an array is name.bin + name.json)."""
    names = []
    arr = lambda n: names.extend([n + '.bin', n + '.json'])
    names.append('patch.json'); arr('global-shifts')
    for i in range(FRAMES): arr(f'initial-frame{i}-samples'); arr(f'initial-frame{i}-fft')
    arr('weights'); names.append('fft-config.json')
    for k in range(1, n_iter + 1):
        arr(f'iter{k}-enter-shifts'); arr(f'iter{k}-reference')
        for i in range(FRAMES):
            t = f'iter{k}-frame{i}'
            for s in ('enter-fft', 'window-fft', 'sum-of-others', 'raw-product'): arr(f'{t}-{s}')
        for i in range(FRAMES):
            t = f'iter{k}-frame{i}'
            for s in ('weighted-pre-dc', 'weighted-api-consumed', 'c2r-temporary-before', 'c2r-temporary-after', 'weighted-api-after', 'real-map', 'peak3x3'): arr(f'{t}-{s}')
            names.append(f'{t}-peak.json')
        arr(f'iter{k}-applied-deltas'); arr(f'iter{k}-exit-shifts')
        for i in range(FRAMES): arr(f'iter{k}-frame{i}-exit-fft')
        names.append(f'iter{k}-stop.json')
    arr('final-local-shifts'); names.append('alignment-complete.json')
    arr('reported-observations'); arr('interpolated-shifts')
    return names

def check_session(cap):
    """Witness 1."""
    s = _json(cap / 'session.json', 'W1_SESSION')
    need(s.get('schema') == 'local-ccf-capture/2', 'W1_SESSION', f"schema {s.get('schema')!r}, need local-ccf-capture/2")
    need(s.get('capture_mode') == 'local_full_width_pair', 'W1_SESSION', f"capture_mode {s.get('capture_mode')!r}")
    need(s.get('local_full_width_weight') is True, 'W1_SESSION', 'local_full_width_weight not true')
    need(s.get('native_truth_input') is False, 'W1_SESSION', 'truth input not false')
    need(s.get('selected_centres') == SELECTED, 'W1_SESSION', f"selected_centres {s.get('selected_centres')!r}")
    dirs = sorted(p.name for p in cap.iterdir() if p.is_dir())
    need(dirs == sorted(f'patch-{x}-{y}' for x, y in SELECTED), 'W1_SESSION', f'patch directories {dirs}')
    extra = sorted(p.name for p in cap.iterdir() if p.is_file())
    need(extra == ['COMPLETE.json', 'session.json'], 'W1_SESSION', f'top-level files {extra}')
    for x, y in SELECTED:
        pj = _json(cap / f'patch-{x}-{y}' / 'patch.json', 'W1_SESSION')
        need(pj.get('centre') == [x, y] and pj.get('capture_mode') == 'local_full_width_pair' and pj.get('local_full_width_weight') is True, 'W1_SESSION', f'patch.json of {x},{y}: {pj}')
        need(pj.get('extents_xy_halfopen') == {(104, 15): [84, 126, 0, 32], (62, 79): [42, 84, 64, 96]}[(x, y)], 'W1_SESSION', f"extents {pj.get('extents_xy_halfopen')}")
    return {'schema': s['schema'], 'capture_mode': s['capture_mode'], 'selected_centres': s['selected_centres']}

def check_norm(cap):
    """Witness 2."""
    out = {}
    for x, y in SELECTED:
        c = _json(cap / f'patch-{x}-{y}' / 'fft-config.json', 'W2_NORM')
        need(c.get('weight_x_norm') == 42 and c.get('capture_mode') == 'local_full_width_pair' and c.get('weight_nfx_inherited_not_used') == 22, 'W2_NORM', f"{x},{y}: {c.get('weight_x_norm')!r}, {c.get('weight_nfx_inherited_not_used')!r}")
        need(c.get('scaled_B') == 150 and c.get('ccf_shape_yx') == [32, 42] and c.get('half_shape_yx') == [32, 22], 'W2_NORM', f'{x},{y}: geometry/scaled_B differ from the pinned scope')
        out[f'{x},{y}'] = {'weight_x_norm': c['weight_x_norm']}
    return out

def check_weights(cap, oracle42, oracle22):
    """Witness 3: captured float32 weight map equals the frozen native-order oracle at x_norm 42 exactly, and is not the inherited (22) map."""
    out = {}
    need(not np.array_equal(oracle42, oracle22), 'W3_WEIGHTS', 'oracle maps for 42 and 22 coincide (oracle cannot discriminate)')
    for x, y in SELECTED:
        d = cap / f'patch-{x}-{y}'; m = _json(d / 'weights.json', 'W3_WEIGHTS')
        need(m.get('dtype') == '<f4' and m.get('shape') == [32, 22] and m.get('bytes') == 32 * 22 * 4, 'W3_WEIGHTS', f'{x},{y}: metadata {m}')
        try: w = np.fromfile(d / 'weights.bin', dtype='<f4')
        except OSError as e: raise Stop('W3_WEIGHTS', f'unreadable weights.bin {x},{y}: {e}')
        need(w.size == 704, 'W3_WEIGHTS', f'{x},{y}: {w.size} values')
        w = w.reshape(32, 22)
        need(np.array_equal(w, oracle42), 'W3_WEIGHTS', f'{x},{y}: captured weights differ from the x_norm 42 oracle in {int((w != oracle42).sum())} bins')
        need(not np.array_equal(w, oracle22), 'W3_WEIGHTS', f'{x},{y}: captured weights equal the inherited map')
        out[f'{x},{y}'] = {'equals_oracle_x42': True, 'differs_from_inherited_x22_bins': int((w != oracle22).sum())}
    return out

def check_log(text):
    """Witness 4: every one of the 9 patch alignments logs the full-width witness line right after its header; the selected patches are among them."""
    lines = text.splitlines(); hdr = re.compile(r'^Patch \((\d+), (\d+)\): (\d+) / 9, .*Center = \((\d+), (\d+)\)')
    heads = [(i, tuple(map(int, m.group(4, 5)))) for i, l in enumerate(lines) if (m := hdr.match(l))]
    need(len(heads) == 9, 'W4_LOG', f'{len(heads)} patch headers, need 9')
    n_witness = sum(1 for l in lines if 'EXPERIMENTAL local full-width weight' in l)
    need(n_witness == 9, 'W4_LOG', f'{n_witness} witness lines, need 9')
    centres = []
    for i, c in heads:
        nxt = lines[i + 1] if i + 1 < len(lines) else ''
        need(nxt == LOG_WITNESS, 'W4_LOG', f'patch {c}: line after the header is {nxt!r}')
        centres.append(c)
    need(sorted(centres) == sorted((x, y) for x in (20, 62, 104) for y in (15, 47, 79)), 'W4_LOG', f'patch centres {sorted(centres)}')
    need(all(tuple(s) in centres for s in SELECTED), 'W4_LOG', 'selected patch missing from the log')
    return {'witness_lines': n_witness, 'patches': len(heads)}

def check_coverage(cap):
    """All five frames, every actually executed iteration, every selected patch; patch-files.json and COMPLETE.json agree with the directory."""
    out = {}
    comp = _json(cap / 'COMPLETE.json', 'COVERAGE')
    need(comp.get('selected_patches') == 2 and comp.get('frames_per_patch_iteration') == FRAMES and comp.get('payload_limit_bytes') == PAYLOAD_LIMIT and 0 < comp.get('bytes_before_complete', 0) <= PAYLOAD_LIMIT, 'COVERAGE', f'COMPLETE.json {comp}')
    for x, y in SELECTED:
        d = cap / f'patch-{x}-{y}'; ac = _json(d / 'alignment-complete.json', 'COVERAGE')
        n = ac.get('iterations'); need(isinstance(n, int) and 1 <= n <= 5, 'COVERAGE', f'{x},{y}: iterations {n!r}')
        stops = sorted(p.name for p in d.glob('iter*-stop.json')); need(stops == [f'iter{k}-stop.json' for k in range(1, n + 1)], 'COVERAGE', f'{x},{y}: stop files {stops} for {n} iterations')
        exp = expected_patch_files(n); listed = _json(d / 'patch-files.json', 'COVERAGE')['files']
        need(listed == exp, 'COVERAGE', f'{x},{y}: patch-files.json differs from the expected writer sequence ({len(listed)} vs {len(exp)})')
        actual = sorted(p.name for p in d.iterdir())
        need(actual == sorted(exp + ['patch-files.json']), 'COVERAGE', f'{x},{y}: directory differs from the expected file set (extra {sorted(set(actual) - set(exp) - {"patch-files.json"})[:3]}, missing {sorted(set(exp) - set(actual))[:3]})')
        for i in range(FRAMES):
            for k in range(1, n + 1):
                pk = _json(d / f'iter{k}-frame{i}-peak.json', 'COVERAGE'); need(pk.get('iteration') == k and pk.get('frame') == i, 'COVERAGE', f'{x},{y}: peak.json identity {pk.get("iteration")},{pk.get("frame")}')
        out[f'{x},{y}'] = {'executed_iterations': n, 'frames': FRAMES, 'files': len(exp) + 1, 'converged': ac.get('converged')}
    return out

def run_all(cap, log_text, oracle42, oracle22):
    cap = Path(cap)
    return {'W1_session': check_session(cap), 'W2_norm': check_norm(cap), 'W3_weights': check_weights(cap, oracle42, oracle22), 'W4_log': check_log(log_text), 'coverage': check_coverage(cap)}
