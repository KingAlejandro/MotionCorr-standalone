import struct
from pathlib import Path

import numpy as np

nx = ny = 512
nframes = 16
rng = np.random.default_rng(20260923)
y, x = np.mgrid[:ny, :nx]
image = np.full((ny, nx), 100.0, dtype=np.float32)
for _ in range(150):
    cx, cy = rng.uniform(0, nx), rng.uniform(0, ny)
    width = rng.uniform(2, 9)
    amplitude = rng.uniform(10, 50)
    dx = (x - cx + nx / 2) % nx - nx / 2
    dy = (y - cy + ny / 2) % ny - ny / 2
    image += amplitude * np.exp(-(dx * dx + dy * dy) / (2 * width * width))

shifts = [(round(0.6 * i), round(-0.4 * i)) for i in range(nframes)]
stack = np.stack([
    np.roll(image, (dy, dx), axis=(0, 1)) + rng.normal(0, 2, image.shape)
    for dx, dy in shifts
]).astype('<f4')

header = bytearray(1024)
struct.pack_into('<4i', header, 0, nx, ny, nframes, 2)
struct.pack_into('<3i', header, 28, nx, ny, nframes)
struct.pack_into('<3f', header, 40, float(nx), float(ny), float(nframes))
struct.pack_into('<3f', header, 52, 90, 90, 90)
struct.pack_into('<3i', header, 64, 1, 2, 3)
struct.pack_into('<3f', header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
header[208:212] = b'MAP '
header[212:216] = bytes((0x44, 0x41, 0, 0))
struct.pack_into('<f', header, 216, float(stack.std()))

output = Path(__file__).with_name('synthetic_movie.mrcs')
with output.open('wb') as f:
    f.write(header)
    stack.tofile(f)
print(output, stack.shape, shifts)
