#!/usr/bin/env python3
"""Create the run directory + case JSON for one matrix case.

Usage: mkcase.py NAME FAMILY [--g G] [--up U] [--gain] [--frames A B] [--cfg L|G] [--binary B] [extra opts...]
FAMILY: f3 | f4 | g (12963).  Movies are symlinks to the read-only corpus.
"""
import argparse, json, os, pathlib, sys
ROOT = pathlib.Path("/mnt/clathrin/alex-motioncorr-rc0/W-EER-Q")
D = pathlib.Path("/home/alex/motioncorr-validation-20261011-vm/corpus/data-https")
FAM = {
 "f3": dict(movie=D/"EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer", nfr=2331, angpix=1.06, dose=1.0, gain=None, g=40),
 "f4": dict(movie=D/"EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer", nfr=5782, angpix=1.64, dose=1.0, gain=None, g=40),
 "g":  dict(movie=D/"EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer", nfr=1911, angpix=0.97, dose=1.282051, gain=D/"EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain", g=49),
}
BIN = {"cuda": str(ROOT/"build/cuda-nvcomp/motioncorr"), "cpu": str(ROOT/"build/cpu-1db86902/motioncorr")}

def make_star(indir, names, angpix):
    star = ['# version 30001', '', 'data_optics', '', 'loop_',
            '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2', '_rlnMicrographOriginalPixelSize #3',
            '_rlnVoltage #4', '_rlnSphericalAberration #5', '_rlnAmplitudeContrast #6',
            'opticsGroup1 1 %s 300 2.7 0.1' % angpix, '',
            '# version 30001', '', 'data_movies', '', 'loop_',
            '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2'] + ['%s 1' % n for n in names] + ['']
    (indir / "movies.star").write_text('\n'.join(star))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name"); ap.add_argument("family")
    ap.add_argument("--g", type=int); ap.add_argument("--up", type=int, default=1)
    ap.add_argument("--gain", action="store_true"); ap.add_argument("--frames", nargs=2, type=int)
    ap.add_argument("--cfg", default="L"); ap.add_argument("--binary", default="cuda")
    ap.add_argument("--arms", default="auto,float"); ap.add_argument("--j", type=int, default=8)
    ap.add_argument("--movie", nargs="+"); ap.add_argument("--shape", nargs=2, type=int)
    ap.add_argument("--no-expected", action="store_true")
    ap.add_argument("--desc", default="")
    ap.add_argument("--keep-mrc", action="store_true")
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--no-compare", action="store_true")
    a, extra = ap.parse_known_args()
    f = FAM[a.family]; g = a.g or f["g"]
    indir = ROOT/"runs"/a.name/"in"; (indir/"Movies").mkdir(parents=True, exist_ok=True)
    srcs = [pathlib.Path(m).resolve() for m in a.movie] if a.movie else [f["movie"]]
    mvs = []
    for i, src in enumerate(srcs):
        mv = "Movies/movie.eer" if len(srcs) == 1 else "Movies/movie%d.eer" % (i + 1)
        link = indir/mv
        if link.is_symlink() or link.exists(): link.unlink()
        os.symlink(src, link); mvs.append(mv)
    angpix = f["angpix"] / (2 ** (a.up - 1)) if a.up > 0 else f["angpix"] * 2
    make_star(indir, mvs, angpix)
    nx = 4096 << (a.up-1) if a.up > 0 else 2048
    shape = (a.shape + [1]) if a.shape else [nx, nx, 1]
    (indir/"manifest.json").write_text(json.dumps({"schema_version": 1, "expected_shape_xyz": shape, "joint_star": "corrected_micrographs.star", "movies": mvs}))
    opts = ["--use_own", "--dose_weighting", "--dose_per_frame", str(f["dose"]), "--bfactor", "150", "--seed", "1",
            "--j", str(a.j), "--gpu", a.gpu, "--eer_grouping", str(g), "--eer_upsampling", str(a.up), "--angpix", str(angpix) if False else None]
    opts = [o for o in opts if o is not None and o != "--angpix"]
    opts = [o for o in opts]
    if not a.no_expected:
        opts += ["--expected_frames", str(f["nfr"] // g)]
    if a.cfg == "L": opts += ["--patch_x", "5", "--patch_y", "5"]
    if a.gain:
        gl = indir/"gain.gain"
        if gl.is_symlink() or gl.exists(): gl.unlink()
        os.symlink(f["gain"], gl); opts += ["--gainref", "gain.gain"]
    if a.frames: opts += ["--first_frame_sum", str(a.frames[0]), "--last_frame_sum", str(a.frames[1])]
    opts += extra
    arms = [{"name": x, "ingest": (None if x == "default" else x)} for x in a.arms.split(",")]
    case = {"name": a.name, "desc": a.desc, "binary": BIN[a.binary], "options": opts, "arms": arms,
            "compare": None if a.no_compare else [arms[0]["name"], arms[1]["name"]], "keep_mrc": a.keep_mrc, "witness": a.binary == "cuda"}
    (ROOT/"cases").mkdir(exist_ok=True)
    (ROOT/"cases"/f"{a.name}.json").write_text(json.dumps(case, indent=1))
    print(json.dumps(case["options"]))
main()
