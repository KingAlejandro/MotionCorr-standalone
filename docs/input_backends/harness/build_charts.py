#!/usr/bin/env python3
"""Render the input-backends charts from the committed campaign data."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mkcharts import (stacked_stages, dot_rows, grouped_bars,
                      BLUE, RED, PURPLE, GREEN, AMBER)

DATA = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

PROV = [
    "4GPUs A100-80GB PCIe, CUDA 12.8, nvCOMP 5.3.0.16, Release | taskset 96-103, --j 8, one flock acquisition",
    "main c499b1d vs experiment/input-nvcomp-widen | both arms built from scratch in the same acquisition",
    "shared box: two other MotionCorr sessions active throughout; load1 recorded per run",
]

st = json.load(open(os.path.join(DATA, "ingest_stages.json")))

# ---------------------------------------------------------------- chart 1
STAGES = ["deflate decode (GPU)", "Adler-32 verify (GPU)", "convert + gain + sum (GPU)", "host-to-device copy"]
COLORS = {STAGES[0]: PURPLE, STAGES[1]: AMBER, STAGES[2]: GREEN, STAGES[3]: RED}
KEYMAP = dict(zip(STAGES, ["deflate decode", "adler-32 verify", "convert + gain + sum", "H2D copy"]))
ORDER = [
    ("u8_lzw_rps1", "uint8 LZW, 24 frames"),
    ("u8_lzw_rps1_48f", "uint8 LZW, 48 frames"),
    ("u8_deflate_rps1", "uint8 Deflate, 24 frames"),
    ("u8_deflate_rps1_48f", "uint8 Deflate, 48 frames"),
    ("u16_deflate_rps8", "uint16 Deflate, 8 rows/strip"),
    ("u16_lzw_rps1", "uint16 LZW (null)"),
    ("u16_deflate_rps1", "uint16 Deflate, 1 row/strip (null)"),
]
ROUTE = {("u8_lzw_rps1", "base"): "float", ("u8_lzw_rps1", "cand"): "compact",
         ("u8_lzw_rps1_48f", "base"): "float", ("u8_lzw_rps1_48f", "cand"): "compact",
         ("u8_deflate_rps1", "base"): "float", ("u8_deflate_rps1", "cand"): "nvcomp",
         ("u8_deflate_rps1_48f", "base"): "float", ("u8_deflate_rps1_48f", "cand"): "nvcomp",
         ("u16_deflate_rps8", "base"): "compact", ("u16_deflate_rps8", "cand"): "nvcomp",
         ("u16_lzw_rps1", "base"): "compact", ("u16_lzw_rps1", "cand"): "compact",
         ("u16_deflate_rps1", "base"): "nvcomp", ("u16_deflate_rps1", "cand"): "nvcomp"}
H2DB = json.load(open(os.path.join(DATA, "h2d_bytes.json")))
pairs = []
for key, label in ORDER:
    arms = []
    for arm, who in (("base", "main"), ("cand", "branch")):
        r = st.get(key, {}).get(arm)
        if not r:
            continue
        mb = H2DB.get(key, {}).get(arm)
        tag = f"{who} — {ROUTE[(key,arm)]}" + (f", {mb:,.0f} MB copied" if mb else "")
        arms.append((tag, {s: r[KEYMAP[s]] for s in STAGES}))
    if arms:
        pairs.append((label, arms))
stacked_stages(
    os.path.join(OUT, "ingest-stages.svg"), pairs, STAGES, COLORS,
    "Where the input path spends device time, per movie",
    PROV + ["one Nsight capture per arm per variant, movie 20170629_00021; device intervals only"],
    ["Device-side ingest only. The alignment, FFT and dose work that follows is excluded; it is 104 ms (24 frames) / 230 ms (48) in every arm,",
     "which is the internal control that these columns are the only thing that changed.",
     "The two null variants copy byte-identical payloads on both arms, so their copy segments differ only in achieved PCIe bandwidth, not in work.",
     "Single time domain: every segment is a GPU interval from one trace. No process wall is drawn on this chart."],
    unit="ms", label_w=430, rowh=30)

# ---------------------------------------------------------------- chart 2
H2D = json.load(open(os.path.join(DATA, "h2d_bytes.json")))
groups = [(lbl, {"main": H2D[k]["base"], "branch": H2D[k]["cand"]}) for k, lbl in ORDER if k in H2D]
grouped_bars(
    os.path.join(OUT, "h2d-bytes.svg"), groups, ["main", "branch"], {"main": RED, "branch": BLUE},
    "Host-to-device bytes per movie",
    PROV + ["Nsight cuda_gpu_mem_size_sum, one capture per arm per variant"],
    ["Byte counts are contention-immune: the same payload reports the same number whatever else the box is doing.",
     "The three unchanged-route variants are byte-identical across arms, which is what makes the others attributable."],
    unit="MB")

# ---------------------------------------------------------------- chart 3
PM = json.load(open(os.path.join(DATA, "per_movie.json")))
rows = []
for key, label in ORDER:
    if key not in PM:
        continue
    for arm, who in (("base", "main"), ("cand", "branch")):
        v = PM[key][arm]
        rows.append((f"{label} — {who}", f"{ROUTE[(key,arm)]}  n={len(v)}", v, ""))
dot_rows(os.path.join(OUT, "per-movie-wall.svg"), rows,
         "Per-movie wall, from the runner's own log",
         PROV + ["median of the movies after the first; a six-movie run spends ~0.95 s on process and CUDA-context startup"],
         ["Each dot is one movie. The bar spans min-max, the rule is the median. Rows marked single observation are the two-movie variants,",
          "which contribute one movie after the first and so have no spread.",
          "Two rows carry one slow movie each (1.80 s and 1.87 s) that stretches the min-max bar; the medians are unaffected and both are retained.",
          "Single time domain: all observations are unprofiled production runs."],
         unit="s", label_w=330, rowh=34)

# ---------------------------------------------------------------- chart 4
RSS = json.load(open(os.path.join(DATA, "rss.json")))
groups = [(lbl, {"main": RSS[k]["base"], "branch": RSS[k]["cand"]}) for k, lbl in ORDER if k in RSS]
grouped_bars(
    os.path.join(OUT, "host-rss.svg"), groups, ["main", "branch"], {"main": RED, "branch": BLUE},
    "Host resident set, whole process",
    PROV + ["Maximum resident set size from /usr/bin/time -v; 6 movies for the 24-frame variants, 2 for the 48-frame ones"],
    ["This is what limits concurrent workers per host, and it is per worker.",
     "The two 48-frame uint8 rows are the shape closest to the deposited data that motivated the change."],
    unit="MiB")
print("charts written to", OUT)
