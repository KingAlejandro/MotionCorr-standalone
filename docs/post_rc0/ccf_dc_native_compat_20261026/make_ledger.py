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
PAIRS = (("C-BASE", "cpu-none", "cuda-none"), ("C-GOAL", "cpu-none", "cuda-both"),
         ("C-COMMON", "cpu-both", "cuda-both"), ("C-CPU", "cpu-none", "cpu-both"))


def rows():
    out = []
    for case in K267:                      # tier K: tiny truth controls, binaries def and exp
        for be in BACKENDS:
            for binary, arm in (("def", "unset"), ("exp", "unset"), ("exp", "none"), ("exp", "global"),
                                ("exp", "local"), ("exp", "both")):
                role = "identity" if arm == "unset" or binary == "def" else ("identity+arm" if arm == "none" else "arm")
                out.append(dict(tier="K", case=case, config="5x5-as-fixture", backend=be, binary=binary, arm=arm,
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
    for i, r in enumerate(out):
        r["job_id"] = "J%03d-%s-%s-%s-%s-%s-%s" % (i + 1, r["tier"], r["case"], r["backend"], r["binary"], r["arm"], r["weight"][:4])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", type=Path, required=True)
    o = ap.parse_args(); o.outdir.mkdir(parents=True, exist_ok=True)
    R = rows()
    key = {(r["tier"], r["case"], r["weight"], r["backend"], r["binary"], r["arm"]): r["job_id"] for r in R}
    cols = ["job_id", "tier", "case", "config", "backend", "binary", "arm", "weight", "stop", "role", "status"]
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
    counts = {t: sum(r["tier"] == t for r in R) for t in "KNM"}
    counts.update(total=len(R), pairs=len(P),
                  N_production=sum(r["tier"] == "N" and r["weight"] == "production" for r in R),
                  N_isotropic=sum(r["tier"] == "N" and r["weight"] == "isotropic" for r in R))
    (o.outdir / "counts.json").write_text(json.dumps(counts, indent=1) + "\n")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
