#!/usr/bin/env python3
"""W-DIAG-S1 analysis of one reference/test run pair (normally CPU vs CUDA).

Reads only products and logs; changes nothing. Reports:
  - per-patch convergence for each attempt (from the per-movie log),
  - the patch sets that entered the polynomial fit (STAR data_local_shift),
  - per-patch trajectory differences for patches both sides kept,
  - fitted _rlnMotionModelCoeff values and the displacement-field difference,
  - counterfactual refits: the reference's observations restricted to the
    test's patch set (and vice versa), fitted the same way as
    motioncorr_runner.cpp (18-term model, least squares),
  - a tile map of the corrected-image difference.
"""
import argparse, json, math, re, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_motioncorr import parse_mrc  # noqa: E402

PATCH_RE = re.compile(r"^Patch \((\d+), (\d+)\): \d+ / \d+.*Center = \((\d+), (\d+)\)")
ITER_RE = re.compile(r"^ Iteration (\d+): RMSD = ([0-9.eE+-]+) px")
CONV_RE = re.compile(r"\[CUDA Patch Alignment\] completed; converged=(yes|no)")
FIT_RE = re.compile(r"Polynomial fit RMSD: X = ([0-9.eE+-]+) px Y = ([0-9.eE+-]+) px")
TOL = 0.5


def parse_log(path):
    patches, cur, in_local, fit = {}, None, False, None
    attempt = None
    for line in open(path, errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("Local alignments:"):
            in_local = True
            continue
        m = FIT_RE.search(line)
        if m:
            fit = (float(m.group(1)), float(m.group(2)))
        if not in_local:
            continue
        m = PATCH_RE.match(line)
        if m:
            cur = (int(m.group(1)), int(m.group(2)))
            patches[cur] = {"center": (int(m.group(3)), int(m.group(4))), "attempts": []}
            attempt = None
            continue
        if cur is None:
            continue
        m = ITER_RE.match(line)
        if m:
            if attempt is None or attempt.get("closed"):
                attempt = {"rmsd": []}
                patches[cur]["attempts"].append(attempt)
            attempt["rmsd"].append(float(m.group(2)))
            continue
        m = CONV_RE.search(line)
        if m and attempt is not None:
            attempt["converged_logged"] = m.group(1) == "yes"
            attempt["closed"] = True
    for p in patches.values():
        for a in p["attempts"]:
            a["converged"] = a.get("converged_logged", bool(a["rmsd"]) and a["rmsd"][-1] < TOL)
            a.pop("closed", None)
        p["final_converged"] = bool(p["attempts"]) and p["attempts"][-1]["converged"]
    return patches, fit


def star_loop(text, block):
    m = re.search(r"data_%s\s*\n(.*?)(?=\n# version|\ndata_|\Z)" % block, text, re.S)
    if not m:
        return [], []
    cols, rows = [], []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith("_rln"):
            cols.append(s.split()[0])
        elif s and not s.startswith("loop_") and cols:
            rows.append([float(x) for x in s.split()])
    return cols, np.array(rows)


def parse_star(path):
    t = open(path).read()
    _, g = star_loop(t, "global_shift")
    _, c = star_loop(t, "local_motion_model")
    _, l = star_loop(t, "local_shift")
    coeffs = c[:, 1] if len(c) else None
    local = {}
    if len(l):
        for f, x, y, sx, sy in l:
            local.setdefault((int(x), int(y)), []).append((f, sx, sy))
    local = {k: np.array(v) for k, v in local.items()}
    return {"global": g, "coeffs": coeffs, "local": local}


def design(xc, yc, z, nx, ny):
    x = xc / nx - 0.5
    y = yc / ny - 0.5
    z2, z3 = z * z, z * z * z
    cols = []
    for s in (np.ones_like(x), x, x * x, y, y * y, x * y):
        cols += [s * z, s * z2, s * z3]
    return np.stack(cols, axis=1)


def refit(local, keys, nx, ny):
    xs, ys, zs, vx, vy = [], [], [], [], []
    for k in keys:
        a = local[k]
        n = len(a)
        xs += [k[0]] * n; ys += [k[1]] * n
        zs += list(a[:, 0] - 1 + 0.5)  # STAR frame = middle_frame + first_frame_sum, printed as int
        vx += list(a[:, 1]); vy += list(a[:, 2])
    A = design(np.array(xs, float), np.array(ys, float), np.array(zs, float), nx, ny)
    cx = np.linalg.lstsq(A, np.array(vx), rcond=None)[0]
    cy = np.linalg.lstsq(A, np.array(vy), rcond=None)[0]
    return np.concatenate([cx, cy])


def field(coeffs, nx, ny, nframes, grid=33):
    g = np.linspace(0, 1, grid)
    X, Y = np.meshgrid(g, g)
    out = np.zeros((nframes, grid, grid, 2))
    for z in range(nframes):
        A = design(X.ravel() * nx + nx / 2 * 0 + 0, Y.ravel() * ny, np.full(X.size, float(z)), nx, ny)
        # design() subtracts 0.5 after dividing by n, so pass pixel coordinates
        out[z, :, :, 0] = (A @ coeffs[:18]).reshape(grid, grid)
        out[z, :, :, 1] = (A @ coeffs[18:]).reshape(grid, grid)
    return out


def tile_map(ref, test, tiles):
    d = test.astype(np.float64) - ref.astype(np.float64)
    ny, nx = d.shape
    ty, tx = ny // tiles, nx // tiles
    sq = np.zeros((tiles, tiles))
    for i in range(tiles):
        for j in range(tiles):
            sq[i, j] = np.sum(d[i * ty:(i + 1) * ty, j * tx:(j + 1) * tx] ** 2)
    sigma = ref.astype(np.float64).std()
    rms = np.sqrt(sq / (ty * tx)) / sigma
    return rms, sq / sq.sum(), float(np.sqrt(np.mean(d ** 2)) / sigma), sigma


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="run dir (reference, CPU)")
    ap.add_argument("--test", required=True, help="run dir (test, CUDA)")
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--no-image", action="store_true")
    a = ap.parse_args()
    R, T = Path(a.ref), Path(a.test)

    def one(run):
        mv = run / "Movies"
        log = next(mv.glob("*.log")); star = next(p for p in mv.glob("*.star"))
        mrc = next(mv.glob("*.mrc"), None)
        return log, star, mrc

    (rl, rs, rm), (tl, ts, tm) = one(R), one(T)
    rp, rfit = parse_log(rl)
    tp, tfit = parse_log(tl)
    rS, tS = parse_star(rs), parse_star(ts)
    t = open(rs).read()
    nx = int(re.search(r"_rlnImageSizeX\s+(\d+)", t).group(1))
    ny = int(re.search(r"_rlnImageSizeY\s+(\d+)", t).group(1))
    nz = int(re.search(r"_rlnImageSizeZ\s+(\d+)", t).group(1))

    res = {"ref": str(R), "test": str(T), "nx": nx, "ny": ny, "frames": nz,
           "fit_rmsd_ref": rfit, "fit_rmsd_test": tfit}
    # global
    g = rS["global"][:, 1:] - tS["global"][:, 1:]
    res["global_shift_rms_px"] = float(np.sqrt(np.mean(np.sum(g ** 2, axis=1))))
    res["global_shift_max_px"] = float(np.max(np.abs(g)))

    # per patch convergence
    rows = []
    for k in sorted(rp):
        a_, b_ = rp[k], tp.get(k)
        rows.append({
            "patch": k, "center": a_["center"],
            "ref_attempts": [[round(x, 4) for x in at["rmsd"]] for at in a_["attempts"]],
            "test_attempts": [[round(x, 4) for x in at["rmsd"]] for at in b_["attempts"]] if b_ else None,
            "ref_converged": a_["final_converged"], "test_converged": b_["final_converged"] if b_ else None,
            "ref_iter1": a_["attempts"][0]["rmsd"][0] if a_["attempts"] else None,
            "test_iter1": b_["attempts"][0]["rmsd"][0] if b_ and b_["attempts"] else None,
            "test_retry_identical": (len(b_["attempts"]) > 1 and
                                     b_["attempts"][0]["rmsd"] == b_["attempts"][1]["rmsd"]) if b_ else None,
        })
    res["patches"] = rows
    ref_keys = set(rS["local"]); test_keys = set(tS["local"])
    res["n_patches_kept"] = {"ref": len(ref_keys), "test": len(test_keys)}
    res["kept_only_ref"] = sorted(ref_keys - test_keys)
    res["kept_only_test"] = sorted(test_keys - ref_keys)
    res["convergence_flips"] = [r["patch"] for r in rows if r["ref_converged"] != r["test_converged"]]
    # log-derived and STAR-derived patch sets must agree
    center_of = {k: tuple(v["center"]) for k, v in rp.items()}
    res["log_star_consistent"] = (
        {center_of[k] for k, v in rp.items() if v["final_converged"]} == ref_keys and
        {tuple(v["center"]) for k, v in tp.items() if v["final_converged"]} == test_keys)

    common = sorted(ref_keys & test_keys)
    pd = []
    for k in common:
        d = rS["local"][k][:, 1:] - tS["local"][k][:, 1:]
        pd.append({"center": k, "rms_px": float(np.sqrt(np.mean(np.sum(d ** 2, axis=1)))),
                   "max_px": float(np.max(np.abs(d)))})
    res["common_patch_traj_diff"] = pd
    res["common_patch_traj_diff_max_px"] = max((x["max_px"] for x in pd), default=None)

    # coefficients and counterfactual fits
    if rS["coeffs"] is not None and tS["coeffs"] is not None:
        rc, tc = rS["coeffs"], tS["coeffs"]
        res["coeffs_ref"] = rc.tolist(); res["coeffs_test"] = tc.tolist()
        rc_fit = refit(rS["local"], sorted(ref_keys), nx, ny)
        tc_fit = refit(tS["local"], sorted(test_keys), nx, ny)
        cf_ref_on_test_set = refit(rS["local"], sorted(ref_keys & test_keys), nx, ny)
        cf_test_on_ref_set = None
        if ref_keys - test_keys and not (test_keys - ref_keys):
            pass
        fr, ft = field(rc, nx, ny, nz), field(tc, nx, ny, nz)
        f_rfit, f_tfit = field(rc_fit, nx, ny, nz), field(tc_fit, nx, ny, nz)
        f_cf = field(cf_ref_on_test_set, nx, ny, nz)
        f_cf_t = field(refit(tS["local"], sorted(ref_keys & test_keys), nx, ny), nx, ny, nz)

        def mag(f):
            return np.sqrt(np.sum(f ** 2, axis=-1))
        res["refit_reproduces_star_coeffs_max_px"] = {
            "ref": float(mag(f_rfit - fr).max()), "test": float(mag(f_tfit - ft).max())}
        res["model_field_diff_ref_vs_test_px"] = {"max": float(mag(fr - ft).max()),
                                                  "rms": float(np.sqrt(np.mean(mag(fr - ft) ** 2)))}
        res["model_field_diff_when_both_fit_common_patches_px"] = {
            "max": float(mag(f_cf - f_cf_t).max()), "rms": float(np.sqrt(np.mean(mag(f_cf - f_cf_t) ** 2)))}
        res["model_field_diff_ref_obs_common_set_vs_test_px"] = {
            "max": float(mag(f_cf - ft).max()), "rms": float(np.sqrt(np.mean(mag(f_cf - ft) ** 2)))}
        res["model_field_max_abs_px"] = {"ref": float(mag(fr).max()), "test": float(mag(ft).max())}
        # where the field difference is largest (last frame), on a 5x5 summary grid
        last = mag(fr - ft)[-1]
        g5 = np.array([[last[int(i * 32 / 4)][int(j * 32 / 4)] for j in range(5)] for i in range(5)])
        res["model_field_diff_last_frame_5x5_corners_px"] = np.round(g5, 2).tolist()
        # residual of the kept patches against each model (pathology check)
        for name, S_, c_ in (("ref", rS, rc), ("test", tS, tc)):
            per = []
            for k, arr in S_["local"].items():
                A = design(np.full(len(arr), k[0], float), np.full(len(arr), k[1], float), arr[:, 0] - 0.5, nx, ny)
                rx = arr[:, 1] - A @ c_[:18]; ry = arr[:, 2] - A @ c_[18:]
                per.append((k, float(np.sqrt(np.mean(rx ** 2 + ry ** 2))), float(np.max(np.hypot(rx, ry)))))
            per.sort(key=lambda x: -x[1])
            res["fit_residual_by_patch_%s" % name] = [{"center": k, "rms_px": round(r, 3), "max_px": round(m, 3)} for k, r, m in per]
    else:
        res["coeffs_ref"] = None if rS["coeffs"] is None else rS["coeffs"].tolist()
        res["coeffs_test"] = None if tS["coeffs"] is None else tS["coeffs"].tolist()

    if not a.no_image and rm and tm:
        rh, ri, _ = parse_mrc(rm)
        th, ti, _ = parse_mrc(tm)
        ri = ri.reshape(rh["ny"], rh["nx"]); ti = ti.reshape(th["ny"], th["nx"])
        rms5, share5, rel, sigma = tile_map(ri, ti, 5)
        rms16, share16, _, _ = tile_map(ri, ti, 16)
        res["image_relative_rmse"] = rel
        res["image_sigma_ref"] = sigma
        res["tile5_relative_rms"] = np.round(rms5, 4).tolist()
        res["tile5_share_of_sq_error"] = np.round(share5, 4).tolist()
        s16 = np.sort(share16.ravel())[::-1]
        res["tile16_top_share"] = {"top1": float(s16[0]), "top8": float(s16[:8].sum()), "top32": float(s16[:32].sum())}
    json.dump(res, open(a.json_out, "w"), indent=1, default=lambda o: list(o) if isinstance(o, tuple) else str(o))
    # short human summary
    print("== %s vs %s" % (R.name, T.name))
    print(" global shift rms/max px: %.4f / %.4f" % (res["global_shift_rms_px"], res["global_shift_max_px"]))
    print(" patches kept ref/test: %s; only-ref %s only-test %s; flips %s; log/star consistent %s" % (
        res["n_patches_kept"], res["kept_only_ref"], res["kept_only_test"], res["convergence_flips"], res["log_star_consistent"]))
    print(" common-patch trajectory diff max px: %s" % res["common_patch_traj_diff_max_px"])
    print(" fit RMSD ref/test: %s / %s" % (rfit, tfit))
    for k in ("refit_reproduces_star_coeffs_max_px", "model_field_diff_ref_vs_test_px",
              "model_field_diff_when_both_fit_common_patches_px", "model_field_max_abs_px",
              "image_relative_rmse", "tile5_share_of_sq_error", "tile16_top_share"):
        if k in res:
            print(" %s: %s" % (k, res[k]))


if __name__ == "__main__":
    main()
