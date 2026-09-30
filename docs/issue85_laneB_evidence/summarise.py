#!/usr/bin/env python3
"""Render the lane B benchmark JSON as the tables used in the issue comment."""
import json, sys

def table(d):
    base = {r["threads"]: r for r in d["image_read"]}
    pers = {r["readers"]: r for r in d["persistent"]}
    npo  = {r["readers"]: r for r in d.get("persistent_no_parse_once", [])}
    keys = sorted(set(base) | set(pers))
    print("| workers | Image::read per frame (s) | persistent pool (s) | pool, no parse-once (s) | pool vs baseline |")
    print("|---:|---:|---:|---:|---:|")
    for k in keys:
        b = base.get(k, {}).get("whole_read_median_s")
        p = pers.get(k, {}).get("whole_read_median_s")
        n = npo.get(k, {}).get("whole_read_median_s")
        ratio = ("%+.1f%%" % ((p / b - 1) * 100)) if (b and p) else "-"
        print("| %d | %.4f | %.4f | %s | %s |" %
              (k, b or 0, p or 0, ("%.4f" % n) if n else "-", ratio))

def stages(d):
    s = d.get("stages_single_threaded_s")
    if not s: return
    order = ["strip_decode", "convert_and_place", "open_close", "layout",
             "set_directory", "alloc_and_first_touch", "raw_pread"]
    # raw_pread is a separate whole-file read, not part of Image::read; the
    # lifecycle a persistent pool removes is open_close + layout + part of
    # set_directory.
    inpath = sum(s[k] for k in order if k not in ("raw_pread",))
    print("\n| stage (single-threaded) | s | % of the in-path total |")
    print("|---|---:|---:|")
    for k in order:
        mark = "" if k != "raw_pread" else " (separate whole-file read, not part of Image::read)"
        print("| %s%s | %.4f | %s |" % (k, mark, s[k],
              ("%.1f%%" % (100 * s[k] / inpath)) if k != "raw_pread" else "-"))
    removed = s["open_close"] + s["layout"] + s["set_directory"]
    print("| **lifecycle a persistent pool removes** | **%.4f** | **%.1f%%** |" %
          (removed, 100 * removed / inpath))
    print("\nstrips: %d, compressed bytes: %d" % (s["strips"], s["compressed_bytes"]))

for path in sys.argv[1:]:
    d = json.load(open(path))
    print("\n## %s" % d["label"])
    p = d["provenance"]
    print("`%s` on %s, %d movies, %dx%d x %d frames, %d reps, LibTIFF %s, "
          "optimized=%s, affinity_cpus=%s, OMP_PROC_BIND=%s"
          % (p["revision"], p["host"], d["movies"], d["nx"], d["ny"], d["frames_read"],
             d["reps"], p["libtiff_runtime"].split()[-1], p["optimized_build"],
             p["affinity_cpus"], p["OMP_PROC_BIND"]))
    print("all arms decoded identical pixels: **%s**, peak RSS %.2f GiB\n"
          % (d["all_arms_decoded_identical_pixels"], d.get("peak_rss_kib", 0) / 1048576))
    table(d)
    stages(d)
