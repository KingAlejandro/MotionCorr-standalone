#!/usr/bin/env python3
"""W-MRC-Q item 1: real EMPIAR movies, --ingest auto vs --ingest float, configs G and L.

Products are compared with tools/profiling/lib/identity.py (complete MRC header, extended
header and payload; STAR/EPS after root normalisation; .log and .pdf inventoried only).
Bulk outputs are removed after comparison; logs, STAR, witness and the JSON verdict stay.

    real_data_identity.py --binary WRAPPER --gpu 0 --inputs DIR --work DIR --out results.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "profiling"))
from lib import identity  # noqa: E402

FAMILIES = [  # docs/workload_corpus/families.json values
    dict(id="e10164", file="10164_TS_01_000_0.0.mrc", mode=0, frames=8, angpix=0.675, expect="compact"),
    dict(id="e10216", file="10216_1739_Fractions.mrc", mode=1, frames=59, angpix=0.517, expect="compact"),
    dict(id="e10028", file="10028_031_movie.mrcs", mode=2, frames=16, angpix=1.34, expect="float"),
]
STAR = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 %s 300 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/%s 1
"""


def movie_log(arm):
    """Per-movie log text; it records whether the resident CUDA session ran (in-VRAM FFT lines)."""
    return "".join(p.read_text() for p in sorted((Path(arm["dir"]) / "out").rglob("*.log")))


def run_arm(binary, gpu, fam, config, ingest, work, inputs, cpu=False, extra=(), rss=False):
    d = Path(work) / fam["id"] / config / ingest
    if d.exists():
        shutil.rmtree(d)
    (d / "Movies").mkdir(parents=True)
    name = Path(fam["file"]).name.split("_", 1)[1]
    name = name if name.endswith(".mrcs") else name[:-4] + ".mrcs"
    os.symlink(Path(inputs).resolve() / fam["file"], d / "Movies" / name)
    (d / "movies.star").write_text(STAR % (fam["angpix"], name))
    out = d / "out"
    out.mkdir()
    witness = d / "witness.txt"
    cmd = [str(binary), "--i", "movies.star", "--o", str(out) + "/", "--use_own", "--dose_weighting",
           "--dose_per_frame", "1.0", "--bfactor", "150", "--seed", "1", "--expected_frames", str(fam["frames"]),
           "--j", "8"]
    if not cpu:
        cmd += ["--gpu", str(gpu), "--ingest", ingest, "--ingest_witness", str(witness)]
    if config == "L":
        cmd += ["--patch_x", "5", "--patch_y", "5"]
    cmd += list(extra)
    env = dict(os.environ)
    rss_file = d / "peak_rss_kib.txt"
    if rss:
        env["MC_RSS_FILE"] = str(rss_file)
    t0 = time.time()
    res = subprocess.run(cmd, cwd=d, capture_output=True, text=True, env=env)
    (d / "stdout_stderr.txt").write_text(res.stdout + res.stderr)
    wit = [l.split()[-1] for l in witness.read_text().split("\n") if l] if witness.exists() else []
    peak = int(rss_file.read_text().strip().split()[-1]) if rss and rss_file.exists() and \
        rss_file.read_text().strip().split()[-1].isdigit() else None
    return {"peak_rss_kib": peak, "products": sorted(os.path.relpath(os.path.join(r, f), out)
                                                      for r, _, fs in os.walk(out) for f in fs),
            "text": res.stdout + res.stderr, "rc": res.returncode, "wall_s_incl_lock_wait": round(time.time() - t0, 1), "witness": wit,
            "out": str(out), "dir": str(d), "cmd": " ".join(cmd)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--families", default="e10164,e10216,e10028")
    ap.add_argument("--configs", default="G,L")
    ap.add_argument("--extra", default="", help="extra motioncorr options, space separated")
    ap.add_argument("--tag", default="", help="subdirectory for this option set")
    ap.add_argument("--expect-route", default="", help="override the expected auto route (float for early binning)")
    ap.add_argument("--rss", action="store_true", help="record peak RSS (KiB) of each arm via the wrapper")
    ap.add_argument("--pinned-compact", action="store_true",
                    help="also run --ingest compact and require a refusal with no products")
    ap.add_argument("--cpu", action="store_true",
                    help="CPU-only binary: one arm per config, outputs kept for compare_trees_dirs.py")
    a = ap.parse_args()
    results = []
    extra = a.extra.split()
    work = str(Path(a.work) / a.tag) if a.tag else a.work
    for fam in FAMILIES:
        if fam["id"] not in a.families.split(","):
            continue
        for config in a.configs.split(","):
            if a.cpu:
                arm = run_arm(a.binary, a.gpu, fam, config, "cpu", work, a.inputs, cpu=True, extra=extra)
                results.append({"family": fam["id"], "mode": fam["mode"], "config": config, "cpu": True,
                                "rc": arm["rc"], "wall_s": arm["wall_s_incl_lock_wait"], "out": arm["out"],
                                "cmd": arm["cmd"], "pass": arm["rc"] == 0})
                print("%s %s cpu rc=%d wall %.1fs" % (fam["id"], config, arm["rc"], arm["wall_s_incl_lock_wait"]),
                      flush=True)
                Path(a.out).write_text(json.dumps(results, indent=1))
                continue
            expect = a.expect_route or fam["expect"]
            arms = {i: run_arm(a.binary, a.gpu, fam, config, i, work, a.inputs, extra=extra, rss=a.rss)
                    for i in ("float", "auto")}
            rec = {"family": fam["id"], "mode": fam["mode"], "config": config, "expect_auto_route": expect,
                   "extra": extra, "tag": a.tag,
                   "arms": {k: {x: v[x] for x in ("rc", "wall_s_incl_lock_wait", "witness", "cmd", "peak_rss_kib")}
                            for k, v in arms.items()}}
            rec["routes_ok"] = arms["float"]["witness"] == ["float"] and arms["auto"]["witness"] == [expect]
            rec["resident_session_used"] = {k: "Computing full-frame Fourier transforms (CUDA in-VRAM)" in movie_log(v) for k, v in arms.items()}
            rec["products"] = arms["auto"]["products"]
            if all(v["rc"] == 0 for v in arms.values()):
                ident = identity.compare_trees(arms["float"]["out"], arms["auto"]["out"], expect_mrc=None)
                rec["identity"] = {k: ident[k] for k in ("identical", "problems", "compared", "mrc_compared",
                                                         "differences", "only_a", "only_b")}
                rec["inventory"] = identity.inventory(arms["float"]["out"])
            if a.pinned_compact:
                pin = run_arm(a.binary, a.gpu, fam, config, "compact", work, a.inputs, extra=extra)
                rec["pinned_compact"] = {"rc": pin["rc"], "products": [p for p in pin["products"] if p.endswith(".mrc")],
                                         "refused": pin["rc"] != 0 and "--ingest compact was requested" in pin["text"]
                                         and not any(p.endswith(".mrc") for p in pin["products"])}
            rec["pass"] = bool(rec["routes_ok"] and rec.get("identity", {}).get("identical")
                               and rec.get("pinned_compact", {"refused": True})["refused"])
            for v in arms.values():  # drop bulk products, keep logs / STAR / witness
                for p in Path(v["out"]).rglob("*.mrc"):
                    p.unlink()
            results.append(rec)
            print(("PASS " if rec["pass"] else "FAIL ") + "%s %s mode %d: route %s/%s identity %s" % (
                fam["id"], config, fam["mode"], arms["float"]["witness"], arms["auto"]["witness"],
                rec.get("identity", {}).get("identical")), flush=True)
            Path(a.out).write_text(json.dumps(results, indent=1))
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
