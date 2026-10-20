#!/usr/bin/env python3
"""S1.3c-null 4GPUs rows: relative RMSE of CUDA diag5 arms off/on/null1/null2 against
the sweep's frozen-F CPU product, accepted patch counts, and two byte-identity checks:
off vs the sweep's CUDA product (neutrality), and on (diag5) vs the S1.3c global+DW arm
(diag4) where it exists.   census_rows.py <out.json> <movie> [...]"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from analyze_c import relrmse, identical, star_sets

RUNS = "/mnt/clathrin/alex-motioncorr-s1ccf/runs"
ARMS = os.environ.get("ARMS", "off,on,null1,null2").split(",")  # e.g. ARMS=pr254 or off,null1,null2,pr254
SW = "/mnt/clathrin/alex-motioncorr-s1/sweep/runs"
out = []
for mv in sys.argv[2:]:
    for g in (5, 3):
        ref = f"{SW}/{mv}-p{g}-F-cpu"
        row = {"movie": mv, "grid": g, "venue": "4GPUs", "cpu_patches": len(star_sets(ref)), "patches": {}}
        for arm in ARMS:
            d = f"{RUNS}/n-{mv}-p{g}-{arm}"
            rj = json.load(open(f"{d}/run.json"))
            assert rj["rc"] == 0, d
            row[arm] = relrmse(ref, d, f"{d}/backend.json")
            row["patches"][arm] = len(star_sets(d))
            row.setdefault("witness", set()).update(rj["gpu_witness_uuids"])
        row["witness"] = sorted(row["witness"])
        if "off" in ARMS:
            row["off_identical_to_sweep_cuda"] = identical(f"{SW}/{mv}-p{g}-F-cuda", f"{RUNS}/n-{mv}-p{g}-off")
        c = f"{RUNS}/c-{mv}-p{g}-globdw"
        if "on" in ARMS:
            row["on_identical_to_s13c_globdw"] = identical(c, f"{RUNS}/n-{mv}-p{g}-on") if Path(c, "run.json").exists() else None
        out.append(row)
        print(mv, g, " ".join("%s %.4f" % (a, row[a]) for a in ARMS),
              "off==sweep", row.get("off_identical_to_sweep_cuda"), "on==S1.3c", row.get("on_identical_to_s13c_globdw"), flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=1)
