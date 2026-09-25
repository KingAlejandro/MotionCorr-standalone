#!/usr/bin/env python3
"""Layer 3: run the prespecified perturbation matrix through the real binary.

CPU-only. Never touches the shared GPU host. Three phases:

  --emit-manifest   write the run list as JSON (no execution)
  --execute         run the manifest with a bounded worker pool
  --collect         compute every diagnostic against the per-movie reference

The manifest is emitted and committed before execution so the run list is
auditable and the matrix cannot drift once results start arriving.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration.prespecification import (  # noqa: E402
    BFACTOR,
    DOSE_PER_FRAME,
    HOLDOUT_MOVIES,
    L3_PROC_BIND,
    L3_REPEATS,
    L3_THREAD_COUNTS,
    PATCH_X,
    PATCH_Y,
    SELECTION_MOVIES,
    SEVERITY_GRIDS,
    split_grid,
)

BASE_OPTS = [
    "--use_own", "--seed", "1", "--dose_weighting",
    "--patch_x", str(PATCH_X), "--patch_y", str(PATCH_Y),
    "--bfactor", str(BFACTOR),
]


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_manifest(movies: List[str], gain_variants: Dict[str, str]) -> List[Dict[str, Any]]:
    """The prespecified layer-3 run list.

    Coverage is deliberately uneven and the reason is recorded per group:
    the harmless matrix needs every selection movie because it sets the noise
    floor that every threshold margin is measured against, while the movie-
    rewriting faults are pilot-scale because each costs a 1.4 GB stack.
    """
    runs: List[Dict[str, Any]] = []

    def add(movie: str, group: str, label: str, **kw: Any) -> None:
        runs.append({
            "run_id": f"{movie}__{label}",
            "movie": movie,
            "group": group,
            "label": label,
            "threads": kw.pop("threads", 1),
            "proc_bind": kw.pop("proc_bind", "unset"),
            "dose_per_frame": kw.pop("dose_per_frame", DOSE_PER_FRAME),
            "gainref": kw.pop("gainref", "Movies/gain.mrc"),
            "star": kw.pop("star", f"{movie}.star"),
            "params": kw,
        })

    for m in movies:
        # H3/REF -- five identical j=1 runs. Repeat 0 is the per-movie oracle.
        for r in range(L3_REPEATS):
            add(m, "H3_repeat" if r else "REF", f"j1_rep{r}", threads=1, repeat=r)
        # H1 -- thread count.
        for j in L3_THREAD_COUNTS:
            if j == 1:
                continue
            add(m, "H1_threads", f"j{j}", threads=j)
        # H3 at j=4 as well: reduction order is where multi-thread variation lives.
        for r in range(1, L3_REPEATS):
            add(m, "H3_repeat", f"j4_rep{r}", threads=4, repeat=r)
        # H2 -- thread placement.
        for bind in L3_PROC_BIND:
            if bind == "unset":
                continue
            add(m, "H2_proc_bind", f"j4_bind_{bind}", threads=4, proc_bind=bind)
        # X6 -- dose-weighting fault, selection severities.
        for rho in split_grid("X6_dose_scale")["selection"]:
            add(m, "X6_dose_scale", f"dose_{rho:g}", threads=1,
                dose_per_frame=DOSE_PER_FRAME * rho, severity=rho)

    # X8 -- gain normalisation fault. Pilot scale: the fault is in the gain
    # reference, which is shared, so a subset of movies is enough to show the
    # response and its movie-to-movie spread.
    for m in movies[:3]:
        for name, path in gain_variants.items():
            sev = SEVERITY_GRIDS["X8_gain_error"]
            add(m, "X8_gain_error", f"gain_{name}", threads=1,
                gainref=path, severity=name)

    return runs


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

KEEP_SUFFIXES = (".mrc", ".star", ".log")


def run_one(run: Dict[str, Any], cfg: Dict[str, str]) -> Dict[str, Any]:
    out_dir = Path(cfg["results"]) / run["run_id"]
    if (out_dir / "DONE").exists():
        return {"run_id": run["run_id"], "status": "cached"}
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    work = Path(cfg["tutorial"])
    cmd = [
        cfg["binary"],
        "--i", str(Path(cfg["stars"]) / run["star"]),
        "--o", str(out_dir / "out"),
        *BASE_OPTS,
        "--j", str(run["threads"]),
        "--dose_per_frame", f"{run['dose_per_frame']:.9g}",
        "--gainref", run["gainref"],
    ]
    env = dict(os.environ)
    env.pop("OMP_NUM_THREADS", None)
    if run["proc_bind"] != "unset":
        env["OMP_PROC_BIND"] = run["proc_bind"]
    else:
        env.pop("OMP_PROC_BIND", None)

    t0 = time.time()
    with open(out_dir / "stdout.log", "wb") as so, open(out_dir / "time.log", "wb") as se:
        rc = subprocess.call(["/usr/bin/time", "-v", *cmd], cwd=work, env=env, stdout=so, stderr=se)
    elapsed = time.time() - t0

    # Keep only what the diagnostics read; a full matrix of EPS/PDF artefacts
    # would be tens of GB of plots nobody looks at.
    for p in (out_dir / "out").rglob("*"):
        if p.is_file() and p.suffix not in KEEP_SUFFIXES:
            p.unlink()

    rec = {"run_id": run["run_id"], "returncode": rc, "elapsed_s": elapsed,
           "cmd": " ".join(cmd), "proc_bind": run["proc_bind"]}
    (out_dir / "run.json").write_text(json.dumps({**run, **rec}, indent=2))
    if rc == 0:
        (out_dir / "DONE").write_text("ok\n")
    return rec


def execute(manifest: List[Dict[str, Any]], cfg: Dict[str, str], workers: int) -> None:
    done = 0
    total = len(manifest)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rec in ex.map(lambda r: run_one(r, cfg), manifest):
            done += 1
            print(f"[{done}/{total}] {rec['run_id']} rc={rec.get('returncode', '-')} "
                  f"{rec.get('elapsed_s', 0):.1f}s", flush=True)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def find_outputs(run_dir: Path) -> Dict[str, Path]:
    mov = run_dir / "out" / "Movies"
    mrc = sorted(mov.glob("*.mrc"))
    star = sorted(p for p in mov.glob("*.star"))
    return {"mrc": mrc[0] if mrc else None, "star": star[0] if star else None}


def collect(manifest: List[Dict[str, Any]], cfg: Dict[str, str], out_json: Path) -> None:
    import numpy as np  # noqa: F401  (imported lazily; heavy on the remote host)

    from tools.calibration import diagnostics as dg
    from tools.calibration import mrcio

    results = Path(cfg["results"])
    by_movie: Dict[str, List[Dict[str, Any]]] = {}
    for r in manifest:
        by_movie.setdefault(r["movie"], []).append(r)

    records: List[Dict[str, Any]] = []
    for movie, runs in sorted(by_movie.items()):
        ref_dir = results / f"{movie}__j1_rep0"
        ref = find_outputs(ref_dir)
        if not ref["mrc"]:
            print(f"  !! no reference output for {movie}, skipping", flush=True)
            continue
        ref_img, _ = mrcio.read_mrc_2d(ref["mrc"])
        ref_shifts = mrcio.global_shifts(mrcio.parse_star(ref["star"]))

        for run in sorted(runs, key=lambda r: r["run_id"]):
            d = results / run["run_id"]
            got = find_outputs(d)
            rec: Dict[str, Any] = {k: run[k] for k in
                                   ("run_id", "movie", "group", "label", "threads",
                                    "proc_bind", "dose_per_frame", "gainref")}
            rec["params"] = run["params"]
            meta = json.loads((d / "run.json").read_text()) if (d / "run.json").exists() else {}
            rec["returncode"] = meta.get("returncode")
            rec["elapsed_s"] = meta.get("elapsed_s")
            if not got["mrc"] or not got["star"]:
                rec["error"] = "missing output"
                records.append(rec)
                continue
            img, _ = mrcio.read_mrc_2d(got["mrc"])
            if img.shape != ref_img.shape:
                rec["error"] = f"shape {img.shape} vs {ref_img.shape}"
                records.append(rec)
                continue
            rec.update(dg.all_image_diagnostics(ref_img, img))
            try:
                rec.update(dg.existing_trajectory_metrics(
                    ref_shifts, mrcio.global_shifts(mrcio.parse_star(got["star"]))))
            except Exception as exc:  # trajectory shape mismatch is itself a result
                rec["traj_error"] = str(exc)
            try:
                rec.update(dg.field_metrics(ref["star"], got["star"], grid=9))
            except Exception as exc:
                rec["field_error_msg"] = str(exc)
            records.append(rec)
            print(f"  {run['run_id']}: relRMSE={rec.get('image_relative_rmse', float('nan')):.3e} "
                  f"dB={rec.get('std_delta_b_a2', float('nan')):+.3f} "
                  f"eps={rec.get('std_eps_incoherent', float('nan')):.3e}", flush=True)

    out_json.write_text(json.dumps({"records": records}, indent=2))
    print(f"wrote {out_json} with {len(records)} records")


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-manifest", type=Path)
    ap.add_argument("--execute", type=Path, help="manifest JSON to run")
    ap.add_argument("--collect", type=Path, help="manifest JSON to score")
    ap.add_argument("--out", type=Path, default=Path("layer3_results.json"))
    ap.add_argument("--movies", default="selection", choices=["selection", "holdout", "both"])
    ap.add_argument("--binary")
    ap.add_argument("--tutorial")
    ap.add_argument("--stars")
    ap.add_argument("--results")
    ap.add_argument("--gain-variants", default="{}",
                    help="JSON mapping of variant name to gain MRC path")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    movies = {
        "selection": list(SELECTION_MOVIES),
        "holdout": list(HOLDOUT_MOVIES),
        "both": list(SELECTION_MOVIES) + list(HOLDOUT_MOVIES),
    }[args.movies]

    if args.emit_manifest:
        man = build_manifest(movies, json.loads(args.gain_variants))
        args.emit_manifest.write_text(json.dumps(man, indent=2))
        groups: Dict[str, int] = {}
        for r in man:
            groups[r["group"]] = groups.get(r["group"], 0) + 1
        print(f"wrote {args.emit_manifest}: {len(man)} runs")
        for g, n in sorted(groups.items()):
            print(f"  {g:20s} {n:4d}")
        return 0

    cfg = {"binary": args.binary, "tutorial": args.tutorial,
           "stars": args.stars, "results": args.results}

    if args.execute:
        execute(json.loads(args.execute.read_text()), cfg, args.workers)
        return 0
    if args.collect:
        collect(json.loads(args.collect.read_text()), cfg, args.out)
        return 0
    ap.error("one of --emit-manifest, --execute or --collect is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
