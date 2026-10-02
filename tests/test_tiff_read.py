#!/usr/bin/env python3
"""Check the TIFF reader against an independently computed expectation.

Covers the two layouts the reader treats differently: ordinary 16-bit samples
split over many strips, and IMOD's packed 4-bit extension, which is recognised
only at specific super-resolution geometries and stores two pixels per byte.
Both must come out Y-flipped relative to the file, matching the MRC convention.

Comparison is per-row sums, which are exact in double for integer samples and
relocate as a unit under any row-striding or flip error, plus the ordered
sample values themselves. Sums are blind to two pixels swapped inside one row,
and for packed 4-bit they are blind to the two samples in a byte coming out in
the wrong order, so only the values pin sample order. The large packed geometry
has 57 M samples, so there the value check covers a bounded number of rows.
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


def expected_row_samples(row, bits, logical_width):
    """One file row's decoded samples, in order."""
    if bits == 4:
        out = []
        for byte in row:
            out.append(float(byte & 0x0F))   # low nibble is the first pixel
            out.append(float((byte >> 4) & 0x0F))
        return out
    return [float(v) for v in struct.unpack("<%dH" % logical_width, row)]


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


def check_samples(helper, name, tiff, frame_rows, bits, logical_width, tmp, max_rows):
    """Exact ordered sample values, streamed a row at a time.

    max_rows bounds both what the helper writes and what is compared, counted
    over the whole stack in output order (frame-major, Y-flipped within a
    frame); None takes every row. The dump's length is asserted first, so a
    truncated dump cannot pass on the rows that happen to be present.
    """
    dump = os.path.join(tmp, name + ".raw")
    cmd = [helper, "read_tiff_raw", tiff, dump]
    height, n_frames = len(frame_rows[0]), len(frame_rows)
    want_rows = height * n_frames if max_rows is None else min(max_rows, height * n_frames)
    if max_rows is not None:
        cmd.append(str(max_rows))
    subprocess.run(cmd, check=True)
    checked = 0
    try:
        # A short dump must fail here rather than pass on the rows that survive.
        assert os.path.getsize(dump) == 24 + 4 * logical_width * want_rows, \
            "%s: raw dump is %d bytes, expected %d" % (
                name, os.path.getsize(dump), 24 + 4 * logical_width * want_rows)
        with open(dump, "rb") as fh:
            nx, ny, nn = struct.unpack("<qqq", fh.read(24))
            assert (nx, ny, nn) == (logical_width, height, n_frames), \
                "%s: raw dump dims %s" % (name, (nx, ny, nn))
            for rows in frame_rows:                 # rows arrive frame-major
                for row in reversed(rows):          # and the reader flips Y
                    if checked == want_rows:
                        return checked * nx
                    got = struct.unpack("<%df" % nx, fh.read(4 * nx))
                    want = expected_row_samples(row, bits, logical_width)
                    if list(got) != want:
                        i = next(k for k in range(nx) if got[k] != want[k])
                        raise AssertionError(
                            "%s: output row %d sample %d differs (%r != %r)" % (
                                name, checked, i, got[i], want[i]))
                    checked += 1
    finally:
        os.unlink(dump)
    return checked * nx


def run_case(helper, name, frame_rows, bits, compression, rows_per_strip, logical_width, tmp,
             max_sample_rows=None):
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
    n = check_samples(helper, name, tiff, frame_rows, bits, logical_width, tmp, max_sample_rows)
    print("  %s: %d frame(s) %dx%d, %d row sums and %d samples exact" % (
        name, nn, nx, ny, len(want), n))


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
        # 57 M samples in all; the value check covers the first 64 output rows,
        # which is what pins the within-byte nibble order that sums cannot see.
        run_case(args.helper, "packed4bit_k2sr", frames, 4, 1, 7, file_w * 2, tmp,
                 max_sample_rows=64)

    print("TIFF read: all cases exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
