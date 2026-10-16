#!/usr/bin/env python3
"""Decode-coverage smoke runs of the format families on real EMPIAR data (#186 follow-up).

One process per family, global alignment (config G), CPU or --gpu with an ingest
witness. Records exit status, products, per-movie frame count and wall time. Also:
  * 10342 with its SerialEM defect list (expected refusal),
  * 10740 gain orientation search (6 candidates, stripe metric on the product),
  * the compressed families both linked (as setup_corpus.py does) and copied.
Python 3.9, standard library plus NumPy (for the orientation metric only).
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

FAMILIES = {
 "e10500f3": dict(movies=["EMPIAR-10500/data/XFEG-Falcon3/GridSquare_14725129/Data/FoilHole_14730491_Data_14726927_14726929_20200316_135927_Fractions.tif",
                          "EMPIAR-10500/data/XFEG-Falcon3/GridSquare_14725129/Data/FoilHole_14730491_Data_14731585_14731587_20200316_140015_Fractions.tif"],
                  angpix=0.827, voltage=300, frames=60, dose=1.0),
 "e10342": dict(movies=["EMPIAR-10342/data/Movies/190830/bna_h1_s1_i0001_movie_Aug30_21.13.54.tif",
                        "EMPIAR-10342/data/Movies/190830/bna_h1_s1_i0001_movie_Aug30_22.52.32.tif"],
                angpix=1.1, voltage=300, frames=50, dose=1.0, gain="EMPIAR-10342/data/Movies/GainRef/190830_gainref.mrc"),
 "e10740": dict(movies=["EMPIAR-10740/data/EMPIAR_sjojoa/frames/19may24k/rawdata/19may24k_1_00001gr_00001sq_00002hl_00002ed.frames.mrc",
                        "EMPIAR-10740/data/EMPIAR_sjojoa/frames/19may24k/rawdata/19may24k_1_00001gr_00001sq_00002hl_00003ed.frames.mrc"],
                angpix=1.03, voltage=300, frames=43, dose=1.16, gain="EMPIAR-10740/data/EMPIAR_sjojoa/gains/19may24k_ref.mrc",
                gain_opts=None),
 "e10374": dict(movies=["EMPIAR-10374/data/Movies/2017-05-04/May04_14.24.37.mrc", "EMPIAR-10374/data/Movies/2017-05-04/May04_14.25.55.mrc"],
                angpix=0.42, voltage=300, frames=50, dose=1.0),
 "e11217": dict(movies=["EMPIAR-11217/data/Compressed-frames/stack_0015.mrcs.bz2", "EMPIAR-11217/data/Compressed-frames/stack_0016.mrcs.bz2"],
                angpix=0.25955, voltage=300, frames=32, dose=1.0, compressed=True),
 "e10202": dict(movies=["EMPIAR-10202/data/01_Raw_Frames_Compressed/17aug31d_00001sq_v01_00002hl_00002ed3.frames.mrc.zst",
                        "EMPIAR-10202/data/01_Raw_Frames_Compressed/17aug31d_00001sq_v01_00002hl_00003ed3.frames.mrc.zst"],
                angpix=0.394, voltage=300, frames=70, dose=1.0, compressed=True),
 "e10666": dict(movies=["EMPIAR-10666/data/eTG-movies-EMPIAR/FoilHole_16376725_Data_16377678_16377679_20171016_1214-38093.tif",
                        "EMPIAR-10666/data/eTG-movies-EMPIAR/FoilHole_16376725_Data_16377702_16377703_20171016_1213-38091.tif"],
                angpix=1.043, voltage=300, frames=40, dose=1.0, gain="EMPIAR-10666/data/eTG-movies-EMPIAR/gain-reference.mrc"),
 "e11404": dict(movies=["EMPIAR-11404/data/20221014_76242_12_8_integrated_movie.tif", "EMPIAR-11404/data/20221014_76243_13_1_integrated_movie.tif"],
                angpix=0.387, voltage=300, frames=45, dose=1.0, gain="EMPIAR-11404/data/gain.mrc"),
}
STAR = ("# version 30001\n\ndata_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n_rlnMicrographOriginalPixelSize #3\n"
        "_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\nopticsGroup1 1 %.5f %.1f 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n")


def setup(run, fam, data, copy):
    if run.exists():
        shutil.rmtree(run)
    (run / "Movies").mkdir(parents=True)
    for m in fam["movies"]:
        dst = run / "Movies" / Path(m).name
        (shutil.copyfile if copy else os.symlink)(str(data / m), str(dst))
    for key in ("gain", "defect"):
        if fam.get(key):
            os.symlink(str(data / fam[key]), str(run / Path(fam[key]).name))
    (run / "movies.star").write_text(STAR % (fam["angpix"], fam["voltage"])
                                     + "".join("Movies/%s 1\n" % Path(m).name for m in fam["movies"]))


def run_mc(binary, run, fam, extra, threads, witness):
    opts = ["--use_own", "--j", str(threads), "--dose_weighting", "--dose_per_frame", str(fam["dose"]),
            "--bfactor", "150", "--seed", "1", "--expected_frames", str(fam["frames"]), "--skip_logfile"]
    if fam.get("gain"):
        opts += ["--gainref", Path(fam["gain"]).name] + list(fam.get("gain_opts") or [])
    if witness:
        opts += ["--ingest_witness", "witness.txt"]
    cmd = [str(binary), "--i", "movies.star", "--o", "out/"] + opts + list(extra)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(run), capture_output=True, text=True,
                       env=dict(os.environ, OMP_NUM_THREADS=str(threads)))
    wall = time.time() - t0
    (run / "stdout.txt").write_text(r.stdout + r.stderr)
    prods = sorted(p.name for p in (run / "out" / "Movies").glob("*.mrc")) if (run / "out" / "Movies").exists() else []
    frames = {}
    for log in (run / "out" / "Movies").glob("*.log") if (run / "out" / "Movies").exists() else []:
        m = re.search(r"Movie size: X = (\d+) Y = (\d+) N = (\d+)", log.read_text(errors="replace"))
        if m:
            frames[log.stem] = [int(m.group(1)), int(m.group(2)), int(m.group(3))]
    errs = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "ERROR" in l or "rror in" in l or "failed" in l.lower()]
    routes = (run / "witness.txt").read_text().split("\n") if witness and (run / "witness.txt").exists() else []
    return dict(cmd=" ".join(cmd), rc=r.returncode, wall_s=round(wall, 2), products=prods, frames=frames,
                errors=sorted(set(errs))[:6], routes=[x for x in routes if x])


def stripe_metric(mrc):
    import numpy as np
    d = mrc.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", d[:16])
    a = np.frombuffer(d[1024:1024 + nx * ny * 4], "<f4").reshape(ny, nx).astype(np.float64)
    a = (a - a.mean()) / a.std()
    # Fixed-pattern residue from a misoriented gain shows up as row/column structure.
    return float(np.std(a.mean(axis=0)) + np.std(a.mean(axis=1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True, type=Path)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", required=True, type=Path)
    a = ap.parse_args()
    extra = ["--gpu", "0"] if a.gpu else []
    res = {}
    fams = {k: v for k, v in FAMILIES.items() if not a.only or re.search(a.only, k)}
    if "e10740" in fams:
        # Orientation search on the first movie only: 6 candidates that give 3838 x 3710.
        f = dict(fams["e10740"]); f["movies"] = f["movies"][:1]; f["frames"] = 43
        scores = {}
        for rot in (1, 3):
            for flip in (0, 1, 2):
                run = a.work / ("e10740_gain_rot%d_flip%d" % (rot, flip))
                f["gain_opts"] = ["--gain_rot", str(rot), "--gain_flip", str(flip)]
                setup(run, f, a.data, False)
                r = run_mc(a.binary, run, f, extra, a.threads, a.gpu)
                p = run / "out" / "Movies" / (Path(f["movies"][0]).name.replace(".frames.mrc", ".frames") + ".mrc")
                prods = list((run / "out" / "Movies").glob("*.mrc"))
                r["stripe_metric"] = stripe_metric(prods[0]) if prods else None
                scores["rot%d_flip%d" % (rot, flip)] = r
                print("e10740 gain", rot, flip, r["rc"], r["stripe_metric"], flush=True)
        best = min((k for k in scores if scores[k]["stripe_metric"] is not None), key=lambda k: scores[k]["stripe_metric"])
        res["e10740_gain_search"] = dict(candidates=scores, best=best)
        rot, flip = int(best[3]), int(best[-1])
        fams["e10740"]["gain_opts"] = ["--gain_rot", str(rot), "--gain_flip", str(flip)]
        # Without rotation the gain shape does not match: record the refusal.
        run = a.work / "e10740_gain_unrotated"
        g = dict(fams["e10740"]); g["gain_opts"] = []; g["movies"] = g["movies"][:1]
        setup(run, g, a.data, False)
        res["e10740_gain_unrotated"] = run_mc(a.binary, run, g, extra, a.threads, a.gpu)
    for name, fam in fams.items():
        for copy in ((False, True) if fam.get("compressed") else (False,)):
            key = name + ("_copied" if copy else "")
            run = a.work / key
            setup(run, fam, a.data, copy)
            res[key] = run_mc(a.binary, run, fam, extra, a.threads, a.gpu)
            print(key, json.dumps({k: res[key][k] for k in ("rc", "wall_s", "products", "frames", "errors", "routes")}), flush=True)
    if "e10342" in fams:
        run = a.work / "e10342_serialem_defect"
        f = dict(fams["e10342"]); f["defect"] = "EMPIAR-10342/data/Movies/Defect/190830_defects.txt"
        setup(run, f, a.data, False)
        res["e10342_serialem_defect"] = run_mc(a.binary, run, f, extra + ["--defect_file", "190830_defects.txt"], a.threads, a.gpu)
        print("e10342_serialem_defect", res["e10342_serialem_defect"]["rc"], res["e10342_serialem_defect"]["errors"][:2])
    a.json.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
