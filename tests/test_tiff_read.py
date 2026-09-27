#!/usr/bin/env python3
"""Check the TIFF reader against an independently computed expectation.

Covers the two layouts the reader treats differently: ordinary 16-bit samples
split over many strips, and IMOD's packed 4-bit extension, which is recognised
only at specific super-resolution geometries and stores two pixels per byte.
Both must come out Y-flipped relative to the file, matching the MRC convention.

Comparison is per-row sums, which are exact in double for integer samples and
relocate as a unit under any row-striding or flip error.
"""
import argparse
import os
import random
import struct
import subprocess
import sys
import tempfile
import zlib

# Byte -> sum of its two 4-bit samples, for the packed case.
NIBBLE_SUM = bytes((b & 0x0F) + ((b >> 4) & 0x0F) for b in range(256))


def write_tiff(path, frame_rows, bits, compression, rows_per_strip, logical_width):
    """Minimal little-endian classic TIFF writer, one IFD per frame."""
    height = len(frame_rows[0])
    with open(path, "wb") as fh:
        fh.write(b"II" + struct.pack("<HI", 42, 0))
        strip_tables = []
        for rows in frame_rows:
            offs, counts = [], []
            for start in range(0, height, rows_per_strip):
                raw = b"".join(rows[start:start + rows_per_strip])
                blob = zlib.compress(raw) if compression == 8 else raw
                offs.append(fh.tell())
                counts.append(len(blob))
                fh.write(blob)
            strip_tables.append((offs, counts))

        prev_next_field = 4
        for offs, counts in strip_tables:
            n = len(offs)
            if n > 1:
                off_pos = fh.tell(); fh.write(struct.pack("<%dI" % n, *offs))
                cnt_pos = fh.tell(); fh.write(struct.pack("<%dI" % n, *counts))
            else:
                off_pos, cnt_pos = offs[0], counts[0]
            entries = sorted([
                (256, 4, 1, logical_width if bits != 4 else logical_width // 2),
                (257, 4, 1, height),
                (258, 3, 1, 8 if bits == 4 else bits),
                (259, 3, 1, compression),
                (262, 3, 1, 1),
                (273, 4, n, off_pos),
                (277, 3, 1, 1),
                (278, 4, 1, rows_per_strip),
                (279, 4, n, cnt_pos),
                (284, 3, 1, 1),
                (339, 3, 1, 1),
            ])
            ifd_pos = fh.tell()
            fh.write(struct.pack("<H", len(entries)))
            for tag, typ, count, value in entries:
                payload = struct.pack("<HH", value, 0) if (typ == 3 and count == 1) \
                    else struct.pack("<I", value)
                fh.write(struct.pack("<HHI", tag, typ, count) + payload)
            next_field = fh.tell()
            fh.write(struct.pack("<I", 0))
            here = fh.tell()
            fh.seek(prev_next_field); fh.write(struct.pack("<I", ifd_pos)); fh.seek(here)
            prev_next_field = next_field


def expected_rowsums(frame_rows, bits, logical_width):
    """Reader flips Y, so file row r lands at height-1-r."""
    out = []
    for rows in frame_rows:
        for row in reversed(rows):
            if bits == 4:
                out.append(float(sum(row.translate(NIBBLE_SUM))))
            else:
                out.append(float(sum(struct.unpack("<%dH" % logical_width, row))))
    return out


def run_case(helper, name, frame_rows, bits, compression, rows_per_strip, logical_width, tmp):
    tiff = os.path.join(tmp, name + ".tif")
    dump = os.path.join(tmp, name + ".bin")
    write_tiff(tiff, frame_rows, bits, compression, rows_per_strip, logical_width)
    subprocess.run([helper, "read_tiff", tiff, dump], check=True)
    with open(dump, "rb") as fh:
        nx, ny, nn = struct.unpack("<qqq", fh.read(24))
        raw = fh.read()
    got = list(struct.unpack("<%dd" % (len(raw) // 8), raw))
    height = len(frame_rows[0])
    assert (nx, ny, nn) == (logical_width, height, len(frame_rows)), \
        "%s: dims %s != %s" % (name, (nx, ny, nn), (logical_width, height, len(frame_rows)))
    want = expected_rowsums(frame_rows, bits, logical_width)
    assert len(got) == len(want), "%s: %d row sums, expected %d" % (name, len(got), len(want))
    bad = [i for i, (a, b) in enumerate(zip(got, want)) if a != b]
    assert not bad, "%s: %d/%d row sums differ, first at row %d (%r != %r)" % (
        name, len(bad), len(want), bad[0], got[bad[0]], want[bad[0]])
    print("  %s: %d frame(s) %dx%d, %d row sums exact" % (name, nn, nx, ny, len(want)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", required=True)
    args = parser.parse_args()
    rng = random.Random(7)

    with tempfile.TemporaryDirectory() as tmp:
        # 16-bit, deflate, one row per strip: the tutorial movies' layout.
        w, h = 29, 37
        frames = [[rng.randbytes(w * 2) for _ in range(h)] for _ in range(3)]
        run_case(args.helper, "u16_deflate_rps1", frames, 16, 8, 1, w, tmp)

        # 16-bit, uncompressed, several rows per strip with a short final strip.
        w, h = 16, 50
        frames = [[rng.randbytes(w * 2) for _ in range(h)] for _ in range(2)]
        run_case(args.helper, "u16_raw_rps7", frames, 16, 1, 7, w, tmp)

        # IMOD packed 4-bit, recognised only at set geometries: 3710 bytes per
        # row is read as 7420 logical pixels, low nibble first.
        # Several rows per strip, not dividing the height, is required here: a
        # wrong row stride within a strip is multiplied by zero and stays
        # invisible when every strip holds exactly one row.
        file_w, h = 3710, 7676
        frames = [[rng.randbytes(file_w) for _ in range(h)]]
        run_case(args.helper, "packed4bit_k2sr", frames, 4, 1, 7, file_w * 2, tmp)

    print("TIFF read: all cases exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
