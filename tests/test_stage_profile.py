#!/usr/bin/env python3
"""Contract for --profile (docs/stage_profile.md).

1. Products are byte-identical with and without --profile (MRC payload and
   header except the label timestamp, and path-normalised STAR files).
2. Every movie's top-level stages tile its wall exactly (exhaustiveness), and
   the expected stage names appear in order.
3. The process record is present and internally consistent.
4. An unwritable --profile path fails the job instead of silently not profiling.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVIE = ROOT / "test-data" / "synthetic" / "synthetic_movie.tiff"
ARGS = ["--use_own", "--j", "2", "--skip_defect", "--angpix", "1", "--voltage", "300",
        "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--dose_weighting",
        "--dose_per_frame", "1", "--save_noDW", "--skip_logfile"]
EXPECTED_ORDER = ["setup", "read gain", "host read movie", "gain and sum", "global fft",
                  "global alignment", "patch alignment", "fit polynomial", "dose weighting",
                  "movie teardown", "submit model and plot"]

failures = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


def run(binary, out, extra):
    cmd = [binary, "--i", str(MOVIE), "--o", str(out) + "/"] + ARGS + extra
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def products(root):
    return sorted(p.relative_to(root) for p in root.rglob("*") if p.suffix in (".mrc", ".star"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plain, prof = tmp / "plain", tmp / "prof"
        profile = tmp / "profile.jsonl"
        r1 = run(a.binary, plain, [])
        r2 = run(a.binary, prof, ["--profile", str(profile)])
        check(r1.returncode == 0 and r2.returncode == 0, "both runs exit 0")
        if r1.returncode or r2.returncode:
            print(r1.stderr[-2000:], r2.stderr[-2000:])
            return 1

        pa, pb = products(plain), products(prof)
        check(pa == pb and len(pa) >= 3, f"same product inventory ({len(pa)} files)")
        for rel in pa:
            x, y = (plain / rel).read_bytes(), (prof / rel).read_bytes()
            if rel.suffix == ".mrc":
                # Bytes 224+ of the header hold the label with a timestamp.
                same = x[1024:] == y[1024:] and x[:224] == y[:224]
            else:
                same = x.replace(str(plain).encode(), b"X") == y.replace(str(prof).encode(), b"X")
            check(same, f"identical {rel}")

        lines = [json.loads(l) for l in profile.read_text().splitlines() if l.strip()]
        movies = [l for l in lines if l["type"] == "movie"]
        process = [l for l in lines if l["type"] == "process"]
        check(len(movies) == 1 and len(process) == 1, "one movie and one process record")
        m = movies[0]
        stage_sum = sum(s["wall_ms"] for s in m["stages"])
        check(abs(stage_sum - m["wall_ms"]) < 0.5,
              f"stages tile the movie ({stage_sum:.3f} vs {m['wall_ms']:.3f} ms)")
        # Independent clock: the runner's own per-movie log line brackets
        # executeOwnMotionCorrection, which the profiled movie must cover within
        # the small setup/teardown outside it. A boundary that loses time between
        # stages makes the stage sum fall short of this.
        log = next(prof.rglob("*.log")).read_text()
        runner_ms = 1e3 * float(log.split("Full movie wall time:")[1].split()[0])
        check(stage_sum >= runner_ms - 1.0,
              f"stages cover the runner's own movie wall ({stage_sum:.3f} >= {runner_ms:.3f} - 1 ms)")
        check(abs(m.get("uncovered_ms", 0)) < 0.5, f"no uncovered time ({m.get('uncovered_ms')})")
        names = [s["name"] for s in m["stages"]]
        idx = [names.index(n) if n in names else -1 for n in EXPECTED_ORDER]
        check(all(i >= 0 for i in idx) and idx == sorted(idx), f"expected stages in order: {names}")
        check(all(s["wall_ms"] >= 0 and s["n"] >= 1 for s in m["stages"]), "non-negative stage walls")
        check(any(s["name"].startswith("patch alignment/") for s in m["sub"]), "sub-stages recorded")
        p = process[0]
        check(p["run_wall_ms"] >= m["wall_ms"] and p["process_cpu_ms"] > 0 and p["peak_rss_kb"] > 0,
              "process record consistent")
        check(any(t["name"].startswith("writer/") for t in p["threads"]), "writer thread tasks recorded")

        # A job with one unreadable movie still fails, but the profile keeps a
        # record for both movies (the failed one with ok=false) and its process line.
        star = tmp / "mixed.star"
        missing = tmp / "missing_movie.tiff"
        # A truncated copy: present, so the batch starts, but undecodable.
        missing.write_bytes(MOVIE.read_bytes()[:4096])
        star.write_text(
            "# version 30001\n\ndata_optics\n\nloop_\n"
            "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
            "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
            "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
            "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
            "# version 30001\n\ndata_movies\n\nloop_\n"
            "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
            "%s 1\n%s 1\n" % (MOVIE, missing))
        mixed_profile = tmp / "mixed.jsonl"
        mixed = subprocess.run([a.binary, "--i", str(star), "--o", str(tmp / "mixed") + "/"] + ARGS
                               + ["--profile", str(mixed_profile)], cwd=ROOT, capture_output=True, text=True)
        check(mixed.returncode != 0, "job with an unreadable movie fails")
        recs = [json.loads(l) for l in mixed_profile.read_text().splitlines() if l.strip()]
        mv = [r for r in recs if r["type"] == "movie"]
        check(len(mv) == 2 and mv[0]["ok"] and not mv[1]["ok"],
              f"both movies recorded, failed one ok=false ({[(r['index'], r['ok']) for r in mv]})")
        check(sum(r["type"] == "process" for r in recs) == 1, "process record written on a failed job")
        for r in mv:
            check(abs(sum(s["wall_ms"] for s in r["stages"]) - r["wall_ms"]) < 0.5,
                  f"failed-job movie {r['index']} stages still tile its wall")

        bad = run(a.binary, tmp / "bad", ["--profile", str(tmp / "no" / "such" / "dir" / "p.jsonl")])
        check(bad.returncode != 0 and "--profile" in (bad.stderr + bad.stdout),
              "unwritable --profile path fails with a named error")
    print("PASS" if not failures else f"{len(failures)} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
