#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Every movie container, sample type and codec MotionCorr reads, end to end.

Fixtures come from test-data/generate_format_fixtures.py: one integer-valued
movie written in each encoding (MRC modes, TIFF sample types and codecs,
compressed MRC, EER 65000/65001/65002) plus gain and defect inputs in several
encodings, rejected encodings and characterisation cases. See that file for the
oracle. Checks, per case kind:

  accept        decode: the decoded movie equals the generator's array exactly
                e2e: products (MRC pixel payload, per-movie shift tables) are
                byte-identical to those of the case's reference
  characterise  as accept, but expect_equal=False cases must DIFFER from the
                producer's convention (a pinned, documented divergence)
  reject        motioncorr exits non-zero (not by signal), names the movie,
                prints the expected text and writes no product for it
  known_failure a pinned defect: the case records the current outcome (accepted
                or refused) and the correct one. KNOWN while the current outcome
                holds; FAIL once it changes, so a fix must update the case.
  not_run       reported, never executed (see the case note)

A case that needs an external decoder that is absent (pbzip2, zstd, xz) is
UNRUN and fails the suite unless --allow-unrun names that tool: a skipped codec
must be visible, not silently green.

On a CUDA build, --ingest-matrix runs every end-to-end batch twice on the GPU,
with --ingest float and --ingest auto, applies the checks above within each mode,
requires each case's products to be byte-identical across the two modes, and
reports the route each movie took (--ingest_witness: nvcomp, compact or float).
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "test-data" / "generate_format_fixtures.py"
BASE_OPTS = ["--use_own", "--j", "1", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
             "--patch_x", "1", "--patch_y", "1", "--bfactor", "150", "--skip_logfile"]
STAR_HEAD = ("# version 30001\n\ndata_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
             "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n_rlnSphericalAberration #5\n"
             "_rlnAmplitudeContrast #6\nopticsGroup1 1 1.000 300.0 2.7 0.1\n\n# version 30001\n\n"
             "data_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n")
SUFFIXES = (".mrcs.xz", ".mrcs.bz2", ".mrcs.zst", ".mrc.xz", ".mrc.bz2", ".mrc.zst",
            ".mrcs", ".mrc", ".tiff", ".tif", ".eer")


def stem(name):
    for s in SUFFIXES:
        if name.endswith(s):
            return name[:-len(s)]
    return name.rsplit(".", 1)[0]


class Report:
    def __init__(self):
        self.rows = []

    def add(self, case, check, status, detail=""):
        self.rows.append((case, check, status, detail))
        if status not in ("PASS", "KNOWN", "NOT RUN"):
            print("  %-44s %-7s %s %s" % (case, check, status, detail), flush=True)

    def summary(self):
        counts = {}
        for r in self.rows:
            counts[r[2]] = counts.get(r[2], 0) + 1
        return counts


# ----------------------------------------------------------------- decode level

def read_raw(helper, path, tmp, max_rows=None):
    dump = Path(tmp) / "raw.bin"
    cmd = [str(helper), "read_tiff_raw", str(path), str(dump)] + ([str(max_rows)] if max_rows else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("helper failed: " + (r.stderr + r.stdout)[-400:])
    data = dump.read_bytes()
    nx, ny, nn = struct.unpack("<qqq", data[:24])
    arr = np.frombuffer(data[24:], dtype="<f4")
    dump.unlink()
    return nx, ny, nn, arr


def render_eer(helper, path, tmp, upsampling, grouping):
    dump = Path(tmp) / "eer.bin"
    r = subprocess.run([str(helper), "render_eer", str(path), str(dump), str(upsampling), str(grouping)],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("helper failed: " + (r.stderr + r.stdout)[-400:])
    data = memoryview(dump.read_bytes())
    nx, ny, groups = struct.unpack("<qqq", data[:24])
    off, out = 24, []
    for _ in range(groups):
        n = struct.unpack("<q", data[off:off + 8])[0]
        off += 8
        idx = np.frombuffer(data[off:off + 8 * n], dtype="<i8")
        off += 8 * n
        val = np.frombuffer(data[off:off + 4 * n], dtype="<f4")
        off += 4 * n
        out.append((idx, val))
    dump.unlink()
    return nx, ny, out


def compare_image(helper, path, tmp, exp, max_rows):
    n, ny, nx = exp.shape
    gx, gy, gn, arr = read_raw(helper, path, tmp, max_rows)
    rows = min(max_rows, ny * n) if max_rows else ny * n
    flat = exp.reshape(-1, nx)[:rows].ravel().astype(np.float32)
    if (gx, gy, gn) != (nx, ny, n) or arr.size != flat.size:
        return False, "dims %s vs %s" % ((gx, gy, gn), (nx, ny, n))
    if np.array_equal(arr, flat):
        return True, ""
    bad = np.flatnonzero(arr != flat)
    return False, "%d of %d samples differ, first at %d (%g vs %g)" % (bad.size, arr.size, bad[0], arr[bad[0]], flat[bad[0]])


def compare_eer(rendered, z, groups):
    gx, gy, got = rendered
    if (gx, gy) != (int(z["nx"]), int(z["ny"])):
        return False, "rendered %dx%d, expected %dx%d" % (gx, gy, int(z["nx"]), int(z["ny"]))
    if len(got) != groups:
        return False, "%d groups rendered, expected %d" % (len(got), groups)
    for g, (idx, val) in enumerate(got):
        ei, ev = z["idx%d" % g], z["val%d" % g]
        if not (np.array_equal(idx, ei) and np.array_equal(val, ev.astype(np.float32))):
            return False, "group %d: %d electrons at %d pixels, expected %d at %d" % (
                g, int(val.sum()), idx.size, int(ev.sum()), ei.size)
    return True, ""


def check_decode(case, fixtures, manifest, helper, tmp, rep):
    """accept: equal to the format oracle. characterise: equal to the pinned
    current output AND different from the format oracle."""
    d = case["decode"]
    want_equal = d.get("expect_equal", True)
    path = fixtures / case["file"]
    try:
        if d["reader"] == "image":
            load = lambda key: np.load(fixtures / manifest["expected"][key])
            fmt_ok, fmt_detail = compare_image(helper, path, tmp, load(d["expected"]), d.get("max_rows"))
            if not want_equal:
                pin_ok, pin_detail = compare_image(helper, path, tmp, load(d["characterised"]), d.get("max_rows"))
        else:
            rendered = render_eer(helper, path, tmp, d["upsampling"], d["grouping"])
            load = lambda key: np.load(fixtures / manifest["expected"][key])
            fmt_ok, fmt_detail = compare_eer(rendered, load(d["expected"]), d["groups"])
            if not want_equal:
                pin_ok, pin_detail = compare_eer(rendered, load(d["characterised"]), d["groups"])
    except Exception as ex:          # noqa: BLE001 - reported as a failure
        rep.add(case["name"], "decode", "FAIL", str(ex)[-300:])
        return
    if want_equal:
        rep.add(case["name"], "decode", "PASS" if fmt_ok else "FAIL", fmt_detail)
    elif pin_ok and not fmt_ok:
        rep.add(case["name"], "decode", "KNOWN", "matches the pinned current output")
    elif fmt_ok:
        rep.add(case["name"], "decode", "FAIL", "now decodes as the format defines; update the case")
    else:
        rep.add(case["name"], "decode", "FAIL", "differs from the pinned current output: " + pin_detail)


# ------------------------------------------------------------------- e2e level

EXTRA_OPTS = []


def run_mc(binary, run_dir, files, options, side_files, fixtures, threads, no_skip_defect, copy=False):
    mov = run_dir / "Movies"
    mov.mkdir(parents=True)
    for f in files:
        if copy:
            shutil.copyfile(fixtures / f, mov / Path(f).name)
        else:
            os.symlink(fixtures / f, mov / Path(f).name)
    for f in side_files:
        os.symlink(fixtures / f, run_dir / Path(f).name)
    (run_dir / "movies.star").write_text(
        STAR_HEAD + "".join("Movies/%s 1\n" % Path(f).name for f in files))
    opts = list(BASE_OPTS)
    if not no_skip_defect:
        opts.append("--skip_defect")
    cmd = [str(binary), "--i", "movies.star", "--o", "out/"] + opts + list(options) + EXTRA_OPTS
    env = dict(os.environ, OMP_NUM_THREADS=str(threads))
    r = subprocess.run(cmd, cwd=run_dir, capture_output=True, text=True, env=env, timeout=1800)
    return r


def product(run_dir, movie_file):
    name = Path(movie_file).name
    # Compressed movies keep their inner suffix with the dot replaced: x.mrcs.xz -> x_mrcs.mrc
    for s in (stem(name), name.rsplit(".", 1)[0].replace(".", "_")):
        p = run_dir / "out" / "Movies" / (s + ".mrc")
        if p.exists():
            return p
    return None


def pixels(path):
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", data[:16])
    nsymbt = struct.unpack("<i", data[92:96])[0]
    return (nx, ny, nz, mode), data[1024 + nsymbt:]


def shift_tables(mrc_path):
    star = mrc_path.with_suffix(".star")
    text = star.read_text() if star.exists() else ""
    blocks = {}
    for m in re.finditer(r"(data_(global_shift|local_shift|local_motion_model)\b.*?)(?=\ndata_|\Z)", text, re.S):
        blocks[m.group(2)] = m.group(1).strip()
    return blocks


def side_inputs(options):
    out = []
    for flag in ("--gainref", "--defect_file"):
        if flag in options:
            out.append(options[options.index(flag) + 1])
    return out


def check_e2e(cases, fixtures, binary, work, threads, rep, available, label="e2e", witness=False):
    runs = {}
    for c in cases:
        e = c["e2e"]
        key = (e["batch"], tuple(e.get("options", [])), bool(e.get("no_skip_defect")), bool(e.get("copy")))
        runs.setdefault(key, []).append(c)
    outputs = {}
    for i, ((batch, options, nsd, copy), members) in enumerate(sorted(runs.items(), key=lambda kv: kv[0])):
        files = sorted({c["file"] for c in members})
        side = [str(Path(members[0]["file"]).parent / s) for s in side_inputs(list(options))]
        run_dir = work / ("%s_%02d_%s" % (label, i, re.sub(r"[^A-Za-z0-9]+", "_", batch)))
        opts = list(options) + (["--ingest_witness", str(run_dir) + ".witness"] if witness else [])
        r = run_mc(binary, run_dir, files, opts, side, fixtures, threads, nsd, copy)
        if witness and Path(str(run_dir) + ".witness").exists():
            for line in Path(str(run_dir) + ".witness").read_text().split("\n"):
                if line.strip():
                    movie, route = line.rsplit(" ", 1)
                    ROUTES.setdefault(label, {})[Path(movie).name] = route
        for c in members:
            if r.returncode != 0:
                # Products alone are not enough: a run that exits non-zero fails every case in it.
                tail = (r.stderr + r.stdout).strip().splitlines()[-1:] if (r.stderr + r.stdout).strip() else ""
                rep.add(c["name"], label, "FAIL", "run exited %d: %s" % (r.returncode, tail))
                continue
            prod = product(run_dir, c["file"])
            if prod is None:
                rep.add(c["name"], label, "FAIL", "no product (rc %d): %s" % (
                    r.returncode, (r.stderr + r.stdout).strip().splitlines()[-1:] if (r.stderr + r.stdout).strip() else ""))
                continue
            outputs[c["name"]] = prod
    for c in cases:
        if c["name"] not in outputs:
            continue
        ref = c["e2e"]["reference"]
        if ref == c["name"]:
            rep.add(c["name"], label, "PASS", "reference")
            continue
        if ref not in outputs:
            rep.add(c["name"], label, "FAIL", "reference %s produced nothing" % ref)
            continue
        (h1, p1), (h2, p2) = pixels(outputs[c["name"]]), pixels(outputs[ref])
        t1, t2 = shift_tables(outputs[c["name"]]), shift_tables(outputs[ref])
        problems = []
        if h1 != h2:
            problems.append("header dims/mode %s vs %s" % (h1, h2))
        elif p1 != p2:
            a, b = np.frombuffer(p1, "<f4"), np.frombuffer(p2, "<f4")
            problems.append("pixels differ at %d of %d (max |d| %.3g)" % (
                int((a != b).sum()), a.size, float(np.abs(a - b).max())))
        if t1 != t2:
            problems.append("shift tables differ (%s)" % ",".join(sorted(k for k in set(t1) | set(t2) if t1.get(k) != t2.get(k))))
        if not t1.get("global_shift"):
            problems.append("no global shift table")
        want_equal = c["kind"] != "characterise" or c.get("decode", {}).get("expect_equal", True)
        if not problems:
            rep.add(c["name"], label, "PASS" if want_equal else "FAIL", "" if want_equal else "expected a difference")
        else:
            rep.add(c["name"], label, "FAIL" if want_equal else "KNOWN", "; ".join(problems))
    return outputs


ROUTES = {}


def compare_modes(cases, out_a, out_b, rep, label):
    for c in cases:
        a, b = out_a.get(c["name"]), out_b.get(c["name"])
        if a is None or b is None:
            continue                   # already reported as a failure in its mode
        (h1, p1), (h2, p2) = pixels(a), pixels(b)
        same = h1 == h2 and p1 == p2 and shift_tables(a) == shift_tables(b)
        route = ROUTES.get("auto", {}).get(Path(c["file"]).name, "?")
        rep.add(c["name"], label, "PASS" if same else "FAIL",
                ("route " + route) if same else "auto (route %s) differs from float" % route)


def check_reject(c, fixtures, binary, work, threads, rep):
    rj = c["reject"]
    run_dir = work / ("reject_" + c["name"])
    options = rj.get("options", [])
    side = [str(Path(c["file"]).parent / s) for s in side_inputs(options)]
    r = run_mc(binary, run_dir, [c["file"]], options, side, fixtures, threads, rj.get("no_skip_defect"))
    text = r.stdout + r.stderr
    problems = []
    if r.returncode == 0:
        problems.append("exit 0: accepted")
    elif r.returncode < 0:
        problems.append("killed by signal %d" % -r.returncode)
    if rj["substring"] and rj["substring"] not in text:
        problems.append("message lacks %r" % rj["substring"])
    if rj.get("names_movie", True) and Path(c["file"]).name not in text:
        problems.append("movie not named")
    if product(run_dir, c["file"]) is not None:
        problems.append("a product was written")
    rep.add(c["name"], "reject", "FAIL" if problems else "PASS", "; ".join(problems))


def check_known(c, fixtures, binary, work, threads, rep):
    run_dir = work / ("known_" + c["name"])
    r = run_mc(binary, run_dir, [c["file"]], c.get("options", []), [], fixtures, threads, False)
    accepted = r.returncode == 0 and product(run_dir, c["file"]) is not None
    refused = r.returncode > 0 and product(run_dir, c["file"]) is None
    observed = "accepted" if accepted else "refused" if refused else "rc %d" % r.returncode
    if observed == c["known"]["current"]:
        rep.add(c["name"], "known", "KNOWN", "still %s (correct: %s)" % (observed, c["known"]["correct"]))
    else:
        rep.add(c["name"], "known", "FAIL", "behaviour changed: now %s (was %s); update the case" % (
            observed, c["known"]["current"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--helper", type=Path, required=True, help="runner_numerics")
    ap.add_argument("--fixtures", type=Path, help="pre-generated fixture directory (default: generate)")
    ap.add_argument("--include-heavy", action="store_true")
    ap.add_argument("--allow-unrun", action="append", default=[], metavar="TOOL",
                    help="do not fail when TOOL (pbzip2, zstd, xz) is missing; its cases are reported UNRUN")
    ap.add_argument("--only", default="", help="regex over case names")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--keep", type=Path, help="keep run directories here")
    ap.add_argument("--json", type=Path, help="write the per-case report as JSON")
    ap.add_argument("--mc-option", action="append", default=[],
                    help="extra motioncorr option for every run (repeat per token), e.g. --mc-option=--gpu --mc-option=0")
    ap.add_argument("--ingest-matrix", action="store_true",
                    help="CUDA build: run end-to-end batches with --ingest float and auto and compare (implies --gpu 0 unless given)")
    a = ap.parse_args()
    EXTRA_OPTS.extend(a.mc_option)
    if a.ingest_matrix and "--gpu" not in EXTRA_OPTS:
        EXTRA_OPTS.extend(["--gpu", "0"])

    tmp = Path(tempfile.mkdtemp(prefix="mc-formats-"))
    try:
        fixtures = a.fixtures
        if fixtures is None:
            fixtures = tmp / "fixtures"
            cmd = [sys.executable, str(GEN), "--outdir", str(fixtures)] + (["--include-heavy"] if a.include_heavy else [])
            subprocess.run(cmd, check=True)
        manifest = json.loads((fixtures / "manifest.json").read_text())
        work = a.keep or tmp / "runs"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        rep = Report()
        sel = re.compile(a.only) if a.only else None
        cases = [c for c in manifest["cases"] if (not sel or sel.search(c["name"]))
                 and (a.include_heavy or not c.get("heavy"))]
        available = {t: shutil.which(t) is not None for t in ("pbzip2", "zstd", "xz")}
        runnable = []
        unrun_fatal = False
        for c in cases:
            missing = [t for t in c.get("requires", []) if not available.get(t, True)]
            if c["kind"] == "unbuilt" or missing:
                tools = missing or c.get("requires", [])
                rep.add(c["name"], "-", "UNRUN", "needs " + ", ".join(tools))
                if not all(t in a.allow_unrun for t in tools):
                    unrun_fatal = True
            elif c["kind"] == "not_run":
                rep.add(c["name"], "-", "NOT RUN", c["note"][:90])
            else:
                runnable.append(c)
        print("decode checks", flush=True)
        for c in runnable:
            if c.get("decode") and c["kind"] in ("accept", "characterise"):
                check_decode(c, fixtures, manifest, a.helper, tmp, rep)
        print("end-to-end runs", flush=True)
        e2e = [c for c in runnable if c.get("e2e") and c["kind"] in ("accept", "characterise")]
        # References must run even when --only filters them out.
        names = {c["name"] for c in e2e}
        for c in manifest["cases"]:
            if c.get("e2e") and c["name"] not in names and any(x["e2e"]["reference"] == c["name"] for x in e2e):
                e2e.append(c)
                names.add(c["name"])
        if a.ingest_matrix:
            base = list(EXTRA_OPTS)
            outs = {}
            for mode in ("float", "auto"):
                EXTRA_OPTS[:] = base + ["--ingest", mode]
                outs[mode] = check_e2e(e2e, fixtures, a.binary, work, a.threads, rep, available,
                                       label=mode, witness=True)
            EXTRA_OPTS[:] = base
            compare_modes(e2e, outs["float"], outs["auto"], rep, "auto=float")
        else:
            check_e2e(e2e, fixtures, a.binary, work, a.threads, rep, available)
        print("rejections and known failures", flush=True)
        for c in runnable:
            if c["kind"] == "reject":
                check_reject(c, fixtures, a.binary, work, a.threads, rep)
            elif c["kind"] == "known_failure":
                check_known(c, fixtures, a.binary, work, a.threads, rep)
        counts = rep.summary()
        width = max(len(r[0]) for r in rep.rows)
        print("\n%-*s  %-7s %-8s %s" % (width, "case", "check", "result", "detail"))
        for case, check, status, detail in rep.rows:
            print("%-*s  %-7s %-8s %s" % (width, case, check, status, detail))
        print("\nsummary:", ", ".join("%s %d" % kv for kv in sorted(counts.items())))
        if a.json:
            a.json.write_text(json.dumps([dict(zip(("case", "check", "result", "detail"), r)) for r in rep.rows], indent=1))
        failed = counts.get("FAIL", 0) > 0 or unrun_fatal
        if unrun_fatal and not counts.get("FAIL"):
            print("UNRUN cases without --allow-unrun: install the decoder or pass --allow-unrun TOOL")
        return 1 if failed else 0
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
