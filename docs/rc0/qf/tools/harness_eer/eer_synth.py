#!/usr/bin/env python3
"""Write a synthetic EER movie (classic TIFF container, private EER compression tags).

Used only for the W-EER-Q overflow-guard and codec-coverage cases: the corpus has no
movie whose grouped counts approach 65535 and only compression tag 65001.

* Fractions are 1 strip each, directory i points at one of V distinct strips (i % V),
  so a movie with tens of thousands of fractions costs V strips on disk. The file is
  extended sparsely so that file_size >= bytes copied by EERRenderer::lazyReadFrames
  (it requires pos + strip_size < file_size).
* --hot adds electrons at fixed source pixels in every fraction. At the 4K -> 2K mode
  (--hot 4) the four source pixels 0, 1, 4096, 4097 merge into one output pixel, so one
  group of G fractions counts 4*G there; at 1:1 modes (--hot 1) it counts G.
* --bg adds K pseudo-random electrons per distinct strip (seeded), so groups differ.

Encoding follows EERRenderer::renderFrames: LSB-first bitstream of [gap:rle_bits]
[symbol:subpixel_bits] units; gap == 2^rle_bits-1 is a skip with no electron; the stored
symbol is true ^ 0x0A (4-bit) or ^ 3 (2-bit); decoding must end with n_pix == W*H.
"""
import argparse, random, struct

def bits_to_bytes(bits):
    out = bytearray((len(bits) + 7) // 8 + 4)
    for i, b in enumerate(bits):
        if b: out[i >> 3] |= 1 << (i & 7)
    return bytes(out)

def push(bits, value, n):
    for k in range(n): bits.append((value >> k) & 1)

def encode(positions, symbols, total, codec, sbits):
    """positions strictly increasing; returns strip bytes."""
    rle = 8 if codec == 65000 else 7
    skip = (1 << rle) - 1
    mask = 3 if sbits == 2 else 0x0A
    bits = []
    npix = 0
    units = 0
    def unit(p, s):
        nonlocal units
        push(bits, p, rle); push(bits, s, sbits); units += 1
    for pos, s in zip(positions, symbols):
        gap = pos - npix
        while gap >= skip:
            if codec == 65000: unit(skip, 0)
            else: push(bits, skip, rle)       # 7-bit stream: a skip carries no symbol
            gap -= skip
        if codec == 65000: unit(gap, s ^ mask)
        else: unit(gap, s ^ mask)
        npix = pos + 1
    rem = total - npix
    while rem >= skip:
        if codec == 65000: unit(skip, 0)
        else: push(bits, skip, rle)
        rem -= skip
    if rem > 0:
        if codec == 65000: unit(rem, 0)
        else: push(bits, rem, rle)
    if codec == 65000:
        if units % 2: unit(skip, 0)
        data = bytearray()
        # 12-bit units are packed low-first: byte stream equals the LSB-first bitstream
        return bits_to_bytes(bits)
    return bits_to_bytes(bits)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--det", type=int, default=4096)
    ap.add_argument("--nfrac", type=int, required=True); ap.add_argument("--codec", type=int, default=65001)
    ap.add_argument("--variants", type=int, default=2); ap.add_argument("--hot", type=int, default=0, choices=[0, 1, 4])
    ap.add_argument("--bg", type=int, default=0); ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    W = H = a.det; total = W * H
    sbits = 2 if a.codec == 65002 else 4
    rng = random.Random(a.seed)
    strips = []
    for v in range(a.variants):
        pos = set()
        if a.hot >= 1: pos.add(0)
        if a.hot == 4: pos.update({1, W, W + 1})
        while len(pos) < (a.hot and {1: 1, 4: 4}[a.hot]) + a.bg: pos.add(rng.randrange(total))
        pos = sorted(pos)
        sym = [rng.randrange(1 << sbits) for _ in pos]
        strips.append(encode(pos, sym, total, a.codec, sbits))
    nd = a.nfrac
    ifd_bytes = 2 + 6 * 12 + 4 + (3 * 12 if a.codec == 65002 else 0)
    if a.codec == 65002: ifd_bytes += 3 * 2   # out-of-line values are inline (SHORT x1), no extra
    hdr = 8
    strip_off = []
    off = hdr
    for s in strips:
        strip_off.append(off); off += len(s)
    ifd_start = off
    nent = 6 + (3 if a.codec == 65002 else 0)
    ifd_size = 2 + nent * 12 + 4
    with open(a.out, "wb") as f:
        f.write(b"II" + struct.pack("<HI", 42, ifd_start))
        for s in strips: f.write(s)
        for i in range(nd):
            so = strip_off[i % len(strips)]; sl = len(strips[i % len(strips)])
            ents = [(256, 3, 1, W), (257, 3, 1, H), (259, 3, 1, a.codec), (273, 4, 1, so), (278, 3, 1, H), (279, 4, 1, sl)]
            if a.codec == 65002:
                ents += [(65007, 3, 1, 7), (65008, 3, 1, 1), (65009, 3, 1, 1)]
            ents.sort()
            nxt = ifd_start + (i + 1) * ifd_size if i + 1 < nd else 0
            f.write(struct.pack("<H", len(ents)))
            for t, ty, cnt, val in ents:
                f.write(struct.pack("<HHI", t, ty, cnt))
                f.write(struct.pack("<I", val) if ty == 4 else struct.pack("<HH", val, 0))
            f.write(struct.pack("<I", nxt))
        end = f.tell()
        copied = sum(len(strips[i % len(strips)]) for i in range(nd))
        f.truncate(max(end, copied + end + (1 << 20)))   # sparse tail so file_size > bytes copied
    print("wrote", a.out, "frac", nd, "strip bytes", [len(s) for s in strips], "file", end, "apparent", max(end, copied + end + (1 << 20)))

if __name__ == "__main__":
    main()
