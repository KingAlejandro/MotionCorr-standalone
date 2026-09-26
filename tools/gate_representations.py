#!/usr/bin/env python3
"""Re-express the relaxed-gate image metric in other units, from committed artifacts only.

Regenerates every table in docs/gate_contract.md section 4A. Read-only: it runs no movie,
touches no gate, and needs no GPU. All inputs are files already in the repository.

  python3 tools/gate_representations.py
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
CUDA_RERUN = REPO / "docs" / "cuda_24_movies_gate2_rerun.json"
CPU_MANIFEST = REPO / "docs" / "spa_24_movies_manifest.json"
FIXTURE = REPO / "test-data" / "fixtures" / "reference_output" / "synthetic_128x128_8frames.mrc"

# The 24 tutorial micrographs are 3710 x 3838; used only for the white-noise expectation.
TUTORIAL_PIXELS = 3710 * 3838
GATE = 0.001


def correlation_bound(d: float) -> float:
    """Lower bound on Pearson r between reference and test, from relative RMSE alone.

    r = 1 + (eps^2 - (sigma_D/sigma_A)^2) / (2 (1 + eps)) with sigma_B = sigma_A (1 + eps).
    Minkowski gives |eps| <= sigma_D/sigma_A <= d, so r is minimised at eps = -d.
    """
    return 1.0 - d * d / (2.0 * (1.0 - d))


def correlation_point(d: float) -> float:
    """Pearson r when the difference is uncorrelated with the reference (eps = 0)."""
    return 1.0 - d * d / 2.0


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(y)))[0, 1])


def section_4a1(rel: np.ndarray) -> None:
    print("4A.1  relative RMSE re-expressed")
    print(f"  {'':16} {'relRMSE':>10} {'r lower':>13} {'r if eps~0':>13} {'nines':>7} "
          f"{'SNR dB':>8} {'unexpl var %':>13}")
    rows = (("Gate limit", GATE), ("CUDA best", rel.min()),
            ("CUDA median", float(np.median(rel))), ("CUDA worst", rel.max()))
    for label, d in rows:
        r = correlation_point(d)
        print(f"  {label:16} {d:10.6f} {correlation_bound(d):13.9f} {r:13.9f} "
              f"{-math.log10(1 - r):7.2f} {20 * math.log10(1 / d):8.1f} {d * d * 100:13.6f}")


def section_4a1_validation() -> None:
    sys.path.insert(0, str(REPO / "tools"))
    from compare_motioncorr import parse_mrc  # noqa: E402  (path set above)

    _, pixels, _ = parse_mrc(FIXTURE)
    ref = pixels.astype(np.float64)
    sigma = ref.std()
    rng = np.random.default_rng(20260925)
    target = 0.010082  # the worst recorded CUDA movie

    noise = rng.standard_normal(ref.size)
    noise *= target * sigma / noise.std()
    highpass = ref - np.convolve(ref, np.ones(9) / 9, mode="same")
    highpass *= target * sigma / highpass.std()
    gain = ref * (1 + target * sigma / math.sqrt(float((ref ** 2).mean())))

    print("\n4A.1  identity checked on real fixture pixels, d = %.6f" % target)
    print(f"  {'difference structure':40} {'measured r':>13} {'1 - d^2/2':>13} {'bound':>13}")
    for label, test in (("white noise, uncorrelated", ref + noise),
                        ("reference's own high-pass content", ref + highpass),
                        ("pure gain change", gain)):
        diff = test - ref
        d = math.sqrt(float((diff ** 2).mean())) / sigma
        print(f"  {label:40} {float(np.corrcoef(ref, test)[0, 1]):13.9f} "
              f"{correlation_point(d):13.9f} {correlation_bound(d):13.9f}")


def section_4a2(rel: np.ndarray) -> None:
    manifest = json.loads(CPU_MANIFEST.read_text())

    def series(key: str) -> np.ndarray:
        return np.array([m[key]["relative_image_rmse"] for m in manifest["movies"]
                         if m.get(key, {}).get("relative_image_rmse") is not None])

    comparisons = (
        ("standalone j4 vs standalone j1", series("j4_vs_j1_relaxed")),
        ("standalone j1 vs PR #25 CPU reference", series("j1_vs_pr25_cpu_exact")),
        ("CUDA (--gpu 0 --j 4) vs fixed CPU j1", rel),
        ("standalone j1 vs upstream RELION 5.1 j1", series("j1_vs_relion_j1_relaxed")),
        ("standalone j4 vs upstream RELION 5.1 j4", series("j4_vs_relion_j4_relaxed")),
    )
    print("\n4A.2  the same metric across every committed comparison of these 24 movies")
    print(f"  {'comparison':42} {'n':>3} {'min':>10} {'median':>10} {'max':>10} {'over limit':>11}")
    for label, values in comparisons:
        print(f"  {label:42} {len(values):3d} {values.min():10.6f} {np.median(values):10.6f} "
              f"{values.max():10.6f} {f'{(values > GATE).sum()}/{len(values)}':>11}")

    upstream = series("j1_vs_relion_j1_relaxed")
    upstream = upstream[upstream > 0]
    print(f"  ratio of medians, upstream disagreement / CUDA disagreement: "
          f"{np.median(upstream) / np.median(rel):.2f}x  (over its {len(upstream)} nonzero movies)")


def section_4a3(rel: np.ndarray, rmse: np.ndarray, max_px: np.ndarray) -> None:
    sigma = rmse / rel
    expected_max = math.sqrt(2 * math.log(TUTORIAL_PIXELS))
    stats = {
        "worst pixel / sigma_ref": max_px / sigma,
        "worst pixel / white-noise expectation": max_px / (rmse * expected_max),
        "share of squared error in that one pixel (%)":
            100 * max_px ** 2 / (TUTORIAL_PIXELS * rmse ** 2),
    }
    print(f"\n4A.3  how the difference is spread over {TUTORIAL_PIXELS:,} pixels "
          f"(white-noise max = {expected_max:.3f} x rmse)")
    print(f"  {'quantity':46} {'min':>10} {'median':>10} {'max':>10}")
    for label, values in stats.items():
        print(f"  {label:46} {values.min():10.4g} {np.median(values):10.4g} {values.max():10.4g}")
    concentration = TUTORIAL_PIXELS * rmse ** 2 / max_px ** 2
    print(f"  pixels at the worst-pixel amplitude that would account for the whole RMSE: "
          f"{concentration.min():.0f} to {concentration.max():.0f} (median {np.median(concentration):.0f})")


def section_4a4(columns: dict) -> None:
    print("\n4A.4  correlation between the metrics themselves (Pearson / Spearman)")
    names = list(columns)
    print(f"  {'':20}" + "".join(f"{n[:17]:>18}" for n in names[1:]))
    for i, a in enumerate(names[:-1]):
        row = f"  {a[:20]:20}" + " " * (18 * i)
        for b in names[i + 1:]:
            row += f"{float(np.corrcoef(columns[a], columns[b])[0, 1]):8.2f}/{spearman(columns[a], columns[b]):<9.2f}"
        print(row)


def main() -> None:
    movies = json.loads(CUDA_RERUN.read_text())["movies"]
    rel = np.array([m["relative_rmse"] for m in movies])
    rmse = np.array([m["image_rmse"] for m in movies])
    max_px = np.array([m["max_pixel_error"] for m in movies])

    print(f"Source: {CUDA_RERUN.relative_to(REPO)} ({len(movies)} movies), "
          f"{CPU_MANIFEST.relative_to(REPO)}, {FIXTURE.relative_to(REPO)}")
    print("These are monotone re-expressions of one measurement. They add interpretability,")
    print("not information, and inherit every blind spot of relative RMSE.\n")

    section_4a1(rel)
    section_4a1_validation()
    section_4a2(rel)
    section_4a3(rel, rmse, max_px)
    section_4a4({
        "relative_rmse": rel,
        "image_rmse": rmse,
        "max_pixel_error": max_px,
        "trajectory_rms_px": np.array([m["trajectory_rms_px"] for m in movies]),
        "max_shift_error_px": np.array([m["max_shift_error_px"] for m in movies]),
        "sigma_ref": rmse / rel,
    })


if __name__ == "__main__":
    main()
