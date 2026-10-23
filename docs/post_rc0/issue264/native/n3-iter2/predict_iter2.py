# SPDX-License-Identifier: GPL-2.0-or-later
"""N3 iteration 2 predictions (review round 2, F5). The iteration-1 files stay frozen.

Reuses the frozen iteration-1 guard emulation (../predict.py, hash-checked) and changes
only A_x and A_y: finite-pair total 3.5 instead of 3.3, so the candidate stops
deterministically at frame 10 (35/11 = 3.1818...) instead of tying exactly 3 there.

Analytic controls, all in exact rationals:
  margin       the running maximum at every evaluated frame of every case and algorithm
               is at least MARGIN (relative) away from the 3 px threshold;
  perturbation scaling all 36 coefficients by 1 +/- 1e-9, or flipping the sign pattern
               of a 1e-9 relative perturbation per coefficient, changes no decision and no
               stopping frame, and moves each value by at most 1e-8 relative;
  negative     the same two checks must FAIL on the iteration-1 A_x/A_y candidate rows
               (frame 10 is exactly 3, and +1e-12 moves the stop from frame 11 to 10).
usage: predict_iter2.py --out predictions_iter2.json
"""
import argparse, hashlib, importlib.util, json, pathlib
from fractions import Fraction as F

HERE = pathlib.Path(__file__).resolve().parent
V1_SCRIPT = HERE.parent / 'predict.py'
V1_JSON = HERE.parent / 'predictions.json'
v1_record = json.loads(V1_JSON.read_text())
assert hashlib.sha256(V1_SCRIPT.read_bytes()).hexdigest() == v1_record['script_sha256'], 'frozen predict.py changed'
spec = importlib.util.spec_from_file_location('predict_v1', V1_SCRIPT)
v1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v1)

THRESHOLD, MARGIN, EPS = F(3), F(5, 1000), F(1, 10**9)
NX, NY, NF, H, V, Z = v1.NX, v1.NY, v1.NF, v1.H, v1.V, v1.Z
a_A = F(35, 10) / (Z * H * (2 - H))
a_Ay = F(35, 10) / (Z * V * (2 - V))
CASES = dict(v1.N3_CASES)
CASES['A_x_legacy_false_accept'] = (v1.coeffs(x=a_A, xx=-a_A), v1.coeffs())
CASES['A_y_legacy_false_accept'] = (v1.coeffs(), v1.coeffs(y=a_Ay, yy=-a_Ay))
CHANGED = ('A_x_legacy_false_accept', 'A_y_legacy_false_accept')
ALGORITHMS = ('legacy', 'finite', 'uncentred')


def trace(algorithm, cx, cy):
    """Running maximum per evaluated frame, stopping frame and returned value (strict > 3)."""
    running, largest = [], F(0)
    for z in range(NF):
        largest = max(largest, v1.frame_max(algorithm, cx, cy, NX, NY, z))
        running.append(largest)
        if largest > THRESHOLD:
            break
    return running, len(running) - 1, largest


def margin(running):
    return min(abs(v - THRESHOLD) / THRESHOLD for v in running)


def perturbed(cx, cy, pattern):
    if pattern in ('up', 'down'):
        s = 1 + EPS if pattern == 'up' else 1 - EPS
        return [c * s for c in cx], [c * s for c in cy]
    signs = [1 if (i * 7 + (pattern == 'alt_b')) % 3 else -1 for i in range(36)]
    both = [c * (1 + signs[i] * EPS) for i, c in enumerate(cx + cy)]
    return both[:18], both[18:]


def stable(algorithm, cx, cy):
    _, stop, value = trace(algorithm, cx, cy)
    for pattern in ('up', 'down', 'alt_a', 'alt_b'):
        _, s, v = trace(algorithm, *perturbed(cx, cy, pattern))
        if s != stop or (v > THRESHOLD) != (value > THRESHOLD) or abs(v - value) > F(1, 10**8) * max(value, F(1)):
            return False
    return True


def main(out):
    rows, failures = {}, []
    for name, (cx, cy) in CASES.items():
        row = {'nx': NX, 'ny': NY, 'n_frames': NF, 'changed_from_iteration1': name in CHANGED,
               'coeffX': [str(v) for v in cx], 'coeffY': [str(v) for v in cy],
               'coeffX_float': [float(v) for v in cx], 'coeffY_float': [float(v) for v in cy]}
        for algorithm in ALGORITHMS:
            running, stop, value = trace(algorithm, cx, cy)
            assert value == v1.guard(algorithm, cx, cy, NX, NY, NF), 'trace disagrees with the frozen emulation'
            m, ok = margin(running), stable(algorithm, cx, cy)
            row[algorithm] = {'value': float(value), 'value_rational': str(value), 'reject': value > THRESHOLD,
                              'stop_frame': stop, 'running_max_by_frame': [float(v) for v in running],
                              'min_relative_margin': float(m), 'perturbation_stable': ok}
            if m < MARGIN or not ok:
                failures.append((name, algorithm, float(m), ok))
            if name in CHANGED and algorithm != 'legacy':
                ex = v1.exhaustive_float(cx, cy, NX, NY, NF, algorithm == 'finite')
                assert abs(ex - float(value)) <= 1e-9 * max(1, ex), (name, algorithm, ex)
                row[algorithm]['exhaustive_float64'] = ex
            if name not in CHANGED:
                assert str(value) == v1_record['n3'][name][algorithm]['value_rational'], (name, algorithm)
        rows[name] = row
    # Negative controls: the iteration-1 A rows must be caught by both checks.
    negative = {}
    for name in CHANGED:
        cx, cy = v1.N3_CASES[name]
        running, stop, value = trace('finite', cx, cy)
        bumped = trace('finite', [c * (1 + F(1, 10**12)) for c in cx], [c * (1 + F(1, 10**12)) for c in cy])
        negative[name] = {'iteration1_min_relative_margin': float(margin(running)),
                          'iteration1_perturbation_stable': stable('finite', cx, cy),
                          'iteration1_stop_frame': stop, 'iteration1_value': str(value),
                          'plus_1e-12_stop_frame': bumped[1], 'plus_1e-12_value': float(bumped[2])}
        assert margin(running) < MARGIN and not stable('finite', cx, cy), 'control failed to detect the F5 tie'
        assert stop == 11 and bumped[1] == 10, 'F5 tie not reproduced'
    assert not failures, failures
    result = {'kind': 'N3 iteration 2 frozen independent rational predictions; no MotionCorr execution',
              'script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              'iteration1_predictions_sha256': hashlib.sha256(V1_JSON.read_bytes()).hexdigest(),
              'iteration1_script_sha256': v1_record['script_sha256'],
              'threshold': 'reject when strictly greater than 3 px', 'margin_rule': f'>= {float(MARGIN)} relative at every evaluated frame',
              'perturbation_rule': 'x(1+-1e-9) uniform and two sign patterns: same decision and stop frame, value within 1e-8 relative',
              'n3': rows, 'negative_controls_iteration1': negative}
    out.write_text(json.dumps(result, indent=1) + '\n')
    for name, row in rows.items():
        print(name, {a: (round(row[a]['value'], 6), 'reject' if row[a]['reject'] else 'accept', 'z' + str(row[a]['stop_frame']),
                         round(row[a]['min_relative_margin'], 4)) for a in ALGORITHMS})
    print('negative controls', json.dumps(negative))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, required=True)
    main(ap.parse_args().out)
