#!/usr/bin/env python3
"""Report EER / TIFF geometry needed to fix --eer_grouping and the gain options.

EER files are TIFF containers with one IFD per raw detector frame, so the frame
count is obtained by walking the IFD chain -- no decode and no full read.  The
same walk reports the gain reference's dimensions and sample format.

This only reads headers.  It computes no endpoint and touches no arm output.

Usage:
    python3 tools/science_issue73/i73_eer_probe.py FILE [FILE ...]
"""

import json
import struct
import sys

# TIFF tags we care about.
TAG_WIDTH, TAG_HEIGHT, TAG_BITS, TAG_COMPRESSION, TAG_SAMPLEFMT = 256, 257, 258, 259, 339

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8,
             13: 4, 16: 8, 17: 8, 18: 8}


def walk(path, max_ifds=100000):
    """Walk the TIFF/BigTIFF IFD chain; return (frame_count, first-IFD tags)."""
    with open(path, "rb") as fh:
        head = fh.read(16)
        endian = "<" if head[:2] == b"II" else ">"
        magic = struct.unpack(endian + "H", head[2:4])[0]
        big = magic == 43
        if magic not in (42, 43):
            raise ValueError(f"{path}: not TIFF/BigTIFF (magic {magic})")

        if big:
            offsize, _, offset = struct.unpack(endian + "HHQ", head[4:16])
            if offsize != 8:
                raise ValueError(f"{path}: unsupported BigTIFF offset size {offsize}")
        else:
            offset = struct.unpack(endian + "I", head[4:8])[0]

        first_tags, count = {}, 0
        while offset and count < max_ifds:
            fh.seek(offset)
            if big:
                n = struct.unpack(endian + "Q", fh.read(8))[0]
                entry, esize = endian + "HHQQ", 20
            else:
                n = struct.unpack(endian + "H", fh.read(2))[0]
                entry, esize = endian + "HHII", 12
            raw = fh.read(n * esize)
            if count == 0:
                for i in range(n):
                    tag, typ, cnt, val = struct.unpack(entry, raw[i * esize:(i + 1) * esize])
                    if tag in (TAG_WIDTH, TAG_HEIGHT, TAG_BITS, TAG_COMPRESSION, TAG_SAMPLEFMT):
                        # Value fits inline when its total size <= the offset field.
                        inline = TYPE_SIZE.get(typ, 1) * cnt <= (8 if big else 4)
                        if inline and typ == 3 and not big:
                            val = val >> 16 if endian == ">" else val & 0xFFFF
                        elif inline and typ == 3 and big:
                            val = val & 0xFFFF
                        first_tags[tag] = val
            count += 1
            nxt = fh.read(8 if big else 4)
            if len(nxt) < (8 if big else 4):
                break
            offset = struct.unpack(endian + ("Q" if big else "I"), nxt)[0]
        return count, first_tags


def main() -> None:
    out = {}
    for path in sys.argv[1:]:
        try:
            n, tags = walk(path)
            out[path] = {
                "ifd_frames": n,
                "width": tags.get(TAG_WIDTH),
                "height": tags.get(TAG_HEIGHT),
                "bits_per_sample": tags.get(TAG_BITS),
                "compression": tags.get(TAG_COMPRESSION),
            }
        except Exception as exc:  # header-only probe: report, do not abort the batch
            out[path] = {"error": str(exc)}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
