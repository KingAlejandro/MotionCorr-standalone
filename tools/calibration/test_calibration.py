#!/usr/bin/env python3
"""Controls for the issue #60 calibration tooling (ADR section 7).

These are not gate tests. They establish that the measuring instrument reads
zero when nothing changed, and reads the closed-form answer when the answer is
known analytically. Nothing in the calibration report may be believed until
these pass.

Run:  python3 tools/calibration/test_calibration.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import diagnostics as dg          # noqa: E402
from tools.calibration import mrcio, perturbations as pt  # noqa: E402
from tools.calibration.prespecification import (          # noqa: E402
    PIXEL_SIZE_A,
    delta_b_for_sigma_px,
)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def make_micrograph(ny: int = 512, nx: int = 512, seed: int = 20260925) -> np.ndarray:
    """A synthetic micrograph with a realistic falling power spectrum plus noise."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((ny, nx))
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    k = np.sqrt(fy * fy + fx * fx)
    # 1/f-ish structure with a soft high-frequency roll-off, plus flat noise.
    env = np.exp(-30.0 * k * k) / (k + 0.02)
    signal = np.fft.irfft2(np.fft.rfft2(white) * env, s=(ny, nx))
    signal = (signal - signal.mean()) / signal.std()
    noise = rng.standard_normal((ny, nx)) * 0.15
    return signal + noise


# ---------------------------------------------------------------------------

def test_null_control() -> None:
    print("\nControl 1: null -- reference against itself must read exactly zero")
    img = make_micrograph()
    m = dg.all_image_diagnostics(img, img.copy())
    check("image_rmse == 0", m["image_rmse"] == 0.0, f"{m['image_rmse']:.3e}")
    check("image_relative_rmse == 0", m["image_relative_rmse"] == 0.0)
    check("image_max_abs_error == 0", m["image_max_abs_error"] == 0.0)
    check("rel_rmse_high ~ 0", m["rel_rmse_high"] < 1e-12, f"{m['rel_rmse_high']:.3e}")
    check("rel_rmse_border ~ 0", m["rel_rmse_border"] < 1e-12, f"{m['rel_rmse_border']:.3e}")
    check("std_shift_px ~ 0", m["std_shift_px"] < 1e-6, f"{m['std_shift_px']:.3e}")
    check("std_scale_dev ~ 0", m["std_scale_dev"] < 1e-9, f"{m['std_scale_dev']:.3e}")
    check("std_delta_b_a2 ~ 0", abs(m["std_delta_b_a2"]) < 1e-6, f"{m['std_delta_b_a2']:.3e}")
    check("std_eps_incoherent ~ 0", m["std_eps_incoherent"] < 1e-9, f"{m['std_eps_incoherent']:.3e}")
    check("hf_signal_retention ~ 1", abs(m["hf_signal_retention"] - 1.0) < 1e-12)


def test_translation_roundtrip() -> None:
    print("\nControl 2: pure translation -- recovered exactly, no envelope loss")
    img = make_micrograph()
    for t in (0.25, 1.0, 2.0, 4.0):
        moved = pt.x1_translation(img, t)
        m = dg.all_image_diagnostics(img, moved)
        err = abs(m["std_shift_px"] - t)
        check(
            f"t={t:>4} px recovered",
            err < 0.01,
            f"measured {m['std_shift_px']:.4f} px, err {err:.1e}, "
            f"dB={m['std_delta_b_a2']:+.3f}, eps={m['std_eps_incoherent']:.2e}, "
            f"relRMSE={m['image_relative_rmse']:.4f}",
        )
        check(f"t={t:>4} px gives no envelope loss", abs(m["std_delta_b_a2"]) < 0.25)
        check(f"t={t:>4} px gives no incoherent residual", m["std_eps_incoherent"] < 0.02)


def test_envelope_roundtrip() -> None:
    print("\nControl 3: applied B-factor -- recovered by the STD fit")
    img = make_micrograph()
    for b in (1.0, 5.0, 25.0, 50.0):
        att = pt.x5_attenuation(img, b)
        m = dg.all_image_diagnostics(img, att)
        rel = abs(m["std_delta_b_a2"] - b) / b
        check(
            f"dB={b:>5} A^2 recovered",
            rel < 0.15,
            f"measured {m['std_delta_b_a2']:.3f} A^2 ({100*rel:.1f}% err), "
            f"R2={m['std_fit_r2']:.4f}, relRMSE={m['image_relative_rmse']:.4f}",
        )


def test_jitter_matches_theory() -> None:
    print("\nControl 4: random jitter -- measured delta-B matches 8 pi^2 sigma^2 a^2")
    img = make_micrograph()
    rng = np.random.default_rng(7)
    for sigma in (0.1, 0.2, 0.4, 0.8):
        # Many frames so the empirical kernel approaches the Gaussian limit.
        jit = pt.x2_jitter_output(img, sigma, 400, rng)
        m = dg.all_image_diagnostics(img, jit)
        predicted = delta_b_for_sigma_px(sigma)
        rel = abs(m["std_delta_b_a2"] - predicted) / predicted
        check(
            f"sigma={sigma:>4} px",
            rel < 0.20,
            f"measured {m['std_delta_b_a2']:.3f} vs predicted {predicted:.3f} A^2 "
            f"({100*rel:.1f}% err), R2={m['std_fit_r2']:.4f}",
        )


def test_hot_pixel_blind_spot() -> None:
    """Sparse faults: closed-form response, and where each diagnostic goes blind.

    For ``n`` pixels forced to ``mean + A`` in an ``N``-pixel image whose
    reference standard deviation is ``s``, the relative RMSE is
    ``sqrt(n) * A / (s * sqrt(N))`` to first order. That is a closed-form
    control, and it also shows that the response scales as 1/sqrt(N): the same
    physical defect reads smaller on a larger micrograph.
    """
    print("\nControl 5: hot pixels -- closed-form response and the max-error blind spot")
    img = make_micrograph()
    n_pix = img.size
    s_ref = float(img.std())
    amp = pt.X7_HOT_PIXEL_SIGMA * s_ref
    maxerrs = []
    for n in (1, 100, 10000):
        hot = pt.x7_hot_pixels(img, n, np.random.default_rng(11))
        m = dg.all_image_diagnostics(img, hot)
        predicted = math.sqrt(n) * amp / (s_ref * math.sqrt(n_pix))
        rel = abs(m["image_relative_rmse"] - predicted) / predicted
        maxerrs.append(m["image_max_abs_error"])
        check(
            f"n={n:>6} relative RMSE matches sqrt(n)A/(s sqrt(N))",
            rel < 0.10,
            f"measured {m['image_relative_rmse']:.4e} vs predicted {predicted:.4e} "
            f"({100*rel:.1f}% err); maxerr={m['image_max_abs_error']:.1f}; "
            f"eps_inc={m['std_eps_incoherent']:.3e}",
        )
    spread = (max(maxerrs) - min(maxerrs)) / max(maxerrs)
    check(
        "max-error cannot distinguish 1 from 10000 hot pixels",
        spread < 0.10,
        f"max-error ranged {min(maxerrs):.1f}..{max(maxerrs):.1f} "
        f"({100*spread:.1f}% spread) across a 10000x change in defect count",
    )


def test_scale_invariance() -> None:
    print("\nControl 6: uniform scale -- reported as scale, not as envelope loss")
    img = make_micrograph()
    for g in (1.001, 1.01, 1.1):
        m = dg.all_image_diagnostics(img, img * g)
        check(
            f"g={g}",
            abs(m["std_scale_g"] - g) < 1e-6 and abs(m["std_delta_b_a2"]) < 0.05,
            f"scale_g={m['std_scale_g']:.6f}, dB={m['std_delta_b_a2']:+.4f}, "
            f"eps={m['std_eps_incoherent']:.2e}, relRMSE={m['image_relative_rmse']:.4f}",
        )


def test_nonsquare() -> None:
    print("\nControl 7: non-square images are handled")
    img = make_micrograph(384, 512)
    m = dg.all_image_diagnostics(img, pt.x1_translation(img, 1.0), border_px=50)
    check("non-square translation recovered", abs(m["std_shift_px"] - 1.0) < 0.01,
          f"{m['std_shift_px']:.4f} px")


def test_gate2_metric_parity() -> None:
    print("\nControl 8: existing metrics reproduce tools/compare_motioncorr.py exactly")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_cmp", Path(__file__).resolve().parents[1] / "compare_motioncorr.py"
    )
    cmp_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cmp_mod)

    rng = np.random.default_rng(3)
    ref = make_micrograph(128, 128).astype(np.float32)
    test = (ref + rng.standard_normal((128, 128)).astype(np.float32) * 0.01).astype(np.float32)
    hdr = {"nx": 128, "ny": 128, "nz": 1, "mode": 2}
    theirs = cmp_mod.compare_images(ref, test, hdr, hdr, b"\x00" * 1024, b"\x00" * 1024)
    mine = dg.existing_image_metrics(ref.astype(np.float64), test.astype(np.float64))
    for a, b in (("rmse", "image_rmse"), ("relative_rmse", "image_relative_rmse"),
                 ("max_abs_pixel_error", "image_max_abs_error")):
        check(f"{b} matches comparator", abs(theirs[a] - mine[b]) <= 1e-15 * max(1.0, abs(theirs[a])),
              f"{theirs[a]!r} vs {mine[b]!r}")


def test_displacement_field() -> None:
    print("\nControl 9: displacement-field evaluator against the shipped model")
    star = Path(__file__).resolve().parents[2] / "test-data/fixtures/reference_output/synthetic_128x128_8frames.star"
    d = mrcio.displacement_field(star, 4, 4)
    check("field shape", d["field"].shape == (8, 4, 4, 2), str(d["field"].shape))
    check("frame 1 is the origin", np.allclose(d["field"][0], 0.0))
    check("no local model in a 1x1-patch run", not d["has_local_model"])
    gs = mrcio.global_shifts(mrcio.parse_star(star))
    check("global shift reproduced at every grid point",
          np.allclose(d["field"][2, :, :, 0], gs[2, 1]))
    # Self-comparison of a field must be identically zero.
    fm = dg.field_metrics(star, star, grid=4)
    check("field null control", fm["field_rms_px"] == 0.0 and fm["field_max_px"] == 0.0)


def test_mrc_roundtrip() -> None:
    print("\nControl 10: MRC write/read round-trip")
    img = make_micrograph(64, 96).astype(np.float32)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.mrc"
        mrcio.write_mrc_2d(p, img)
        back, _ = mrcio.read_mrc_2d(p)
        check("round-trip is exact in float32", np.array_equal(back.astype(np.float32), img))
        check("shape preserved", back.shape == img.shape, str(back.shape))


def main() -> int:
    print("=" * 72)
    print(" MotionCorr issue #60 calibration tooling controls")
    print("=" * 72)
    test_null_control()
    test_translation_roundtrip()
    test_envelope_roundtrip()
    test_jitter_matches_theory()
    test_hot_pixel_blind_spot()
    test_scale_invariance()
    test_nonsquare()
    test_gate2_metric_parity()
    test_displacement_field()
    test_mrc_roundtrip()
    print("\n" + "=" * 72)
    if FAILURES:
        print(f" {len(FAILURES)} CONTROL(S) FAILED: {', '.join(FAILURES)}")
        return 1
    print(" ALL CONTROLS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
