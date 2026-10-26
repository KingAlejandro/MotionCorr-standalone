#!/usr/bin/env python3
"""Deterministic job ledger and comparison pairs for CONTROL_PLAN.md. No jobs are run here.

    python3 -I make_ledger.py --outdir <dir>   ->  ledger.csv, pairs.csv, counts.json
"""
import argparse, csv, json
from pathlib import Path

K267 = ["zero", "integer", "fractional", "affine", "pedestal", "noisy", "flat", "repeated"]
NCELLS = [f"vel{v}-N{n}" for v in (0, 1) for n in (5, 9, 13, 20)]
MOVIES = [f"{m}-{c}" for m in ("00021", "00046") for c in ("G", "L")]  # G/L as defined in PR288 RESULT
BACKENDS = ("cpu", "cuda")
LOCAL_CASES = ("affine", "pedestal", "noisy")   # original K267 CLI: 3x3 patches; the other five ID use 1x1 (global only)
PAIRS = (("C-BASE", "cpu-none", "cuda-none"), ("C-GOAL", "cpu-none", "cuda-both"),
         ("C-COMMON", "cpu-both", "cuda-both"), ("C-CPU", "cpu-none", "cpu-both"))


def rows():
    out = []
    for case in K267:                      # tier K: tiny truth controls, binaries def and exp
        for be in BACKENDS:
            for binary, arm in (("def", "unset"), ("exp", "unset"), ("exp", "none"), ("exp", "global"),
                                ("exp", "local"), ("exp", "both")):
                role = "identity" if arm == "unset" or binary == "def" else ("identity+arm" if arm == "none" else "arm")
                out.append(dict(tier="K", case=case, config="3x3 (original CLI)" if case in LOCAL_CASES else "1x1 global-only (original CLI)",
                                backend=be, binary=binary, arm=arm,
                                weight="production", stop="production", role=role, status="HELD"))
    for weight, binary in (("production", "exp"), ("isotropic", "iso")):   # tier N: W5 phase-ramp controls
        for cell in NCELLS:
            for be in BACKENDS:
                for arm in ("none", "both"):
                    out.append(dict(tier="N", case=cell, config="global-only", backend=be, binary=binary, arm=arm,
                                    weight=weight, stop="production", role="arm", status="HELD"))
    for mv in MOVIES:                      # tier M: native movies, held behind sections 1 and 3 plus parent pins
        for be in BACKENDS:
            for arm in ("none", "both"):
                out.append(dict(tier="M", case=mv, config="as-PR288", backend=be, binary="exp", arm=arm,
                                weight="production", stop="production", role="arm", status="HELD"))
    for r in out:
        # Gates each row feeds. B3: def/exp identity triple per (ID, backend). B4: stage counts on a real CUDA run.
        g = []
        if r["tier"] == "K" and (r["binary"] == "def" or r["arm"] in ("unset", "none")):
            g.append("B3")
        k_exp = r["tier"] == "K" and r["binary"] == "exp" and r["arm"] != "unset"
        if k_exp and r["case"] in LOCAL_CASES and r["backend"] == "cuda":
            g.append("B4")   # positive: the local stage is requested, so cuda_batched must be reached
        if k_exp and r["case"] not in LOCAL_CASES and r["arm"] in ("local", "both"):
            g.append("SEL")  # no local stage requested: a selected local arm must be a no-op, local coverage NOT_APPLICABLE
            r["role"] = "selectivity" if r["arm"] == "local" else "arm+selectivity"
        r["gates"] = "+".join(g)
        r["cli"] = {"K": "tools/ccf_dc_native_rows.py:k267_argv", "N": "tools/ccf_dc_native_rows.py:n_argv",
                    "M": "PENDING parent pin (PR288 command)"}[r["tier"]]
    for i, r in enumerate(out):
        r["job_id"] = "J%03d-%s-%s-%s-%s-%s-%s" % (i + 1, r["tier"], r["case"], r["backend"], r["binary"], r["arm"], r["weight"][:4])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", type=Path, required=True)
    o = ap.parse_args(); o.outdir.mkdir(parents=True, exist_ok=True)
    R = rows()
    key = {(r["tier"], r["case"], r["weight"], r["backend"], r["binary"], r["arm"]): r["job_id"] for r in R}
    cols = ["job_id", "tier", "case", "config", "backend", "binary", "arm", "weight", "stop", "role", "gates", "cli", "status"]
    with open(o.outdir / "ledger.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(R)
    P = []
    for r in R:                            # one pair set per (tier, case, weight), anchored at its cpu-none job
        if r["backend"] != "cpu" or r["arm"] != "none" or r["binary"] != "exp" and r["tier"] != "N":
            continue
        if r["tier"] == "K" and r["binary"] != "exp":
            continue
        b = "iso" if r["weight"] == "isotropic" else "exp"
        for cid, a, c in PAIRS:
            ja = key[(r["tier"], r["case"], r["weight"], a.split("-")[0], b, a.split("-")[1])]
            jc = key[(r["tier"], r["case"], r["weight"], c.split("-")[0], b, c.split("-")[1])]
            P.append(dict(comparison=cid, tier=r["tier"], case=r["case"], weight=r["weight"], job_a=ja, job_b=jc))
    with open(o.outdir / "pairs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["comparison", "tier", "case", "weight", "job_a", "job_b"]); w.writeheader(); w.writerows(P)
    # C-REPRO: every cpu none N-control job must reproduce its retained cpu arm-a row (evidence/retained_cpu_reference.json).
    retained = json.loads((Path(__file__).with_name("evidence") / "retained_cpu_reference.json").read_text())["rows"]
    short = {"production": "prod", "isotropic": "iso"}
    ref = {(x["movie"], x["weight"]) for x in retained}
    rp = [dict(job_id=r["job_id"], movie=r["case"].replace("-", "_"), weight=r["weight"]) for r in R
          if r["tier"] == "N" and r["backend"] == "cpu" and r["arm"] == "none"]
    assert {(x["movie"], short[x["weight"]]) for x in rp} == ref, "C-REPRO rows must match the retained reference rows"
    with open(o.outdir / "repro.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["job_id", "movie", "weight"]); w.writeheader(); w.writerows(rp)
    counts = {t: sum(r["tier"] == t for r in R) for t in "KNM"}
    counts.update(total=len(R), pairs=len(P), repro=len(rp), B3_rows=sum("B3" in r["gates"] for r in R),
                  B4_rows=sum("B4" in r["gates"] for r in R),
                  N_production=sum(r["tier"] == "N" and r["weight"] == "production" for r in R),
                  N_isotropic=sum(r["tier"] == "N" and r["weight"] == "isotropic" for r in R))
    (o.outdir / "counts.json").write_text(json.dumps(counts, indent=1) + "\n")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
