#!/usr/bin/env python3
"""Independent diagnostic field/signal evaluation; does not run MotionCorr."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "test-data"))
import generate_motion_diagnostics as gen
from motion_field import read_motion_star, read_mrc


def sample(image, p):
    """Standalone bilinear detector sampling; reject, never clip, outside coordinates."""
    x, y = p[..., 0], p[..., 1]
    if not np.isfinite(p).all() or x.min() < 0 or y.min() < 0 or x.max() >= image.shape[1]-1 or y.max() >= image.shape[0]-1:
        raise ValueError("candidate samples outside fixed valid detector region")
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    dx, dy = x-ix, y-iy
    return ((1-dy)*((1-dx)*image[iy, ix]+dx*image[iy, ix+1]) +
            dy*((1-dx)*image[iy+1, ix]+dx*image[iy+1, ix+1]))


def vector_metrics(e):
    v = np.linalg.norm(e, axis=-1)
    return dict(rms=float(np.sqrt(np.mean(v*v))), p95=float(np.percentile(v, 95)), max=float(v.max()))


def signal_metrics(image, target):
    e = image-target
    rms = float(np.sqrt(np.mean(e*e)))
    contrast = float(np.std(target))
    return dict(rmse=rms, contrast_normalized_rmse=rms/contrast if contrast > 1e-12 else None,
                mean_error=float(e.mean()))


def evaluate(r, movie, target, truth, field, roi):
    q = gen.grid(r)
    expected = (r["frames"], r["ny"], r["nx"], 2)
    if field.shape != expected or truth.shape != expected or movie.shape != expected[:-1] or target.shape != expected[1:-1]:
        raise ValueError("geometry mismatch")
    if not all(np.isfinite(a).all() for a in (movie, target, truth, field)):
        raise ValueError("nonfinite input")
    y0, y1, x0, x1 = roi
    sl = np.s_[y0:y1, x0:x1]
    err = field-truth
    inner = err[:, y0:y1, x0:x1]
    border = np.ones(q.shape[:2], dtype=bool)
    border[sl] = False
    px = vector_metrics(inner)
    aa = vector_metrics(inner*r["pixel_size"])
    corrected, oracle = [], []
    for f in range(r["frames"]):
        corrected.append(sample(movie[f].astype(float), (q-field[f])[sl]))
        oracle.append(sample(movie[f].astype(float), (q-truth[f])[sl]))
    t = target[sl].astype(float)
    accuracy = aa["rms"] <= .20 and aa["p95"] <= .40 and aa["max"] <= .80
    return dict(role=r["role"], gauge="fixed frame-0 material coordinates; no registration",
        accuracy_status=("UNIDENTIFIABLE" if r["signal"] in ("flat", "repeated") else ("PASS" if accuracy else "FAIL")),
        field_distance_status="PASS" if accuracy else "FAIL",
        identifiable=r["signal"] not in ("flat", "repeated"),
        field_px=px, field_angstrom=aa, border_px=vector_metrics(err[:, border]),
        per_frame_px=[vector_metrics(e) for e in inner],
        global_mean_error_px=vector_metrics(inner.mean(axis=(1, 2))),
        local_error_px=vector_metrics(inner-inner.mean(axis=(1, 2), keepdims=True)),
        signal=dict(uncorrected=signal_metrics(movie[:, y0:y1, x0:x1].astype(float).mean(axis=0), t),
                    true_motion_bilinear=signal_metrics(np.mean(oracle, axis=0), t),
                    estimated_motion_bilinear=signal_metrics(np.mean(corrected, axis=0), t)),
        signal_status="CHARACTERIZATION", application_consistency_status="NOT_TESTED")


def check_case(fixtures, name, candidate, summed_image=None):
    m = json.loads((fixtures/"MANIFEST.json").read_text())
    if m["schema"] != gen.SCHEMA:
        raise ValueError("unsupported fixture schema")
    c = m["cases"][name]
    if c["recipe"] != gen.recipe(name) or c["roi"] != [12, 84, 12, 116]:
        raise ValueError("recipe/ROI differs from versioned family")
    expected_files = {f"{name}.mrcs", f"{name}_target.npy", f"{name}_field.npy", f"{name}.star"}
    if set(c["files"]) != expected_files:
        raise ValueError("incomplete fixture file inventory")
    for f, h in c["files"].items():
        if gen.digest(fixtures/f) != h:
            raise ValueError(f"fixture hash mismatch: {f}")
    r = c["recipe"]
    if candidate.suffix == ".star":
        s = read_motion_star(candidate)
        if (s.nx, s.ny, s.n_frames, s.first_frame, s.binning) != (r["nx"], r["ny"], r["frames"], 1, 1.) or s.motion_model_version not in (0, 1) or not np.isclose(s.pixel_size, r["pixel_size"], rtol=0, atol=1e-6):
            raise ValueError("unsupported STAR geometry, frame origin, binning, model or pixel size")
        q = gen.grid(r)
        field = s.field(s.frames, q[..., 0].ravel(), q[..., 1].ravel()).reshape((r["frames"], r["ny"], r["nx"], 2))
    else:
        field = np.load(candidate, allow_pickle=False)
    movie, _ = read_mrc(fixtures/f"{name}.mrcs")
    result = evaluate(r, movie, np.load(fixtures/f"{name}_target.npy", allow_pickle=False),
                      np.load(fixtures/f"{name}_field.npy", allow_pickle=False), field, c["roi"])
    if summed_image is not None:
        summed, _ = read_mrc(summed_image)
        if summed.shape != (1, r["ny"], r["nx"]) or not np.isfinite(summed).all():
            raise ValueError("invalid non-dose-weighted summed-image geometry or pixels")
        y0, y1, x0, x1 = c["roi"]
        target = np.load(fixtures/f"{name}_target.npy", allow_pickle=False)
        result["signal"]["published_sum_divided_by_frames"] = signal_metrics(
            summed[0, y0:y1, x0:x1]/r["frames"], target[y0:y1, x0:x1])
        result["summed_image_sha256"] = gen.digest(summed_image)
    result.update(case=name, candidate_sha256=gen.digest(candidate), fixture_files=c["files"])
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--case", choices=list(gen.CASES), required=True)
    ap.add_argument("--candidate", type=Path, required=True, help="motion STAR or dense F,Y,X,2 .npy in px")
    ap.add_argument("--summed-image", type=Path, help="optional full-frame non-DW sum, all five frames")
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    try:
        result = check_case(args.fixtures, args.case, args.candidate, args.summed_image)
    except (ValueError, KeyError, OSError) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    args.json.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(f"{result['case']}: {result['role']} accuracy={result['accuracy_status']}; signal=CHARACTERIZATION")
    # A characterization FAIL remains visible and never becomes an accuracy PASS.
    sys.exit(1 if result["role"] == "gate" and result["accuracy_status"] == "FAIL" else 0)
