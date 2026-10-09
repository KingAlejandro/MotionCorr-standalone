#!/usr/bin/env python3
"""Compare two MotionCorr output trees movie by movie (docs/fft_size_policy.md).

Per movie: tools/compare_motioncorr.py --gate backend on the DW sum (and on the
noDW sum when both trees have it), with the relaxed relative-RMSE limit as its
non-blocking diagnostic; plus local-shift differences, Pearson correlation of
the sums and the radially averaged power-spectrum ratio in ten bands up to
Nyquist. Thresholds are the tool's own; nothing here overrides them.

  validate_compare.py REF_DIR TEST_DIR --test-log TIME_V_LOG --json-out OUT
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
from compare_motioncorr import parse_mrc, parse_star_file  # noqa: E402

BANDS = 10


def gate(ref_mrc, test_mrc, ref_star, test_star, log):
    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        cmd = [sys.executable, str(REPO / "tools" / "compare_motioncorr.py"),
               "--ref-mrc", str(ref_mrc), "--test-mrc", str(test_mrc),
               "--ref-star", str(ref_star), "--test-star", str(test_star),
               "--test-log", str(log), "--gate", "backend", "--json-out", tmp.name]
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        rep = json.loads(Path(tmp.name).read_text())
    t = rep["checks"].get("motion_trajectory", {})
    im = rep["checks"].get("corrected_image", {})
    return {
        "status": rep["overall_status"], "rc": rc,
        "trajectory_passed": t.get("passed"), "star_passed": rep["checks"].get("star_fields", {}).get("passed"),
        "image_passed": im.get("passed"), "geometry": im.get("geometry_matches"),
        "max_shift_err": t.get("max_shift_error"), "shift_rms": t.get("coord_rms_error"),
        "rmse": im.get("rmse"), "max_abs_err": im.get("max_abs_pixel_error"),
        "rel_rmse": im.get("relative_rmse"),
        "rel_rmse_diag": im.get("relative_rmse_diagnostic", {}).get("status"),
        "fail_reasons": t.get("fail_reasons", []) + im.get("fail_reasons", []) + rep.get("errors", []),
    }


def local_shifts(star):
    blk = parse_star_file(star).get("local_shift")
    if not blk:
        return {}
    labels, rows = blk["labels"], blk["rows"]
    i = {k: labels.index(k) for k in ("_rlnMicrographFrameNumber", "_rlnCoordinateX", "_rlnCoordinateY",
                                      "_rlnMicrographShiftX", "_rlnMicrographShiftY")}
    return {(r[i["_rlnMicrographFrameNumber"]], r[i["_rlnCoordinateX"]], r[i["_rlnCoordinateY"]]):
            (float(r[i["_rlnMicrographShiftX"]]), float(r[i["_rlnMicrographShiftY"]])) for r in rows}


def local_diff(ref_star, test_star):
    a, b = local_shifts(ref_star), local_shifts(test_star)
    keys = sorted(set(a) & set(b))
    if not keys:
        return {"rows": 0, "unmatched": len(set(a) ^ set(b))}
    d = np.array([[a[k][0] - b[k][0], a[k][1] - b[k][1]] for k in keys])
    return {"rows": len(keys), "unmatched": len(set(a) ^ set(b)),
            "max_abs": float(np.abs(d).max()), "rms": float(np.sqrt((d ** 2).sum(1).mean()))}


def spectrum_bands(img):
    f = np.fft.rfft2(img - img.mean())
    p = (f.real ** 2 + f.imag ** 2)
    ny, nx = img.shape
    ky = np.fft.fftfreq(ny)[:, None] * 2.0
    kx = np.fft.rfftfreq(nx)[None, :] * 2.0
    r = np.sqrt(kx ** 2 + ky ** 2)
    band = np.minimum((r * BANDS).astype(int), BANDS)  # BANDS = corners beyond Nyquist
    return np.bincount(band.ravel(), weights=p.ravel(), minlength=BANDS + 1)[:BANDS]


def image_metrics(ref_mrc, test_mrc):
    rh, rp, _ = parse_mrc(ref_mrc)
    th, tp, _ = parse_mrc(test_mrc)
    a = rp.astype(np.float64).reshape(rh["ny"], rh["nx"])
    b = tp.astype(np.float64).reshape(th["ny"], th["nx"])
    ratio = spectrum_bands(b) / spectrum_bands(a)
    return {"pearson_r": float(np.corrcoef(a.ravel(), b.ravel())[0, 1]),
            "ps_ratio": [float(x) for x in ratio],
            "ps_max_dev": float(np.abs(ratio - 1.0).max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", type=Path)
    ap.add_argument("test", type=Path)
    ap.add_argument("--test-log", type=Path, required=True)
    ap.add_argument("--json-out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for ref_star in sorted((args.ref / "Movies").glob("*.star")):
        name = ref_star.stem
        test_star = args.test / "Movies" / ref_star.name
        row = {"movie": name}
        for kind, suffix in (("dw", ".mrc"), ("nodw", "_noDW.mrc")):
            rm, tm = args.ref / "Movies" / (name + suffix), args.test / "Movies" / (name + suffix)
            if not rm.exists() and not tm.exists():
                continue
            if not (rm.exists() and tm.exists() and test_star.exists()):
                row[kind] = {"status": "FAIL", "fail_reasons": ["missing product"]}
                continue
            row[kind] = gate(rm, tm, ref_star, test_star, args.test_log)
            row[kind].update(image_metrics(rm, tm))
        if test_star.exists():
            row["local"] = local_diff(ref_star, test_star)
        rows.append(row)
    args.json_out.write_text(json.dumps({"ref": str(args.ref), "test": str(args.test), "movies": rows}, indent=1))
    for kind in ("dw", "nodw"):
        rs = [r[kind] for r in rows if kind in r]
        if not rs:
            continue
        def mx(k):
            v = [r[k] for r in rs if r.get(k) is not None]
            return max(v) if v else float("nan")
        print(f"{kind}: backend PASS {sum(r['status'] == 'PASS' for r in rs)}/{len(rs)}"
              f"  relRMSE<=1e-3 {sum(r.get('rel_rmse_diag') == 'PASS' for r in rs)}/{len(rs)}"
              f"  max: shift {mx('max_shift_err'):.4g} rms {mx('shift_rms'):.4g} rmse {mx('rmse'):.4g}"
              f" maxerr {mx('max_abs_err'):.4g} relRMSE {mx('rel_rmse'):.4g} psdev {mx('ps_max_dev'):.4g}"
              f"  min r {min(r.get('pearson_r', 1) for r in rs):.6f}")
        for r in rows:
            if kind in r and r[kind]["status"] != "PASS":
                print(f"  FAIL {r['movie']} {kind}: {r[kind]['fail_reasons']}")
    loc = [r["local"] for r in rows if r.get("local", {}).get("rows")]
    if loc:
        print(f"local: max abs {max(x['max_abs'] for x in loc):.4g} px, max rms {max(x['rms'] for x in loc):.4g} px,"
              f" unmatched rows {sum(x['unmatched'] for x in loc)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
