#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarise probe_formats.py output: movie imagesets per actual on-disk encoding.

Counts imagesets (entry + imageset name), not files, in the 'micrographs -
multiframe' category; gain, reference and defect files and single-frame MRC
files are excluded. Prints a Markdown table and writes JSON.
Usage: summarize_census.py OUT.json PROBE.jsonl [PROBE.jsonl ...]
"""
import collections, json, sys

COMP = {None: "none", 1: "none", 5: "LZW", 8: "Deflate", 32946: "Deflate (32946)", 32773: "PackBits", 7: "JPEG"}
SAMPLE = {(8, 1): "u8", (8, None): "u8", (8, 2): "s8", (16, 1): "u16", (16, None): "u16", (16, 2): "s16",
          (32, 3): "f32", (32, 1): "u32", (16, 3): "f16", (64, 3): "f64"}


def classify(r):
    f = r.get("file", "").lower()
    if any(k in f for k in ("gain", "_ref", "defect", "countref", "norm_")):
        return None
    c = r.get("container") or ""
    if c == "MRC":
        if (r.get("nz") or 0) <= 2:
            return None
        ext = (" + %s ext header" % (r.get("exttyp") or "?").strip()) if r.get("nsymbt") else ""
        return "MRC mode %s%s" % (r["mode"], ext if r.get("exttyp", "").strip() else (" + ext header" if r.get("nsymbt") else ""))
    if c.startswith("compressed:"):
        return "MRC compressed (.%s)" % c.split(":")[1] if ".mrc" in f else "other compressed (.%s: %s)" % (c.split(":")[1], f.rsplit(".", 2)[-2])
    if c in ("TIFF", "BigTIFF"):
        comp = r.get("compression")
        if comp in (65000, 65001, 65002):
            o = r.get("orientation")
            return "EER %s %sx%s%s" % (comp, r.get("width"), r.get("length"), "" if not o or o == 1 else " (orientation tag %s)" % o)
        bits = r.get("bits")
        if isinstance(bits, list):
            return "TIFF %d samples per pixel" % len(bits)
        s = SAMPLE.get((bits, r.get("sampleformat")), "bits %s fmt %s" % (bits, r.get("sampleformat")))
        pred = " + predictor %s" % r["predictor"] if r.get("predictor") not in (None, 1) else ""
        endian = " big-endian" if r.get("byteorder") == "big" else ""
        return "%s %s %s%s%s" % (c, s, COMP.get(comp, str(comp)), pred, endian)
    if c.startswith("EER legacy"):
        return "EER legacy container"
    return None


def main():
    rows = [json.loads(l) for p in sys.argv[2:] for l in open(p)]
    sets = collections.defaultdict(set)
    examples = collections.defaultdict(list)
    for r in rows:
        if "error" in r or r.get("meta_category") != "micrographs - multiframe":
            continue
        k = classify(r)
        if not k:
            continue
        key = (r["entry"], r.get("imageset"))
        if key not in sets[k]:
            sets[k].add(key)
            if r["entry"] not in examples[k] and len(examples[k]) < 4:
                examples[k].append(r["entry"])
    table = sorted(((len(v), k) for k, v in sets.items()), reverse=True)
    print("| encoding | imagesets | examples |\n|---|---:|---|")
    for n, k in table:
        print("| %s | %d | %s |" % (k, n, ", ".join(examples[k])))
    json.dump({k: {"imagesets": n, "examples": examples[k], "entries": sorted({e for e, _ in sets[k]}, key=int)}
               for n, k in table}, open(sys.argv[1], "w"), indent=1)


if __name__ == "__main__":
    main()
