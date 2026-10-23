#!/usr/bin/env python3
"""Frozen #268 quality-report prototype controls (PROTOCOL.md).

    quality_controls.py campaign --fixtures DIR --root NEWDIR --b0 BIN --b1 BIN --b2 BIN \
        [--cpu 14] [--record-only]
    quality_controls.py check --root DIR
    quality_controls.py selftest

`campaign` verifies fixture hashes, runs P1..P12 once each (no retries), then
runs `check`. `check` evaluates E1..E7 and the checker negative controls N1..N5
from the retained run tree and writes `<root>/results.json`. `selftest` runs the
checker's negative controls on synthetic data only (no MotionCorr process).
Standard library only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CASES6 = ["zero", "integer", "fractional", "affine", "flat", "noisy"]
COMMON = ["--use_own", "--j", "1", "--bin_factor", "1", "--seed", "1", "--skip_defect",
          "--save_noDW", "--first_frame_sum", "1", "--last_frame_sum", "5", "--skip_logfile"]
FLAG = "--experimental_quality_report"
SKIP_SUFFIXES = (".log", ".pdf", ".eps", ".lst")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- setup

def verify_fixtures(fixtures: Path) -> dict:
    record = json.loads((REPO / "test-data/motion_diagnostics_v2/GENERATION_RECORD.json").read_text())
    out = {}
    for case in CASES6:
        for name, digest in record["cases"][case]["files"].items():
            got = sha256(fixtures / name)
            if got != digest:
                raise SystemExit(f"fixture mismatch {name}: {got} != {digest}")
            out[name] = got
    return out


def movies_star(fixtures: Path, cases) -> str:
    optics = (fixtures / "zero.star").read_text().split("data_movies")[0].rstrip()
    rows = "\n".join(f"in/{c}.mrcs 1" for c in cases)
    return (f"{optics}\n\n# version 30001\n\ndata_movies\n\nloop_\n"
            f"_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n{rows}\n")


def stage(run: Path, fixtures: Path, cases) -> None:
    (run / "in").mkdir(parents=True)
    for c in cases:
        shutil.copy2(fixtures / f"{c}.mrcs", run / "in" / f"{c}.mrcs")
    (run / "in" / "batch.star").write_text(movies_star(fixtures, cases))


PLAN = [
    # id, binary, cases, patches, extra argv, injection
    ("P1", "b0", CASES6, 3, [], None),
    ("P2", "b1", CASES6, 3, [], None),
    ("P3", "b2", CASES6, 3, [], None),
    ("P4", "b2", CASES6, 3, [FLAG], None),
    ("P5", "b0", ["affine"], 3, ["--max_iter", "1"], None),
    ("P6", "b2", ["affine"], 3, ["--max_iter", "1", FLAG], None),
    ("P7", "b0", ["zero", "integer"], 1, [], "product_dir"),
    ("P8", "b2", ["zero", "integer"], 1, [FLAG], "product_dir"),
    ("P9", "b2", CASES6, 3, [FLAG], "sidecar_dir"),
    ("P10", "b2", CASES6, 3, [FLAG], "summary_dir"),
    ("P11", "b2", CASES6, 3, ["--only_do_unfinished", FLAG], "resume"),
    ("P12", "b0", CASES6, 3, ["--only_do_unfinished"], "resume_reference"),
    # Amendment A1 (PROTOCOL.md): the too-few-observations fallback.
    ("P13", "b0", ["integer"], 3, ["--max_iter", "1"], None),
    ("P14", "b2", ["integer"], 3, ["--max_iter", "1", FLAG], None),
]


def product_files(out: Path, case: str):
    return sorted(p for p in (out / "in").glob(f"{case}*") if p.is_file())


def prepare_resume(root: Path, run: Path, with_sidecars: bool) -> None:
    out = run / "out"
    (out / "in").mkdir(parents=True)
    sources = {"zero": "P1", "integer": "P1", "fractional": "P4", "affine": "P4", "flat": "P4", "noisy": "P4"}
    for case, src in sources.items():
        for f in product_files(root / src / "out", case):
            if ".quality" in f.name and (not with_sidecars or ".superseded-" in f.name):
                continue
            shutil.copy2(f, out / "in" / f.name)
    (out / "in" / "flat.star").unlink()
    if with_sidecars:
        side = out / "in" / "affine.quality.json"
        data = json.loads(side.read_text())
        data["products"]["star"]["sha256"] = "0" * 64
        side.write_text(json.dumps(data, indent=2) + "\n")


def campaign(args) -> int:
    root = Path(args.root)
    root.mkdir(parents=False, exist_ok=False)
    fixtures = Path(args.fixtures)
    binaries = {k: Path(getattr(args, k)).resolve() for k in ("b0", "b1", "b2")}
    manifest = dict(fixtures=verify_fixtures(fixtures),
                    binaries={k: dict(path=str(v), sha256=sha256(v)) for k, v in binaries.items()},
                    cpu=args.cpu, host=os.uname().nodename, started=time.time(), runs=[])
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    env = dict(os.environ, OMP_NUM_THREADS="1")
    for pid, binary, cases, patches, extra, injection in PLAN:
        run = root / pid
        stage(run, fixtures, cases)
        if injection == "product_dir":
            (run / "out" / "in" / "integer.mrc").mkdir(parents=True)
        elif injection == "sidecar_dir":
            (run / "out" / "in" / "flat.quality.json").mkdir(parents=True)
        elif injection == "summary_dir":
            (run / "out" / "quality_summary.json").mkdir(parents=True)
        elif injection == "resume":
            prepare_resume(root, run, with_sidecars=True)
        elif injection == "resume_reference":
            prepare_resume(root, run, with_sidecars=False)
        argv = [str(binaries[binary]), "--i", "in/batch.star", "--o", "out/"] + COMMON + \
               ["--patch_x", str(patches), "--patch_y", str(patches)] + extra
        if args.cpu is not None:
            argv = ["taskset", "-c", str(args.cpu)] + argv
        t0 = time.time()
        proc = subprocess.run(argv, cwd=run, env=env, capture_output=True, text=True)
        (run / "stdout.txt").write_text(proc.stdout)
        (run / "stderr.txt").write_text(proc.stderr)
        rec = dict(id=pid, binary=binary, argv=argv, cwd=str(run), exit=proc.returncode,
                   seconds=round(time.time() - t0, 3), injection=injection)
        (run / "run.json").write_text(json.dumps(rec, indent=2) + "\n")
        manifest["runs"].append(rec)
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{pid} exit {proc.returncode} ({rec['seconds']} s)", flush=True)
    if args.record_only:
        return 0
    return check(argparse.Namespace(root=str(root)))


# ---------------------------------------------------------------- comparison

def normalized_digest(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".mrc" and len(data) >= 1024:
        data = data[:224] + b"\0" * 80 + data[304:]  # first label holds the write time
    return hashlib.sha256(data).hexdigest()


def products(out: Path) -> dict:
    result = {}
    if not out.exists():
        return result
    for p in sorted(out.rglob("*")):
        if not p.is_file() or ".quality" in p.name or p.name.startswith("quality_summary"):
            continue
        if p.suffix in SKIP_SUFFIXES or ".tmp." in p.name:
            continue
        result[str(p.relative_to(out))] = normalized_digest(p)
    return result


def exit_of(run: Path) -> int:
    return json.loads((run / "run.json").read_text())["exit"]


# ---------------------------------------------------------------- log witness

def log_sections(log_text: str):
    """Global and per-patch RMSD sequences as printed by the solver."""
    glob_part, _, local_part = log_text.partition("Local alignments:")
    it = re.compile(r"^ Iteration (\d+): RMSD = (\S+) px", re.M)
    global_rmsd = [float(m.group(2)) for m in it.finditer(glob_part)]
    patches = []
    for block in re.split(r"^Patch \(", local_part, flags=re.M)[1:]:
        patches.append([float(m.group(2)) for m in it.finditer(block)])
    return global_rmsd, patches


def close(a, b) -> bool:
    # The log prints six significant digits by default.
    return a is not None and abs(a - b) <= 5e-6 * max(1.0, abs(b))


def check_sidecar_against_log(side: dict, log_text: str, max_iter: int) -> list:
    errs = []
    g = side["global_alignment"]
    rmsd, patches = log_sections(log_text)
    if g["iterations"] != len(rmsd):
        errs.append(f"global iterations {g['iterations']} != logged {len(rmsd)}")
    elif rmsd:
        if not close(g["final_incremental_rmsd_px"], rmsd[-1]):
            errs.append(f"global final rmsd {g['final_incremental_rmsd_px']} != logged {rmsd[-1]}")
        expect = "converged" if rmsd[-1] < 0.5 else "iteration_limit"
        if g["state"] != expect:
            errs.append(f"global state {g['state']} != {expect}")
        if expect == "iteration_limit" and len(rmsd) != max_iter:
            errs.append("iteration_limit without max_iter iterations")
    loc = side["local_alignment"]
    if loc["state"] == "attempted":
        if len(patches) != loc["patches_planned"] or len(loc["patches"]) != len(patches):
            errs.append("patch count mismatch with log")
        for rec, logged in zip(loc["patches"], patches):
            attempts = rec["attempts"]
            total = sum(a["iterations"] for a in attempts)
            if total != len(logged):
                errs.append(f"patch {rec['index']} iterations {total} != logged {len(logged)}")
                continue
            if attempts and not close(attempts[-1]["final_incremental_rmsd_px"], logged[-1]):
                errs.append(f"patch {rec['index']} final rmsd mismatch")
            final = "converged" if logged and logged[-1] < 0.5 else "dropped"
            if rec["final"] != final:
                errs.append(f"patch {rec['index']} final {rec['final']} != {final}")
        if loc["converged_patches"] + loc["dropped_patches"] != loc["patches_planned"]:
            errs.append("converged + dropped != planned")
        if loc["same_input_retries"] != 0 and side["identity"]["backend"] == "cpu":
            errs.append("CPU route reported a same-input retry")
    if side["motion_identifiability"] != "not_assessed" or side["peak_validity"] != "not_assessed":
        errs.append("identifiability/peak validity claimed")
    return errs


def check_model_against_star(side: dict, star_text: str) -> list:
    has_local = "data_local_motion_model" in star_text
    state = side["local_model"]["state"]
    if side["local_alignment"]["state"] == "not_requested":
        return [] if state == "not_requested" and not has_local else [f"1x1 model state {state}"]
    if has_local != (state == "retained"):
        return [f"local model state {state} but STAR local block {has_local}"]
    if state == "global_only":
        obs, reason = side["local_model"]["observations"], side["local_model"]["reason"]
        if reason == "too_few_converged_observations" and not (obs is not None and obs <= 18):
            return ["too_few reason with observations > 18"]
        if reason != "too_few_converged_observations" and not (obs is not None and obs > 18):
            return [f"{reason} with observations <= 18"]
    return []


def summary_consistent(summary: dict, sidecars: dict) -> list:
    errs = []
    counts = {"global_alignment": {}, "local_model": {}, "publication": {}}
    for e in summary["movies"]:
        if e["source"] == "unknown_legacy":
            continue
        for key in counts:
            counts[key][e[key]] = counts[key].get(e[key], 0) + 1
        side = sidecars.get(e["movie"])
        if side is not None and e["source"] == "this_run":
            if e["global_alignment"] != side["global_alignment"]["state"]:
                errs.append(f"{e['movie']} summary global differs from sidecar")
            if e["publication"] != side["publication"]["state"]:
                errs.append(f"{e['movie']} summary publication differs from sidecar")
    for key in counts:
        if counts[key] != summary["counts"][key]:
            errs.append(f"summary counts {key} {summary['counts'][key]} != {counts[key]}")
    return errs


def load_run_sidecars(out: Path) -> dict:
    result = {}
    for p in sorted((out / "in").glob("*.quality.json")):
        if p.is_file():
            data = json.loads(p.read_text())
            result[data["movie"]["path"]] = data
    return result


def verify_report_run(run: Path, cases, max_iter: int, expect_published: dict) -> list:
    out = run / "out"
    errs = []
    sidecars = load_run_sidecars(out)
    for case in cases:
        movie = f"in/{case}.mrcs"
        side = sidecars.get(movie)
        if side is None:
            errs.append(f"{case}: no sidecar")
            continue
        log = (out / "in" / f"{case}.log").read_text()
        errs += [f"{case}: {e}" for e in check_sidecar_against_log(side, log, max_iter)]
        pub = side["publication"]["state"]
        if pub != expect_published.get(case, "published"):
            errs.append(f"{case}: publication {pub}")
            continue
        if pub == "published":
            star = out / "in" / f"{case}.star"
            if not star.is_file() or not (out / "in" / f"{case}.mrc").is_file():
                errs.append(f"{case}: published without products")
                continue
            errs += [f"{case}: {e}" for e in check_model_against_star(side, star.read_text())]
            if side["products"]["star"]["sha256"] != sha256(star):
                errs.append(f"{case}: STAR binding mismatch")
            if side["products"]["micrograph"]["sha256"] != sha256(out / "in" / f"{case}.mrc"):
                errs.append(f"{case}: micrograph binding mismatch")
        if side["movie"]["sha256"] != sha256(run / "in" / f"{case}.mrcs"):
            errs.append(f"{case}: movie binding mismatch")
    return errs


# ---------------------------------------------------------------- rows

def row(name, ok, detail):
    return dict(row=name, verdict="PASS" if ok else "FAIL", detail=detail)


def check(args) -> int:
    root = Path(args.root)
    rows, facts = [], {}
    R = lambda pid: root / pid
    have = lambda pid: (R(pid) / "run.json").exists()

    def unrun(name, why):
        rows.append(dict(row=name, verdict="UNRUN", detail=why))

    # E1
    if all(have(p) for p in ("P1", "P2", "P3")):
        p1 = products(R("P1") / "out")
        d = dict(p2_equal=products(R("P2") / "out") == p1, p3_equal=products(R("P3") / "out") == p1,
                 exits=[exit_of(R(p)) for p in ("P1", "P2", "P3")],
                 p3_quality_files=sorted(str(p) for p in (R("P3") / "out").rglob("*quality*")),
                 p1_files=len(p1))
        rows.append(row("E1 default-off neutrality", d["p2_equal"] and d["p3_equal"] and
                        d["exits"] == [0, 0, 0] and not d["p3_quality_files"] and d["p1_files"] > 0, d))
    else:
        unrun("E1 default-off neutrality", "P1/P2/P3 missing")

    # E2
    if have("P1") and have("P4"):
        out = R("P4") / "out"
        errs = verify_report_run(R("P4"), CASES6, 5, {})
        summary_path = out / "quality_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        sidecars = load_run_sidecars(out)
        if summary is None:
            errs.append("no summary")
        else:
            errs += summary_consistent(summary, sidecars)
            if not summary["quality_evidence_complete"] or summary["joint_output"]["state"] != "published":
                errs.append("summary not complete/published")
        identical = products(out) == products(R("P1") / "out")
        states = {Path(k).stem: v["global_alignment"]["state"] for k, v in sidecars.items()}
        models = {Path(k).stem: [v["local_model"]["state"], v["local_model"]["reason"],
                                 v["local_alignment"]["converged_patches"]] for k, v in sidecars.items()}
        prediction = dict(zero="converged", integer="iteration_limit", fractional="iteration_limit",
                          noisy="iteration_limit", affine="converged", flat="converged")
        facts["P4_global_states"] = states
        facts["P4_local"] = models
        facts["P4_prediction_differences"] = {k: [prediction[k], v] for k, v in states.items() if prediction.get(k) != v}
        d = dict(products_identical_to_P1=identical, exit=exit_of(R("P4")), errors=errs)
        rows.append(row("E2 report-on, solver-consistent", identical and d["exit"] == 0 and not errs, d))
    else:
        unrun("E2 report-on, solver-consistent", "P1/P4 missing")

    # E3
    if have("P5") and have("P6"):
        errs = verify_report_run(R("P6"), ["affine"], 1, {})
        side = load_run_sidecars(R("P6") / "out").get("in/affine.mrcs")
        if side:
            g = side["global_alignment"]
            if g["state"] != "iteration_limit" or g["iterations"] != 1:
                errs.append(f"forced global {g['state']} {g['iterations']}")
            if side["local_alignment"]["converged_patches"] < 4 and (
                    side["local_model"]["state"], side["local_model"]["reason"]) != (
                    "global_only", "too_few_converged_observations"):
                errs.append("too-few fallback not reported")
            facts["P6_local"] = [side["local_alignment"]["converged_patches"],
                                 side["local_model"]["state"], side["local_model"]["reason"]]
        identical = products(R("P6") / "out") == products(R("P5") / "out")
        d = dict(products_identical_to_P5=identical, exits=[exit_of(R("P5")), exit_of(R("P6"))], errors=errs)
        rows.append(row("E3 forced max_iter=1 limit and local drops", identical and d["exits"] == [0, 0] and not errs, d))
    else:
        unrun("E3 forced max_iter=1 limit and local drops", "P5/P6 missing")

    # E4
    if have("P7") and have("P8"):
        out = R("P8") / "out"
        errs = verify_report_run(R("P8"), ["zero", "integer"], 5, {"integer": "failed"})
        sidecars = load_run_sidecars(out)
        integer = sidecars.get("in/integer.mrcs")
        if integer and integer["publication"]["reason"] != "product_write_failed":
            errs.append(f"integer reason {integer['publication']['reason']}")
        for k, v in sidecars.items():
            if v["local_alignment"]["state"] != "not_requested" or v["local_model"]["state"] != "not_requested":
                errs.append(f"{k} local not not_requested")
        summary_path = out / "quality_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        if not summary or summary["joint_output"]["state"] != "withheld_movie_failures":
            errs.append("summary joint state")
        else:
            errs += summary_consistent(summary, sidecars)
        e7, e8 = exit_of(R("P7")), exit_of(R("P8"))
        identical = products(out) == products(R("P7") / "out")
        d = dict(exits=[e7, e8], retained_products_identical=identical, errors=errs)
        rows.append(row("E4 product write failure reported", e7 == e8 and e7 != 0 and identical and not errs, d))
    else:
        unrun("E4 product write failure reported", "P7/P8 missing")

    # E5
    if have("P1") and have("P4") and have("P9"):
        out = R("P9") / "out"
        sidecars = load_run_sidecars(out)
        summary_path = out / "quality_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        errs = []
        if "in/flat.mrcs" in sidecars:
            errs.append("flat sidecar present")
        flat = [e for e in (summary or {}).get("movies", []) if e["movie"] == "in/flat.mrcs"]
        if not summary or not flat or not flat[0]["sidecar"]["write_failed"] or summary["quality_evidence_complete"]:
            errs.append("summary does not record the flat write failure")
        p4 = load_run_sidecars(R("P4") / "out")
        for k, v in sidecars.items():
            a, b = copy.deepcopy(v), copy.deepcopy(p4.get(k))
            for x in (a, b):
                if x:
                    x.pop("identity", None)
                    # Amendment A2: MRC write time makes product hashes run-specific.
                    for product in (x.get("products") or {}).values():
                        if product:
                            product.pop("sha256", None)
            if a != b:
                errs.append(f"{k} differs from P4 beyond identity and product hashes")
        errs += verify_report_run(R("P9"), [c for c in CASES6 if c != "flat"], 5, {})
        identical = products(out) == products(R("P1") / "out")
        d = dict(products_identical_to_P1=identical, exit=exit_of(R("P9")), sidecars=len(sidecars), errors=errs)
        rows.append(row("E5 sidecar write failure", identical and d["exit"] == 0 and len(sidecars) == 5 and not errs, d))
    else:
        unrun("E5 sidecar write failure", "P1/P4/P9 missing")

    # E6
    if have("P1") and have("P10"):
        out = R("P10") / "out"
        stderr = (R("P10") / "stderr.txt").read_text()
        d = dict(products_identical_to_P1=products(out) == products(R("P1") / "out"), exit=exit_of(R("P10")),
                 sidecars=len(load_run_sidecars(out)), summary_is_dir=(out / "quality_summary.json").is_dir(),
                 warning="quality summary not written" in stderr)
        rows.append(row("E6 aggregate write failure", all([d["products_identical_to_P1"], d["exit"] == 0,
                        d["sidecars"] == 6, d["summary_is_dir"], d["warning"]]), d))
    else:
        unrun("E6 aggregate write failure", "P1/P10 missing")

    # E7
    if have("P11") and have("P12"):
        o11, o12 = R("P11") / "out", R("P12") / "out"
        errs = []
        summary_path = o11 / "quality_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
        expect = {"in/zero.mrcs": ("unknown_legacy", "sidecar_missing"),
                  "in/integer.mrcs": ("unknown_legacy", "sidecar_missing"),
                  "in/affine.mrcs": ("unknown_legacy", "sidecar_stale"),
                  "in/fractional.mrcs": ("resumed_sidecar", None),
                  "in/noisy.mrcs": ("resumed_sidecar", None),
                  "in/flat.mrcs": ("this_run", None)}
        got = {e["movie"]: (e["source"], e["reason"]) for e in (summary or {}).get("movies", [])}
        if got != expect:
            errs.append(f"resume sources {got}")
        if not summary or summary["quality_evidence_complete"]:
            errs.append("summary claims complete evidence")
        joint_equal = sha256(o11 / "corrected_micrographs.star") == sha256(o12 / "corrected_micrographs.star") \
            if (o11 / "corrected_micrographs.star").is_file() and (o12 / "corrected_micrographs.star").is_file() else False
        flat_equal = {k: v for k, v in products(o11).items() if "flat" in k} == \
                     {k: v for k, v in products(o12).items() if "flat" in k}
        d = dict(exits=[exit_of(R("P11")), exit_of(R("P12"))], joint_star_equal=joint_equal,
                 flat_products_equal=flat_equal, all_products_equal=products(o11) == products(o12), errors=errs)
        rows.append(row("E7 old/missing/stale sidecar resume", d["exits"] == [0, 0] and joint_equal and flat_equal
                        and d["all_products_equal"] and not errs, d))
    else:
        unrun("E7 old/missing/stale sidecar resume", "P11/P12 missing")

    # E8 (amendment A1)
    if have("P13") and have("P14"):
        errs = verify_report_run(R("P14"), ["integer"], 1, {})
        side = load_run_sidecars(R("P14") / "out").get("in/integer.mrcs")
        if side:
            g, m = side["global_alignment"], side["local_model"]
            if g["state"] != "iteration_limit" or g["iterations"] != 1:
                errs.append(f"forced global {g['state']} {g['iterations']}")
            if (m["state"], m["reason"]) != ("global_only", "too_few_converged_observations"):
                errs.append(f"model {m['state']} {m['reason']}")
            facts["P14_local"] = [side["local_alignment"]["converged_patches"], m["state"], m["reason"], m["observations"]]
        identical = products(R("P14") / "out") == products(R("P13") / "out")
        d = dict(products_identical_to_P13=identical, exits=[exit_of(R("P13")), exit_of(R("P14"))], errors=errs)
        rows.append(row("E8 too-few-observations fallback reported", identical and d["exits"] == [0, 0] and not errs, d))
    else:
        unrun("E8 too-few-observations fallback reported", "P13/P14 missing")

    rows += negative_controls(root)
    result = dict(rows=rows, facts=facts)
    (root / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(f"{r['verdict']:6} {r['row']}")
    return 0 if all(r["verdict"] == "PASS" for r in rows) else 1


# ---------------------------------------------------------------- negative controls

def negative_controls(root: Path) -> list:
    """Each tamper must make the corresponding checker reject (N1..N5)."""
    rows = []
    p4, p8 = root / "P4", root / "P8"
    if not (p4 / "run.json").exists():
        return [dict(row="N1-N5 checker negative controls", verdict="UNRUN", detail="P4 missing")]
    work = root / "negative_controls"
    if work.exists():
        shutil.rmtree(work)

    def clone(src, name):
        dst = work / name
        shutil.copytree(src, dst, symlinks=True)
        return dst

    def tamper_sidecar(run, case, fn):
        p = run / "out" / "in" / f"{case}.quality.json"
        data = json.loads(p.read_text())
        fn(data)
        p.write_text(json.dumps(data, indent=2) + "\n")

    n1 = clone(p4, "N1")
    tamper_sidecar(n1, "integer", lambda d: d["global_alignment"].update(state="converged"))
    rows.append(row("N1 integer state->converged rejected", bool(verify_report_run(n1, ["integer"], 5, {})), "checker must reject"))

    n2 = clone(p4, "N2")
    f = n2 / "out" / "in" / "fractional.mrc"
    data = bytearray(f.read_bytes()); data[2048] ^= 0x01; f.write_bytes(bytes(data))
    rows.append(row("N2 voxel byte flip rejected", products(n2 / "out") != products(p4 / "out"), "comparator must reject"))

    n3 = clone(p4, "N3")
    tamper_sidecar(n3, "flat", lambda d: d.update(motion_identifiability="identifiable"))
    rows.append(row("N3 flat identifiable claim rejected", bool(verify_report_run(n3, ["flat"], 5, {})), "checker must reject"))

    if (p8 / "run.json").exists():
        n4 = clone(p8, "N4")
        tamper_sidecar(n4, "integer", lambda d: d["publication"].update(state="published", reason=None))
        rows.append(row("N4 failed movie claimed published rejected",
                        bool(verify_report_run(n4, ["integer"], 5, {"integer": "failed"})), "checker must reject"))
    else:
        rows.append(dict(row="N4 failed movie claimed published rejected", verdict="UNRUN", detail="P8 missing"))

    n5 = clone(p4, "N5")
    def bump(d):
        patches = d["local_alignment"]["patches"]
        if patches and patches[0]["attempts"]:
            patches[0]["attempts"][0]["iterations"] += 1
    tamper_sidecar(n5, "affine", bump)
    rows.append(row("N5 patch iteration count rejected", bool(verify_report_run(n5, ["affine"], 5, {})), "checker must reject"))
    return rows


def selftest(_args) -> int:
    """Checker logic on synthetic records; no MotionCorr process."""
    log = ("Global alignment:\n Iteration 1: RMSD = 3.5 px\n Iteration 2: RMSD = 0.25 px\n"
           "Local alignments:\nPatch (1, 1): 1 / 1\n Iteration 1: RMSD = 0.75 px\n")
    side = {"global_alignment": {"state": "converged", "iterations": 2, "final_incremental_rmsd_px": 0.25},
            "local_alignment": {"state": "attempted", "patches_planned": 1, "converged_patches": 0,
                                "dropped_patches": 1, "same_input_retries": 0,
                                "patches": [{"index": 1, "final": "dropped", "attempts": [
                                    {"iterations": 1, "final_incremental_rmsd_px": 0.75}]}]},
            "identity": {"backend": "cpu"}, "motion_identifiability": "not_assessed",
            "peak_validity": "not_assessed"}
    ok = not check_sidecar_against_log(side, log, 5)
    bad = copy.deepcopy(side); bad["global_alignment"]["state"] = "iteration_limit"
    ok &= bool(check_sidecar_against_log(bad, log, 5))
    bad = copy.deepcopy(side); bad["local_alignment"]["patches"][0]["final"] = "converged"
    ok &= bool(check_sidecar_against_log(bad, log, 5))
    bad = copy.deepcopy(side); bad["motion_identifiability"] = "identifiable"
    ok &= bool(check_sidecar_against_log(bad, log, 5))
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("campaign")
    c.add_argument("--fixtures", required=True)
    c.add_argument("--root", required=True)
    for k in ("b0", "b1", "b2"):
        c.add_argument(f"--{k}", required=True)
    c.add_argument("--cpu", type=int)
    c.add_argument("--record-only", action="store_true")
    k = sub.add_parser("check")
    k.add_argument("--root", required=True)
    sub.add_parser("selftest")
    args = ap.parse_args()
    return {"campaign": campaign, "check": check, "selftest": selftest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
