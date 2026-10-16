#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Census of EMPIAR imageset metadata (data_format, voxel_type, size, frames).

Reads https://www.ebi.ac.uk/empiar/api/entry/<id>/ for every id in a range and
keeps only what the format census needs. The metadata is self-reported by
depositors and often wrong; probe_formats.py reads the actual file headers.

Usage: empiar_catalogue.py FIRST_ID LAST_ID_EXCLUSIVE OUT.json [--workers 6]
"""
import argparse, concurrent.futures as cf, json, time, urllib.error, urllib.request

KEYS = ("name", "directory", "category", "header_format", "data_format", "voxel_type",
        "image_width", "image_height", "frames_per_image", "num_images_or_tilt_series", "pixel_width")


def get(i):
    url = "https://www.ebi.ac.uk/empiar/api/entry/%d/" % i
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return i, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return i, None
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return i, "ERR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first", type=int)
    ap.add_argument("last", type=int)
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    out = {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, d in ex.map(get, range(a.first, a.last)):
            if d is None:
                continue
            if d == "ERR":
                out[i] = "ERR"
                continue
            e = list(d.values())[0]
            out[i] = dict(title=e.get("title"), release=e.get("release_date"),
                          imagesets=[{k: s.get(k) for k in KEYS} for s in e.get("imagesets", [])])
    json.dump(out, open(a.out, "w"))
    print(len(out), "entries,", sum(1 for v in out.values() if v == "ERR"), "errors")


if __name__ == "__main__":
    main()
