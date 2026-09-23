"""Recreate the deterministic 32-frame motion-correction comparison movie."""

import struct
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter


n = 1536
nframes = 32
rng = np.random.default_rng(314159)

texture = gaussian_filter(rng.standard_normal((n, n), dtype=np.float32), 2)
texture += 0.7 * gaussian_filter(
    rng.standard_normal((n, n), dtype=np.float32), 12
)
texture = (texture - texture.mean()) / texture.std()
base = (100 + 22 * texture).astype(np.float32)

header = bytearray(1024)
struct.pack_into("<4i", header, 0, n, n, nframes, 2)
struct.pack_into("<3i", header, 28, n, n, nframes)
struct.pack_into("<3f", header, 40, float(n), float(n), float(nframes))
struct.pack_into("<3f", header, 52, 90, 90, 90)
struct.pack_into("<3i", header, 64, 1, 2, 3)
header[208:212] = b"MAP "
header[212:216] = bytes((0x44, 0x41, 0, 0))

output = Path(__file__).with_name("large_movie.mrcs")
with output.open("wb") as stream:
    stream.write(header)
    for i in range(nframes):
        frame = np.roll(base, (round(-0.35 * i), round(0.55 * i)), axis=(0, 1))
        frame = frame + rng.normal(0, 2, frame.shape).astype(np.float32)
        frame.tofile(stream)

print(output, output.stat().st_size)
