#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Quick checks on cut-down real movies, one per corpus family (opt-in).

The assets (test-data/real_cutdown_manifest.json) are a few frames of real EMPIAR
movies in their producers' exact encodings: EPU and SerialEM TIFF (LZW, Deflate,
old Deflate, signed, float), MRC modes 0/1/2/6/101, bzip2 and zstd MRC, and EPU
EER with its .gain. They are not versioned; fetch them with --download (a release
URL) or point --assets at a copy. Per item:

  files    SHA-256 of every file matches the manifest
  decode   SHA-256 of MotionCorr's decoded samples matches (runner_numerics;
           decoding is exact, so this is portable)
  run      motioncorr with the family's options exits 0 with a product and the
           expected frame count
  refuse   where listed (EMPIAR-10342's SerialEM defect list), the run is refused

CTest registers this as RealCutdown only when MC_REAL_CUTDOWN_DIR is set.
"""
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAR = ("# version 30001\n\ndata_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n_rlnMicrographOriginalPixelSize #3\n"
        "_rlnVoltage #4\n_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\nopticsGroup1 1 %s %s 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\nMovies/%s 1\n")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(base, rel, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Release assets are flat: the item directory is folded into the asset name.
    url = base.rstrip("/") + "/" + rel.replace("/", "__")
    with urllib.request.urlopen(url, timeout=120) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def opt(options, flag):
    return options[options.index(flag) + 1] if flag in options else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--helper", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=ROOT / "test-data" / "real_cutdown_manifest.json")
    ap.add_argument("--download", help="release base URL; missing assets are fetched into --assets")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--allow-unrun", action="append", default=[])
    a = ap.parse_args()
    man = json.loads(a.manifest.read_text())
    rows, fatal = [], False

    def report(item, check, status, detail=""):
        nonlocal fatal
        rows.append((item, check, status, detail))
        if status == "FAIL":
            fatal = True
        print("%-28s %-7s %-6s %s" % (item, check, status, detail), flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="mc-cutdown-"))
    try:
        for it in man["items"]:
            if a.only and not re.search(a.only, it["id"]):
                continue
            missing = [t for t in it.get("requires", []) if shutil.which(t) is None]
            if missing:
                report(it["id"], "-", "UNRUN", "needs " + ", ".join(missing))
                fatal |= not all(t in a.allow_unrun for t in missing)
                continue
            ok = True
            for f in it["files"]:
                p = a.assets / f["path"]
                if not p.exists() and a.download:
                    fetch(a.download, f["path"], p)
                if not p.exists():
                    report(it["id"], "files", "FAIL", "missing " + f["path"]); ok = False; break
                if sha256(p) != f["sha256"]:
                    report(it["id"], "files", "FAIL", "SHA-256 mismatch " + f["path"]); ok = False; break
            if not ok:
                continue
            report(it["id"], "files", "PASS")
            movie = a.assets / it["movie"]
            dump = tmp / "dump.bin"
            src = movie
            if movie.name.endswith((".bz2", ".zst", ".xz")):
                src = tmp / movie.name.rsplit(".", 1)[0]
                dec = {"bz2": ["bzip2", "-dc"], "zst": ["zstd", "-dc"], "xz": ["xz", "-dc"]}[movie.name.rsplit(".", 1)[1]]
                with open(src, "wb") as out:
                    subprocess.run(dec + [str(movie)], stdout=out, check=True)
            if movie.name.endswith(".eer"):
                cmd = [str(a.helper), "render_eer", str(src), str(dump), "1", str(it["eer_grouping"])]
            else:
                cmd = [str(a.helper), "read_tiff_raw", str(src), str(dump)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            got = sha256(dump) if r.returncode == 0 else None
            report(it["id"], "decode", "PASS" if got == it["decoded"]["sha256"] else "FAIL",
                   "" if got == it["decoded"]["sha256"] else ("helper rc %d" % r.returncode if got is None else "decoded samples differ"))
            if src != movie:
                src.unlink()
            run = tmp / it["id"]
            (run / "Movies").mkdir(parents=True)
            (shutil.copyfile if it.get("copy") else os.symlink)(str(movie), str(run / "Movies" / movie.name))
            for f in it["files"][1:]:
                os.symlink(str(a.assets / f["path"]), str(run / Path(f["path"]).name))
            o = it["options"]
            (run / "movies.star").write_text(STAR % (opt(o, "--angpix"), opt(o, "--voltage"), movie.name))
            n = it["decoded"]["n"]
            base = [str(a.binary), "--i", "movies.star", "--use_own", "--j", str(a.threads), "--seed", "1",
                    "--skip_logfile", "--expected_frames", str(n)] + [x for x in o]
            r = subprocess.run(base + ["--o", "out/"], cwd=run, capture_output=True, text=True,
                               env=dict(os.environ, OMP_NUM_THREADS=str(a.threads)))
            prods = list((run / "out" / "Movies").glob("*.mrc")) if (run / "out").exists() else []
            frames = None
            for log in (run / "out" / "Movies").glob("*.log") if prods else []:
                m = re.search(r"Movie size: X = \d+ Y = \d+ N = (\d+)", log.read_text(errors="replace"))
                frames = int(m.group(1)) if m else None
            good = r.returncode == 0 and len(prods) == 1 and frames == n
            report(it["id"], "run", "PASS" if good else "FAIL",
                   "" if good else "rc %d, products %d, frames %s" % (r.returncode, len(prods), frames))
            if it.get("refuse"):
                rf = it["refuse"]
                r = subprocess.run(base + ["--o", "refused/"] + rf["options"], cwd=run, capture_output=True, text=True)
                published = list((run / "refused").rglob("*.mrc")) if (run / "refused").exists() else []
                good = r.returncode > 0 and rf["substring"] in (r.stdout + r.stderr) and not published
                report(it["id"], "refuse", "PASS" if good else "FAIL", "" if good else "rc %d, %d products written" % (
                    r.returncode, len(published)))
            shutil.rmtree(run, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    counts = {}
    for r in rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print("summary:", ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
