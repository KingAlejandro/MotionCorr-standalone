# Input backends: census, routes, correctness and performance

Branch `experiment/input-backends-v2`, based on `main` at `c499b1d` (merged
#128). Not based on #133's ancestry: that PR rewrites the same CUDA session for
plan pooling, and keeping the input work off it is what lets the two be
reviewed apart.

## 0. Format census

Every variant is generated losslessly from the RELION tutorial movies by
`harness/gen_matrix.py` — one decode per source movie, every variant written
from the same in-memory sample array. The tutorial data is counting-mode: the
maximum sample over `20170629_00021` is **68**, so a uint8 re-encode is
value-lossless and the generator refuses it outright if any sample would not
fit. That is what makes "the same movie in another format must produce the same
products" an exact gate rather than an approximation.

Dimensions are read independently with `tifffile`, not inferred from the
filename. All variants: 3710 x 3838, 1 sample/pixel, contiguous planar,
little-endian native, `FillOrder` absent (MSB2LSB), 24 frames unless stated.

| variant | codec | sample | bits | predictor | rows/strip | strips/frame | frames | bytes (movie 00021) |
|---|---|---|---|---|---|---|---|---|
| `u16_deflate_rps1` *(the tutorial files, unmodified)* | Deflate | uint | 16 | 1 | 1 | 3838 | 24 | 126,550,106 |
| `u8_lzw_rps1` | LZW | uint | 8 | 1 | 1 | 3838 | 24 | 106,902,076 |
| `u8_lzw_rps64` | LZW | uint | 8 | 1 | 64 | 60 (last 2 rows) | 24 | 95,181,204 |
| `u8_deflate_rps1` | Deflate | uint | 8 | 1 | 1 | 3838 | 24 | 92,573,485 |
| `u8_deflate_rps16` | Deflate | uint | 8 | 1 | 16 | 240 (last 14 rows) | 24 | 92,629,682 |
| `u16_lzw_rps1` | LZW | uint | 16 | 1 | 1 | 3838 | 24 | 128,052,925 |
| `u16_deflate_rps2` | Deflate | uint | 16 | 1 | 2 | 1919 (exact) | 24 | 125,726,947 |
| `u16_deflate_rps8` | Deflate | uint | 16 | 1 | 8 | 480 (last 6 rows) | 24 | 123,795,665 |
| `u16_deflate_rps512` | Deflate | uint | 16 | 1 | 512 | 8 (last 254 rows) | 24 | 123,084,401 |
| `u16_deflate_pred2` | Deflate | uint | 16 | **2** | 1 | 3838 | 24 | 149,825,412 |
| `u16_raw_rps1` | none | uint | 16 | 1 | 1 | 3838 | 24 | 684,029,576 |
| `u16_deflate_rps1_48f` | Deflate | uint | 16 | 1 | 1 | 3838 | **48** | 255,681,005 |
| `u8_lzw_rps1_48f` | LZW | uint | 8 | 1 | 1 | 3838 | **48** | 213,804,156 |
| `u8_deflate_rps1_48f` | Deflate | uint | 8 | 1 | 1 | 3838 | **48** | 185,146,973 |

Two format classes are **out of scope and unchanged**: EER (rendered by
`renderEER`, never offered to either accelerated route) and compressed MRC
(`isCompressedMRC`, same). Nothing here was run on EER or MRC input and nothing
here claims anything about them.

The 48-frame variants are the 24 frames tiled twice. They exercise frame count,
the nvCOMP batch selector and the staging mapping; they are not a second
specimen and the per-frame content repeats.

### What a deposited uint8 LZW movie is, and is not, represented by

The deposited real-data files that motivated this work are LZW uint8. The
`u8_lzw_*` variants above hold **real cryo-EM counting-mode content at a real
detector geometry in exactly that encoding**, but they are re-encodes of the
tutorial collection, not the deposited files. Codec work, sample width, strip
geometry and frame count are faithful; the specimen, the detector and the
compression ratio a different collection would reach are not. No performance
figure here is a measurement of the deposited collection.
