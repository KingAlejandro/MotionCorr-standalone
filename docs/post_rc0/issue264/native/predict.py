# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen #264 native predictions from an independent rational guard emulation.

No MotionCorr code is imported or executed. Three guard algorithms are emulated
exactly in Fractions, each with the per-frame early exit at a strict > 3 px:
  legacy     - base 36913740: corners (0,0),(1,0),(0,1),(1,1) plus one forward step;
  finite     - candidate: maximum over every in-image adjacent pixel pair at ix/n-0.5,
               evaluated at the corners of each valid pair rectangle (exact for a
               spatially quadratic field) and cross-checked against an exhaustive
               float64 scan of all pairs for every N3 case;
  uncentred  - deliberate mutant: the candidate with ix/n (no -0.5).
Coefficient layout (STAR/model, 18 per component): groups 1,x,x^2,y,y^2,xy, each
multiplied by z, z^2, z^3 (z = 0-based frame index).

usage: predict.py --out predictions.json [--rc0-stars DIR]
"""
import argparse, hashlib, json, pathlib, re
from fractions import Fraction as F

import numpy as np

THRESHOLD = F(3)


def field(c, z, x, y):
    z, z2, z3 = F(z), F(z) ** 2, F(z) ** 3
    t = [c[3 * k] * z + c[3 * k + 1] * z2 + c[3 * k + 2] * z3 for k in range(6)]
    return t[0] + t[1] * x + t[2] * x * x + t[3] * y + t[4] * y * y + t[5] * x * y


def frame_max(algorithm, cx, cy, nx, ny, z):
    hx, hy = F(1, nx), F(1, ny)
    pairs = []
    if algorithm == 'legacy':
        for x0, y0 in ((0, 0), (1, 0), (0, 1), (1, 1)):
            pairs += [((F(x0), F(y0)), (F(x0) + hx, F(y0))), ((F(x0), F(y0)), (F(x0), F(y0) + hy))]
    else:
        off = F(1, 2) if algorithm == 'finite' else F(0)
        for axis in (0, 1):
            if (nx, ny)[axis] < 2:
                continue
            last_x, last_y = nx - 1 - (axis == 0), ny - 1 - (axis == 1)
            for ix in (0, last_x):
                for iy in (0, last_y):
                    a = (F(ix, nx) - off, F(iy, ny) - off)
                    b = (F(ix + (axis == 0), nx) - off, F(iy + (axis == 1), ny) - off)
                    pairs.append((a, b))
    return max(max(abs(field(cx, z, *b) - field(cx, z, *a)), abs(field(cy, z, *b) - field(cy, z, *a)))
               for a, b in pairs)


def guard(algorithm, cx, cy, nx, ny, n_frames):
    largest = F(0)
    for z in range(n_frames):
        largest = max(largest, frame_max(algorithm, cx, cy, nx, ny, z))
        if largest > THRESHOLD:
            break
    return largest


def exhaustive_float(cx, cy, nx, ny, n_frames, centred=True):
    off = 0.5 if centred else 0.0
    x = np.arange(nx) / nx - off
    y = (np.arange(ny) / ny - off)[:, None]
    worst = 0.0
    for z in range(n_frames):
        for c in (cx, cy):
            t = [float(c[3 * k]) * z + float(c[3 * k + 1]) * z * z + float(c[3 * k + 2]) * z ** 3 for k in range(6)]
            f = t[0] + t[1] * x + t[2] * x * x + t[3] * y + t[4] * y * y + t[5] * x * y
            if nx > 1: worst = max(worst, float(np.abs(np.diff(f, axis=1)).max()))
            if ny > 1: worst = max(worst, float(np.abs(np.diff(f, axis=0)).max()))
        if worst > 3:
            break
    return worst


def coeffs(**terms):
    """terms: name -> value for the z-linear coefficient of 1,x,xx,y,yy,xy."""
    names = ['c', 'x', 'xx', 'y', 'yy', 'xy']
    out = [F(0)] * 18
    for name, value in terms.items():
        out[3 * names.index(name)] = F(value)
    return out


# N3 fixture: km_local_nonsquare (768 x 512, 12 frames); alignment grid unbinned.
NX, NY, NF = 768, 512, 12
H, V = F(1, NX), F(1, NY)
Z = NF - 1  # linear-in-z fields peak at the last frame
# Coefficients chosen so the finite-pair total is the stated target; see FROZEN.md.
a_A = F(330, 100) / (Z * H * (2 - H))        # x - x^2, finite 3.30, legacy ~1.65
a_B = F(270, 100) / (Z * H * (3 - 6 * H))    # x + 2x^2, finite 2.70, legacy ~4.5
a_Ay = F(330, 100) / (Z * V * (2 - V))
a_By = F(270, 100) / (Z * V * (3 - 6 * V))
c_E = F(297, 100) * 2 * NY / Z               # xy, finite 2.97 (vertical pairs), legacy ~5.94
N3_CASES = {
    'A_x_legacy_false_accept': (coeffs(x=a_A, xx=-a_A), coeffs()),
    'B_x_legacy_false_reject': (coeffs(x=a_B, xx=2 * a_B), coeffs()),
    'A_y_legacy_false_accept': (coeffs(), coeffs(y=a_Ay, yy=-a_Ay)),
    'B_y_legacy_false_reject': (coeffs(), coeffs(y=a_By, yy=2 * a_By)),
    'E_xy_nonsquare_near_threshold': (coeffs(xy=c_E), coeffs()),
    'F_mild_both_accept': (coeffs(c=F(2), x=F(3, 2)), coeffs(c=F(-1), y=F(4, 5))),
    'G_large_both_reject': (coeffs(x=F(30) / (Z * H)), coeffs()),
}


def n3_predictions():
    rows = {}
    for name, (cx, cy) in N3_CASES.items():
        row = {'nx': NX, 'ny': NY, 'n_frames': NF,
               'coeffX': [str(v) for v in cx], 'coeffY': [str(v) for v in cy],
               'coeffX_float': [float(v) for v in cx], 'coeffY_float': [float(v) for v in cy]}
        for algorithm in ('legacy', 'finite', 'uncentred'):
            value = guard(algorithm, cx, cy, NX, NY, NF)
            row[algorithm] = {'value': float(value), 'value_rational': str(value), 'reject': value > THRESHOLD}
        for centred, algorithm in ((True, 'finite'), (False, 'uncentred')):
            ex = exhaustive_float(cx, cy, NX, NY, NF, centred)
            assert abs(ex - row[algorithm]['value']) <= 1e-9 * max(1, ex), (name, algorithm, ex, row[algorithm])
            row[algorithm]['exhaustive_float64'] = ex
        rows[name] = row
    return rows


def read_star_model(path):
    text = pathlib.Path(path).read_text()
    nx = int(re.search(r'_rlnImageSizeX\s+(\d+)', text).group(1))
    ny = int(re.search(r'_rlnImageSizeY\s+(\d+)', text).group(1))
    nf = int(re.search(r'_rlnImageSizeZ\s+(\d+)', text).group(1))
    block = text.split('data_local_motion_model', 1)
    if len(block) < 2:
        return nx, ny, nf, None
    vals = {}
    for line in block[1].splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            vals[int(parts[0])] = F(parts[1])
    assert sorted(vals) == list(range(36)), path
    return nx, ny, nf, ([vals[i] for i in range(18)], [vals[i] for i in range(18, 36)])


def tutorial_predictions(star_dir):
    rows = {}
    for star in sorted(pathlib.Path(star_dir).glob('*_frameImage.star')):
        nx, ny, nf, model = read_star_model(star)
        row = {'star_sha256': hashlib.sha256(star.read_bytes()).hexdigest(), 'nx': nx, 'ny': ny, 'n_frames': nf}
        if model is None:
            row['model'] = None
        else:
            for algorithm in ('legacy', 'finite'):
                value = guard(algorithm, *model, nx, ny, nf)
                row[algorithm] = {'value': float(value), 'reject': value > THRESHOLD}
        rows[star.name] = row
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=pathlib.Path, required=True)
    ap.add_argument('--rc0-stars', type=pathlib.Path)
    args = ap.parse_args()
    result = {'kind': 'frozen independent rational guard predictions; no MotionCorr execution',
              'script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              'threshold': 'reject when strictly greater than 3 px', 'n3': n3_predictions()}
    if args.rc0_stars:
        result['tutorial_rc0_L_s0'] = tutorial_predictions(args.rc0_stars)
    args.out.write_text(json.dumps(result, indent=1) + '\n')
    for name, row in result['n3'].items():
        print(name, {a: (round(row[a]['value'], 6), 'reject' if row[a]['reject'] else 'accept') for a in ('legacy', 'finite', 'uncentred')})
    for name, row in result.get('tutorial_rc0_L_s0', {}).items():
        print(name, {a: (round(row[a]['value'], 4), row[a]['reject']) for a in ('legacy', 'finite')} if row.get('legacy') else 'no model')
