#!/usr/bin/env python3
"""Paired baseline-vs-candidate timing with arm order alternating within each
pair, so the positional bias (advantage to whichever arm runs second, mostly
page-cache warming) is recoverable from the same data as observed = E +/- P."""
import argparse, hashlib, json, statistics, subprocess, time, shutil, os
from pathlib import Path

def load1(): return float(open("/proc/loadavg").read().split()[0])

def run(binary, work, outdir, j, cfg):
    if (work/outdir).exists(): shutil.rmtree(work/outdir)
    cmd = ["/usr/bin/time","-f","RUSAGE %e %U %S %M", str(binary), "--i","movies1.star",
           "--o",outdir,"--use_own","--j",str(j),"--dose_weighting","--dose_per_frame","1.277",
           "--bfactor","150","--gainref","Movies/gain.mrc","--do_at_most","1"] + cfg.split()
    t0=time.perf_counter()
    r=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
    wall=time.perf_counter()-t0
    ru=[l for l in r.stderr.splitlines() if l.startswith("RUSAGE")]
    e,u,s,m = (ru[-1].split()[1:5] if ru else (wall,0,0,0))
    mrc=sorted((work/outdir/"Movies").glob("*.mrc"))
    px=hashlib.sha256(mrc[0].read_bytes()[1024:]).hexdigest() if mrc else None
    stages={}
    for line in r.stdout.splitlines():
        if " sec (" in line and ":" in line:
            tag,rest=line.split(":",1)
            try: stages[tag.strip()]=float(rest.strip().split(" sec")[0])
            except ValueError: pass
    for m2 in mrc: m2.unlink()
    return {"wall_s":round(wall,3),"time_wall":float(e),"user_s":float(u),"sys_s":float(s),
            "maxrss_kb":int(m),"pixels_sha256":px,"stages":stages,"rc":r.returncode}

ap=argparse.ArgumentParser()
ap.add_argument("--base",required=True); ap.add_argument("--cand",required=True)
ap.add_argument("--work",default="/home/ubuntu/mc-issue26/work")
ap.add_argument("--j",type=int,default=1); ap.add_argument("--pairs",type=int,default=8)
ap.add_argument("--cfg",default="--patch_x 1 --patch_y 1")
ap.add_argument("--out",required=True); ap.add_argument("--label",default="")
a=ap.parse_args(); work=Path(a.work)

res={"label":a.label,"j":a.j,"cfg":a.cfg,"pairs":a.pairs,
     "base":a.base,"cand":a.cand,
     "base_sha256":hashlib.sha256(Path(a.base).read_bytes()).hexdigest(),
     "cand_sha256":hashlib.sha256(Path(a.cand).read_bytes()).hexdigest(),
     "started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"data":[]}
digests=set()
for p in range(1,a.pairs+1):
    order = ["base","cand"] if p%2==1 else ["cand","base"]
    rec={"pair":p,"order":order,"load1":load1()}
    for arm in order:
        rec[arm]=run(a.base if arm=="base" else a.cand, work, f"pab_{arm}", a.j, a.cfg)
        digests.add(rec[arm]["pixels_sha256"])
    rec["delta_s"]=round(rec["cand"]["time_wall"]-rec["base"]["time_wall"],3)
    res["data"].append(rec)
    print(f"pair {p} order={order[0]}-first base={rec['base']['time_wall']:.2f} "
          f"cand={rec['cand']['time_wall']:.2f} delta={rec['delta_s']:+.2f}s load1={rec['load1']:.1f}",flush=True)
    Path(a.out).write_text(json.dumps(res,indent=2))

d=[r["delta_s"] for r in res["data"]]
b=[r["base"]["time_wall"] for r in res["data"]]; c=[r["cand"]["time_wall"] for r in res["data"]]
bf=[r["delta_s"] for r in res["data"] if r["order"][0]=="base"]
cf=[r["delta_s"] for r in res["data"] if r["order"][0]=="cand"]
res["summary"]={
 "base_median":round(statistics.median(b),3),"cand_median":round(statistics.median(c),3),
 "base_mean":round(statistics.mean(b),3),"cand_mean":round(statistics.mean(c),3),
 "mean_delta_s":round(statistics.mean(d),3),
 "sd_delta_s":round(statistics.stdev(d),3) if len(d)>1 else None,
 "pct_change":round(100*statistics.mean(d)/statistics.mean(b),2),
 "n_pairs_cand_faster":sum(1 for x in d if x<0),"n_pairs":len(d),
 "delta_base_first_mean":round(statistics.mean(bf),3) if bf else None,
 "delta_cand_first_mean":round(statistics.mean(cf),3) if cf else None,
 "positional_bias_P_s":round((statistics.mean(bf)-statistics.mean(cf))/2,3) if bf and cf else None,
 "distinct_pixel_digests":sorted(x for x in digests if x),
 "bit_exact_across_all_runs":len([x for x in digests if x])==1,
}
res["finished_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
Path(a.out).write_text(json.dumps(res,indent=2))
print(json.dumps(res["summary"],indent=2))
