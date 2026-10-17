#!/usr/bin/env python3
"""Make damaged copies of a real EER movie (for the W-EER-Q failure cases).

  eer_corrupt.py SRC DST truncate FRACTION          copy the first FRACTION of the bytes
  eer_corrupt.py SRC DST random   FRAME NBYTES      overwrite NBYTES mid-strip of directory FRAME with random bytes
  eer_corrupt.py SRC DST ff       FRAME             set the whole strip of directory FRAME to 0xFF
  eer_corrupt.py SRC DST zero     FRAME             set the whole strip of directory FRAME to 0x00
Finds strip offsets by walking the (Big)TIFF IFD chain with struct only.
"""
import os, random, shutil, struct, sys

def strips(path):
    out = []
    with open(path, "rb") as f:
        h = f.read(16); e = "<" if h[:2] == b"II" else ">"
        big = struct.unpack(e + "H", h[2:4])[0] == 43
        off = struct.unpack(e + "Q", h[8:16])[0] if big else struct.unpack(e + "I", h[4:8])[0]
        while off:
            f.seek(off)
            n = struct.unpack(e + ("Q" if big else "H"), f.read(8 if big else 2))[0]
            esz = 20 if big else 12
            raw = f.read(n * esz); tags = {}
            for i in range(n):
                ent = raw[i * esz:(i + 1) * esz]
                tag, typ = struct.unpack(e + "HH", ent[:4])
                val = ent[12:20] if big else ent[8:12]
                fmt = {3: "H", 4: "I", 16: "Q"}.get(typ, "I")
                tags[tag] = struct.unpack(e + fmt, val[:struct.calcsize(fmt)])[0]
            out.append((tags[273], tags[279]))
            off = struct.unpack(e + ("Q" if big else "I"), f.read(8 if big else 4))[0]
    return out

def main():
    src, dst, mode = sys.argv[1:4]
    if mode == "truncate":
        frac = float(sys.argv[4]); size = os.path.getsize(src)
        n = int(size * frac)
        with open(src, "rb") as a, open(dst, "wb") as b:
            left = n
            while left:
                blk = a.read(min(left, 1 << 24)); b.write(blk); left -= len(blk)
        print("truncated to", n, "of", size)
        return
    shutil.copyfile(src, dst)
    fr = int(sys.argv[4]); st = strips(src)
    off, ln = st[fr]
    with open(dst, "r+b") as f:
        if mode == "random":
            nb = int(sys.argv[5]); rng = random.Random(1234)
            f.seek(off + ln // 2); f.write(bytes(rng.randrange(256) for _ in range(nb)))
            print("frame", fr, "strip", off, ln, "random", nb, "bytes at", off + ln // 2)
        else:
            f.seek(off); f.write((b"\xff" if mode == "ff" else b"\x00") * ln)
            print("frame", fr, "strip", off, ln, mode)
main()
