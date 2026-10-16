# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure-Python writers for every movie container MotionCorr reads.

Used by generate_format_fixtures.py. Standard library and NumPy only, so the
fixtures are deterministic and need no TIFF library. Nothing here decodes: the
oracle in tests/test_input_formats.py is the array the generator started from,
and the decoder under test is MotionCorr's own (LibTIFF, rwMRC.h, renderEER.cpp).
A wrong encoder therefore fails the suite; it cannot make a wrong decoder pass.

Conventions that matter for the oracle:
  * MRC: file row 0 is decoded row 0.
  * TIFF (rwTIFF.h): file row 0 is decoded row ny-1. Callers pass the array in
    decoded orientation and these writers reverse the rows.
  * EER (renderEER.cpp): electron position p lands at row p // width, column
    p % width, without a flip.
  * 4-bit packed (MRC mode 101, IMOD packed TIFF): low nibble is the first pixel.
"""
import struct
import zlib

import numpy as np

# --------------------------------------------------------------------------- MRC

MRC_DTYPES = {0: "i1", 1: "i2", 2: "f4", 6: "u2", 12: "f2"}


def pack_nibbles(values):
    """Two 4-bit samples per byte, first sample in the low nibble."""
    flat = np.asarray(values, dtype=np.uint8).ravel()
    if flat.size % 2:
        raise ValueError("4-bit packing needs an even sample count")
    if flat.max(initial=0) > 15:
        raise ValueError("4-bit samples must be 0..15")
    return (flat[0::2] | (flat[1::2] << 4)).astype(np.uint8).tobytes()


def mrc_bytes(movie, mode, endian="<", ext_header=b"", exttyp=b"", imod_flags=None,
              payload=None, nz_header=None, label=b"MotionCorr synthetic format fixture"):
    """MRC2014 file bytes for movie[n, y, x] stored in the given mode.

    payload overrides the sample bytes (used for deliberately malformed or
    unsupported modes); nz_header overrides the frame count in the header.
    """
    movie = np.asarray(movie)
    nz, ny, nx = movie.shape
    if nz_header is not None:
        nz = nz_header
    e = endian
    h = bytearray(1024)
    struct.pack_into(e + "4i", h, 0, nx, ny, nz, mode)
    struct.pack_into(e + "3i", h, 28, nx, ny, nz)                 # mx, my, mz
    struct.pack_into(e + "3f", h, 40, float(nx), float(ny), float(nz))  # 1 A/px
    struct.pack_into(e + "3f", h, 52, 90.0, 90.0, 90.0)
    struct.pack_into(e + "3i", h, 64, 1, 2, 3)
    vals = movie.astype(np.float64)
    struct.pack_into(e + "3f", h, 76, float(vals.min()), float(vals.max()), float(vals.mean()))
    struct.pack_into(e + "i", h, 92, len(ext_header))             # nsymbt
    h[104:108] = (exttyp + b"    ")[:4]
    struct.pack_into(e + "i", h, 108, 20140)                      # nversion
    if imod_flags is not None:
        struct.pack_into(e + "ii", h, 152, 1146047817, imod_flags)  # IMOD stamp, flags
    h[208:212] = b"MAP "
    h[212:216] = bytes([0x11, 0x11, 0, 0]) if e == ">" else bytes([0x44, 0x44, 0, 0])
    struct.pack_into(e + "f", h, 216, float(vals.std()))
    struct.pack_into(e + "i", h, 220, 1)
    h[224:224 + len(label)] = label
    if payload is None:
        if mode == 101:
            payload = pack_nibbles(movie)
        else:
            payload = movie.astype(np.dtype(MRC_DTYPES[mode]).newbyteorder(e)).tobytes()
    return bytes(h) + ext_header + payload


# ------------------------------------------------------------------------- codecs

def lzw_encode(data):
    """TIFF 6.0 LZW (MSB-first codes, early change), as LibTIFF's tif_lzw.c writes it.

    Code width grows when the next free code exceeds the current maximum; the
    table is reset with a Clear code when code 4094 would be assigned; the final
    code bumps the width exactly as the decoder will before it reads EOI.
    """
    CLEAR, EOI, FIRST = 256, 257, 258
    out = bytearray()
    acc = 0
    nacc = 0

    def put(code, width):
        nonlocal acc, nacc
        acc = (acc << width) | code
        nacc += width
        while nacc >= 8:
            nacc -= 8
            out.append((acc >> nacc) & 0xFF)
        acc &= (1 << nacc) - 1

    width, maxcode, free = 9, 511, FIRST
    table = {}
    put(CLEAR, width)
    it = iter(data)
    try:
        ent = next(it)
    except StopIteration:
        put(EOI, width)
        if nacc:
            out.append((acc << (8 - nacc)) & 0xFF)
        return bytes(out)
    for c in it:
        key = (ent << 8) | c
        code = table.get(key)
        if code is not None:
            ent = code
            continue
        put(ent, width)
        ent = c
        table[key] = free
        free += 1
        if free == 4094:          # CODE_MAX - 1: table full
            put(CLEAR, width)
            table.clear()
            width, maxcode, free = 9, 511, FIRST
        elif free > maxcode:
            width += 1
            maxcode = (1 << width) - 1
    put(ent, width)
    free += 1
    if free == 4094:
        put(CLEAR, width)
        width = 9
    elif free > maxcode:
        width += 1
    put(EOI, width)
    if nacc:
        out.append((acc << (8 - nacc)) & 0xFF)
    return bytes(out)


def packbits_encode_row(row):
    """Apple PackBits for one row; TIFF requires runs not to cross rows."""
    out = bytearray()
    i, n = 0, len(row)
    while i < n:
        j = i + 1
        while j < n and j - i < 128 and row[j] == row[i]:
            j += 1
        if j - i >= 2:
            out.append((257 - (j - i)) & 0xFF)
            out.append(row[i])
            i = j
            continue
        j = i + 1
        while j < n and j - i < 128 and not (j + 1 < n and row[j] == row[j + 1]):
            j += 1
        out.append(j - i - 1)
        out += row[i:j]
        i = j
    return bytes(out)


def predict_horizontal(rows, dtype):
    """TIFF predictor 2 on native sample values, wrapping at the sample width."""
    dtype = np.dtype(dtype)
    if dtype.kind == "f":
        raise ValueError("predictor 2 is for integer samples")
    rows = np.asarray(rows).astype(dtype)          # same-dtype subtraction wraps
    out = rows.copy()
    out[:, 1:] = rows[:, 1:] - rows[:, :-1]
    return out


def predict_float(rows, endian):
    """TIFF predictor 3 (floating point), as LibTIFF's fpDiff does it.

    Each row's samples are split into byte planes, most significant byte first,
    and the planes are then differenced byte-wise along the row.
    """
    rows = np.asarray(rows)
    bps = rows.dtype.itemsize
    be = rows.astype(rows.dtype.newbyteorder(">"))
    out = []
    for r in be:
        b = np.frombuffer(r.tobytes(), dtype=np.uint8).reshape(-1, bps)
        planes = b.T.reshape(-1).astype(np.uint8)         # plane 0 = MSBs
        d = planes.copy()
        d[1:] = (planes[1:].astype(np.int16) - planes[:-1].astype(np.int16)).astype(np.uint8)
        out.append(d.tobytes())
    return out


# --------------------------------------------------------------------------- TIFF

TIFF_SAMPLE = {  # numpy kind/size -> (bits, sampleformat)
    ("u", 1): (8, 1), ("i", 1): (8, 2), ("u", 2): (16, 1), ("i", 2): (16, 2),
    ("u", 4): (32, 1), ("i", 4): (32, 2), ("f", 4): (32, 3), ("f", 8): (64, 3),
}
SHORT, LONG, LONG8 = 3, 4, 16


class TiffWriter:
    """Minimal multi-page TIFF / BigTIFF writer, one IFD per page.

    Strips (or tiles) are encoded by the caller-selected codec. Extra tags are
    (tag, type, values) triples written verbatim; EER pages use this for their
    private compression codes and depth tags.
    """

    def __init__(self, path, endian="<", bigtiff=False):
        self.fh = open(path, "wb")
        self.e = endian
        self.big = bigtiff
        bom = b"II" if endian == "<" else b"MM"
        if bigtiff:
            self.fh.write(bom + struct.pack(endian + "HHHQ", 43, 8, 0, 0))
            self.next_ptr = 8
        else:
            self.fh.write(bom + struct.pack(endian + "HI", 42, 0))
            self.next_ptr = 4

    def _align(self):
        if self.fh.tell() % 2:
            self.fh.write(b"\0")

    def _values(self, typ, values):
        fmt = {SHORT: "H", LONG: "I", LONG8: "Q"}[typ]
        return struct.pack(self.e + fmt * len(values), *values)

    def write_page(self, width, length, segments, bits, sampleformat, compression,
                   rows_per_strip=None, tile=None, predictor=1, spp=1, extra_tags=(),
                   photometric=1, write_sampleformat=True, minimal=False):
        e = self.e
        offs, counts = [], []
        for seg in segments:
            self._align()
            offs.append(self.fh.tell())
            counts.append(len(seg))
            self.fh.write(seg)
        n = len(offs)
        off_type = LONG8 if self.big else LONG
        tags = [(256, LONG, [width]), (257, LONG, [length]), (259, SHORT, [compression]),
                (262, SHORT, [photometric])]
        if not minimal:     # EPU's EER pages carry none of these
            tags += [(258, SHORT, [bits] * spp), (277, SHORT, [spp]), (284, SHORT, [1])]
        if write_sampleformat:
            tags.append((339, SHORT, [sampleformat] * spp))
        if predictor != 1:
            tags.append((317, SHORT, [predictor]))
        if tile:
            tags += [(322, LONG, [tile[0]]), (323, LONG, [tile[1]]),
                     (324, off_type, offs), (325, off_type, counts)]
        else:
            tags += [(273, off_type, offs), (278, LONG, [rows_per_strip]),
                     (279, off_type, counts)]
        tags += list(extra_tags)
        tags.sort(key=lambda t: t[0])
        # Out-of-line tag values first, then the IFD itself.
        inline = 8 if self.big else 4
        entries = []
        for tag, typ, vals in tags:
            raw = self._values(typ, vals)
            if len(raw) <= inline:
                entries.append((tag, typ, len(vals), raw.ljust(inline, b"\0")))
            else:
                self._align()
                ptr = self.fh.tell()
                self.fh.write(raw)
                entries.append((tag, typ, len(vals),
                                struct.pack(e + ("Q" if self.big else "I"), ptr)))
        self._align()
        ifd = self.fh.tell()
        if self.big:
            self.fh.write(struct.pack(e + "Q", len(entries)))
            for tag, typ, cnt, val in entries:
                self.fh.write(struct.pack(e + "HHQ", tag, typ, cnt) + val)
            nxt = self.fh.tell()
            self.fh.write(struct.pack(e + "Q", 0))
        else:
            self.fh.write(struct.pack(e + "H", len(entries)))
            for tag, typ, cnt, val in entries:
                self.fh.write(struct.pack(e + "HHI", tag, typ, cnt) + val)
            nxt = self.fh.tell()
            self.fh.write(struct.pack(e + "I", 0))
        here = self.fh.tell()
        self.fh.seek(self.next_ptr)
        self.fh.write(struct.pack(e + ("Q" if self.big else "I"), ifd))
        self.fh.seek(here)
        self.next_ptr = nxt

    def close(self):
        self.fh.close()


def tiff_segments(frame_file_rows, dtype, compression, predictor, rows_per_strip=None,
                  tile=None, endian="<"):
    """Encode one page given in FILE row order (top row first)."""
    rows = np.asarray(frame_file_rows)
    length, width = rows.shape
    fdt = np.dtype(dtype).newbyteorder(endian)

    def encode(block_rows):
        if predictor == 2:
            raw = predict_horizontal(block_rows, np.dtype(dtype)).astype(fdt).tobytes()
        elif predictor == 3:
            raw = b"".join(predict_float(block_rows.astype(np.dtype(dtype)), endian))
        else:
            raw = block_rows.astype(fdt).tobytes()
        if compression == 1:
            return raw
        if compression in (8, 32946):
            return zlib.compress(raw, 6)
        if compression == 5:
            return lzw_encode(raw)
        if compression == 32773:
            rb = width * fdt.itemsize
            return b"".join(packbits_encode_row(raw[i:i + rb]) for i in range(0, len(raw), rb))
        raise ValueError("unsupported compression %d" % compression)

    if tile:
        tw, tl = tile
        segs = []
        for y0 in range(0, length, tl):
            for x0 in range(0, width, tw):
                blk = np.zeros((tl, tw), dtype=rows.dtype)
                part = rows[y0:y0 + tl, x0:x0 + tw]
                blk[:part.shape[0], :part.shape[1]] = part
                segs.append(encode(blk))
        return segs
    return [encode(rows[s:s + rows_per_strip]) for s in range(0, length, rows_per_strip)]


def write_tiff_movie(path, movie, dtype, compression=1, predictor=1, rows_per_strip=None,
                     tile=None, endian="<", bigtiff=False, spp=1, extra_tags=(),
                     flip_for_reader=True):
    """movie[n, y, x] in decoded orientation -> multi-page TIFF."""
    movie = np.asarray(movie)
    n, ny, nx = movie.shape
    kind = np.dtype(dtype)
    bits, sf = TIFF_SAMPLE[(kind.kind, kind.itemsize)]
    rps = rows_per_strip or ny
    w = TiffWriter(path, endian, bigtiff)
    for f in range(n):
        file_rows = movie[f][::-1] if flip_for_reader else movie[f]
        if spp > 1:
            file_rows = np.repeat(file_rows, spp, axis=1)   # interleaved samples
        segs = tiff_segments(file_rows, dtype, compression, predictor, rps, tile, endian)
        w.write_page(nx, ny, segs, bits, sf, compression, rows_per_strip=rps, tile=tile,
                     predictor=predictor, spp=spp, extra_tags=extra_tags)
    w.close()


def write_packed4_tiff(path, movie):
    """IMOD packed 4-bit TIFF: 8-bit pages at half the logical width.

    rwTIFF.h recognises this only at K2/K3 super-resolution geometries and
    doubles the width; the low nibble is the first pixel.
    """
    movie = np.asarray(movie)
    n, ny, nx = movie.shape
    w = TiffWriter(path)
    for f in range(n):
        file_rows = movie[f][::-1]
        packed = np.frombuffer(pack_nibbles(file_rows), dtype=np.uint8).reshape(ny, nx // 2)
        segs = tiff_segments(packed, np.uint8, 1, 1, 16)
        w.write_page(nx // 2, ny, segs, 8, 1, 1, rows_per_strip=16)
    w.close()


# ---------------------------------------------------------------------------- EER

EER_FOOTER_OK = b"ThermoFisherECComprOK000"


class BitWriterLSB:
    """LSB-first bit stream: the next field starts at the lowest unused bit."""

    def __init__(self):
        self.chunks = []      # (value, nbits)

    def put(self, value, nbits):
        self.chunks.append((value, nbits))

    def to_bytes(self):
        vals = np.array([c[0] for c in self.chunks], dtype=np.uint64)
        bits = np.array([c[1] for c in self.chunks], dtype=np.uint64)
        if vals.size == 0:
            return b""
        start = np.concatenate(([0], np.cumsum(bits)[:-1])).astype(np.uint64)
        total = int(start[-1] + bits[-1])
        out = np.zeros((total + 7) // 8 + 8, dtype=np.uint8)
        byte = (start >> np.uint64(3)).astype(np.int64)
        shifted = vals << (start & np.uint64(7))               # < 2**19 for <= 12-bit codes
        for lane in range(3):
            part = ((shifted >> np.uint64(8 * lane)) & np.uint64(0xFF)).astype(np.uint8)
            np.bitwise_or.at(out, byte + lane, part)
        return out[:(total + 7) // 8].tobytes()


def eer_frame_codes(positions, symbols, total_pixels, rle_bits, sym_bits, sym_xor):
    """Run-length codes for one EER fraction.

    positions: strictly increasing linear pixel indices; symbols: decoded
    subpixel codes (the decoder XORs the stored value with sym_xor). A run of
    the maximum value (2**rle_bits - 1) advances without an electron. The final
    run lands exactly on total_pixels, which renderEER.cpp requires.
    """
    maxrun = (1 << rle_bits) - 1
    codes = []          # (run, stored symbol or None)
    nxt = 0
    for p, s in zip(positions.tolist(), symbols.tolist()):
        d = p - nxt
        while d >= maxrun:
            codes.append((maxrun, None))
            d -= maxrun
        codes.append((d, s ^ sym_xor))
        nxt = p + 1
    rem = total_pixels - nxt
    if rem == 0:
        codes.append((0, None))
    while rem > 0:
        r = min(rem, maxrun)
        codes.append((r, None))
        rem -= r
    return codes


def eer_encode_7bit(positions, symbols, total_pixels, sym_bits):
    """65001 (7-bit runs, 4-bit symbols) or 65002 with 1+1 subpixel bits."""
    sym_xor = 0x0A if sym_bits == 4 else 0x03
    bw = BitWriterLSB()
    for run, sym in eer_frame_codes(positions, symbols, total_pixels, 7, sym_bits, sym_xor):
        bw.put(run, 7)
        if sym is not None:
            bw.put(sym, sym_bits)
    return bw.to_bytes()


def eer_encode_8bit(positions, symbols, total_pixels):
    """65000: 8-bit run + 4-bit symbol, two 12-bit codes per 3 bytes."""
    codes = eer_frame_codes(positions, symbols, total_pixels, 8, 4, 0x0A)
    if len(codes) % 2:
        codes.append((0, 0))     # never reached: the decoder stops at total_pixels
    out = bytearray()
    for i in range(0, len(codes), 2):
        p1, s1 = codes[i]
        p2, s2 = codes[i + 1]
        s1 = 0 if s1 is None else s1
        s2 = 0 if s2 is None else s2
        out += bytes([p1 & 0xFF, (s1 & 0x0F) | ((p2 & 0x0F) << 4), (p2 >> 4) | ((s2 & 0x0F) << 4)])
    return bytes(out)


def write_eer(path, fractions, size, compression, orientation=None, legacy=False):
    """fractions: list of (positions, symbols) per raw fraction.

    compression 65000 / 65001 / 65002 (65002 written with RLE depth 7 and 1+1
    subpixel bits, the only detailed encoding renderEER.cpp accepts).
    legacy=True writes the pre-TIFF container: each fraction padded to 8 bytes,
    followed by its length in 8-byte words and the OK footer. Legacy fractions
    use the 8-bit code, as RELION 3.1 assumed for that container.
    """
    total = size * size
    if legacy:
        with open(path, "wb") as fh:
            for pos, sym in fractions:
                data = eer_encode_8bit(pos, sym, total)
                data += b"\0" * ((-len(data)) % 8)
                fh.write(data)
                fh.write(struct.pack("<q", len(data) // 8))
                fh.write(EER_FOOTER_OK)
        return
    w = TiffWriter(path, "<", bigtiff=True)
    extra = []
    if compression == 65002:
        extra = [(65007, SHORT, [7]), (65008, SHORT, [1]), (65009, SHORT, [1])]
    if orientation is not None:
        extra.append((274, SHORT, [orientation]))
    for pos, sym in fractions:
        if compression == 65000:
            data = eer_encode_8bit(pos, sym, total)
        elif compression == 65001:
            data = eer_encode_7bit(pos, sym, total, 4)
        elif compression == 65002:
            data = eer_encode_7bit(pos, sym, total, 2)
        else:
            raise ValueError(compression)
        data += b"\0" * ((-len(data)) % 8)     # EPU pads each fraction to 8 bytes
        w.write_page(size, size, [data], 1, 1, compression, rows_per_strip=size,
                     extra_tags=extra, write_sampleformat=False, minimal=True)
    w.close()
