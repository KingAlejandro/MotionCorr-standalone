"""Spectrum-level shifter closure (pre-registered): iter2-enter-fft_f vs initial_f * exp(-2pi i(kx s_x/42 + ky s_y/32)),
s = iter1-applied-deltas (== iter2-enter-shifts), ky = y>16 ? y-32 : y. No FFT, no J, no truth.
Gate (correct convention): max over bins of |diff| <= 4 * 2^-24 * |initial| + 1e-30. Mutants (sign flip, axis swap, ky16->-16)
reported; sign/swap expected to fail by orders of magnitude; ky16 mutant is expected to be visible here because the
initial spectra are unweighted (y16 row is not suppressed at this stage).
"""
import os, json, numpy as np
CAP = "/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1/evidence/runs/ON/capture"
def cp(p):
    a = np.fromfile(p, dtype="<f4").reshape(32, 22, 2); return a[..., 0].astype(np.float64) + 1j * a[..., 1]
kx = np.arange(22.0)[None, :]
def ky_of(y16): return np.array([y if y < 16 else (y16 if y == 16 else y - 32) for y in range(32)], float)[:, None]
out = {}
for patch in ("patch-62-47", "patch-62-79"):
    P = os.path.join(CAP, patch); s = np.fromfile(P + "/iter1-applied-deltas.bin", dtype="<f8").reshape(5, 2); r = {}
    for name, sg, swap, y16 in (("correct", -1, False, 16), ("sign_flip", +1, False, 16), ("axis_swap", -1, True, 16), ("ky16_negative", -1, False, -16)):
        worst_ratio = 0.0; worst_abs = 0.0
        for f in range(5):
            F0 = cp(f"{P}/initial-frame{f}-fft.bin"); E = cp(f"{P}/iter2-frame{f}-enter-fft.bin")
            sx, sy = (s[f, 1], s[f, 0]) if swap else (s[f, 0], s[f, 1])
            pred = F0 * np.exp(sg * 2j * np.pi * (kx * sx / 42 + ky_of(y16) * sy / 32))
            d = np.abs(pred - E); worst_abs = max(worst_abs, float(d.max()))
            worst_ratio = max(worst_ratio, float((d / (4 * 2.0**-24 * np.abs(F0) + 1e-30)).max()))
        r[name] = {"max_abs_diff": worst_abs, "max_ratio_to_gate": worst_ratio, "within_gate": bool(worst_ratio <= 1.0)}
    out[patch] = r
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_opus_shifter_v1_result.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
