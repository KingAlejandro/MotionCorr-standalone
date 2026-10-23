#!/usr/bin/env python3
"""Frozen #268 quality-report controls, v2 (PROTOCOL_V2.md).

    quality_controls_v2.py campaign --fixtures DIR --root NEWDIR --v0 BIN --v1 BIN --v2 BIN \
        --revision SHA [--cpu 14]
    quality_controls_v2.py check --root DIR --revision SHA
    quality_controls_v2.py selftest

`campaign` verifies fixtures, runs Q1..Q16 once each (no retries) and then
`check`. The v1 harness (quality_controls.py) is kept unchanged for the
c347f59f evidence; a few of its helpers are reused here. Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_controls as v1  # noqa: E402

CASES6 = v1.CASES6
COMMON = v1.COMMON
FLAG = v1.FLAG
NON_UTF8 = b"in/zero\xe9.mrcs"
UTF8 = "in/zéro.mrcs".encode()


# ---------------------------------------------------------------- staging

def write_star(run: Path, fixtures: Path, rows) -> None:
    optics = (fixtures / "zero.star").read_bytes().split(b"data_movies")[0].rstrip()
    body = b"\n".join(r + b" 1" for r in rows)
    (run / "in" / "batch.star").write_bytes(optics + b"\n\n# version 30001\n\ndata_movies\n\nloop_\n"
                                            b"_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n" + body + b"\n")


def stage_files(run: Path, fixtures: Path, files) -> None:
    """files: list of (relative path bytes under run, fixture case)."""
    (run / "in").mkdir(parents=True)
    for rel, case in files:
        shutil.copy2(fixtures / f"{case}.mrcs", os.path.join(os.fsencode(run), rel))


def batch6(run, fixtures):
    stage_files(run, fixtures, [(f"in/{c}.mrcs".encode(), c) for c in CASES6])
    write_star(run, fixtures, [f"in/{c}.mrcs".encode() for c in CASES6])


def collision(run, fixtures):
    stage_files(run, fixtures, [(b"in/zero.mrcs", "zero"), (b"in/affine.mrcs", "affine"), (b"in/affine.mrc", "integer")])
    write_star(run, fixtures, [b"in/zero.mrcs", b"in/zero.mrcs", b"in/affine.mrcs", b"in/affine.mrc"])


def encoding(run, fixtures):
    stage_files(run, fixtures, [(NON_UTF8, "zero"), (UTF8, "integer")])
    write_star(run, fixtures, [NON_UTF8, UTF8])


def pair(run, fixtures):
    stage_files(run, fixtures, [(b"in/zero.mrcs", "zero"), (b"in/integer.mrcs", "integer")])
    write_star(run, fixtures, [b"in/zero.mrcs", b"in/integer.mrcs"])


def single_integer(run, fixtures):
    stage_files(run, fixtures, [(b"in/integer.mrcs", "integer")])
    write_star(run, fixtures, [b"in/integer.mrcs"])


TAMPER = {  # Q9: case -> mutation of a copied Q4 sidecar
    "zero": lambda d: d["global_alignment"].update(state="BOGUS"),
    "integer": lambda d: d.update(motion_identifiability="identifiable"),
    "fractional": lambda d: d.pop("global_alignment"),
    "affine": lambda d: d["movie"].update(bytes=str(d["movie"]["bytes"])),
    "noisy": lambda d: d.update(peak_validity="valid"),
}


def resume_tree(root: Path, run: Path, fixtures: Path, with_sidecars: bool) -> None:
    batch6(run, fixtures)
    out = run / "out" / "in"
    out.mkdir(parents=True)
    for case in CASES6:
        for f in v1.product_files(root / "Q4" / "out", case):
            if ".quality" in f.name and not with_sidecars:
                continue
            shutil.copy2(f, out / f.name)
        if with_sidecars and case in TAMPER:
            side = out / f"{case}.quality.json"
            data = json.loads(side.read_text())
            TAMPER[case](data)
            side.write_text(json.dumps(data, indent=2) + "\n")


PLAN = [
    # id, binary, stage, patches, extra, injection
    ("Q1", "v0", batch6, 3, [], None),
    ("Q2", "v1", batch6, 3, [], None),
    ("Q3", "v2", batch6, 3, [], None),
    ("Q4", "v2", batch6, 3, [FLAG], None),
    ("Q5", "v0", collision, 3, [], None),
    ("Q6", "v2", collision, 3, [FLAG], None),
    ("Q7", "v0", encoding, 1, [], None),
    ("Q8", "v2", encoding, 1, [FLAG], None),
    ("Q9", "v2", None, 3, ["--only_do_unfinished", FLAG], "resume"),
    ("Q10", "v0", None, 3, ["--only_do_unfinished"], "resume_reference"),
    ("Q11", "v0", pair, 1, [], "product_dir"),
    ("Q12", "v2", pair, 1, [FLAG], "product_dir"),
    ("Q13", "v2", batch6, 3, [FLAG], "sidecar_dir"),
    ("Q14", "v0", single_integer, 3, ["--max_iter", "1"], None),
    ("Q15", "v2", single_integer, 3, ["--max_iter", "1", FLAG], None),
    ("Q16", "v1", batch6, 3, [FLAG], None),
]


def campaign(args) -> int:
    root = Path(args.root)
    root.mkdir(parents=False, exist_ok=False)
    fixtures = Path(args.fixtures)
    binaries = {k: Path(getattr(args, k)).resolve() for k in ("v0", "v1", "v2")}
    manifest = dict(fixtures=v1.verify_fixtures(fixtures),
                    binaries={k: dict(path=str(p), sha256=v1.sha256(p)) for k, p in binaries.items()},
                    revision=args.revision, cpu=args.cpu, skipped=args.skip, host=os.uname().nodename, started=time.time(), runs=[])
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    env = dict(os.environ, OMP_NUM_THREADS="1")
    for qid, binary, stage, patches, extra, injection in PLAN:
        if qid in args.skip:  # development only; the frozen campaign skips nothing
            continue
        run = root / qid
        if injection == "resume":
            resume_tree(root, run, fixtures, with_sidecars=True)
        elif injection == "resume_reference":
            resume_tree(root, run, fixtures, with_sidecars=False)
        else:
            stage(run, fixtures)
        if injection == "product_dir":
            (run / "out" / "in" / "integer.mrc").mkdir(parents=True)
        elif injection == "sidecar_dir":
            (run / "out" / "in" / "flat.quality.json").mkdir(parents=True)
        before = tree_hashes(run / "out")
        argv = [str(binaries[binary]), "--i", "in/batch.star", "--o", "out/"] + COMMON + \
               ["--patch_x", str(patches), "--patch_y", str(patches)] + extra
        if args.cpu is not None:
            argv = ["taskset", "-c", str(args.cpu)] + argv
        t0 = time.time()
        proc = subprocess.run(argv, cwd=run, env=env, capture_output=True)
        (run / "stdout.txt").write_bytes(proc.stdout)
        (run / "stderr.txt").write_bytes(proc.stderr)
        rec = dict(id=qid, binary=binary, argv=argv, cwd=str(run), exit=proc.returncode,
                   seconds=round(time.time() - t0, 3), injection=injection, out_before=before)
        (run / "run.json").write_text(json.dumps(rec, indent=2) + "\n")
        manifest["runs"].append({k: v for k, v in rec.items() if k != "out_before"})
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{qid} exit {proc.returncode} ({rec['seconds']} s)", flush=True)
    return check(argparse.Namespace(root=str(root), revision=args.revision))


# ---------------------------------------------------------------- helpers

def tree_hashes(out: Path) -> dict:
    result = {}
    if out.exists():
        for dirpath, _, files in os.walk(os.fsencode(out)):
            for f in files:
                p = os.path.join(dirpath, f)
                result[os.path.relpath(p, os.fsencode(out)).hex()] = v1.sha256(Path(os.fsdecode(p)))
    return result


def products(out: Path) -> dict:
    """v1 comparison rule on byte paths (non-UTF-8 names included)."""
    result = {}
    if not out.exists():
        return result
    for dirpath, _, files in os.walk(os.fsencode(out)):
        for f in files:
            if b".quality" in f or f.startswith(b"quality_summary") or b".tmp." in f:
                continue
            if any(f.endswith(s.encode()) for s in v1.SKIP_SUFFIXES):
                continue
            p = os.path.join(dirpath, f)
            result[os.path.relpath(p, os.fsencode(out)).hex()] = v1.normalized_digest(Path(os.fsdecode(p)))
    return result


# Wall time, and error backtraces that name the binary/source path or carry
# addresses (Linux "bin(+0x..) [0x..]", macOS "N  bin  0x.. symbol + off").
LOG_DROP = re.compile(rb"^(Full movie wall time:|in: .*, line \d+$|\d+\s+\S+\s+0x[0-9a-f]+ )"
                      rb"|\(\+0x[0-9a-f]+\) \[0x[0-9a-f]+\]$")


def logs(out: Path) -> dict:
    result = {}
    if not out.exists():
        return result
    for dirpath, _, files in os.walk(os.fsencode(out)):
        for f in files:
            if f.endswith(b".log"):
                p = os.path.join(dirpath, f)
                with open(p, "rb") as h:
                    lines = [l for l in h.read().split(b"\n") if not LOG_DROP.search(l)]
                result[os.path.relpath(p, os.fsencode(out)).hex()] = b"\n".join(lines)
    return result


def tmp_files(run: Path) -> list:
    return [os.fsdecode(os.path.join(d, f)) for d, _, fs in os.walk(os.fsencode(run / "out")) for f in fs if b".tmp." in f]


def run_rec(run: Path) -> dict:
    return json.loads((run / "run.json").read_text())


def mc_argv(rec: dict) -> list:
    argv = rec["argv"]
    return argv[3:] if argv[0] == "taskset" else argv


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def load_json_strict(path: Path):
    """Strict UTF-8 JSON, rejecting duplicate keys and non-finite numbers."""
    def no_dupes(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate key")
        return dict(pairs)
    def no_constant(name):
        raise ValueError(name)
    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=no_dupes, parse_constant=no_constant)


def decode_text(value):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, dict) and set(value) == {"non_utf8_bytes_hex"}:
        return bytes.fromhex(value["non_utf8_bytes_hex"])
    raise ValueError(f"bad text {value!r}")


def sidecars(run: Path) -> dict:
    """movie path bytes -> (sidecar path, data)."""
    result = {}
    base = os.fsencode(run / "out" / "in")
    if not os.path.isdir(base):
        return result
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if f.endswith(b".quality.json") and os.path.isfile(p):
            data = load_json_strict(Path(os.fsdecode(p)))
            result[decode_text(data["movie"]["path"])] = (Path(os.fsdecode(p)), data)
    return result


def membership(run: Path) -> list:
    text = (run / "in" / "batch.star").read_bytes().split(b"_rlnOpticsGroup #2\n")[-1]
    return [l.rsplit(b" ", 1)[0] for l in text.split(b"\n") if l.strip()]


# ---------------------------------------------------------------- checks

FIT = re.compile(r"Polynomial fit RMSD: X = (\S+) px Y = (\S+) px")


def strong_sidecar(run: Path, movie: bytes, side: dict, v2sha: str, revision: str, expect_pub="published") -> list:
    errs = []
    rec = run_rec(run)
    argv = mc_argv(rec)
    ident = side["identity"]
    if ident["binary_sha256"] != v2sha:
        errs.append("identity binary hash")
    if ident["configured_source_revision"] != revision or ident["configured_source_dirty"] != "false":
        errs.append("identity source revision/dirty")
    if [decode_text(a) for a in ident["argv"]] != [a.encode() for a in argv]:
        errs.append("identity argv")
    movie_file = os.path.join(os.fsencode(run), movie)
    if side["movie"]["bytes"] != os.path.getsize(movie_file):
        errs.append("movie.bytes")
    if side["movie"]["sha256"] != v1.sha256(Path(os.fsdecode(movie_file))):
        errs.append("movie sha256")
    stem = movie.rsplit(b".", 1)[0]
    log_path = Path(os.fsdecode(os.path.join(os.fsencode(run / "out"), stem + b".log")))
    log = log_path.read_text(errors="surrogateescape")
    errs += v1.check_sidecar_against_log(side, log, int(option(argv, "--max_iter", "5")))
    g, loc, m = side["global_alignment"], side["local_alignment"], side["local_model"]
    if g["route"] != "cpu" or g["max_iter"] != int(option(argv, "--max_iter", "5")) or g["tolerance_px"] != 0.5:
        errs.append("global route/max_iter/tolerance")
    finals = [p["final"] for p in loc["patches"]]
    if loc["patches_recorded"] != len(loc["patches"]) or \
            loc["solver_attempts"] != sum(len(p["attempts"]) for p in loc["patches"]) or \
            [loc["converged_patches"], loc["dropped_patches"], loc["interrupted_patches"]] != \
            [finals.count("converged"), finals.count("dropped"), finals.count("interrupted")]:
        errs.append("local counts")
    if any(a["route"] != "cpu" or a["kind"] != "first" for p in loc["patches"] for a in p["attempts"]):
        errs.append("patch route/kind")
    if loc["state"] == "attempted":
        if m["observations"] != 5 * loc["converged_patches"] or m["min_observations_exclusive"] != 18:
            errs.append("observations / bound limit")
        fit = FIT.search(log)
        if fit:
            if not (v1.close(m["fit_rmsd_x_px"], float(fit.group(1))) and v1.close(m["fit_rmsd_y_px"], float(fit.group(2)))) \
                    or m["fit_rmsd_limit_px"] != 10 or m["distortion_limit_px"] != 3:
                errs.append("fit rmsd / limits")
        elif m["fit_rmsd_x_px"] is not None or m["fit_rmsd_limit_px"] is not None:
            errs.append("fit fields without a fit")
    pub = side["publication"]["state"]
    if pub != expect_pub:
        errs.append(f"publication {pub}")
    elif pub == "published":
        star = Path(os.fsdecode(os.path.join(os.fsencode(run / "out"), stem + b".star")))
        mic = Path(os.fsdecode(os.path.join(os.fsencode(run / "out"), stem + b".mrc")))
        errs += v1.check_model_against_star(side, star.read_text(errors="surrogateescape"))
        if side["products"]["star"]["sha256"] != v1.sha256(star) or side["products"]["micrograph"]["sha256"] != v1.sha256(mic):
            errs.append("product bindings")
    return errs


def summary_checks(run: Path, v2sha: str, revision: str) -> tuple:
    errs = []
    path = run / "out" / "quality_summary.json"
    if not path.is_file():
        return None, ["no summary"]
    summary = load_json_strict(path)
    if summary["identity"]["binary_sha256"] != v2sha or summary["identity"]["configured_source_revision"] != revision:
        errs.append("summary identity")
    movies = [decode_text(e["movie"]) for e in summary["movies"]]
    if movies != membership(run):
        errs.append("summary entries != membership occurrences")
    counts = {"global_alignment": {}, "local_model": {}, "publication": {}}
    legacy = collisions = failures = 0
    for e in summary["movies"]:
        counts["publication"][e["publication"]] = counts["publication"].get(e["publication"], 0) + 1
        collisions += e["output_root_collision"]
        failures += e["sidecar"]["write_failed"]
        if e["sidecar"]["sha256"] is not None:
            if v1.sha256(Path(os.fsdecode(os.path.join(os.fsencode(run), decode_text(e["sidecar"]["path"]))))) != e["sidecar"]["sha256"]:
                errs.append("summary sidecar sha256")
        if e["source"] == "unknown_legacy":
            legacy += 1
            continue
        for k in ("global_alignment", "local_model"):
            counts[k][e[k]] = counts[k].get(e[k], 0) + 1
    c = summary["counts"]
    if any(counts[k] != c[k] for k in counts) or c["movies"] != len(summary["movies"]) or \
            [c["unknown_legacy"], c["output_root_collisions"], c["sidecar_write_failures"]] != [legacy, collisions, failures]:
        errs.append("summary counts")
    if summary["quality_evidence_complete"] != (legacy == 0 and collisions == 0 and failures == 0):
        errs.append("quality_evidence_complete")
    return summary, errs


def report_run(run: Path, v2sha: str, revision: str, expect_pub=None) -> list:
    """Strong checks on every sidecar plus the summary, for an ordinary report run."""
    expect_pub = expect_pub or {}
    errs = []
    summary, s_errs = summary_checks(run, v2sha, revision)
    errs += s_errs
    sc = sidecars(run)
    for movie in membership(run):
        if movie not in sc:
            errs.append(f"{movie!r}: no sidecar")
            continue
        errs += [f"{movie!r}: {e}" for e in strong_sidecar(run, movie, sc[movie][1], v2sha, revision,
                                                           expect_pub.get(movie, "published"))]
        if summary:
            entry = [e for e in summary["movies"] if decode_text(e["movie"]) == movie]
            if not entry or entry[0]["global_alignment"] != sc[movie][1]["global_alignment"]["state"] or \
                    entry[0]["publication"] != sc[movie][1]["publication"]["state"]:
                errs.append(f"{movie!r}: summary entry differs from sidecar")
    return errs


def collision_checks(run: Path, v2sha: str, revision: str) -> list:
    summary, errs = summary_checks(run, v2sha, revision)
    if summary is None:
        return errs
    if len(summary["movies"]) != 4 or any(not e["output_root_collision"] or e["publication"] != "ambiguous_output_root"
                                          or e["sidecar"]["path"] is not None for e in summary["movies"]):
        errs.append("collision entries")
    if summary["quality_evidence_complete"]:
        errs.append("collision evidence claimed complete")
    if sidecars(run):
        errs.append("sidecar written for a colliding root")
    return errs


def encoding_checks(run: Path, v2sha: str, revision: str) -> list:
    errs = report_run(run, v2sha, revision)
    sc = sidecars(run)
    if NON_UTF8 not in sc or not isinstance(sc[NON_UTF8][1]["movie"]["path"], dict):
        errs.append("non-UTF-8 path not hex-encoded")
    elif bytes.fromhex(sc[NON_UTF8][1]["movie"]["path"]["non_utf8_bytes_hex"]) != NON_UTF8:
        errs.append("hex bytes differ from file name")
    if UTF8 not in sc or sc[UTF8][1]["movie"]["path"] != UTF8.decode():
        errs.append("UTF-8 path not a plain string")
    return errs


RESUME_EXPECT = {b"in/zero.mrcs": ("unknown_legacy", "sidecar_invalid"),
                 b"in/integer.mrcs": ("unknown_legacy", "sidecar_invalid"),
                 b"in/fractional.mrcs": ("unknown_legacy", "sidecar_invalid"),
                 b"in/affine.mrcs": ("unknown_legacy", "sidecar_invalid"),
                 b"in/noisy.mrcs": ("unknown_legacy", "sidecar_invalid"),
                 b"in/flat.mrcs": ("resumed_sidecar", None)}


def resume_checks(run: Path, v2sha: str, revision: str) -> list:
    summary, errs = summary_checks(run, v2sha, revision)
    if summary is None:
        return errs
    got = {decode_text(e["movie"]): (e["source"], e["reason"]) for e in summary["movies"]}
    if got != RESUME_EXPECT:
        errs.append(f"resume classification {got}")
    # Per-movie files (products and sidecars) must be untouched; the joint STAR
    # and report are rewritten by every resume, with or without the flag.
    rec = run_rec(run)
    per_movie = lambda d: {k: v for k, v in d.items() if bytes.fromhex(k).startswith(b"in/")}
    if per_movie(tree_hashes(run / "out")) != per_movie(rec["out_before"]):
        errs.append("resume changed per-movie files")
    return errs


def row(name, ok, detail):
    return dict(row=name, verdict="PASS" if ok else "FAIL", detail=detail)


def check(args) -> int:
    root = Path(args.root)
    manifest = json.loads((root / "manifest.json").read_text())
    v2sha, revision = manifest["binaries"]["v2"]["sha256"], args.revision
    R = lambda q: root / q
    have = lambda q: (R(q) / "run.json").exists()
    ex = lambda q: run_rec(R(q))["exit"]
    rows, facts = [], {}

    def guarded(name, needed, fn):
        if not all(have(q) for q in needed):
            rows.append(dict(row=name, verdict="UNRUN", detail=f"missing {needed}"))
            return
        try:
            ok, detail = fn()
        except Exception as e:  # a crash is a FAIL, never a pass
            ok, detail = False, {"exception": repr(e)}
        rows.append(row(name, ok, detail))

    def r1():
        p1, l1 = products(R("Q1") / "out"), logs(R("Q1") / "out")
        d = dict(q2=products(R("Q2") / "out") == p1, q3=products(R("Q3") / "out") == p1,
                 q2_logs=logs(R("Q2") / "out") == l1, q3_logs=logs(R("Q3") / "out") == l1,
                 exits=[ex(q) for q in ("Q1", "Q2", "Q3")], q3_quality=[k for k in tree_hashes(R("Q3") / "out")
                                                                    if b"quality" in bytes.fromhex(k)])
        return all([d["q2"], d["q3"], d["q2_logs"], d["q3_logs"], d["exits"] == [0, 0, 0], not d["q3_quality"], p1]), d
    guarded("R1 default-off neutrality (products and logs)", ["Q1", "Q2", "Q3"], r1)

    def r2():
        errs = report_run(R("Q4"), v2sha, revision)
        summary = load_json_strict(R("Q4") / "out" / "quality_summary.json")
        facts["Q4_states"] = {e["movie"]: [e["global_alignment"], e["local_model"]] for e in summary["movies"]}
        if not summary["quality_evidence_complete"] or summary["joint_output"]["state"] != "published":
            errs.append("summary not complete/published")
        d = dict(products=products(R("Q4") / "out") == products(R("Q1") / "out"),
                 logs=logs(R("Q4") / "out") == logs(R("Q1") / "out"), exit=ex("Q4"), errors=errs)
        return d["products"] and d["logs"] and d["exit"] == 0 and not errs, d
    guarded("R2 report-on with strengthened checks", ["Q1", "Q4"], r2)

    def r3():
        errs = collision_checks(R("Q6"), v2sha, revision)
        joint = [v1.sha256(R(q) / "out" / "corrected_micrographs.star") for q in ("Q5", "Q6")]
        d = dict(products=products(R("Q6") / "out") == products(R("Q5") / "out"),
                 logs=logs(R("Q6") / "out") == logs(R("Q5") / "out"), exits=[ex("Q5"), ex("Q6")],
                 joint_equal=joint[0] == joint[1], errors=errs)
        return d["products"] and d["logs"] and d["exits"][0] == d["exits"][1] and d["joint_equal"] and not errs, d
    guarded("R3 duplicate input and shared output root", ["Q5", "Q6"], r3)

    def r4():
        d = dict(exits=[ex("Q7"), ex("Q8")], products=products(R("Q8") / "out") == products(R("Q7") / "out"))
        if d["exits"][0] != 0:
            d["note"] = "reference did not process the encoded names; conditional checks not applicable"
            return d["exits"][0] == d["exits"][1] and d["products"], d
        d["errors"] = encoding_checks(R("Q8"), v2sha, revision)
        return d["exits"] == [0, 0] and d["products"] and not d["errors"], d
    guarded("R4 non-UTF-8 and UTF-8 movie paths", ["Q7", "Q8"], r4)

    def r5():
        errs = resume_checks(R("Q9"), v2sha, revision)
        joint = [v1.sha256(R(q) / "out" / "corrected_micrographs.star") for q in ("Q9", "Q10")]
        d = dict(exits=[ex("Q9"), ex("Q10")], joint_equal=joint[0] == joint[1], errors=errs)
        return d["exits"] == [0, 0] and d["joint_equal"] and not errs, d
    guarded("R5 strict resume validation", ["Q9", "Q10"], r5)

    def r6():
        errs = report_run(R("Q12"), v2sha, revision, {b"in/integer.mrcs": "failed"})
        side = sidecars(R("Q12")).get(b"in/integer.mrcs")
        if not side or side[1]["publication"]["reason"] != "product_write_failed":
            errs.append("integer reason")
        summary = load_json_strict(R("Q12") / "out" / "quality_summary.json")
        if summary["joint_output"]["state"] != "withheld_movie_failures":
            errs.append("joint state")
        d = dict(exits=[ex("Q11"), ex("Q12")], products=products(R("Q12") / "out") == products(R("Q11") / "out"),
                 logs=logs(R("Q12") / "out") == logs(R("Q11") / "out"), errors=errs)
        return d["exits"][0] == d["exits"][1] != 0 and d["products"] and d["logs"] and not errs, d
    guarded("R6 product write failure", ["Q11", "Q12"], r6)

    def r7():
        summary, errs = summary_checks(R("Q13"), v2sha, revision)
        flat = [e for e in summary["movies"] if e["movie"] == "in/flat.mrcs"] if summary else []
        if not flat or not flat[0]["sidecar"]["write_failed"] or summary["quality_evidence_complete"]:
            errs.append("flat write failure not recorded")
        d = dict(exit=ex("Q13"), products=products(R("Q13") / "out") == products(R("Q1") / "out"),
                 sidecars=len(sidecars(R("Q13"))), errors=errs)
        return d["exit"] == 0 and d["products"] and d["sidecars"] == 5 and not errs, d
    guarded("R7 sidecar write failure", ["Q1", "Q13"], r7)

    def r8():
        errs = report_run(R("Q15"), v2sha, revision)
        side = sidecars(R("Q15")).get(b"in/integer.mrcs")
        m = side[1]["local_model"] if side else {}
        if (m.get("state"), m.get("reason"), m.get("min_observations_exclusive"), m.get("fit_rmsd_limit_px"),
                m.get("distortion_limit_px")) != ("global_only", "too_few_converged_observations", 18, None, None):
            errs.append(f"too-few model fields {m}")
        d = dict(exits=[ex("Q14"), ex("Q15")], products=products(R("Q15") / "out") == products(R("Q14") / "out"), errors=errs)
        return d["exits"] == [0, 0] and d["products"] and not errs, d
    guarded("R8 too-few fallback with bound limit", ["Q14", "Q15"], r8)

    def r9():  # PROTOCOL_V2 amendment A1: unknown options only warn
        stderr = (R("Q16") / "stderr.txt").read_bytes()
        d = dict(exit=ex("Q16"),
                 warns=b"Option --experimental_quality_report" in stderr and b"is not a valid RELION argument" in stderr,
                 products=products(R("Q16") / "out") == products(R("Q1") / "out"),
                 logs=logs(R("Q16") / "out") == logs(R("Q1") / "out"),
                 quality=[k for k in tree_hashes(R("Q16") / "out") if b"quality" in bytes.fromhex(k)])
        return d["exit"] == 0 and d["warns"] and d["products"] and d["logs"] and not d["quality"], d
    guarded("R9 OFF build warns about the flag and is otherwise neutral", ["Q1", "Q16"], r9)

    def r10():
        found = {q: tmp_files(R(q)) for q, *_ in PLAN if have(q)}
        return not any(found.values()), {k: v for k, v in found.items() if v}
    guarded("R10 no temporary files left (runs present)", [], r10)

    rows += negative_controls(root, v2sha, revision)
    (root / "results.json").write_text(json.dumps(dict(rows=rows, facts=facts), indent=2, default=repr) + "\n")
    for r in rows:
        print(f"{r['verdict']:6} {r['row']}")
    return 0 if all(r["verdict"] == "PASS" for r in rows) else 1


# ---------------------------------------------------------------- negative controls

def negative_controls(root: Path, v2sha: str, revision: str) -> list:
    rows = []
    work = root / "negative_controls_v2"
    if work.exists():
        shutil.rmtree(work)

    def clone(q, name):
        dst = work / name
        shutil.copytree(root / q, dst, symlinks=True)
        return dst

    def edit_json(path: Path, fn):
        data = load_json_strict(path)
        fn(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def side_path(run, case):
        return run / "out" / "in" / f"{case}.quality.json"

    def bump_final(d):
        loc = d["local_alignment"]
        p = next(p for p in loc["patches"] if p["final"] == "converged")
        p["final"] = "dropped"
        loc["converged_patches"] -= 1
        loc["dropped_patches"] += 1

    sidecar_cases = [
        ("NC1 identity binary hash", lambda d: d["identity"].update(binary_sha256="0" * 64)),
        ("NC2 identity argv", lambda d: d["identity"]["argv"].append("--extra")),
        ("NC5 solver_attempts", lambda d: d["local_alignment"].update(solver_attempts=d["local_alignment"]["solver_attempts"] + 1)),
        ("NC6 patch final relabel, counts consistent", bump_final),
        ("NC7 observations", lambda d: d["local_model"].update(observations=d["local_model"]["observations"] + 5)),
        ("NC8 fit_rmsd_x", lambda d: d["local_model"].update(fit_rmsd_x_px=d["local_model"]["fit_rmsd_x_px"] + 0.01)),
        ("NC9 movie.bytes", lambda d: d["movie"].update(bytes=d["movie"]["bytes"] + 1)),
    ]
    q4 = root / "Q4"
    if (q4 / "run.json").exists():
        rows.append(row("PC untouched Q4 copy accepted", not report_run(clone("Q4", "PC"), v2sha, revision), "must accept"))
        for i, (name, fn) in enumerate(sidecar_cases):
            run = clone("Q4", f"NCS{i}")
            edit_json(side_path(run, "affine"), fn)
            rows.append(row(name + " rejected", bool(report_run(run, v2sha, revision)), "must reject"))
        run = clone("Q4", "NC3")
        edit_json(run / "out" / "quality_summary.json", lambda d: d["movies"][0]["sidecar"].update(sha256="0" * 64))
        rows.append(row("NC3 summary sidecar sha256 rejected", bool(report_run(run, v2sha, revision)), "must reject"))
        run = clone("Q4", "NC4")
        edit_json(run / "out" / "quality_summary.json", lambda d: d["counts"].update(movies=d["counts"]["movies"] + 1))
        rows.append(row("NC4 summary count rejected", bool(report_run(run, v2sha, revision)), "must reject"))
    else:
        rows.append(dict(row="PC/NC1-NC9 on Q4", verdict="UNRUN", detail="Q4 missing"))
    if (root / "Q6" / "run.json").exists():
        run = clone("Q6", "NC10")
        edit_json(run / "out" / "quality_summary.json", lambda d: d["movies"][2].update(publication="published"))
        rows.append(row("NC10 collision entry relabelled published rejected", bool(collision_checks(run, v2sha, revision)), "must reject"))
    if (root / "Q8" / "run.json").exists() and run_rec(root / "Q8")["exit"] == 0:
        run = clone("Q8", "NC11")
        sc = sidecars(run)
        if NON_UTF8 in sc:
            edit_json(sc[NON_UTF8][0], lambda d: d["movie"].update(path={"non_utf8_bytes_hex": NON_UTF8.hex()[:-2] + "00"}))
        rows.append(row("NC11 encoded path hex altered rejected", bool(encoding_checks(run, v2sha, revision)), "must reject"))
    if (root / "Q9" / "run.json").exists():
        run = clone("Q9", "NC12")
        edit_json(run / "out" / "quality_summary.json",
                  lambda d: d["movies"][0].update(source="resumed_sidecar", reason=None))
        rows.append(row("NC12 resume entry relabelled resumed_sidecar rejected", bool(resume_checks(run, v2sha, revision)), "must reject"))
    return rows


def selftest(_args) -> int:
    ok = v1.selftest(None) == 0
    ok &= decode_text({"non_utf8_bytes_hex": "e9"}) == b"\xe9" and decode_text("a") == b"a"
    try:
        decode_text({"non_utf8_bytes_hex": "e9", "x": 1})
        ok = False
    except ValueError:
        pass
    ok &= bool(LOG_DROP.search(b"Full movie wall time: 0.1 s")) and not LOG_DROP.search(b" Iteration 1: RMSD = 1 px")
    print("selftest v2", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("campaign")
    c.add_argument("--fixtures", required=True)
    c.add_argument("--root", required=True)
    for k in ("v0", "v1", "v2"):
        c.add_argument(f"--{k}", required=True)
    c.add_argument("--revision", required=True)
    c.add_argument("--cpu", type=int)
    c.add_argument("--skip", type=lambda v: v.split(","), default=[], help="development only")
    k = sub.add_parser("check")
    k.add_argument("--root", required=True)
    k.add_argument("--revision", required=True)
    sub.add_parser("selftest")
    args = ap.parse_args()
    return {"campaign": campaign, "check": check, "selftest": selftest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
