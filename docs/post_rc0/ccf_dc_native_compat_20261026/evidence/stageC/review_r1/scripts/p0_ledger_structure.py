# Static structure of the pinned ledger/pairs/repro as the driver plans them (no producer).
import sys, csv, collections
W = sys.argv[1]; sys.path.insert(0, W + "/tools")
import ccf_dc_stagec_driver as drv
D = W + "/docs/post_rc0/ccf_dc_native_compat_20261026/"
led = drv.load_ledger(D + "ledger.csv"); plan = drv.make_plan(led)
by = {r["job_id"]: r for r in led}
ph = collections.Counter(p for p, _ in plan)
print("phases", dict(ph), "total", len(plan))
print("phase1", [(j["case"], j["backend"], j["binary"], j["arm"]) for p, j in plan if p == 1])
print("phase2 backends", collections.Counter(j["backend"] for p, j in plan if p == 2))
print("phase3 backends", collections.Counter(j["backend"] for p, j in plan if p == 3))
pairs = [r for r in drv.load_ledger(D + "pairs.csv") if r["tier"] in drv.TIERS]
bad = []
for p in pairs:
    a, b = by[p["job_a"]], by[p["job_b"]]
    if not (a["case"] == b["case"] == p["case"] and a["tier"] == b["tier"] == p["tier"]):
        bad.append(("case/tier", p))
    if a["tier"] in drv.TIERS and (a["job_id"] not in {j["job_id"] for _, j in plan} or b["job_id"] not in {j["job_id"] for _, j in plan}):
        bad.append(("not planned", p))
print("pairs", len(pairs), "case/tier mismatches", len(bad), collections.Counter(p["comparison"] for p in pairs))
rep = drv.load_ledger(D + "repro.csv")
rr = [by[r["job_id"]] for r in rep]
print("repro", len(rep), collections.Counter((j["tier"], j["backend"], j["arm"], j["binary"], j["weight"]) for j in rr))
cpu_none_n = [j for j in led if j["tier"] == "N" and j["backend"] == "cpu" and j["arm"] == "none"]
print("cpu N arm-none rows", len(cpu_none_n), "== repro set:", {j["job_id"] for j in cpu_none_n} == {j["job_id"] for j in rr})
k = collections.Counter((j["case"], j["backend"], j["binary"], j["arm"]) for j in led if j["tier"] == "K")
print("K duplicate (case,backend,binary,arm) keys:", [x for x, n in k.items() if n > 1])
trip = {(j["case"], j["backend"]) for j in led if j["tier"] == "K"}
print("B3 triples complete:", sum(all(k[(c, b, bi, a)] for bi, a in (("def","unset"),("exp","unset"),("exp","none"))) for c, b in trip), "of", len(trip))
print("gates", collections.Counter(j["gates"] for j in led if j["tier"] in drv.TIERS))
print("columns", list(led[0].keys()))
