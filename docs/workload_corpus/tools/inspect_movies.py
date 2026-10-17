#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Full-header inventory of downloaded corpus files (frame counts included).

TIFF/BigTIFF/EER: walks every directory and reports the first page's tags and the
page count. MRC: header fields. .bz2/.zst MRC: the inner header after partial
decompression. Usage: inspect_movies.py DATA_ROOT OUT.json [GLOB ...]
"""
import struct, sys, os, json, glob, bz2, subprocess, re
def tiff_info(p):
    with open(p, "rb") as f:
        h = f.read(16); e = "<" if h[:2] == b"II" else ">"
        big = struct.unpack(e+"H", h[2:4])[0] == 43
        off = struct.unpack(e+"Q", h[8:16])[0] if big else struct.unpack(e+"I", h[4:8])[0]
        n = 0; first = None
        while off and n < 200000:
            f.seek(off)
            cnt = struct.unpack(e+("Q" if big else "H"), f.read(8 if big else 2))[0]
            ent = f.read(cnt*(20 if big else 12))
            tags = {}
            for i in range(cnt):
                b = ent[i*(20 if big else 12):(i+1)*(20 if big else 12)]
                tag, typ = struct.unpack(e+"HH", b[:4])
                v = b[12:20] if big else b[8:12]
                if typ == 3: val = struct.unpack(e+"H", v[:2])[0]
                elif typ == 4: val = struct.unpack(e+"I", v[:4])[0]
                elif typ == 16: val = struct.unpack(e+"Q", v[:8])[0]
                else: val = None
                tags[tag] = val
            if first is None: first = tags
            off = struct.unpack(e+("Q" if big else "I"), f.read(8 if big else 4))[0]; n += 1
    t = first
    return dict(container="BigTIFF" if big else "TIFF", endian=e, frames=n, width=t.get(256), length=t.get(257), bits=t.get(258), compression=t.get(259), sampleformat=t.get(339), rps=t.get(278), predictor=t.get(317), orientation=t.get(274))
def mrc_info(head):
    nx, ny, nz, mode = struct.unpack("<4i", head[:16]); ns = struct.unpack("<i", head[92:96])[0]
    return dict(container="MRC", mode=mode, nx=nx, ny=ny, nz=nz, nsymbt=ns, exttyp=head[104:108].decode("latin-1"), imod_flags=struct.unpack("<i", head[156:160])[0], apix_header=round(struct.unpack("<f", head[40:44])[0]/max(1,struct.unpack("<i", head[28:32])[0]), 4))
import argparse
ap = argparse.ArgumentParser(); ap.add_argument("data"); ap.add_argument("out"); ap.add_argument("globs", nargs="*", default=["EMPIAR-*/**/*"]); A = ap.parse_args()
out = {}
for p in sorted(q for g in A.globs for q in glob.glob(os.path.join(A.data, g), recursive=True)):
    if os.path.isdir(p) or p.endswith((".xml", ".txt", ".partial")): continue
    rec = {"bytes": os.path.getsize(p)}
    if p.endswith(".bz2"):
        d = bz2.BZ2Decompressor(); rec.update(mrc_info(d.decompress(open(p, "rb").read(3_000_000))[:1024])); rec["container"] = "MRC in bz2"
    elif p.endswith(".zst"):
        head = subprocess.run("head -c 2000000 '%s' | zstd -dc 2>/dev/null | head -c 1024" % p, shell=True, capture_output=True).stdout
        rec.update(mrc_info(head)); rec["container"] = "MRC in zst"
    else:
        with open(p, "rb") as f: head = f.read(1024)
        rec.update(tiff_info(p) if head[:2] in (b"II", b"MM") else mrc_info(head))
    out[os.path.relpath(p, A.data)] = rec
    print(os.path.relpath(p, A.data)[-75:], json.dumps({k: v for k, v in rec.items() if v is not None}))
json.dump(out, open(A.out, "w"), indent=1)
