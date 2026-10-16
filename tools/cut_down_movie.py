#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Cut a real movie down to a few frames without re-encoding it.

The quick real-data set (test-data/real_cutdown_manifest.json) is made with this
tool so that each cut-down file keeps the producer's exact encoding: the same
compressed strips, byte order, tags and private EER blobs.

  TIFF / BigTIFF / EER   copies directories [first, first+frames) with their raw
                         strip or tile bytes; every other tag is copied verbatim
                         (offset-valued IFD pointers such as SubIFDs are dropped)
  MRC (.mrc / .mrcs)     header with the new frame count, the extended header
                         verbatim, and the selected frames; --crop X0 Y0 W H
                         crops raw samples (modes 0, 1, 2, 6, 12; mode 101 with
                         even X0 and W) and updates the dimensions and cell
  compressed MRC         decompressed, cut as above, recompressed with the same
                         codec (bz2 and xz in-process, zst through zstd)

Python 3.8+, standard library only. Usage:
  cut_down_movie.py INPUT OUTPUT --frames N [--first K] [--crop X0 Y0 W H]
"""
import argparse
import bz2
import lzma
import struct
import subprocess
import sys
from pathlib import Path

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8,
             13: 4, 16: 8, 17: 8, 18: 8}
OFFSET_TAGS = {273: 279, 324: 325}                   # data offsets -> byte counts
POINTER_TAGS = {330, 34665, 34853, 40965}            # sub-IFD pointers: not copied
MRC_BPP = {0: 1, 1: 2, 2: 4, 6: 2, 12: 2}


def read_ifds(fh):
    head = fh.read(16)
    e = "<" if head[:2] == b"II" else ">"
    big = struct.unpack(e + "H", head[2:4])[0] == 43
    off = struct.unpack(e + "Q", head[8:16])[0] if big else struct.unpack(e + "I", head[4:8])[0]
    ifds = []
    while off:
        fh.seek(off)
        n = struct.unpack(e + ("Q" if big else "H"), fh.read(8 if big else 2))[0]
        raw = fh.read(n * (20 if big else 12))
        nxt = struct.unpack(e + ("Q" if big else "I"), fh.read(8 if big else 4))[0]
        entries = []
        for i in range(n):
            b = raw[i * (20 if big else 12):(i + 1) * (20 if big else 12)]
            if big:
                tag, typ, cnt = struct.unpack(e + "HHQ", b[:12]); field = b[12:20]
            else:
                tag, typ, cnt = struct.unpack(e + "HHI", b[:8]); field = b[8:12]
            size = TYPE_SIZE.get(typ, 1) * cnt
            if size <= len(field):
                data = field[:size]
            else:
                ptr = struct.unpack(e + ("Q" if big else "I"), field)[0]
                pos = fh.tell()
                fh.seek(ptr)
                data = fh.read(size)
                fh.seek(pos)
            entries.append((tag, typ, cnt, data))
        ifds.append(entries)
        off = nxt
    return e, big, ifds


def values(e, typ, cnt, data):
    fmt = {3: "H", 4: "I", 16: "Q"}[typ]
    return list(struct.unpack(e + fmt * cnt, data))


def cut_tiff(src, dst, first, frames):
    with open(src, "rb") as fh:
        e, big, ifds = read_ifds(fh)
        if first + frames > len(ifds):
            raise SystemExit("%s has %d directories; asked for %d from %d" % (src, len(ifds), frames, first))
        out = open(dst, "wb")
        bom = b"II" if e == "<" else b"MM"
        out.write(bom + (struct.pack(e + "HHHQ", 43, 8, 0, 0) if big else struct.pack(e + "HI", 42, 0)))
        next_ptr = 8 if big else 4
        dropped = set()
        for entries in ifds[first:first + frames]:
            tags = {t: (typ, cnt, data) for t, typ, cnt, data in entries}
            new = []
            for tag, typ, cnt, data in entries:
                if tag in POINTER_TAGS:
                    dropped.add(tag)
                    continue
                if tag in OFFSET_TAGS:
                    counts = values(e, *tags[OFFSET_TAGS[tag]][:2], tags[OFFSET_TAGS[tag]][2])
                    offs = values(e, typ, cnt, data)
                    new_offs = []
                    for o, c in zip(offs, counts):
                        if out.tell() % 2:
                            out.write(b"\0")
                        new_offs.append(out.tell())
                        fh.seek(o)
                        out.write(fh.read(c))
                    if not big and max(new_offs, default=0) > 0xFFFFFFFF:
                        raise SystemExit("classic TIFF offset overflow")
                    data = struct.pack(e + {3: "H", 4: "I", 16: "Q"}[typ] * cnt, *new_offs)
                new.append((tag, typ, cnt, data))
            inline = 8 if big else 4
            fields = []
            for tag, typ, cnt, data in new:
                if len(data) <= inline:
                    fields.append((tag, typ, cnt, data.ljust(inline, b"\0")))
                else:
                    if out.tell() % 2:
                        out.write(b"\0")
                    ptr = out.tell()
                    out.write(data)
                    fields.append((tag, typ, cnt, struct.pack(e + ("Q" if big else "I"), ptr)))
            if out.tell() % 2:
                out.write(b"\0")
            ifd = out.tell()
            out.write(struct.pack(e + ("Q" if big else "H"), len(fields)))
            for tag, typ, cnt, field in fields:
                out.write(struct.pack(e + ("HHQ" if big else "HHI"), tag, typ, cnt) + field)
            nxt = out.tell()
            out.write(b"\0" * (8 if big else 4))
            here = out.tell()
            out.seek(next_ptr)
            out.write(struct.pack(e + ("Q" if big else "I"), ifd))
            out.seek(here)
            next_ptr = nxt
        out.close()
    if dropped:
        print("dropped pointer tags %s" % sorted(dropped), file=sys.stderr)
    return len(ifds)


def cut_mrc_bytes(raw, first, frames, crop=None):
    e = "<"
    nx, ny, nz, mode = struct.unpack("<4i", raw[:16])
    if not (0 < nx < 1 << 20 and 0 < ny < 1 << 20):
        e = ">"
        nx, ny, nz, mode = struct.unpack(">4i", raw[:16])
    nsymbt = struct.unpack(e + "i", raw[92:96])[0]
    if mode == 101:
        frame_bytes = nx * ny // 2
    elif mode in MRC_BPP:
        frame_bytes = nx * ny * MRC_BPP[mode]
    else:
        raise SystemExit("MRC mode %d is not a movie mode" % mode)
    if first + frames > nz:
        raise SystemExit("movie has %d frames; asked for %d from %d" % (nz, frames, first))
    base = 1024 + nsymbt
    payload = raw[base + first * frame_bytes: base + (first + frames) * frame_bytes]
    head = bytearray(raw[:1024])
    apix = struct.unpack(e + "f", head[40:44])[0] / max(1, struct.unpack(e + "i", head[28:32])[0])
    if crop:
        x0, y0, w, h = crop
        if x0 + w > nx or y0 + h > ny:
            raise SystemExit("crop outside the frame")
        if mode == 101 and (x0 % 2 or w % 2):
            raise SystemExit("4-bit crops need even X0 and W")
        rows = []
        for f in range(frames):
            fr = payload[f * frame_bytes:(f + 1) * frame_bytes]
            for y in range(y0, y0 + h):
                if mode == 101:
                    rows.append(fr[(y * nx + x0) // 2:(y * nx + x0 + w) // 2])
                else:
                    b = MRC_BPP[mode]
                    rows.append(fr[(y * nx + x0) * b:(y * nx + x0 + w) * b])
        payload = b"".join(rows)
        nx, ny = w, h
    struct.pack_into(e + "3i", head, 0, nx, ny, frames)
    struct.pack_into(e + "3i", head, 28, nx, ny, frames)
    struct.pack_into(e + "3f", head, 40, nx * apix, ny * apix, frames * apix)
    return bytes(head) + raw[1024:base] + payload


def decompress(src):
    name = src.name
    if name.endswith(".bz2"):
        return bz2.decompress(src.read_bytes()), "bz2"
    if name.endswith(".xz"):
        return lzma.decompress(src.read_bytes()), "xz"
    if name.endswith(".zst"):
        return subprocess.run(["zstd", "-dc", "--", str(src)], check=True, capture_output=True).stdout, "zst"
    return src.read_bytes(), None


def compress(data, codec):
    if codec == "bz2":
        return bz2.compress(data, 9)
    if codec == "xz":
        return lzma.compress(data)
    if codec == "zst":
        return subprocess.run(["zstd", "-q", "-19", "-c", "-"], input=data, check=True, capture_output=True).stdout
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--frames", type=int, required=True, help="frames (EER: raw fractions) to keep")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--crop", type=int, nargs=4, metavar=("X0", "Y0", "W", "H"), help="MRC only")
    a = ap.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with open(a.input, "rb") as fh:
        magic = fh.read(4)
    if magic in (b"II*\0", b"MM\0*", b"II+\0", b"MM\0+"):
        if a.crop:
            raise SystemExit("--crop would re-encode a TIFF; only frame subsets are supported")
        n = cut_tiff(a.input, a.output, a.first, a.frames)
        print("%s: kept directories %d..%d of %d" % (a.output.name, a.first, a.first + a.frames - 1, n))
        return 0
    raw, codec = decompress(a.input)
    out = cut_mrc_bytes(raw, a.first, a.frames, a.crop)
    a.output.write_bytes(compress(out, codec))
    print("%s: MRC frames %d..%d%s%s" % (a.output.name, a.first, a.first + a.frames - 1,
                                        " crop %s" % a.crop if a.crop else "", " (%s)" % codec if codec else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
