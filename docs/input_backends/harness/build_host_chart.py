#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mkcharts import stacked_stages, BLUE, RED, PURPLE, GREEN, AMBER
DATA, OUT = sys.argv[1], sys.argv[2]
hs = json.load(open(os.path.join(DATA, "host_stages.json")))

S = ["host decode (read movie)", "device ingest (nvCOMP)", "gain + sum + upload"]
COL = {S[0]: RED, S[1]: PURPLE, S[2]: GREEN}
K = {S[0]: "read movie", S[1]: "device ingest (nvCOMP)", S[2]: "apply gain and initial sum"}
ORDER = [
    ("u8_lzw_rps1", "uint8 LZW, 24f x 6 movies"),
    ("u8_lzw_rps1_48f", "uint8 LZW, 48f x 2 movies"),
    ("u8_deflate_rps1", "uint8 Deflate, 24f x 6"),
    ("u8_deflate_rps1_48f", "uint8 Deflate, 48f x 2"),
    ("u16_deflate_rps8", "uint16 Deflate rps8, 24f x 6"),
    ("u16_lzw_rps1", "uint16 LZW (null), 24f x 6"),
    ("u16_deflate_rps1", "uint16 Deflate rps1 (null)"),
]
pairs = []
for k, lbl in ORDER:
    arms = []
    for arm, who in (("base", "main"), ("cand", "branch")):
        r = hs.get(k, {}).get(arm)
        if not r:
            continue
        tag = f"{who} — {r['route']}"
        if arm == "base" and r["route"] == "nvcomp":
            tag += "  (ingest untagged in main)"
        arms.append((tag, {s: r[K[s]] for s in S}))
    if arms:
        pairs.append((lbl, arms))

stacked_stages(
    os.path.join(OUT, "host-stages.svg"), pairs, S, COL,
    "Where the input path spends host time, per run",
    ["4GPUs A100-80GB PCIe, CUDA 12.8, nvCOMP 5.3.0.16, Release | taskset 96-103, --j 8, one flock acquisition",
     "separate TIMING=ON builds of both arms; median of 3 repetitions; whole-run stage totals, not per movie",
     "these walls are NOT comparable with the production figures elsewhere -- an instrumented build is a different binary"],
    ["\"host decode\" is the LibTIFF decode, and on the float route the float materialisation with it. \"device ingest\" is the whole GPU",
     "ingest including its own file reads, which is why the nvCOMP arms show no host decode and no separate gain stage.",
     "main predates the device-ingest timer, so where main itself takes nvCOMP that stage is untagged and reads as zero; that row is marked, not compared.",
     "Single time domain: every segment is a host-side stage timer from the same instrumented run."],
    unit="s", label_w=430, rowh=30)
print("host chart written")
