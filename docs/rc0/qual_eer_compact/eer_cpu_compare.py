#!/usr/bin/env python3
"""W-EER-Q step 7: CPU-only EER products, candidate (1db86902) vs pre-#196 main (0ac2726a).

Reuses the run directory made by mkcase.py (movies.star, manifest.json). No GPU, no lock;
the CPU lane is taskset 112-119. Usage: eer_cpu_compare.py CASE_NAME
"""
import json, pathlib, re, shutil, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import eer_matrix as m

ROOT = m.ROOT
BINS = {"base0ac2726a": ROOT / "build/cpu-0ac2726a/motioncorr", "cand1db86902": ROOT / "build/cpu-1db86902/motioncorr"}

name = sys.argv[1]
case = json.load(open(ROOT / "cases" / f"{name}.json"))
caseroot = ROOT / "runs" / name; indir = caseroot / "in"
logdir = ROOT / "results" / name; logdir.mkdir(parents=True, exist_ok=True)
res = {"case": name, "desc": case.get("desc"), "options": case["options"], "arms": {}}
opts = [o for o in case["options"]]
# the CPU build has no GPU: drop --gpu <id>
i = opts.index("--gpu"); del opts[i:i + 2]
for arm, b in BINS.items():
    out = caseroot / f"out-{arm}"; out.mkdir(parents=True, exist_ok=True)
    tfile = logdir / f"{arm}.time"
    cmd = ["taskset", "-c", m.CPUS, "env", "CUDA_VISIBLE_DEVICES=", "/usr/bin/time", "-v", "-o", str(tfile), str(b),
           "--i", "movies.star", "--o", str(out) + "/"] + opts
    m.wait_bench_free([])
    t0 = time.time()
    with open(logdir / f"{arm}.stdout", "wb") as so, open(logdir / f"{arm}.stderr", "wb") as se:
        rc = subprocess.run(cmd, cwd=indir, stdout=so, stderr=se).returncode
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", tfile.read_text())
    res["arms"][arm] = {"rc": rc, "wall_s": round(time.time() - t0, 1), "peak_rss_mib": round(int(rss.group(1)) / 1024, 1) if rss else None, "cmd": cmd}
    print(name, arm, res["arms"][arm]["rc"], res["arms"][arm]["wall_s"], res["arms"][arm]["peak_rss_mib"], flush=True)
if all(a["rc"] == 0 for a in res["arms"].values()):
    res["compare_complete_tree"] = m.compare(case, caseroot / "out-base0ac2726a", caseroot / "out-cand1db86902", indir / "manifest.json", indir / "movies.star", logdir / "compare-base-vs-cand.json")
    print(name, "compare", res["compare_complete_tree"]["rc"], res["compare_complete_tree"]["stdout"])
for d in caseroot.glob("out-*"):
    for f in d.rglob("*.mrc"): f.unlink()
    dst = logdir / d.name
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(d, dst, ignore=shutil.ignore_patterns("*.mrc", "*.eps", "*.pdf"))
(logdir / "result.json").write_text(json.dumps(res, indent=1))
