#!/usr/bin/env python3
"""Re-encode an int16/uint16 MRC stack as Adobe Deflate uint16 TIFF, RowsPerStrip=1 (nvCOMP-eligible).
Same tag layout as tests/run_nvcomp_reconstruction_controls.py:write_deflate_tiff. usage: src.mrc dst.tiff"""
import struct, sys, zlib
import numpy as np
src, dst = sys.argv[1:3]
h = open(src, 'rb').read(1024)
nx, ny, nz, mode = struct.unpack('<4i', h[:16]); nsym = struct.unpack_from('<i', h, 92)[0]
assert mode in (1, 6), mode
a = np.memmap(src, dtype='<i2' if mode == 1 else '<u2', mode='r', offset=1024 + nsym, shape=(nz, ny, nx))
mn = int(a.min()); print('min', mn, 'max', int(a.max()))
# movie-1-only fixture: negative samples are clipped; it is used only as the failing movie
tags = 12; ifd = 2 + 12 * tags + 4; tab = ny * 8
cursor = 8 + nz * (ifd + tab)
comp = []
for z in range(nz):
    fr = np.clip(np.ascontiguousarray(a[z]), 0, None).astype("<u2")
    comp.append([zlib.compress(fr[y].tobytes(), 1) for y in range(ny)])
with open(dst, 'wb') as f:
    f.write(struct.pack('<2sHI', b'II', 42, 8))
    offs = []
    for rows in comp:
        o = []
        for r in rows:
            o.append(cursor); cursor += len(r)
        offs.append(o)
    tc = 8 + nz * ifd
    tables = bytearray()
    for i, rows in enumerate(comp):
        op = tc; tables += struct.pack('<%dI' % ny, *offs[i])
        cp = tc + ny * 4; tables += struct.pack('<%dI' % ny, *[len(r) for r in rows]); tc += tab
        vals = [(256, 4, 1, nx), (257, 4, 1, ny), (258, 3, 1, 16), (259, 3, 1, 8), (262, 3, 1, 1),
                (273, 4, ny, op), (277, 3, 1, 1), (278, 4, 1, 1), (279, 4, ny, cp), (284, 3, 1, 1),
                (317, 3, 1, 1), (339, 3, 1, 1)]
        f.write(struct.pack('<H', tags))
        for t, ty, c, v in vals:
            f.write(struct.pack('<HHII', t, ty, c, v))
        f.write(struct.pack('<I', 8 + (i + 1) * ifd if i + 1 < nz else 0))
    f.write(bytes(tables))
    for rows in comp:
        for r in rows:
            f.write(r)
print('wrote', dst)
