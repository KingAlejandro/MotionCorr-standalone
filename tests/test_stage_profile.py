#!/usr/bin/env python3
"""Contract for --profile (docs/stage_profile.md).

1. Products are byte-identical with and without --profile, including the
   hot-pixel/defect path that consumes the CPU RNG.
2. Attribution, not just tiling. Stage sums equal the movie wall by
   construction, so that alone proves nothing. Instead, each named stage must
   contain the work it names. Every expected stage is present, in order, and
   the stages whose work is known to be substantial on this fixture carry it.
   Deleting or moving a boundary charges that work to a neighbour and fails here.
3. Sub-stages carry their parent prefix, and the process record is consistent.
4. Failed movies are recorded, including a failure inside a stage, and failed
   jobs still write the process record.
5. An unwritable --profile path fails the job instead of silently not profiling.
6. --profile_device_timing 0 keeps the stage profile but turns off CUDA event
   timing, and the process record says which mode ran. With --gpu the CUDA log
   blocks are checked too: the default --profile prints per-kernel timings,
   --profile_device_timing 0 prints the unprofiled "not measured" lines.
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
# Defect correction on (hot-pixel threshold low enough to find pixels), so the
# RNG-consuming path runs under --profile and is part of the identity check.
ARGS = ["--use_own", "--j", "2", "--hotpixel_sigma", "2", "--angpix", "1", "--voltage", "300",
        "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--dose_weighting",
        "--dose_per_frame", "1", "--save_noDW", "--skip_logfile"]
EXPECTED_ORDER = ["setup", "read gain", "session and device ingest", "host read movie",
                  "allocate host sum", "gain and sum", "hot pixels", "fix defects",
                  "release preprocessing", "global fft", "power spectrum", "global alignment",
                  "allocate reconstruction", "global ifft", "patch alignment", "fit polynomial",
                  "release alignment", "unweighted sums", "dose weighting", "movie teardown",
                  "submit model and plot"]
# Stages that do real, CPU-heavy work on this fixture, and the sub-stage each
# must contain. Their share of the movie is asserted below.
SUBSTANTIAL = {"host read movie": "READ_MOVIE", "global fft": "GLOBAL_FFT",
               "global alignment": "GLOBAL_ALIGNMENT", "patch alignment": "PATCH_ALIGN",
               "dose weighting": "DOSE_WEIGHTING"}

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


TIMED_LINES = ("   Custom kernel execution time:", "  Dose Weighting Kernel:")
UNTIMED_LINES = ("   Per-kernel timing:            not measured", "  Per-stage timing:      not measured")


def device_timing_mode(binary, tmp, gpu):
    """Item 6 of the docstring: the profile with and without device timing."""
    backend = ["--gpu", str(gpu)] if gpu is not None else []
    logs, notes = {}, {}
    for arm, extra in (("plain", []), ("timed", ["--profile", str(tmp / "timed.jsonl")]),
                       ("untimed", ["--profile", str(tmp / "untimed.jsonl"), "--profile_device_timing", "0"])):
        r = run(binary, tmp / ("dt_" + arm), backend + extra)
        check(r.returncode == 0, f"device-timing arm {arm} exits 0")
        if r.returncode:
            print(r.stderr[-2000:])
            return
        logs[arm] = "\n".join(p.read_text() for p in sorted((tmp / ("dt_" + arm)).rglob("*.log")))
        if extra:
            recs = [json.loads(l) for l in Path(extra[1]).read_text().splitlines() if l.strip()]
            proc = [x for x in recs if x["type"] == "process"]
            movies = [x for x in recs if x["type"] == "movie"]
            notes[arm] = proc[0].get("device_timing") if proc else None
            check(len(movies) == 1 and movies[0]["ok"] and len(movies[0]["stages"]) >= len(EXPECTED_ORDER) - 2,
                  f"{arm} profile still records the movie's stages")
    check(notes.get("timed") == "on" and notes.get("untimed") == "off",
          f"process record names the device timing mode ({notes})")
    bad = run(binary, tmp / "dt_bad", ["--profile", str(tmp / "bad.jsonl"), "--profile_device_timing", "2"])
    check(bad.returncode != 0 and "--profile_device_timing" in (bad.stderr + bad.stdout),
          "an invalid --profile_device_timing value fails with a named error")
    if gpu is None:
        return
    # The CUDA path ran (otherwise none of these lines exist), and the untimed
    # profile has the production log shape: no per-step timings at all.
    check(all(l in logs["timed"] for l in TIMED_LINES), "default --profile prints per-step CUDA timings")
    check(not any(l in logs["untimed"] for l in TIMED_LINES), "--profile_device_timing 0 prints no per-step CUDA timings")
    check(all(l in logs["untimed"] for l in UNTIMED_LINES) and all(l in logs["plain"] for l in UNTIMED_LINES),
          "--profile_device_timing 0 logs the unprofiled 'not measured' lines")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--gpu", type=int, help="also check the CUDA log blocks on this device")
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
        # Tiling is structural (each boundary closes one stage and opens the next);
        # this only guards against a stage being dropped from the output.
        check(abs(stage_sum - m["wall_ms"]) < 0.5,
              f"stages tile the movie ({stage_sum:.3f} vs {m['wall_ms']:.3f} ms)")
        names = [s["name"] for s in m["stages"]]
        idx = [names.index(n) if n in names else -1 for n in EXPECTED_ORDER]
        check(all(i >= 0 for i in idx) and idx == sorted(idx), f"all expected stages in order: {names}")
        by = {s["name"]: s for s in m["stages"]}
        subs = {s["name"]: s for s in m["sub"]}
        # Attribution: each substantial stage holds its own sub-stage, and that
        # sub-stage is most of the stage. A misplaced boundary moves the work.
        for stage, inner in SUBSTANTIAL.items():
            key = f"{stage}/{inner}"
            st, sb = by.get(stage), subs.get(key)
            check(st is not None and sb is not None and sb["wall_ms"] <= st["wall_ms"] + 0.01
                  and sb["wall_ms"] >= 0.5 * st["wall_ms"] and st["wall_ms"] > 0.2,
                  f"{stage} contains its own work ({key}: "
                  f"{sb and round(sb['wall_ms'], 3)} of {st and round(st['wall_ms'], 3)} ms)")
        # The catch-all must stay small: if boundaries are deleted the work lands
        # in 'setup' or 'movie teardown', which on this fixture do almost nothing.
        catch_all = sum(by[n]["wall_ms"] for n in ("setup", "movie teardown") if n in by)
        check(catch_all < 0.25 * m["wall_ms"],
              f"catch-all stages stay small ({catch_all:.3f} of {m['wall_ms']:.3f} ms)")
        # Faults are counted per stage from the same thread counter; the movie
        # total must equal their sum (same check for CPU time).
        check(abs(sum(s["minflt"] for s in m["stages"]) - m["minflt"]) <= 0,
              "stage page faults sum to the movie total")
        check(all(k.split("/")[0] in by for k in subs), "every sub-stage is keyed under a top-level stage")
        check(all(s["wall_ms"] >= 0 and s["n"] >= 1 for s in m["stages"]), "non-negative stage walls")
        check(any(s["name"].startswith("patch alignment/") for s in m["sub"]), "sub-stages recorded")
        p = process[0]
        check(p["run_wall_ms"] >= m["wall_ms"] and p["process_cpu_ms"] > 0 and p["peak_rss_kb"] > 0,
              "process record consistent")
        check(any(t["name"].startswith("writer/") for t in p["threads"]), "writer thread tasks recorded")

        # A job with one unreadable movie still fails, but the profile keeps a
        # record for both movies (the failed one with ok=false) and its process line.
        # A failure inside a stage (unsupported voltage, raised in dose
        # weighting after patch alignment) must close the open nested range,
        # record ok=false and still write the process record.
        mid_profile = tmp / "mid.jsonl"
        mid = subprocess.run([a.binary, "--i", str(MOVIE), "--o", str(tmp / "mid") + "/"]
                             + [x if x != "300" else "250" for x in ARGS]
                             + ["--profile", str(mid_profile)], cwd=ROOT, capture_output=True, text=True)
        recs = [json.loads(l) for l in mid_profile.read_text().splitlines() if l.strip()]
        mv = [r for r in recs if r["type"] == "movie"]
        check(mid.returncode != 0 and len(mv) == 1 and not mv[0]["ok"]
              and mv[0]["stages"][-1]["name"] in ("dose weighting", "submit model and plot")
              and any(s["name"].startswith("dose weighting/DOSE_WEIGHTING") for s in mv[0]["sub"]),
              f"mid-stage failure recorded with its open stage closed ({[s['name'] for s in mv[0]['stages']][-3:] if mv else None})")
        check(sum(r["type"] == "process" for r in recs) == 1, "process record written after a mid-stage failure")

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
        device_timing_mode(a.binary, tmp, a.gpu)
    print("PASS" if not failures else f"{len(failures)} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
