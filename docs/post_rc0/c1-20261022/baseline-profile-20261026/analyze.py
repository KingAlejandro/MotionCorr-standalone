import json,sys,os,hashlib,re,subprocess,glob
sys.path.insert(0,"/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools/profiling")
from lib import identity
SC="/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026"
runs={}
for d,tags in (("kit-run1",["A1","A2"]),("kit-run2",["A3","A4"])):
    rr=[json.loads(l) for l in open(f"{SC}/{d}/runs.jsonl")]
    rr=[r for r in rr if r["kind"]=="round"]
    for t,r in zip(tags,rr): runs[t]=r
W=[json.loads(l) for l in open(f"{SC}/kit-run1/runs.jsonl")][0]
out={}
out["warmup"]={"wall_s":W["wall_s"]}
for t,r in runs.items():
    out[t]={"wall_s":r["wall_s"],"cpu_s":r["cpu_s"],"user_s":r["user_s"],"sys_s":r["sys_s"],"peak_rss_bytes":r["peak_rss_bytes"],"minflt":r["minflt"],"flags":r["flags"],"affinity":r["payload_affinity"],"exe_verified":r["payload_exe_verified"],"peak_vram_delta_bytes":r["vram"]["peak_device_delta_bytes"],"foreign_gpu_pids":r["vram"]["foreign_pids"],"lane_foreign_cores":r["lane"]["foreign_cores"],"out_dir":r["out_dir"],"load1_before":r["load1_before"]}
w=[out[t]["wall_s"] for t in ("A1","A2","A3","A4")]
out["wall_summary"]={"samples":w,"min":min(w),"max":max(w),"range_pct_of_min":100*(max(w)-min(w))/min(w),"AA12_pct":100*abs(w[1]-w[0])/((w[0]+w[1])/2),"AA34_pct":100*abs(w[3]-w[2])/((w[2]+w[3])/2),"mean":sum(w)/4}
# identity A1 vs others, and P1 vs A1
ident={}
base=out["A1"]["out_dir"]
for t in ("A2","A3","A4"): ident["A1_vs_"+t]=identity.compare_trees(base,out[t]["out_dir"])
ident["A1_vs_P1"]=identity.compare_trees(base,SC+"/p1/out")
out["identity"]={k:{kk:vv for kk,vv in v.items() if kk!="files"} for k,v in ident.items()}
# inventory and whole-file hashes
def sha(p):
    h=hashlib.sha256(); h.update(open(p,"rb").read()); return h.hexdigest()
inv={}
for t,d in (("A1",out["A1"]["out_dir"]),("A2",out["A2"]["out_dir"]),("A3",out["A3"]["out_dir"]),("A4",out["A4"]["out_dir"]),("P1",SC+"/p1/out")):
    files={}
    for root,_,fs in os.walk(d):
        for f in fs:
            p=os.path.join(root,f); files[os.path.relpath(p,d)]=(os.path.getsize(p),sha(p))
    inv[t]=files
out["inventory_A1"]={k:v[0] for k,v in inv["A1"].items()}
names=sorted(inv["A1"])
out["whole_file_hash_equal"]={n:{t:(inv[t].get(n,(0,None))[1]==inv["A1"][n][1]) for t in ("A2","A3","A4","P1")} for n in names}
# MRC payload hashes (header label excluded: 1024-byte header; compare header[:224] + payload)
def mrcsig(p):
    raw=open(p,"rb").read(); return hashlib.sha256(raw[:224]+raw[1024:]).hexdigest()
out["mrc_payload_equal"]={n:{t:(mrcsig(os.path.join(d,n))==mrcsig(os.path.join(out["A1"]["out_dir"],n))) for t,d in (("A2",out["A2"]["out_dir"]),("A3",out["A3"]["out_dir"]),("A4",out["A4"]["out_dir"]),("P1",SC+"/p1/out"))} for n in names if n.endswith(".mrc")}
# pdf pages
pdf=os.path.join(out["A1"]["out_dir"],"logfile.pdf")
try:
    r=subprocess.run(["gs","-q","-dNODISPLAY","-dNOSAFER","-c","(%s) (r) file runpdfbegin pdfpagecount = quit"%pdf],capture_output=True,text=True); out["logfile_pdf_pages"]=r.stdout.strip()
except Exception as e: out["logfile_pdf_pages"]=str(e)
out["witness"]=open(SC+"/ingest-witness.txt").read().splitlines()
json.dump(out,open(SC+"/baseline-results.json","w"),indent=1,default=str)
print(json.dumps(out["wall_summary"])); print(json.dumps(out["identity"],default=str)[:800]); print(len(names),"files in A1:",names)
print("whole-file hash differences:",{n:[t for t,v in d.items() if not v] for n,d in out["whole_file_hash_equal"].items() if not all(d.values())})
print("mrc payload all equal:",all(all(d.values()) for d in out["mrc_payload_equal"].values()))
print("pdf pages",out["logfile_pdf_pages"],"witness",out["witness"])
