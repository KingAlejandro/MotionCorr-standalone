#!/usr/bin/env python3
"""Compact scientific outcome tables from the retained row.json / pairs_report.json of the Stage C run (no producer is run)."""
import json, glob, os, collections, sys
R = sys.argv[1] if len(sys.argv) > 1 else "runs"
rows = []
for d in sorted(glob.glob(f"{R}/runs/J*")):
    row = json.load(open(d + "/row.json")); rec = json.load(open(d + "/receipt.json")); job = rec["ledger_row"]
    def m(x):
        return None if not x else {k: x.get(k) for k in ("rms", "p95", "max")}
    if job["tier"] == "K":
        ra = (row.get("tap") or {}).get("field_angstrom"); rs = (row.get("star") or {}).get("field_angstrom")
        va = (row.get("tap") or {}).get("accuracy_status"); vs = (row.get("star") or {}).get("accuracy_status")
    else:
        ra, rs = m(row.get("runtime")), m(row.get("STAR")); va = (row.get("runtime") or {}).get("verdict"); vs = (row.get("STAR") or {}).get("verdict")
    rows.append(dict(job_id=job["job_id"], tier=job["tier"], case=job["case"], backend=job["backend"], binary=job["binary"], arm=job["arm"],
                     weight=job["weight"], row_status=row["row_status"], runtime_verdict=va, star_verdict=vs, runtime_A=ra, star_A=rs,
                     convergence=(row.get("convergence") or {}).get("status"), local_enabled=row.get("local_enabled"),
                     stage_coverage=row.get("stage_coverage"), exit=rec["rc"]))
json.dump(rows, open("outcomes_rows.json", "w"), indent=1)
c = collections.Counter((r["tier"], r["backend"], r["binary"], r["star_verdict"]) for r in rows)
print("rows", len(rows))
for k, v in sorted(c.items(), key=lambda kv: str(kv[0])): print(" ", k, v)
pairs = json.load(open(f"{R}/pairs_report.json"))
ev = [p for p in pairs if p["status"] == "EVALUATED"]
print("pairs evaluated", len(ev), "of", len(pairs), collections.Counter(p["comparison"] for p in ev))
reg = [(p["comparison"], p["case"], p["weight"], rep) for p in ev for rep in ("runtime", "STAR") if p.get(rep, {}).get("regression_pass_to_fail")]
inc = [(p["comparison"], p["case"], rep) for p in ev for rep in ("runtime", "STAR") if p.get(rep, {}).get("numeric_increase")]
print("pass->fail regressions:", reg)
print("pairs with any numeric increase (b worse than a in rms/p95/max):", len(inc), "of", 2 * len(ev), "representations")
