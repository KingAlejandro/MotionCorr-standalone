# Falcon4 at `--eer_upsampling 2` (8192 x 8192 x 144 groups): prediction, written before the run

Fit to three NVML per-process peaks already measured on this build (GPU2, `--ingest auto`, config L,
c01 / c02 / c10 in `results.md`):

| case | frames x Mpx | movie as float (MiB) | NVML peak (MiB) |
|---|---|---:|---:|
| Falcon3 up1 | 58 x 16.78 | 3712 | 8738 |
| Falcon4 up1 | 144 x 16.78 | 9217 | 20446 |
| Falcon3 up2 | 58 x 67.11 | 14848 | 33694 |

Model VRAM = a * movie_float + b * frame_px + c. Falcon3 up1 vs Falcon4 up1 (same frame, different frame count) give
a = 2.127 (float movie plus the full-frame FFT copy); the up2 point then gives b and c (b * 16.78 Mpx = 423 MiB,
c = 419 MiB context and constants).

Falcon4 up2: movie_float = 144 x 67.11 Mpx x 4 B = 36864 MiB.
**Predicted device peak = 2.127 x 36864 + 4 x 423 + 419 = 80.5 GiB-ish, about 80 520 MiB**, against 81 920 MiB total on the A100 80GB.
That is inside the card by under 2 %, so an out-of-memory failure is likely and a pass would be marginal.

Host (RSS): compact = u16 staging + EER file buffer + ~0.3 GiB; float = float movie + file buffer + ~0.9 GiB (overheads from c10 and c02).
- staging u16: 144 x 67.11 Mpx x 2 B = 18432 MiB; EER file buffer 2795 MiB (2.93 GB file).
- **Predicted peak RSS: compact ~21.5 GiB (about 21 500 MiB), float ~40.5 GiB (about 40 500 MiB).** The host has 432 GB.

A fitting companion run (m2) uses `--last_frame_sum 100` (100 groups): movie_float = 25600 MiB,
predicted device peak 2.127 x 25600 + 1692 + 419 = ~56 560 MiB.
