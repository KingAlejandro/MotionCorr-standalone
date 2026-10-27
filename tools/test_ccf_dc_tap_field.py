#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Analytic controls for tools/ccf_dc_tap_field.py: coefficient index, power, axis, unit and schema.

The expected field is written out here from the C++ ``ThirdOrderPolynomialModel::getShiftAt`` group
layout (coefficient 3*g+k multiplies z^(k+1) times spatial group g in [1, u, u^2, v, v^2, uv]) and not
taken from the code under test. Conventional-order, wrong-axis and wrong-power mutants must be
rejected by the same check, otherwise the check cannot see them.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

import ccf_dc_tap_field as bridge

NX, NY, F = 96, 64, 5   # anisotropic on purpose: u uses nx, v uses ny
SPATIAL = [lambda u, v: np.ones_like(u), lambda u, v: u, lambda u, v: u * u,
           lambda u, v: v, lambda u, v: v * v, lambda u, v: u * v]


def tap(cx=None, cy=None, glob=None, enabled=True):
    return {
        "global": glob if glob is not None else [[0.0, 0.0]] * F,
        "coeff_x": cx if cx is not None else [0.0] * 18,
        "coeff_y": cy if cy is not None else [0.0] * 18, "local_enabled": enabled}


def analytic(i, axis):
    """Field for a single unit coefficient index i on axis 0 (x) or 1 (y)."""
    yy, xx = np.mgrid[:NY, :NX]
    u, v = xx / NX - 0.5, yy / NY - 0.5
    out = np.zeros((F, NY, NX, 2))
    g, k = divmod(i, 3)
    for z in range(F):
        out[z, :, :, axis] = float(z) ** (k + 1) * SPATIAL[g](u, v)
    return out


def single_cases():
    for axis in (0, 1):
        for i in range(18):
            c = [0.0] * 18
            c[i] = 1.0
            yield i, axis, (tap(cx=c) if axis == 0 else tap(cy=c))


def matches(field_fn):
    """True iff field_fn reproduces every single-coefficient analytic field exactly."""
    for i, axis, t in single_cases():
        got = field_fn(t, NX, NY, F)
        if got.shape != (F, NY, NX, 2) or not np.allclose(got, analytic(i, axis), rtol=0, atol=1e-12):
            return False
    return True


def mutant_conventional_order(t, nx, ny, frames):
    """[1,u,v,u^2,uv,v^2] instead of [1,u,u^2,v,v^2,uv]."""
    yy, xx = np.mgrid[:ny, :nx]
    u, v = xx / nx - 0.5, yy / ny - 0.5
    sp = [np.ones_like(u), u, v, u * u, u * v, v * v]
    out = np.zeros((frames, ny, nx, 2))
    for a, key in enumerate(("coeff_x", "coeff_y")):
        for z in range(frames):
            out[z, :, :, a] = sum(t[key][3 * g + k] * float(z) ** (k + 1) * sp[g] for g in range(6) for k in range(3))
    return out


def mutant_swapped_dims(t, nx, ny, frames):
    """u normalised by ny and v by nx."""
    yy, xx = np.mgrid[:ny, :nx]
    u, v = xx / ny - 0.5, yy / nx - 0.5   # wrong normalisation axes
    out = np.zeros((frames, ny, nx, 2))
    for a, key in enumerate(("coeff_x", "coeff_y")):
        for z in range(frames):
            out[z, :, :, a] = sum(t[key][3 * g + k] * float(z) ** (k + 1) * SPATIAL[g](u, v) for g in range(6) for k in range(3))
    return out


def mutant_power_offset(t, nx, ny, frames):
    """z^k instead of z^(k+1), or frame starting at 1."""
    yy, xx = np.mgrid[:ny, :nx]
    u, v = xx / nx - 0.5, yy / ny - 0.5
    out = np.zeros((frames, ny, nx, 2))
    for a, key in enumerate(("coeff_x", "coeff_y")):
        for z in range(frames):
            out[z, :, :, a] = sum(t[key][3 * g + k] * float(z + 1) ** (k + 1) * SPATIAL[g](u, v) for g in range(6) for k in range(3))
    return out


def mutant_axes_swapped(t, nx, ny, frames):
    return bridge.dense_field(t, nx, ny, frames)[..., ::-1]


def mutant_xy_coeff_swapped(t, nx, ny, frames):
    return bridge.dense_field(dict(t, coeff_x=t["coeff_y"], coeff_y=t["coeff_x"]), nx, ny, frames)


class TapFieldTest(unittest.TestCase):
    def test_bridge_matches_every_coefficient_index_and_power(self):
        self.assertTrue(matches(lambda t, nx, ny, f: bridge.dense_field(bridge.load_tap(self.write(t), f), nx, ny, f)))

    def test_mutants_are_rejected(self):
        for name, fn in [("conventional spatial order", mutant_conventional_order),
                         ("u/v normalised by the wrong axis", mutant_swapped_dims),
                         ("time index offset", mutant_power_offset),
                         ("x/y components swapped", mutant_axes_swapped),
                         ("x/y coefficient sets swapped", mutant_xy_coeff_swapped)]:
            self.assertFalse(matches(fn), name + " was not detected by the analytic check")

    def test_zero_global_and_frame_zero(self):
        z = bridge.dense_field(tap(), NX, NY, F)
        self.assertTrue((z == 0).all())
        g = [[0.0, 0.0], [1.5, -2.0], [3.0, -4.0], [4.5, -6.0], [6.0, -8.0]]
        f = bridge.dense_field(tap(glob=g), NX, NY, F)
        for i in range(F):
            self.assertTrue((f[i, :, :, 0] == g[i][0]).all() and (f[i, :, :, 1] == g[i][1]).all())
        c = [0.0] * 18
        c[0], c[1], c[2] = 1.0, 1.0, 1.0   # z + z^2 + z^3 at u,v-independent group
        f0 = bridge.dense_field(tap(cx=c), NX, NY, F)
        self.assertTrue((f0[0] == 0).all(), "frame 0 must carry no local displacement")
        self.assertEqual(f0[2, 0, 0, 0], 2 + 4 + 8)

    def test_units_are_pixels_unscaled(self):
        c = [0.0] * 18
        c[0] = 0.885   # an Angstrom-looking value must stay pixels
        f = bridge.dense_field(tap(cx=c), NX, NY, F)
        self.assertEqual(f[3, 5, 7, 0], 0.885 * 3)

    def test_local_disabled_never_publishes_a_local_field(self):
        c = [0.0] * 18
        c[4] = 0.25
        with self.assertRaises(bridge.TapError):
            bridge.load_tap(self.write(tap(cx=c, enabled=False)), F)
        g = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]]
        t = bridge.load_tap(self.write(tap(glob=g, enabled=False)), F)
        f = bridge.dense_field(t, NX, NY, F)
        self.assertTrue((f[3] == 3.0).all())

    def test_schema_rejections(self):
        good = tap()
        nan = float("nan")
        cases = {
            "placeholder": {"status": "incomplete"},
            "missing key": {k: v for k, v in good.items() if k != "coeff_y"},
            "extra key": dict(good, status="x"),
            "short global": dict(good, **{"global": [[0.0, 0.0]] * (F - 1)}),
            "ragged global": dict(good, **{"global": [[0.0, 0.0]] * (F - 1) + [[0.0]]}),
            "short coeff": dict(good, coeff_x=[0.0] * 17),
            "long coeff": dict(good, coeff_y=[0.0] * 19),
            "nan coeff": dict(good, coeff_x=[nan] + [0.0] * 17),
            "inf global": dict(good, **{"global": [[0.0, 0.0]] * (F - 1) + [[math.inf, 0.0]]}),
            "string value": dict(good, coeff_x=["1"] + [0.0] * 17),
            "bool value": dict(good, coeff_x=[True] + [0.0] * 17),
            "enabled not bool": dict(good, local_enabled=1),
        }
        for name, t in cases.items():
            with self.assertRaises(bridge.TapError, msg=name):
                bridge.load_tap(self.write(t), F)
        with self.assertRaises(bridge.TapError):
            bridge.load_tap(Path(tempfile.gettempdir()) / "no-such-tap-xyz.json", F)
        with self.assertRaises(bridge.TapError):
            bridge.load_tap(self.write(good), F + 1)   # frames come from the pinned config, never the tap

    def write(self, t):
        d = Path(self._tmp.name) / f"t{len(list(Path(self._tmp.name).iterdir()))}.json"
        d.write_text(json.dumps(t))
        return d

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)


if __name__ == "__main__":
    unittest.main()
