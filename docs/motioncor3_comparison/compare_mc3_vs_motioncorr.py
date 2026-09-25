#!/usr/bin/env python3
"""Cross-implementation comparison: MotionCorr-standalone (RELION 'own') vs MotionCor3.

The two programs implement different algorithms. Nothing here tests or asserts bit
parity; every metric is a similarity measure valid across independent implementations.

Design notes that are load-bearing (each one came from a defect found in review):

* Sub-pixel registration is mandatory, not a refinement. MotionCor3 references the
  centre frame and RELION references frame 0, so the two sums are translated by a
  non-integer amount. Removing only the integer part leaves up to 0.5 px, and half a
  pixel of misregistration alone drives the FRC at Nyquist from 1.00 to 0.49 -- i.e.
  an unregistered comparison reports "these disagree beyond 1.8 A" for two *identical*
  images. The offset is therefore estimated by upsampled DFT and removed in Fourier
  space before any image metric is computed.
* The registered image is cropped inward afterwards, because a Fourier shift is
  circular and wraps content across the edge.
* rfft2 ring sums double-count the kx=0 and kx=nyquist columns (both members of each
  Hermitian pair live in that column), so those get weight 0.5.
* MotionCor3's MRC header amin/amax/amean are read from a device buffer that is never
  written before the sum is saved (CSaveSerialCryoEM.cpp:231), i.e. they are
  uninitialised VRAM. Header statistics are recomputed from pixels for both arms.
* The shift sign convention is +1 on both sides (verified in both sources). A negative
  best fit is a bug to report, not a free parameter to absorb, so all four axis-flip
  combinations are tested and anything other than (+,+) is flagged.
"""

import argparse
import json
import os
import statistics
import sys

import numpy as np

MRC_MODES = {0: np.int8, 1: np.int16, 2: np.float32, 6: np.uint16}


def read_mrc(path):
    with open(path, "rb") as fh:
        hdr = fh.read(1024)
        nx, ny, nz, mode = np.frombuffer(hdr, dtype="<i4", count=4)
        nsymbt = int(np.frombuffer(hdr, dtype="<i4", count=1, offset=92)[0])
        cella = np.frombuffer(hdr, dtype="<f4", count=3, offset=40)
        machst = hdr[212:216]
        if int(mode) not in MRC_MODES:
            raise ValueError(f"{path}: unsupported MRC mode {mode}")
        if machst not in (b"DA\x00\x00", b"DD\x00\x00", b"\x44\x41\x00\x00"):
            # not fatal on x86 where both tools write LE, but record it
            pass
        if nsymbt:
            fh.read(nsymbt)
        count = int(nx) * int(ny) * max(int(nz), 1)
        data = np.fromfile(fh, dtype=MRC_MODES[int(mode)], count=count)
    if data.size != count:
        raise ValueError(f"{path}: short read ({data.size} of {count})")
    data = data.reshape(max(int(nz), 1), int(ny), int(nx))
    if data.shape[0] != 1:
        raise ValueError(f"{path}: expected one 2-D section, got nz={nz}")
    img = data[0].astype(np.float32)
    meta = {
        "path": os.path.basename(path),
        "nx": int(nx), "ny": int(ny), "mode": int(mode),
        # recomputed from pixels: MotionCor3's header stats are uninitialised VRAM
        "pix_min": float(img.min()), "pix_max": float(img.max()),
        "pix_mean": float(img.mean()), "pix_std": float(img.std()),
        "frac_exactly_zero": float((img == 0).mean()),
        "angpix_from_header": float(cella[0] / nx) if nx else None,
    }
    return img, meta


# ---------------------------------------------------------------- trajectories

def read_relion_global_shift(path):
    with open(path) as fh:
        lines = fh.read().splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() != "data_global_shift":
        i += 1
    if i >= len(lines):
        raise ValueError(f"{path}: no data_global_shift block")
    i += 1
    # do not cross into another data_ block while hunting for loop_: data_local_shift
    # reuses the SAME _rlnMicrographShiftX/Y labels and would parse silently
    while i < len(lines) and lines[i].strip() != "loop_":
        if lines[i].strip().startswith("data_"):
            raise ValueError(f"{path}: data_global_shift is not a loop block")
        i += 1
    i += 1
    cols, rows = [], []
    while i < len(lines) and lines[i].strip().startswith("_"):
        cols.append(lines[i].split()[0])
        i += 1
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("data_") or s.startswith("#"):
            break
        rows.append(s.split())
        i += 1
    ix, iy = cols.index("_rlnMicrographShiftX"), cols.index("_rlnMicrographShiftY")
    return (np.array([float(r[ix]) for r in rows]),
            np.array([float(r[iy]) for r in rows]))


def read_mc3_full_log(path):
    xs, ys = [], []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split()
            if len(p) < 3:
                continue
            try:
                xs.append(float(p[1])); ys.append(float(p[2]))
            except ValueError:
                continue
    return np.array(xs), np.array(ys)


def compare_trajectories(ax, ay, bx, by):
    if len(ax) != len(bx):
        return {"error": f"frame count mismatch: motioncorr={len(ax)} motioncor3={len(bx)}"}
    n = len(ax)
    if n == 0:
        return {"error": "empty trajectory"}

    # Both tools store the measured displacement and apply its negative, so the
    # expected relation is (+1, +1). Test all four flips; anything else is a finding.
    results = {}
    for sy in (1.0, -1.0):
        for sx in (1.0, -1.0):
            cx, cy = sx * bx, sy * by
            dx = (ax - ax.mean()) - (cx - cx.mean())
            dy = (ay - ay.mean()) - (cy - cy.mean())
            d = np.hypot(dx, dy)
            results[(int(sx), int(sy))] = (float(np.sqrt(np.mean(d ** 2))),
                                           float(d.max()), int(np.argmax(d)) + 1, d)

    expected = results[(1, 1)]
    best_key = min(results, key=lambda k: results[k][0])
    rms, mx, mxf, d = expected
    out = {
        "n_frames": n,
        "coord_rms_shift_px": rms,
        "max_shift_diff_px": mx,
        "max_diff_at_frame": mxf,
        "sign_convention_expected": "(+x,+y)",
        "sign_convention_best_fit": f"({best_key[0]:+d}x,{best_key[1]:+d}y)",
        "sign_convention_agrees": best_key == (1, 1),
        "rms_under_best_fit_sign_px": results[best_key][0],
        "total_path_px_motioncorr": float(np.sum(np.hypot(np.diff(ax), np.diff(ay)))),
        "total_path_px_motioncor3": float(np.sum(np.hypot(np.diff(bx), np.diff(by)))),
        "accum_motion_px_motioncorr": float(np.hypot(ax[-1] - ax[0], ay[-1] - ay[0])),
        "accum_motion_px_motioncor3": float(np.hypot(bx[-1] - bx[0], by[-1] - by[0])),
        # MotionCor3 truncates its global shift to 0.01 px (CStackShift::TruncateDecimal),
        # so this metric has a hard floor around 0.004 px.
        "quantisation_floor_px": 0.01 / (12 ** 0.5),
    }
    return out


# ---------------------------------------------------------------------- images

def centre_crop(img, size):
    ny, nx = img.shape
    s = min(size, ny, nx)
    return img[(ny - s) // 2:(ny - s) // 2 + s, (nx - s) // 2:(nx - s) // 2 + s]


def _dftups(data, nor, noc, usfac, roff, coff):
    """Upsampled inverse DFT of `data` in a small region, by matrix multiply."""
    nr, nc = data.shape
    kernc = np.exp((-2j * np.pi / (nc * usfac))
                   * (np.fft.ifftshift(np.arange(nc))[:, None] - np.floor(nc / 2))
                   * (np.arange(noc)[None, :] - coff))
    kernr = np.exp((-2j * np.pi / (nr * usfac))
                   * (np.arange(nor)[:, None] - roff)
                   * (np.fft.ifftshift(np.arange(nr))[None, :] - np.floor(nr / 2)))
    return kernr @ data @ kernc


def register_subpixel(a, b, usfac=100):
    """Sub-pixel (dy, dx) correction that maps b onto a. Upsampled-DFT phase corr."""
    A, B = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    R = A * np.conj(B)
    mag = np.abs(R); mag[mag == 0] = 1.0
    R = R / mag                                   # phase correlation
    cc = np.fft.ifft2(R)
    ny, nx = cc.shape
    py, px = np.unravel_index(int(np.argmax(np.abs(cc))), cc.shape)
    dy = py - ny if py > ny // 2 else py
    dx = px - nx if px > nx // 2 else px
    peak_int = float(np.abs(cc[py, px]))
    # refine around the integer peak on a 1.5 px window at 1/usfac resolution
    w = int(np.ceil(usfac * 1.5))
    roff = w // 2 - dy * usfac
    coff = w // 2 - dx * usfac
    # _dftups uses a NEGATIVE exponent while the coarse stage used ifft2 (positive),
    # so the cross-power spectrum must be conjugated for the fine stage or the peak
    # lands mirrored and pins to the window edge.
    fine = _dftups(np.conj(R), w, w, usfac, roff, coff)
    fy, fx = np.unravel_index(int(np.argmax(np.abs(fine))), fine.shape)
    dy_f = dy + (fy - w // 2) / usfac
    dx_f = dx + (fx - w // 2) / usfac
    return dy_f, dx_f, peak_int


def fourier_shift(img, dy, dx):
    n0, n1 = img.shape
    F = np.fft.fft2(img)
    ky = np.fft.fftfreq(n0)[:, None]
    kx = np.fft.fftfreq(n1)[None, :]
    return np.real(np.fft.ifft2(F * np.exp(-2j * np.pi * (ky * dy + kx * dx))))


def frc(a, b):
    """Fourier Ring Correlation. Hann-windowed; half-plane columns down-weighted."""
    n = a.shape[0]
    w = np.hanning(n)
    win = np.outer(w, w)
    A = np.fft.rfft2((a - a.mean()) * win)
    B = np.fft.rfft2((b - b.mean()) * win)
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.rfftfreq(n)[None, :]
    r = np.sqrt(fy ** 2 + fx ** 2) * n
    nb = n // 2
    # kx=0 and kx=Nyquist columns hold BOTH members of each conjugate pair
    wt = np.ones(A.shape); wt[:, 0] = 0.5; wt[:, -1] = 0.5
    valid = r < nb
    k = np.minimum(r.astype(np.int32), nb - 1)[valid]
    Av, Bv, wv = A[valid], B[valid], wt[valid]
    num = np.bincount(k, weights=wv * (Av * np.conj(Bv)).real, minlength=nb)
    da = np.bincount(k, weights=wv * (Av * np.conj(Av)).real, minlength=nb)
    db = np.bincount(k, weights=wv * (Bv * np.conj(Bv)).real, minlength=nb)
    den = np.sqrt(da * db)
    out = np.zeros(nb)
    nz = den > 0
    out[nz] = num[nz] / den[nz]
    return out


def frc_at_resolution(curve, n, angpix, res_a):
    """FRC value at a given resolution in Angstrom (nearest ring)."""
    k = n * angpix / res_a
    if k < 1 or k >= len(curve):
        return None
    return float(curve[int(round(k))])


def frc_crossing(curve, threshold, n, angpix, run=3):
    """First resolution where the FRC drops below `threshold` and STAYS below.

    Requires `run` consecutive sub-threshold bins, so one noisy ring cannot
    terminate the search and report a wildly pessimistic resolution.
    """
    for k in range(1, len(curve) - run + 1):
        if curve[k - 1] < threshold:
            continue
        if all(curve[k + j] < threshold for j in range(run)):
            denom = curve[k - 1] - curve[k]
            frac = 0.0 if denom == 0 else (curve[k - 1] - threshold) / denom
            kk = (k - 1) + frac
            return float(n * angpix / kk) if kk > 0 else None
    return None  # agreement holds to Nyquist


def compare_images(a_path, b_path, angpix, crop, margin=64):
    a, ameta = read_mrc(a_path)
    b, bmeta = read_mrc(b_path)
    out = {"motioncorr": ameta, "motioncor3": bmeta,
           "shape_match": (a.shape == b.shape)}
    if not out["shape_match"]:
        out["error"] = f"shape mismatch {a.shape} vs {b.shape}; not comparable"
        return out

    # register on crop+margin, then trim the margin off: a Fourier shift is circular
    big = crop + 2 * margin
    ca, cb = centre_crop(a, big), centre_crop(b, big)
    dy, dx, peak = register_subpixel(ca, cb)
    out["mc3_minus_motioncorr_offset_px"] = {
        "dy": round(-dy, 4), "dx": round(-dx, 4), "phase_corr_peak": round(peak, 6)}
    cb = fourier_shift(cb, dy, dx)
    ca, cb = centre_crop(ca, crop), centre_crop(cb, crop)

    fa, fb = ca.ravel().astype(np.float64), cb.ravel().astype(np.float64)
    s, o = np.polyfit(fa, fb, 1)
    # scale and offset are diagnostics: they surface MotionCor3's positivity clamp
    # and its unweighted DC term in the dose-weighted sum
    out["linear_fit_mc3_vs_mc"] = {"scale": float(s), "offset": float(o)}

    curve = frc(ca.astype(np.float64), cb.astype(np.float64))
    n = crop
    out["frc"] = {
        "crop_px": n,
        "angpix": angpix,
        "nyquist_A": 2 * angpix,
        "at_20A": frc_at_resolution(curve, n, angpix, 20.0),
        "at_10A": frc_at_resolution(curve, n, angpix, 10.0),
        "at_5A": frc_at_resolution(curve, n, angpix, 5.0),
        "at_3A": frc_at_resolution(curve, n, angpix, 3.0),
        "at_nyquist": float(curve[-1]),
        "res_at_0.5_A": frc_crossing(curve, 0.5, n, angpix),
        "mean_to_half_nyquist": float(np.mean(curve[1:n // 4])),
        "curve_decimated": [round(float(v), 4) for v in curve[::max(1, len(curve) // 48)]],
    }
    return out


# ----------------------------------------------------------------------------

def summarise(records, key_path):
    vals = []
    for r in records:
        node = r
        for k in key_path:
            if not isinstance(node, dict) or k not in node:
                node = None
                break
            node = node[k]
        if isinstance(node, (int, float)):
            vals.append(float(node))
    if not vals:
        return None
    vals.sort()
    return {"n": len(vals), "min": vals[0], "median": statistics.median(vals),
            "max": vals[-1],
            "mean": sum(vals) / len(vals)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motioncorr-dir", required=True)
    ap.add_argument("--mc3-dir", required=True)
    ap.add_argument("--mc3-logdir", required=True)
    ap.add_argument("--movies", required=True)
    ap.add_argument("--angpix", type=float, required=True)
    ap.add_argument("--crop", type=int, default=2048)
    ap.add_argument("--json-out", required=True)
    args = ap.parse_args()

    bases = [l.strip() for l in open(args.movies) if l.strip()]
    results = []
    for base in bases:
        rec = {"movie": base}
        pairs = {
            "dose_weighted": (os.path.join(args.motioncorr_dir, "Movies", base + ".mrc"),
                              os.path.join(args.mc3_dir, base + "_DW.mrc")),
            "unweighted":    (os.path.join(args.motioncorr_dir, "Movies", base + "_noDW.mrc"),
                              os.path.join(args.mc3_dir, base + ".mrc")),
        }
        for tag, (pa, pb) in pairs.items():      # independent: one failure must not
            try:                                  # take the other down with it
                if not (os.path.exists(pa) and os.path.exists(pb)):
                    rec[tag] = {"error": "missing input",
                                "motioncorr": os.path.exists(pa),
                                "motioncor3": os.path.exists(pb)}
                    continue
                rec[tag] = compare_images(pa, pb, args.angpix, args.crop)
            except Exception as exc:
                rec[tag] = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            ax, ay = read_relion_global_shift(
                os.path.join(args.motioncorr_dir, "Movies", base + ".star"))
            log = os.path.join(args.mc3_logdir, base + "-Patch-Full.log")
            if not os.path.exists(log):
                log = os.path.join(args.mc3_logdir, base + "-Full.log")
            bx, by = read_mc3_full_log(log)
            rec["trajectory"] = compare_trajectories(ax, ay, bx, by)
            rec["trajectory"]["mc3_log"] = os.path.basename(log)
        except Exception as exc:
            rec["trajectory"] = {"error": f"{type(exc).__name__}: {exc}"}
        results.append(rec)
        print(f"[done] {base}", flush=True)

    summary = {
        "n_movies": len(results),
        "n_with_any_error": sum(
            1 for r in results
            if any(isinstance(r.get(k), dict) and "error" in r[k]
                   for k in ("dose_weighted", "unweighted", "trajectory"))),
        "n_sign_convention_disagree": sum(
            1 for r in results
            if r.get("trajectory", {}).get("sign_convention_agrees") is False),
        "trajectory_rms_px": summarise(results, ["trajectory", "coord_rms_shift_px"]),
        "trajectory_max_px": summarise(results, ["trajectory", "max_shift_diff_px"]),
        "dw_offset_dy_px": summarise(results, ["dose_weighted", "mc3_minus_motioncorr_offset_px", "dy"]),
        "dw_offset_dx_px": summarise(results, ["dose_weighted", "mc3_minus_motioncorr_offset_px", "dx"]),
        "dw_frc_at_10A": summarise(results, ["dose_weighted", "frc", "at_10A"]),
        "dw_frc_at_5A": summarise(results, ["dose_weighted", "frc", "at_5A"]),
        "dw_frc_at_3A": summarise(results, ["dose_weighted", "frc", "at_3A"]),
        "dw_frc_at_nyquist": summarise(results, ["dose_weighted", "frc", "at_nyquist"]),
        "dw_frc_res_at_0.5_A": summarise(results, ["dose_weighted", "frc", "res_at_0.5_A"]),
        "nodw_frc_at_5A": summarise(results, ["unweighted", "frc", "at_5A"]),
        "nodw_frc_at_nyquist": summarise(results, ["unweighted", "frc", "at_nyquist"]),
        "dw_linear_scale": summarise(results, ["dose_weighted", "linear_fit_mc3_vs_mc", "scale"]),
        "nodw_linear_scale": summarise(results, ["unweighted", "linear_fit_mc3_vs_mc", "scale"]),
    }
    with open(args.json_out, "w") as fh:
        json.dump({"summary": summary, "movies": results}, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
