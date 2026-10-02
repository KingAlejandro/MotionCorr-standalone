#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mkcharts import stacked_stages, BLUE, RED, PURPLE, GREEN, AMBER
DATA, OUT = sys.argv[1], sys.argv[2]
hs = json.load(open(os.path.join(DATA, "host_stages.json")))

# The retained campaign-8 payload has no source/binary pin. Do not borrow the
# different production campaign's hashes or label this as current PR137 evidence.
# Preserve original host_stages.json and host-stages.{svg,png}; write a corrected
# scoped chart alongside them. New strict-parser JSON uses null for absent timers.
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
# This renderer is specific to the retained seven-variant, three-repetition
# campaign. Do not silently render a prefix or claim three reps for other data.
if set(hs) != {k for k, _ in ORDER}:
    raise ValueError("host chart requires the complete historical variant inventory")
for variant in hs.values():
    if set(variant) != {"base", "cand"} or any(r.get("reps") != 3 for r in variant.values()):
        raise ValueError("host chart requires both arms and three declared repetitions")
pairs = []
for k, lbl in ORDER:
    arms = []
    for arm, who in (("base", "historical base"), ("cand", "historical candidate")):
        r = hs.get(k, {}).get(arm)
        if not r:
            continue
        widened = k.startswith("u8_deflate") or k == "u16_deflate_rps8"
        if arm == "cand" and widened:
            who = "historical stacked #138"
        tag = f"{who} — {r['route']}"
        if arm == "base" and r["route"] == "nvcomp":
            tag += " (untagged)"
        unavailable = any(r.get(K[s]) is None for s in S) or (arm == "base" and r["route"] == "nvcomp")
        values = {s: r[K[s]] for s in S if r.get(K[s]) is not None}
        values["__total_unavailable__"] = unavailable
        arms.append((tag, values))
    if arms:
        pairs.append((lbl, arms))

stacked_stages(
    os.path.join(OUT, "host-stages-scoped.svg"), pairs, S, COL,
    "Historical input-route elapsed stages (TIMING=ON)",
    ["4GPUs A100-80GB PCIe, CUDA 12.8, nvCOMP 5.3.0.16, Release | taskset 96-103, --j 8, one flock acquisition",
     "Historical stacked #137 + #138 experiment; not current #137 acceptance or current-source performance",
     "retained summary reports separate TIMING=ON builds and per-stage medians of 3 repetitions; whole-run totals",
     "these walls are NOT comparable with the production figures elsewhere -- an instrumented build is a different binary"],
    ["\"host decode\" is the LibTIFF decode, and on the float route the float materialisation with it. \"device ingest\" is the whole GPU",
     "ingest including its own file reads, which is why the nvCOMP arms show no host decode and no separate gain stage.",
     "Baseline nvCOMP ingestion was untagged: unavailable is not zero, and the baseline total is not compared.",
     "TIMING-arm source commits and binary SHA256 pins: UNRECORDED in this retained payload; production-run hashes are not substituted.",
     "Original data/plots are preserved; their raw-run success and completeness have not been revalidated here.",
     "New parser output requires successful complete runs; absent optional timers are explicit null, not zero.",
     "Every segment is a host elapsed stage timer, not CPU utilization or pure GPU duration. Totals sum per-stage medians."],
    unit="s", label_w=430, rowh=30)
print("host chart written")
