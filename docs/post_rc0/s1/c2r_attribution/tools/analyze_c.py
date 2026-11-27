#!/usr/bin/env python3
"""S1.3c attribution table: CPU (sweep, frozen F) vs CUDA diag4 arms off/glob/globdw.

  analyze_c.py <runs_dir> <sweep_runs_dir> <out.json> <label-prefix> <movie> [<movie> ...]

Per movie and grid: relative RMSE (compare_motioncorr --gate backend, recorded
only), accepted patch sets from the per-movie STAR (data_local_shift centres),
the S1 screen (relative RMSE >= 0.1, as #243), whether the off arm's products
are byte-identical to the sweep's CUDA product (neutrality / replay check), and
whether glob/globdw products differ from off at all.
"""
import glob, json, re, subprocess, sys
from pathlib import Path

PY = sys.executable
CMP = "/mnt/clathrin/alex-motioncorr-s1ccf/src-prod/tools/compare_motioncorr.py"
IDT = str(Path(__file__).parent / "identity.py")


def star_sets(run):
    st = glob.glob(str(Path(run) / "Movies" / "*.star"))
    t = open(st[0]).read()
    m = re.search(r"data_local_shift\s*\n(.*?)(?=\n# version|\ndata_|\Z)", t, re.S)
    if not m:
        return set()
    pts = set()
    for line in m.group(1).splitlines():
        p = line.split()
        if len(p) == 5 and not line.strip().startswith("_"):
            pts.add((int(float(p[1])), int(float(p[2]))))
    return pts


def relrmse(ref, test, out):
    r = subprocess.run([PY, CMP, "--ref", ref, "--test", test, "--gate", "backend", "--json-out", out],
                       capture_output=True, text=True)
    m = re.search(r"Relative RMSE:\s+(\S+)", r.stdout)
    return float(m.group(1)) if m else None


def identical(a, b):
    r = subprocess.run([PY, IDT, a, b], capture_output=True, text=True)
    try:
        return json.loads(r.stdout.splitlines()[-1])["identical"]
    except Exception:
        return None


def main(runs, sweep, out, prefix, *movies):
    res = []
    for mv in movies:
        for g in (5, 3):
            ref = f"{sweep}/{mv}-p{g}-F-cpu"
            swc = f"{sweep}/{mv}-p{g}-F-cuda"
            if not Path(ref).exists():
                continue
            row = {"movie": mv, "grid": g, "cpu_patches": len(star_sets(ref))}
            cset = star_sets(ref)
            for arm in ("off", "glob", "globdw"):
                d = f"{runs}/{prefix}-{mv}-p{g}-{arm}"
                if not Path(d, "run.json").exists():
                    continue
                rj = json.load(open(f"{d}/run.json"))
                gset = star_sets(d)
                rr = relrmse(ref, d, f"{d}/backend.json")
                row[arm] = {"rc": rj["rc"], "witness": rj.get("gpu_witness_uuids"), "rel_rmse": rr,
                            "s1": rr is not None and rr >= 0.1, "cuda_patches": len(gset),
                            "cpu_only": sorted(cset - gset), "cuda_only": sorted(gset - cset)}
            if "off" in row:
                row["off_identical_to_sweep_cuda"] = identical(swc, f"{runs}/{prefix}-{mv}-p{g}-off")
                for arm in ("glob", "globdw"):
                    if arm in row:
                        row[arm]["identical_to_off"] = identical(f"{runs}/{prefix}-{mv}-p{g}-off", f"{runs}/{prefix}-{mv}-p{g}-{arm}")
            res.append(row)
            f = lambda a: ("%.4f" % row[a]["rel_rmse"]) if a in row and row[a]["rel_rmse"] is not None else "-"
            print(mv, "p%d" % g, "off", f("off"), "glob", f("glob"), "globdw", f("globdw"),
                  "| patches cpu", row["cpu_patches"], "cuda", [row[a]["cuda_patches"] for a in ("off", "glob", "globdw") if a in row],
                  "| off==sweep", row.get("off_identical_to_sweep_cuda"), flush=True)
    json.dump(res, open(out, "w"), indent=1, default=list)


if __name__ == "__main__":
    main(*sys.argv[1:])
