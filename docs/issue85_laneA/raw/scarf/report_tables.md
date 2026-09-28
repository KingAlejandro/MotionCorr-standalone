### Run identity

```
date_utc=2026-09-28T15:37:57Z
venue=SCARF Slurm, exclusive node, partition scarf, constraint scarf23
slurm_job_id=3512505
node=cn3121.scarf.rl.ac.uk
kernel=Linux 5.14.0-687.42.1.el9_8.x86_64 #1 SMP PREEMPT_DYNAMIC Wed Aug 26 12:55:43 UTC 2026 x86_64 GNU/Linux
nproc=64
cpu_model=AMD EPYC 7502P 32-Core Processor
numa=4
mem_total_kb=263444256 kB
source_revision=fbf1ccb6d1e691bf61381ea70128b7718d6a8517
source_dirty_files=0
bundle_sha256=a83351a09daeaea46ca2a028f2e7eaa2f6018d83739e399f02451cc137e8555b
bench_sha256=65710a1b7582bb11a232991b53f598347b37fe99f0b9cd4995ed6b9e3d8945c9
cmake=cmake version 3.31.8
gcc=gcc (GCC) 11.5.0 20240719 (Red Hat 11.5.0-14)
libtiff_soname=/usr/lib64/libtiff.so.5
fftw=3.3.8
panfs_mount=panfs://130.246.139.193/scarf/work4/scd panfs 781250000000 520106708032 261143291968      67% /work4/scd
local_scratch=/dev/sda8      xfs    829108692 5409392 823699300       1% /tmp
omp_proc_bind=<unset, matches production>
exclusive=yes (--exclusive), so no interference witness is needed
```


### Comparator controls

**Oracle sensitivity** (mutation applied to the reference buffer)

| mutation class     | exact ordered | global sum | ordered row sums | pixels differing |
|--------------------|---------------|------------|------------------|------------------|
| value_1ulp         | detects       | detects    | detects          | 1                |
| swap_pixels_in_row | detects       | BLIND      | BLIND            | 2                |
| swap_rows_in_frame | detects       | BLIND      | detects          | 5132             |
| yflip_one_frame    | detects       | BLIND      | detects          | 9725650          |
| swap_two_frames    | detects       | BLIND      | detects          | 19402214         |

**Live fault injection** into the real output of `production_image_read`. The uninjected row must pass and every injected row must fail, or the gate is not falsifiable.

| injected fault     | exact-gate verdict | pixels differing |
|--------------------|--------------------|------------------|
| none               | pass               | 0                |
| swap_pixels_in_row | FAIL (correct)     | 2                |
| swap_rows_in_frame | FAIL (correct)     | 5132             |
| swap_two_frames    | FAIL (correct)     | 19402214         |
| value_1ulp         | FAIL (correct)     | 1                |
| yflip_one_frame    | FAIL (correct)     | 9725650          |


### Node-local /tmp (xfs), warm, representative movie

Source: `local_warm_rep.json`  ·  regime `warm`  ·  mask `0-63` (64 vCPU)  ·  median of 3 per movie  ·  1 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=1   | W=2   | W=4   | W=8   | W=16  | W=24  | W=32  | W=48  | W=64  | fastest |
|--------------------------------|-------|-------|-------|-------|-------|-------|-------|-------|-------|---------|
| pread_whole_file               | 0.015 | 0.013 | 0.013 | 0.013 | 0.013 | 0.014 | 0.015 | 0.013 | 0.014 | W=2     |
| pread_strip_extents            | 0.068 | 0.041 | 0.021 | 0.012 | 0.012 | 0.008 | 0.008 | 0.007 | 0.022 | W=48    |
| tiff_dirscan_persistent        | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | W=2     |
| tiff_open_per_frame_meta       | 0.006 | 0.004 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | W=16    |
| tiff_read_raw_strip            | 0.027 | 0.017 | 0.013 | 0.011 | 0.010 | 0.010 | 0.010 | 0.010 | 0.016 | W=32    |
| tiff_decode_only               | 1.903 | 0.954 | 0.482 | 0.245 | 0.190 | 0.111 | 0.088 | 0.103 | 0.103 | W=32    |
| decode_place_u16_natural       | 1.947 | 0.978 | 0.497 | 0.255 | 0.197 | 0.117 | 0.094 | 0.095 | 0.096 | W=32    |
| persistent_handle_to_u16       | 1.959 | 0.984 | 0.498 | 0.257 | 0.198 | 0.116 | 0.118 | 0.095 | 0.121 | W=48    |
| persistent_handle_to_f32       | 2.013 | 1.012 | 0.513 | 0.265 | 0.205 | 0.097 | 0.121 | 0.123 | 0.124 | W=24    |
| openperframe_handle_to_f32     | 2.019 | 1.013 | 0.510 | 0.263 | 0.197 | 0.095 | 0.096 | 0.100 | 0.114 | W=24    |
| strip_batch_to_f32_b64         | 2.013 | 1.018 | 0.519 | 0.271 | 0.149 | 0.107 | 0.090 | 0.077 | 0.084 | W=48    |
| strip_batch_to_f32_b256        | 2.011 | 1.014 | 0.515 | 0.269 | 0.149 | 0.103 | 0.087 | 0.073 | 0.068 | W=64    |
| convert_u16_to_f32_resident    | 0.110 | 0.093 | 0.060 | 0.059 | 0.062 | 0.063 | 0.066 | 0.046 | 0.056 | W=48    |
| alloc_first_touch_f32          | 0.138 | 0.095 | 0.050 | 0.036 | 0.045 | 0.029 | 0.033 | 0.034 | 0.065 | W=24    |
| alloc_first_touch_f32_malloc   | 0.138 | 0.095 | 0.050 | 0.036 | 0.041 | 0.026 | 0.033 | 0.034 | 0.061 | W=24    |
| alloc_first_touch_f32_perframe | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.001 | 0.001 | 0.001 | 0.011 | W=1     |
| alloc_first_touch_u16          | 0.069 | 0.047 | 0.025 | 0.018 | 0.020 | 0.014 | 0.017 | 0.017 | 0.037 | W=24    |
| production_image_read          | 2.073 | 1.039 | 0.524 | 0.268 | 0.181 | 0.097 | 0.098 | 0.097 | 0.124 | W=24    |
| production_image_read_prealloc | 2.022 | 1.016 | 0.514 | 0.264 | 0.177 | 0.096 | 0.095 | 0.111 | 0.113 | W=32    |
| omp_dispatch_only              | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.012 | W=16    |

**Attribution chain at W=1 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.027        | +0.027 | +1.3%          |
| + Deflate decompression                                                     | 1.903        | +1.876 | +90.5%         |
| + write decoded rows to destination                                         | 1.947        | +0.044 | +2.1%          |
| + Y-flipped placement                                                       | 1.959        | +0.012 | +0.6%          |
| + uint16 to float conversion                                                | 2.013        | +0.054 | +2.6%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 2.073        | +0.060 | +2.9%          |

**Attribution chain at W=2 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.017        | +0.017 | +1.7%          |
| + Deflate decompression                                                     | 0.954        | +0.937 | +90.2%         |
| + write decoded rows to destination                                         | 0.978        | +0.024 | +2.3%          |
| + Y-flipped placement                                                       | 0.984        | +0.005 | +0.5%          |
| + uint16 to float conversion                                                | 1.012        | +0.028 | +2.7%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 1.039        | +0.027 | +2.6%          |

**Attribution chain at W=4 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.013        | +0.013 | +2.5%          |
| + Deflate decompression                                                     | 0.482        | +0.469 | +89.5%         |
| + write decoded rows to destination                                         | 0.497        | +0.015 | +2.8%          |
| + Y-flipped placement                                                       | 0.498        | +0.002 | +0.3%          |
| + uint16 to float conversion                                                | 0.513        | +0.015 | +2.8%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.524        | +0.011 | +2.1%          |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.011        | +0.011 | +4.1%          |
| + Deflate decompression                                                     | 0.245        | +0.234 | +87.2%         |
| + write decoded rows to destination                                         | 0.255        | +0.010 | +3.7%          |
| + Y-flipped placement                                                       | 0.257        | +0.002 | +0.7%          |
| + uint16 to float conversion                                                | 0.265        | +0.008 | +3.2%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.268        | +0.003 | +1.1%          |

**Attribution chain at W=16 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.010        | +0.010 | +5.6%          |
| + Deflate decompression                                                     | 0.190        | +0.180 | +99.0%         |
| + write decoded rows to destination                                         | 0.197        | +0.007 | +3.7%          |
| + Y-flipped placement                                                       | 0.198        | +0.001 | +0.6%          |
| + uint16 to float conversion                                                | 0.205        | +0.007 | +3.8%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.181        | -0.023 | -12.8%         |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.010        | +0.010 | +10.0%         |
| + Deflate decompression                                                     | 0.111        | +0.101 | +104.3%        |
| + write decoded rows to destination                                         | 0.117        | +0.006 | +5.9%          |
| + Y-flipped placement                                                       | 0.116        | -0.001 | -0.6%          |
| + uint16 to float conversion                                                | 0.097        | -0.019 | -19.7%         |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.097        | +0.000 | +0.1%          |

**Attribution chain at W=32 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.010        | +0.010 | +9.9%          |
| + Deflate decompression                                                     | 0.088        | +0.078 | +79.8%         |
| + write decoded rows to destination                                         | 0.094        | +0.006 | +5.9%          |
| + Y-flipped placement                                                       | 0.118        | +0.024 | +25.0%         |
| + uint16 to float conversion                                                | 0.121        | +0.003 | +2.8%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.098        | -0.023 | -23.3%         |

**Attribution chain at W=48 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.010        | +0.010 | +10.7%         |
| + Deflate decompression                                                     | 0.103        | +0.093 | +95.2%         |
| + write decoded rows to destination                                         | 0.095        | -0.008 | -8.5%          |
| + Y-flipped placement                                                       | 0.095        | +0.000 | +0.2%          |
| + uint16 to float conversion                                                | 0.123        | +0.028 | +28.7%         |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.097        | -0.026 | -26.2%         |

**Attribution chain at W=64 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.016        | +0.016 | +12.6%         |
| + Deflate decompression                                                     | 0.103        | +0.087 | +70.2%         |
| + write decoded rows to destination                                         | 0.096        | -0.006 | -4.9%          |
| + Y-flipped placement                                                       | 0.121        | +0.025 | +20.0%         |
| + uint16 to float conversion                                                | 0.124        | +0.002 | +1.9%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.124        | +0.000 | +0.3%          |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=1     | 2.0127 | 2.0192 | +0.3%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=2     | 1.0117 | 1.0130 | +0.1%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=4     | 0.5128 | 0.5103 | -0.5%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 0.2652 | 0.2632 | -0.8%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=16    | 0.2046 | 0.1967 | -3.9%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 0.0971 | 0.0950 | -2.2%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=32    | 0.1207 | 0.0957 | -20.7% | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=48    | 0.1230 | 0.1001 | -18.6% | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=64    | 0.1235 | 0.1145 | -7.3%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=1     | 2.0127 | 2.0132 | +0.0%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=2     | 1.0117 | 1.0182 | +0.6%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=4     | 0.5128 | 0.5189 | +1.2%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 0.2652 | 0.2708 | +2.1%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=16    | 0.2046 | 0.1493 | -27.0% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 0.0971 | 0.1071 | +10.3% | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=32    | 0.1207 | 0.0900 | -25.5% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=48    | 0.1230 | 0.0773 | -37.2% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=64    | 0.1235 | 0.0842 | -31.8% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=1     | 2.0127 | 2.0114 | -0.1%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=2     | 1.0117 | 1.0143 | +0.3%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=4     | 0.5128 | 0.5152 | +0.5%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 0.2652 | 0.2686 | +1.3%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=16    | 0.2046 | 0.1488 | -27.3% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 0.0971 | 0.1029 | +6.0%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=32    | 0.1207 | 0.0872 | -27.8% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=48    | 0.1230 | 0.0730 | -40.6% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=64    | 0.1235 | 0.0683 | -44.7% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=1     | 0.1382 | 0.0694 | -49.8% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=2     | 0.0946 | 0.0471 | -50.3% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=4     | 0.0499 | 0.0250 | -49.8% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.0359 | 0.0180 | -49.8% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=16    | 0.0449 | 0.0205 | -54.4% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.0295 | 0.0135 | -54.1% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=32    | 0.0334 | 0.0166 | -50.5% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=48    | 0.0340 | 0.0173 | -49.1% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=64    | 0.0650 | 0.0372 | -42.7% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                            | verdict |
|--------------------------------|---------|
| decode_place_u16_natural       | PASS    |
| openperframe_handle_to_f32     | PASS    |
| persistent_handle_to_f32       | PASS    |
| persistent_handle_to_u16       | PASS    |
| production_image_read          | PASS    |
| production_image_read_prealloc | PASS    |
| strip_batch_to_f32_b256        | PASS    |
| strip_batch_to_f32_b64         | PASS    |

**Parallel efficiency vs W=1** (speedup / workers; 100% would be linear)

| arm                            | W=1  | W=2  | W=4 | W=8 | W=16 | W=24 | W=32 | W=48 | W=64 |
|--------------------------------|------|------|-----|-----|------|------|------|------|------|
| pread_whole_file               | 100% | 58%  | 29% | 14% | 7%   | 4%   | 3%   | 2%   | 2%   |
| pread_strip_extents            | 100% | 83%  | 81% | 68% | 36%  | 36%  | 26%  | 20%  | 5%   |
| tiff_dirscan_persistent        | 100% | 50%  | 25% | 12% | 5%   | 4%   | 3%   | 2%   | 1%   |
| tiff_open_per_frame_meta       | 100% | 65%  | 44% | 25% | 13%  | 8%   | 6%   | 4%   | 3%   |
| tiff_read_raw_strip            | 100% | 77%  | 52% | 31% | 17%  | 12%  | 9%   | 5%   | 3%   |
| tiff_decode_only               | 100% | 100% | 99% | 97% | 63%  | 71%  | 68%  | 38%  | 29%  |
| decode_place_u16_natural       | 100% | 99%  | 98% | 95% | 62%  | 69%  | 65%  | 43%  | 32%  |
| persistent_handle_to_u16       | 100% | 100% | 98% | 95% | 62%  | 70%  | 52%  | 43%  | 25%  |
| persistent_handle_to_f32       | 100% | 99%  | 98% | 95% | 61%  | 86%  | 52%  | 34%  | 25%  |
| openperframe_handle_to_f32     | 100% | 100% | 99% | 96% | 64%  | 89%  | 66%  | 42%  | 28%  |
| strip_batch_to_f32_b64         | 100% | 99%  | 97% | 93% | 84%  | 78%  | 70%  | 54%  | 37%  |
| strip_batch_to_f32_b256        | 100% | 99%  | 98% | 94% | 84%  | 81%  | 72%  | 57%  | 46%  |
| convert_u16_to_f32_resident    | 100% | 59%  | 46% | 23% | 11%  | 7%   | 5%   | 5%   | 3%   |
| alloc_first_touch_f32          | 100% | 73%  | 69% | 48% | 19%  | 20%  | 13%  | 8%   | 3%   |
| alloc_first_touch_f32_malloc   | 100% | 73%  | 70% | 48% | 21%  | 22%  | 13%  | 9%   | 4%   |
| alloc_first_touch_f32_perframe | 100% | 39%  | 21% | 8%  | 3%   | 1%   | 1%   | 0%   | 0%   |
| alloc_first_touch_u16          | 100% | 74%  | 69% | 48% | 21%  | 21%  | 13%  | 8%   | 3%   |
| production_image_read          | 100% | 100% | 99% | 97% | 71%  | 89%  | 66%  | 44%  | 26%  |
| production_image_read_prealloc | 100% | 100% | 98% | 96% | 71%  | 88%  | 67%  | 38%  | 28%  |
| omp_dispatch_only              | 100% | 50%  | 41% | 29% | 15%  | 9%   | 5%   | 3%   | 0%   |


### PanFS, cold-requested (fadvise DONTNEED), ALL 24 movies

Source: `panfs_cold_all24.json`  ·  regime `cold`  ·  mask `0-63` (64 vCPU)  ·  median of 3 per movie  ·  24 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=8    | W=24   | fastest |
|--------------------------------|--------|--------|---------|
| pread_whole_file               | 1.914  | 1.781  | W=24    |
| pread_strip_extents            | 39.907 | 13.112 | W=24    |
| tiff_dirscan_persistent        | 0.680  | 0.683  | W=8     |
| tiff_open_per_frame_meta       | 0.524  | 0.698  | W=8     |
| tiff_read_raw_strip            | 1.856  | 1.555  | W=24    |
| tiff_decode_only               | 7.294  | 3.329  | W=24    |
| decode_place_u16_natural       | 7.510  | 3.387  | W=24    |
| persistent_handle_to_u16       | 7.532  | 3.419  | W=24    |
| persistent_handle_to_f32       | 7.761  | 3.556  | W=24    |
| openperframe_handle_to_f32     | 7.628  | 3.347  | W=24    |
| strip_batch_to_f32_b64         | 7.856  | 3.541  | W=24    |
| strip_batch_to_f32_b256        | 7.593  | 3.179  | W=24    |
| convert_u16_to_f32_resident    | 1.691  | 1.649  | W=24    |
| alloc_first_touch_f32          | 0.842  | 0.806  | W=24    |
| alloc_first_touch_f32_malloc   | 0.840  | 0.766  | W=24    |
| alloc_first_touch_f32_perframe | 0.008  | 0.017  | W=8     |
| alloc_first_touch_u16          | 0.425  | 0.390  | W=24    |
| production_image_read          | 7.863  | 3.597  | W=24    |
| production_image_read_prealloc | 7.711  | 3.515  | W=24    |
| omp_dispatch_only              | 0.000  | 0.000  | W=24    |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 1.856        | +1.856 | +23.6%         |
| + Deflate decompression                                                     | 7.294        | +5.439 | +69.2%         |
| + write decoded rows to destination                                         | 7.510        | +0.215 | +2.7%          |
| + Y-flipped placement                                                       | 7.532        | +0.022 | +0.3%          |
| + uint16 to float conversion                                                | 7.761        | +0.229 | +2.9%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 7.863        | +0.102 | +1.3%          |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 1.555        | +1.555 | +43.2%         |
| + Deflate decompression                                                     | 3.329        | +1.773 | +49.3%         |
| + write decoded rows to destination                                         | 3.387        | +0.058 | +1.6%          |
| + Y-flipped placement                                                       | 3.419        | +0.032 | +0.9%          |
| + uint16 to float conversion                                                | 3.556        | +0.137 | +3.8%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 3.597        | +0.041 | +1.1%          |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 7.7612 | 7.6279 | -1.7%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 3.5560 | 3.3471 | -5.9%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 7.7612 | 7.8557 | +1.2%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 3.5560 | 3.5411 | -0.4%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 7.7612 | 7.5929 | -2.2%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 3.5560 | 3.1788 | -10.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.8418 | 0.4250 | -49.5% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.8057 | 0.3904 | -51.5% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                            | verdict |
|--------------------------------|---------|
| decode_place_u16_natural       | PASS    |
| openperframe_handle_to_f32     | PASS    |
| persistent_handle_to_f32       | PASS    |
| persistent_handle_to_u16       | PASS    |
| production_image_read          | PASS    |
| production_image_read_prealloc | PASS    |
| strip_batch_to_f32_b256        | PASS    |
| strip_batch_to_f32_b64         | PASS    |


### PanFS (shared storage), warm, ALL 24 movies

Source: `panfs_warm_all24.json`  ·  regime `warm`  ·  mask `0-63` (64 vCPU)  ·  median of 3 per movie  ·  24 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=8    | W=24   | W=64   | fastest |
|--------------------------------|--------|--------|--------|---------|
| pread_whole_file               | 0.723  | 0.735  | 0.733  | W=8     |
| pread_strip_extents            | 12.055 | 11.810 | 12.076 | W=24    |
| tiff_dirscan_persistent        | 0.026  | 0.026  | 0.029  | W=24    |
| tiff_open_per_frame_meta       | 0.069  | 0.075  | 0.136  | W=8     |
| tiff_read_raw_strip            | 1.039  | 1.039  | 1.246  | W=24    |
| tiff_decode_only               | 6.291  | 2.349  | 2.981  | W=24    |
| decode_place_u16_natural       | 6.482  | 2.379  | 2.980  | W=24    |
| persistent_handle_to_u16       | 6.508  | 2.406  | 2.905  | W=24    |
| persistent_handle_to_f32       | 6.744  | 2.717  | 3.118  | W=24    |
| openperframe_handle_to_f32     | 6.720  | 2.588  | 2.883  | W=24    |
| strip_batch_to_f32_b64         | 6.800  | 2.667  | 2.129  | W=64    |
| strip_batch_to_f32_b256        | 6.767  | 2.626  | 2.002  | W=64    |
| convert_u16_to_f32_resident    | 1.799  | 1.715  | 1.813  | W=24    |
| alloc_first_touch_f32          | 0.843  | 0.734  | 1.054  | W=24    |
| alloc_first_touch_f32_malloc   | 0.832  | 0.720  | 1.029  | W=24    |
| alloc_first_touch_f32_perframe | 0.009  | 0.016  | 0.123  | W=8     |
| alloc_first_touch_u16          | 0.426  | 0.366  | 0.558  | W=24    |
| production_image_read          | 6.818  | 2.465  | 3.002  | W=24    |
| production_image_read_prealloc | 6.679  | 2.412  | 2.846  | W=24    |
| omp_dispatch_only              | 0.000  | 0.000  | 0.085  | W=8     |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 1.039        | +1.039 | +15.2%         |
| + Deflate decompression                                                     | 6.291        | +5.252 | +77.0%         |
| + write decoded rows to destination                                         | 6.482        | +0.191 | +2.8%          |
| + Y-flipped placement                                                       | 6.508        | +0.026 | +0.4%          |
| + uint16 to float conversion                                                | 6.744        | +0.236 | +3.5%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 6.818        | +0.074 | +1.1%          |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 1.039        | +1.039 | +42.1%         |
| + Deflate decompression                                                     | 2.349        | +1.310 | +53.1%         |
| + write decoded rows to destination                                         | 2.379        | +0.030 | +1.2%          |
| + Y-flipped placement                                                       | 2.406        | +0.027 | +1.1%          |
| + uint16 to float conversion                                                | 2.717        | +0.311 | +12.6%         |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 2.465        | -0.252 | -10.2%         |

**Attribution chain at W=64 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 1.246        | +1.246 | +41.5%         |
| + Deflate decompression                                                     | 2.981        | +1.735 | +57.8%         |
| + write decoded rows to destination                                         | 2.980        | -0.002 | -0.1%          |
| + Y-flipped placement                                                       | 2.905        | -0.075 | -2.5%          |
| + uint16 to float conversion                                                | 3.118        | +0.213 | +7.1%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 3.002        | -0.116 | -3.9%          |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 6.7443 | 6.7199 | -0.4%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 2.7170 | 2.5879 | -4.7%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=64    | 3.1182 | 2.8833 | -7.5%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 6.7443 | 6.8001 | +0.8%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 2.7170 | 2.6673 | -1.8%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=64    | 3.1182 | 2.1286 | -31.7% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 6.7443 | 6.7673 | +0.3%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 2.7170 | 2.6262 | -3.3%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=64    | 3.1182 | 2.0023 | -35.8% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.8425 | 0.4262 | -49.4% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.7344 | 0.3658 | -50.2% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=64    | 1.0541 | 0.5581 | -47.1% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                            | verdict |
|--------------------------------|---------|
| decode_place_u16_natural       | PASS    |
| openperframe_handle_to_f32     | PASS    |
| persistent_handle_to_f32       | PASS    |
| persistent_handle_to_u16       | PASS    |
| production_image_read          | PASS    |
| production_image_read_prealloc | PASS    |
| strip_batch_to_f32_b256        | PASS    |
| strip_batch_to_f32_b64         | PASS    |


### PanFS (shared storage), warm, representative movie

Source: `panfs_warm_rep.json`  ·  regime `warm`  ·  mask `0-63` (64 vCPU)  ·  median of 3 per movie  ·  1 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=1   | W=2   | W=4   | W=8   | W=16  | W=24  | W=32  | W=48  | W=64  | fastest |
|--------------------------------|-------|-------|-------|-------|-------|-------|-------|-------|-------|---------|
| pread_whole_file               | 0.031 | 0.032 | 0.032 | 0.032 | 0.032 | 0.032 | 0.031 | 0.032 | 0.031 | W=32    |
| pread_strip_extents            | 0.563 | 0.554 | 0.492 | 0.503 | 0.491 | 0.494 | 0.489 | 0.496 | 0.498 | W=32    |
| tiff_dirscan_persistent        | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | W=1     |
| tiff_open_per_frame_meta       | 0.005 | 0.004 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.003 | 0.004 | W=8     |
| tiff_read_raw_strip            | 0.095 | 0.065 | 0.046 | 0.039 | 0.041 | 0.042 | 0.043 | 0.044 | 0.046 | W=8     |
| tiff_decode_only               | 1.972 | 0.999 | 0.503 | 0.255 | 0.173 | 0.091 | 0.092 | 0.094 | 0.123 | W=24    |
| decode_place_u16_natural       | 2.017 | 1.022 | 0.518 | 0.265 | 0.180 | 0.096 | 0.097 | 0.099 | 0.123 | W=24    |
| persistent_handle_to_u16       | 2.026 | 1.026 | 0.520 | 0.266 | 0.180 | 0.121 | 0.098 | 0.100 | 0.116 | W=32    |
| persistent_handle_to_f32       | 2.085 | 1.056 | 0.534 | 0.277 | 0.189 | 0.127 | 0.102 | 0.104 | 0.131 | W=32    |
| openperframe_handle_to_f32     | 2.092 | 1.058 | 0.535 | 0.276 | 0.187 | 0.123 | 0.099 | 0.104 | 0.127 | W=32    |
| strip_batch_to_f32_b64         | 2.085 | 1.059 | 0.537 | 0.280 | 0.149 | 0.111 | 0.091 | 0.080 | 0.080 | W=48    |
| strip_batch_to_f32_b256        | 2.086 | 1.058 | 0.536 | 0.277 | 0.150 | 0.111 | 0.089 | 0.077 | 0.074 | W=64    |
| convert_u16_to_f32_resident    | 0.108 | 0.093 | 0.077 | 0.076 | 0.074 | 0.071 | 0.060 | 0.062 | 0.058 | W=64    |
| alloc_first_touch_f32          | 0.138 | 0.094 | 0.050 | 0.036 | 0.029 | 0.042 | 0.041 | 0.050 | 0.047 | W=16    |
| alloc_first_touch_f32_malloc   | 0.139 | 0.095 | 0.050 | 0.036 | 0.029 | 0.038 | 0.038 | 0.043 | 0.051 | W=16    |
| alloc_first_touch_f32_perframe | 0.000 | 0.002 | 0.000 | 0.000 | 0.000 | 0.001 | 0.001 | 0.001 | 0.001 | W=1     |
| alloc_first_touch_u16          | 0.070 | 0.048 | 0.025 | 0.018 | 0.015 | 0.020 | 0.020 | 0.021 | 0.026 | W=16    |
| production_image_read          | 2.152 | 1.087 | 0.547 | 0.281 | 0.189 | 0.112 | 0.125 | 0.127 | 0.127 | W=24    |
| production_image_read_prealloc | 2.095 | 1.061 | 0.533 | 0.274 | 0.185 | 0.098 | 0.098 | 0.122 | 0.122 | W=24    |
| omp_dispatch_only              | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | W=24    |

**Attribution chain at W=1 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.095        | +0.095 | +4.4%          |
| + Deflate decompression                                                     | 1.972        | +1.877 | +87.2%         |
| + write decoded rows to destination                                         | 2.017        | +0.045 | +2.1%          |
| + Y-flipped placement                                                       | 2.026        | +0.009 | +0.4%          |
| + uint16 to float conversion                                                | 2.085        | +0.059 | +2.8%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 2.152        | +0.067 | +3.1%          |

**Attribution chain at W=2 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.065        | +0.065 | +6.0%          |
| + Deflate decompression                                                     | 0.999        | +0.933 | +85.9%         |
| + write decoded rows to destination                                         | 1.022        | +0.024 | +2.2%          |
| + Y-flipped placement                                                       | 1.026        | +0.004 | +0.4%          |
| + uint16 to float conversion                                                | 1.056        | +0.030 | +2.7%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 1.087        | +0.031 | +2.8%          |

**Attribution chain at W=4 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.046        | +0.046 | +8.5%          |
| + Deflate decompression                                                     | 0.503        | +0.457 | +83.5%         |
| + write decoded rows to destination                                         | 0.518        | +0.015 | +2.7%          |
| + Y-flipped placement                                                       | 0.520        | +0.002 | +0.3%          |
| + uint16 to float conversion                                                | 0.534        | +0.015 | +2.7%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.547        | +0.013 | +2.3%          |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.039        | +0.039 | +14.0%         |
| + Deflate decompression                                                     | 0.255        | +0.216 | +77.0%         |
| + write decoded rows to destination                                         | 0.265        | +0.010 | +3.4%          |
| + Y-flipped placement                                                       | 0.266        | +0.001 | +0.5%          |
| + uint16 to float conversion                                                | 0.277        | +0.010 | +3.6%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.281        | +0.004 | +1.5%          |

**Attribution chain at W=16 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.041        | +0.041 | +21.9%         |
| + Deflate decompression                                                     | 0.173        | +0.132 | +69.9%         |
| + write decoded rows to destination                                         | 0.180        | +0.007 | +3.6%          |
| + Y-flipped placement                                                       | 0.180        | +0.000 | +0.2%          |
| + uint16 to float conversion                                                | 0.189        | +0.009 | +4.6%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.189        | -0.000 | -0.1%          |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.042        | +0.042 | +37.1%         |
| + Deflate decompression                                                     | 0.091        | +0.050 | +44.1%         |
| + write decoded rows to destination                                         | 0.096        | +0.005 | +4.5%          |
| + Y-flipped placement                                                       | 0.121        | +0.025 | +22.4%         |
| + uint16 to float conversion                                                | 0.127        | +0.006 | +5.0%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.112        | -0.015 | -13.1%         |

**Attribution chain at W=32 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.043        | +0.043 | +34.3%         |
| + Deflate decompression                                                     | 0.092        | +0.049 | +39.7%         |
| + write decoded rows to destination                                         | 0.097        | +0.005 | +4.1%          |
| + Y-flipped placement                                                       | 0.098        | +0.001 | +0.9%          |
| + uint16 to float conversion                                                | 0.102        | +0.003 | +2.6%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.125        | +0.023 | +18.4%         |

**Attribution chain at W=48 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.044        | +0.044 | +34.4%         |
| + Deflate decompression                                                     | 0.094        | +0.050 | +39.4%         |
| + write decoded rows to destination                                         | 0.099        | +0.005 | +4.2%          |
| + Y-flipped placement                                                       | 0.100        | +0.001 | +0.5%          |
| + uint16 to float conversion                                                | 0.104        | +0.004 | +3.4%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.127        | +0.023 | +18.0%         |

**Attribution chain at W=64 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.046        | +0.046 | +36.0%         |
| + Deflate decompression                                                     | 0.123        | +0.077 | +60.5%         |
| + write decoded rows to destination                                         | 0.123        | +0.000 | +0.3%          |
| + Y-flipped placement                                                       | 0.116        | -0.007 | -5.5%          |
| + uint16 to float conversion                                                | 0.131        | +0.015 | +12.2%         |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.127        | -0.004 | -3.5%          |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=1     | 2.0851 | 2.0917 | +0.3%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=2     | 1.0561 | 1.0581 | +0.2%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=4     | 0.5343 | 0.5346 | +0.1%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 0.2766 | 0.2758 | -0.3%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=16    | 0.1890 | 0.1872 | -0.9%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 0.1270 | 0.1228 | -3.3%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=32    | 0.1016 | 0.0989 | -2.6%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=48    | 0.1040 | 0.1041 | +0.2%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=64    | 0.1314 | 0.1266 | -3.7%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=1     | 2.0851 | 2.0847 | -0.0%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=2     | 1.0561 | 1.0594 | +0.3%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=4     | 0.5343 | 0.5370 | +0.5%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 0.2766 | 0.2798 | +1.2%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=16    | 0.1890 | 0.1495 | -20.9% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 0.1270 | 0.1113 | -12.4% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=32    | 0.1016 | 0.0913 | -10.2% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=48    | 0.1040 | 0.0801 | -22.9% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=64    | 0.1314 | 0.0803 | -38.9% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=1     | 2.0851 | 2.0859 | +0.0%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=2     | 1.0561 | 1.0582 | +0.2%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=4     | 0.5343 | 0.5361 | +0.3%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 0.2766 | 0.2770 | +0.2%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=16    | 0.1890 | 0.1504 | -20.4% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 0.1270 | 0.1114 | -12.3% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=32    | 0.1016 | 0.0890 | -12.4% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=48    | 0.1040 | 0.0773 | -25.7% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=64    | 0.1314 | 0.0741 | -43.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=1     | 0.1384 | 0.0696 | -49.7% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=2     | 0.0945 | 0.0476 | -49.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=4     | 0.0498 | 0.0253 | -49.2% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.0361 | 0.0179 | -50.5% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=16    | 0.0294 | 0.0148 | -49.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.0421 | 0.0201 | -52.4% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=32    | 0.0412 | 0.0197 | -52.3% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=48    | 0.0501 | 0.0207 | -58.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=64    | 0.0467 | 0.0258 | -44.8% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                            | verdict |
|--------------------------------|---------|
| decode_place_u16_natural       | PASS    |
| openperframe_handle_to_f32     | PASS    |
| persistent_handle_to_f32       | PASS    |
| persistent_handle_to_u16       | PASS    |
| production_image_read          | PASS    |
| production_image_read_prealloc | PASS    |
| strip_batch_to_f32_b256        | PASS    |
| strip_batch_to_f32_b64         | PASS    |

**Parallel efficiency vs W=1** (speedup / workers; 100% would be linear)

| arm                            | W=1  | W=2 | W=4 | W=8 | W=16 | W=24 | W=32 | W=48 | W=64 |
|--------------------------------|------|-----|-----|-----|------|------|------|------|------|
| pread_whole_file               | 100% | 50% | 24% | 12% | 6%   | 4%   | 3%   | 2%   | 2%   |
| pread_strip_extents            | 100% | 51% | 29% | 14% | 7%   | 5%   | 4%   | 2%   | 2%   |
| tiff_dirscan_persistent        | 100% | 50% | 25% | 12% | 6%   | 4%   | 3%   | 2%   | 1%   |
| tiff_open_per_frame_meta       | 100% | 74% | 46% | 24% | 11%  | 7%   | 5%   | 3%   | 2%   |
| tiff_read_raw_strip            | 100% | 73% | 51% | 30% | 14%  | 9%   | 7%   | 5%   | 3%   |
| tiff_decode_only               | 100% | 99% | 98% | 96% | 71%  | 90%  | 67%  | 44%  | 25%  |
| decode_place_u16_natural       | 100% | 99% | 97% | 95% | 70%  | 87%  | 65%  | 42%  | 26%  |
| persistent_handle_to_u16       | 100% | 99% | 97% | 95% | 70%  | 70%  | 64%  | 42%  | 27%  |
| persistent_handle_to_f32       | 100% | 99% | 98% | 94% | 69%  | 68%  | 64%  | 42%  | 25%  |
| openperframe_handle_to_f32     | 100% | 99% | 98% | 95% | 70%  | 71%  | 66%  | 42%  | 26%  |
| strip_batch_to_f32_b64         | 100% | 98% | 97% | 93% | 87%  | 78%  | 71%  | 54%  | 41%  |
| strip_batch_to_f32_b256        | 100% | 99% | 97% | 94% | 87%  | 78%  | 73%  | 56%  | 44%  |
| convert_u16_to_f32_resident    | 100% | 58% | 35% | 18% | 9%   | 6%   | 6%   | 4%   | 3%   |
| alloc_first_touch_f32          | 100% | 73% | 69% | 48% | 29%  | 14%  | 10%  | 6%   | 5%   |
| alloc_first_touch_f32_malloc   | 100% | 73% | 70% | 48% | 29%  | 15%  | 11%  | 7%   | 4%   |
| alloc_first_touch_f32_perframe | 100% | 5%  | 16% | 9%  | 3%   | 2%   | 1%   | 1%   | 0%   |
| alloc_first_touch_u16          | 100% | 73% | 69% | 49% | 29%  | 14%  | 11%  | 7%   | 4%   |
| production_image_read          | 100% | 99% | 98% | 96% | 71%  | 80%  | 54%  | 35%  | 26%  |
| production_image_read_prealloc | 100% | 99% | 98% | 95% | 71%  | 89%  | 66%  | 36%  | 27%  |
| omp_dispatch_only              | 100% | 50% | 41% | 28% | 2%   | 9%   | 6%   | 2%   | 1%   |
