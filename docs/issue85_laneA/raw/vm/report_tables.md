### Input identity

```
nx = 3710
ny = 3838
nframes = 24
bits_per_sample = 16
sample_format = 1
compression = 8
predictor = 1
rows_per_strip = 1
strips_per_frame = 3838
strips_total = 92112
strip_size_bytes = 7420
max_compressed_strip_bytes = 1493
compressed_bytes = 125808249
decoded_bytes_u16 = 683471040
decoded_bytes_f32 = 1366942080
file_bytes = 126550106
```

### Run identity

```
date_utc=2026-09-28T15:23:32Z
host=4-gpu-vm
kernel=Linux 6.8.0-136-generic #136-Ubuntu SMP PREEMPT_DYNAMIC Wed Jul  1 21:53:05 UTC 2026 x86_64 GNU/Linux
requested_mask=72-95
nproc_total=124
cpu_model=AMD EPYC 7452 32-Core Processor
numa=2
numa_node_cpus=0:0-61
numa_node_cpus=1:62-123
mem_total_kb=454003720 kB
governor=unknown
libtiff=4.5.1+git230720-4ubuntu2.5
zlib=1:1.3.dfsg-3.1ubuntu2.2
gcc=g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
loadavg_at_start=3.48 5.34 8.29 3/4926 1556615
omp_proc_bind=<unset, matches production>
omp_num_threads=<unset>
source_revision=UNAVAILABLE (no git metadata in /home/alex/mc85-laneA)
source_dirty_files=UNAVAILABLE
source_revision_declared=5ada983cfd1d6d8ef411120286402e380bdd4747
bench_sha256=49fb4954b5ba9435393fb5a15603bbfebec30c213b64737a87876ec46006c93c
h2d_sha256=4096f52e7ecd6d5767e1f7efb329dfc3bef4a95773de1b43de90ba0b522ae92c
storage_mount=/dev/sda1      ext4  3.1T  2.4T  656G  79% /
gpu=0, GPU-eddb42fe-4f9a-adde-76d3-b924e14add54, NVIDIA A100 80GB PCIe, 570.86.10
gpu=1, GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d, NVIDIA A100 80GB PCIe, 570.86.10
gpu=2, GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598, NVIDIA A100 80GB PCIe, 570.86.10
gpu=3, GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d, NVIDIA A100 80GB PCIe, 570.86.10
source_manifest_files=238
source_manifest_sha256=f8d23f023f095d39ff8cd3d5a2bd44869570756b9611cb1cf21ac9f27921dbce

# --- build configuration, appended after the run (finding: identity recorded
# the binary hash but not the flags, in a repo whose known benchmark trap is
# an unqualified -O0 build) ---
cmake_build_type=CMAKE_BUILD_TYPE:STRING=Release
cxx_flags=CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp
build_dir=/home/alex/mc85-laneA/build
loadavg_at_end=5.41 5.13 6.24 4/5605 1756314
interference_witness=see cpu_stat_delta.txt
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


### Regime 1a - warm page cache, local ext4, one representative movie

Source: `warm_ext4_rep.json`  ·  regime `warm`  ·  mask `72-95` (24 vCPU)  ·  median of 3 per movie  ·  1 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=1   | W=2   | W=4   | W=8   | W=16  | W=24  | fastest |
|--------------------------------|-------|-------|-------|-------|-------|-------|---------|
| pread_whole_file               | 0.022 | 0.021 | 0.021 | 0.017 | 0.016 | 0.017 | W=16    |
| pread_strip_extents            | 0.083 | 0.075 | 0.038 | 0.016 | 0.011 | 0.006 | W=24    |
| tiff_dirscan_persistent        | 0.001 | 0.002 | 0.002 | 0.002 | 0.002 | 0.002 | W=1     |
| tiff_open_per_frame_meta       | 0.008 | 0.010 | 0.012 | 0.007 | 0.009 | 0.010 | W=8     |
| tiff_read_raw_strip            | 0.038 | 0.034 | 0.025 | 0.016 | 0.018 | 0.023 | W=8     |
| tiff_decode_only               | 0.848 | 0.670 | 0.370 | 0.144 | 0.110 | 0.073 | W=24    |
| decode_place_u16_natural       | 0.882 | 0.717 | 0.375 | 0.153 | 0.118 | 0.079 | W=24    |
| persistent_handle_to_u16       | 0.875 | 0.732 | 0.531 | 0.158 | 0.116 | 0.082 | W=24    |
| persistent_handle_to_f32       | 0.949 | 1.044 | 0.494 | 0.172 | 0.129 | 0.093 | W=24    |
| openperframe_handle_to_f32     | 0.957 | 0.724 | 0.369 | 0.168 | 0.124 | 0.080 | W=24    |
| strip_batch_to_f32_b64         | 0.949 | 0.612 | 0.280 | 0.162 | 0.133 | 0.086 | W=24    |
| strip_batch_to_f32_b256        | 0.963 | 0.657 | 0.281 | 0.168 | 0.109 | 0.088 | W=24    |
| convert_u16_to_f32_resident    | 0.133 | 0.124 | 0.056 | 0.068 | 0.062 | 0.053 | W=24    |
| alloc_first_touch_f32          | 1.026 | 0.900 | 0.455 | 0.302 | 0.265 | 0.273 | W=16    |
| alloc_first_touch_f32_malloc   | 1.001 | 0.853 | 0.454 | 0.292 | 0.288 | 0.265 | W=24    |
| alloc_first_touch_f32_perframe | 1.031 | 0.815 | 0.361 | 0.227 | 0.254 | 0.217 | W=24    |
| alloc_first_touch_u16          | 0.662 | 0.412 | 0.236 | 0.153 | 0.147 | 0.138 | W=24    |
| production_image_read          | 2.182 | 1.410 | 0.559 | 0.297 | 0.219 | 0.134 | W=24    |
| omp_dispatch_only              | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.001 | W=16    |

**Attribution chain at W=1 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.038        | +0.038 | +1.8%          |
| + Deflate decompression                                                     | 0.848        | +0.810 | +37.1%         |
| + write decoded rows to destination                                         | 0.882        | +0.034 | +1.6%          |
| + Y-flipped placement                                                       | 0.875        | -0.007 | -0.3%          |
| + uint16 to float conversion                                                | 0.949        | +0.075 | +3.4%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 2.182        | +1.233 | +56.5%         |

**Attribution chain at W=2 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.034        | +0.034 | +2.4%          |
| + Deflate decompression                                                     | 0.670        | +0.636 | +45.1%         |
| + write decoded rows to destination                                         | 0.717        | +0.047 | +3.4%          |
| + Y-flipped placement                                                       | 0.732        | +0.015 | +1.0%          |
| + uint16 to float conversion                                                | 1.044        | +0.313 | +22.2%         |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 1.410        | +0.366 | +25.9%         |

**Attribution chain at W=4 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.025        | +0.025 | +4.5%          |
| + Deflate decompression                                                     | 0.370        | +0.345 | +61.7%         |
| + write decoded rows to destination                                         | 0.375        | +0.005 | +0.9%          |
| + Y-flipped placement                                                       | 0.531        | +0.156 | +27.9%         |
| + uint16 to float conversion                                                | 0.494        | -0.038 | -6.7%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.559        | +0.065 | +11.7%         |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.016        | +0.016 | +5.2%          |
| + Deflate decompression                                                     | 0.144        | +0.129 | +43.4%         |
| + write decoded rows to destination                                         | 0.153        | +0.009 | +3.0%          |
| + Y-flipped placement                                                       | 0.158        | +0.005 | +1.5%          |
| + uint16 to float conversion                                                | 0.172        | +0.015 | +5.0%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.297        | +0.124 | +41.9%         |

**Attribution chain at W=16 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.018        | +0.018 | +8.3%          |
| + Deflate decompression                                                     | 0.110        | +0.091 | +41.7%         |
| + write decoded rows to destination                                         | 0.118        | +0.008 | +3.8%          |
| + Y-flipped placement                                                       | 0.116        | -0.002 | -0.8%          |
| + uint16 to float conversion                                                | 0.129        | +0.013 | +5.9%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.219        | +0.090 | +41.0%         |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.023        | +0.023 | +17.1%         |
| + Deflate decompression                                                     | 0.073        | +0.050 | +37.5%         |
| + write decoded rows to destination                                         | 0.079        | +0.005 | +4.0%          |
| + Y-flipped placement                                                       | 0.082        | +0.003 | +2.4%          |
| + uint16 to float conversion                                                | 0.093        | +0.011 | +8.2%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.134        | +0.041 | +30.8%         |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=1     | 0.9494 | 0.9572 | +0.8%  | A faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=2     | 1.0444 | 0.7240 | -30.7% | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=4     | 0.4937 | 0.3695 | -25.2% | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 0.1724 | 0.1677 | -2.7%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=16    | 0.1292 | 0.1240 | -4.0%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 0.0928 | 0.0796 | -14.2% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=1     | 0.9494 | 0.9492 | -0.0%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=2     | 1.0444 | 0.6123 | -41.4% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=4     | 0.4937 | 0.2802 | -43.3% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 0.1724 | 0.1618 | -6.1%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=16    | 0.1292 | 0.1334 | +3.3%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 0.0928 | 0.0857 | -7.6%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=1     | 0.9494 | 0.9635 | +1.5%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=2     | 1.0444 | 0.6568 | -37.1% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=4     | 0.4937 | 0.2809 | -43.1% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 0.1724 | 0.1675 | -2.8%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=16    | 0.1292 | 0.1091 | -15.6% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 0.0928 | 0.0876 | -5.5%  | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=1     | 1.0259 | 0.6625 | -35.4% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=2     | 0.9000 | 0.4116 | -54.3% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=4     | 0.4553 | 0.2363 | -48.1% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.3016 | 0.1528 | -49.4% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=16    | 0.2651 | 0.1467 | -44.7% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.2726 | 0.1384 | -49.2% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                        | verdict |
|----------------------------|---------|
| decode_place_u16_natural   | PASS    |
| openperframe_handle_to_f32 | PASS    |
| persistent_handle_to_f32   | PASS    |
| persistent_handle_to_u16   | PASS    |
| production_image_read      | PASS    |
| strip_batch_to_f32_b256    | PASS    |
| strip_batch_to_f32_b64     | PASS    |

**Parallel efficiency vs W=1** (speedup / workers; 100% would be linear)

| arm                            | W=1  | W=2 | W=4 | W=8 | W=16 | W=24 |
|--------------------------------|------|-----|-----|-----|------|------|
| pread_whole_file               | 100% | 51% | 26% | 16% | 9%   | 5%   |
| pread_strip_extents            | 100% | 55% | 55% | 67% | 48%  | 57%  |
| tiff_dirscan_persistent        | 100% | 27% | 13% | 8%  | 4%   | 2%   |
| tiff_open_per_frame_meta       | 100% | 41% | 17% | 16% | 6%   | 3%   |
| tiff_read_raw_strip            | 100% | 57% | 38% | 31% | 13%  | 7%   |
| tiff_decode_only               | 100% | 63% | 57% | 73% | 48%  | 48%  |
| decode_place_u16_natural       | 100% | 62% | 59% | 72% | 47%  | 47%  |
| persistent_handle_to_u16       | 100% | 60% | 41% | 69% | 47%  | 45%  |
| persistent_handle_to_f32       | 100% | 45% | 48% | 69% | 46%  | 43%  |
| openperframe_handle_to_f32     | 100% | 66% | 65% | 71% | 48%  | 50%  |
| strip_batch_to_f32_b64         | 100% | 78% | 85% | 73% | 44%  | 46%  |
| strip_batch_to_f32_b256        | 100% | 73% | 86% | 72% | 55%  | 46%  |
| convert_u16_to_f32_resident    | 100% | 53% | 59% | 24% | 13%  | 10%  |
| alloc_first_touch_f32          | 100% | 57% | 56% | 43% | 24%  | 16%  |
| alloc_first_touch_f32_malloc   | 100% | 59% | 55% | 43% | 22%  | 16%  |
| alloc_first_touch_f32_perframe | 100% | 63% | 71% | 57% | 25%  | 20%  |
| alloc_first_touch_u16          | 100% | 80% | 70% | 54% | 28%  | 20%  |
| production_image_read          | 100% | 77% | 98% | 92% | 62%  | 68%  |
| omp_dispatch_only              | 100% | 30% | 38% | 30% | 16%  | 0%   |


### Regime 1b - warm page cache, local ext4, ALL 24 tutorial movies

Source: `warm_ext4_all24.json`  ·  regime `warm`  ·  mask `72-95` (24 vCPU)  ·  median of 3 per movie  ·  24 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=8   | W=24  | fastest |
|--------------------------------|-------|-------|---------|
| pread_whole_file               | 0.442 | 0.454 | W=8     |
| pread_strip_extents            | 0.380 | 0.215 | W=24    |
| tiff_dirscan_persistent        | 0.035 | 0.049 | W=8     |
| tiff_open_per_frame_meta       | 0.165 | 0.310 | W=8     |
| tiff_read_raw_strip            | 0.394 | 0.607 | W=8     |
| tiff_decode_only               | 3.803 | 2.192 | W=24    |
| decode_place_u16_natural       | 4.082 | 2.136 | W=24    |
| persistent_handle_to_u16       | 4.142 | 2.193 | W=24    |
| persistent_handle_to_f32       | 4.459 | 2.354 | W=24    |
| openperframe_handle_to_f32     | 4.316 | 2.138 | W=24    |
| strip_batch_to_f32_b64         | 4.089 | 2.414 | W=24    |
| strip_batch_to_f32_b256        | 3.994 | 2.349 | W=24    |
| convert_u16_to_f32_resident    | 1.465 | 1.393 | W=24    |
| alloc_first_touch_f32          | 7.795 | 6.536 | W=24    |
| alloc_first_touch_f32_malloc   | 7.964 | 6.960 | W=24    |
| alloc_first_touch_f32_perframe | 5.671 | 5.789 | W=8     |
| alloc_first_touch_u16          | 3.962 | 3.421 | W=24    |
| production_image_read          | 7.382 | 3.486 | W=24    |
| omp_dispatch_only              | 0.001 | 0.007 | W=8     |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.394        | +0.394 | +5.3%          |
| + Deflate decompression                                                     | 3.803        | +3.409 | +46.2%         |
| + write decoded rows to destination                                         | 4.082        | +0.279 | +3.8%          |
| + Y-flipped placement                                                       | 4.142        | +0.060 | +0.8%          |
| + uint16 to float conversion                                                | 4.459        | +0.318 | +4.3%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 7.382        | +2.922 | +39.6%         |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.607        | +0.607 | +17.4%         |
| + Deflate decompression                                                     | 2.192        | +1.585 | +45.5%         |
| + write decoded rows to destination                                         | 2.136        | -0.056 | -1.6%          |
| + Y-flipped placement                                                       | 2.193        | +0.057 | +1.6%          |
| + uint16 to float conversion                                                | 2.354        | +0.161 | +4.6%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 3.486        | +1.133 | +32.5%         |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 4.4593 | 4.3164 | -3.2%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 2.3536 | 2.1385 | -9.1%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 4.4593 | 4.0887 | -8.3%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 2.3536 | 2.4138 | +2.6%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 4.4593 | 3.9941 | -10.4% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 2.3536 | 2.3491 | -0.2%  | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 7.7953 | 3.9625 | -49.2% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 6.5356 | 3.4208 | -47.7% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                        | verdict |
|----------------------------|---------|
| decode_place_u16_natural   | PASS    |
| openperframe_handle_to_f32 | PASS    |
| persistent_handle_to_f32   | PASS    |
| persistent_handle_to_u16   | PASS    |
| production_image_read      | PASS    |
| strip_batch_to_f32_b256    | PASS    |
| strip_batch_to_f32_b64     | PASS    |


### Regime 2a - tmpfs (/dev/shm), one representative movie

Source: `tmpfs_rep.json`  ·  regime `warm`  ·  mask `72-95` (24 vCPU)  ·  median of 3 per movie  ·  1 movie(s), summed

**Wall seconds for the whole set, by decode worker count**

| arm                            | W=1   | W=2   | W=4   | W=8   | W=16  | W=24  | fastest |
|--------------------------------|-------|-------|-------|-------|-------|-------|---------|
| pread_whole_file               | 0.026 | 0.021 | 0.021 | 0.021 | 0.020 | 0.026 | W=16    |
| pread_strip_extents            | 0.082 | 0.056 | 0.028 | 0.015 | 0.010 | 0.030 | W=16    |
| tiff_dirscan_persistent        | 0.001 | 0.001 | 0.001 | 0.001 | 0.002 | 0.005 | W=1     |
| tiff_open_per_frame_meta       | 0.008 | 0.006 | 0.007 | 0.007 | 0.008 | 0.016 | W=2     |
| tiff_read_raw_strip            | 0.040 | 0.029 | 0.020 | 0.016 | 0.018 | 0.029 | W=8     |
| tiff_decode_only               | 0.811 | 0.523 | 0.272 | 0.148 | 0.111 | 0.112 | W=16    |
| decode_place_u16_natural       | 0.863 | 0.571 | 0.290 | 0.155 | 0.116 | 0.126 | W=16    |
| persistent_handle_to_u16       | 0.878 | 0.583 | 0.300 | 0.157 | 0.117 | 0.078 | W=24    |
| persistent_handle_to_f32       | 0.962 | 0.648 | 0.316 | 0.169 | 0.124 | 0.086 | W=24    |
| openperframe_handle_to_f32     | 0.961 | 0.612 | 0.315 | 0.163 | 0.118 | 0.081 | W=24    |
| strip_batch_to_f32_b64         | 0.932 | 0.657 | 0.327 | 0.172 | 0.106 | 0.094 | W=24    |
| strip_batch_to_f32_b256        | 0.931 | 0.613 | 0.341 | 0.161 | 0.104 | 0.089 | W=24    |
| convert_u16_to_f32_resident    | 0.118 | 0.097 | 0.052 | 0.050 | 0.044 | 0.051 | W=16    |
| alloc_first_touch_f32          | 0.928 | 0.694 | 0.447 | 0.310 | 0.272 | 0.269 | W=24    |
| alloc_first_touch_f32_malloc   | 0.929 | 0.694 | 0.440 | 0.312 | 0.272 | 0.266 | W=24    |
| alloc_first_touch_f32_perframe | 0.899 | 0.595 | 0.337 | 0.216 | 0.216 | 0.243 | W=8     |
| alloc_first_touch_u16          | 0.468 | 0.309 | 0.202 | 0.146 | 0.129 | 0.128 | W=24    |
| production_image_read          | 1.666 | 1.041 | 0.553 | 0.277 | 0.207 | 0.131 | W=24    |
| omp_dispatch_only              | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | W=16    |

**Attribution chain at W=1 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.040        | +0.040 | +2.4%          |
| + Deflate decompression                                                     | 0.811        | +0.770 | +46.3%         |
| + write decoded rows to destination                                         | 0.863        | +0.052 | +3.1%          |
| + Y-flipped placement                                                       | 0.878        | +0.015 | +0.9%          |
| + uint16 to float conversion                                                | 0.962        | +0.084 | +5.1%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 1.666        | +0.703 | +42.2%         |

**Attribution chain at W=2 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.029        | +0.029 | +2.8%          |
| + Deflate decompression                                                     | 0.523        | +0.494 | +47.5%         |
| + write decoded rows to destination                                         | 0.571        | +0.048 | +4.6%          |
| + Y-flipped placement                                                       | 0.583        | +0.011 | +1.1%          |
| + uint16 to float conversion                                                | 0.648        | +0.066 | +6.3%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 1.041        | +0.393 | +37.7%         |

**Attribution chain at W=4 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.020        | +0.020 | +3.6%          |
| + Deflate decompression                                                     | 0.272        | +0.252 | +45.5%         |
| + write decoded rows to destination                                         | 0.290        | +0.018 | +3.2%          |
| + Y-flipped placement                                                       | 0.300        | +0.010 | +1.8%          |
| + uint16 to float conversion                                                | 0.316        | +0.016 | +2.9%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.553        | +0.238 | +42.9%         |

**Attribution chain at W=8 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.016        | +0.016 | +5.9%          |
| + Deflate decompression                                                     | 0.148        | +0.132 | +47.5%         |
| + write decoded rows to destination                                         | 0.155        | +0.007 | +2.4%          |
| + Y-flipped placement                                                       | 0.157        | +0.002 | +0.8%          |
| + uint16 to float conversion                                                | 0.169        | +0.011 | +4.1%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.277        | +0.109 | +39.2%         |

**Attribution chain at W=16 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.018        | +0.018 | +8.5%          |
| + Deflate decompression                                                     | 0.111        | +0.093 | +44.8%         |
| + write decoded rows to destination                                         | 0.116        | +0.005 | +2.6%          |
| + Y-flipped placement                                                       | 0.117        | +0.001 | +0.5%          |
| + uint16 to float conversion                                                | 0.124        | +0.007 | +3.2%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.207        | +0.084 | +40.4%         |

**Attribution chain at W=24 (cumulative, and what each step adds)**

| component                                                                   | cumulative s | adds s | share of stage |
|-----------------------------------------------------------------------------|--------------|--------|----------------|
| storage access + LibTIFF strip bookkeeping (through libtiff's file mapping) | 0.029        | +0.029 | +21.8%         |
| + Deflate decompression                                                     | 0.112        | +0.084 | +63.8%         |
| + write decoded rows to destination                                         | 0.126        | +0.014 | +10.7%         |
| + Y-flipped placement                                                       | 0.078        | -0.048 | -36.9%         |
| + uint16 to float conversion                                                | 0.086        | +0.008 | +6.2%          |
| + per-frame TIFFOpen, Image/fImageHandler lifecycle and frame allocation    | 0.131        | +0.045 | +34.5%         |

**Direct A/B comparisons.** Same work, one structural difference. A positive percentage means B costs more than A.

| comparison (A vs B)                                            | workers | A s    | B s    | B vs A | winner   |
|----------------------------------------------------------------|---------|--------|--------|--------|----------|
| one TIFF* per worker vs one per frame (the PR B question)      | W=1     | 0.9624 | 0.9610 | -0.1%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=2     | 0.6484 | 0.6121 | -5.6%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=4     | 0.3158 | 0.3148 | -0.3%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=8     | 0.1686 | 0.1626 | -3.5%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=16    | 0.1238 | 0.1176 | -5.0%  | B faster |
| one TIFF* per worker vs one per frame (the PR B question)      | W=24    | 0.0859 | 0.0814 | -5.2%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=1     | 0.9624 | 0.9318 | -3.2%  | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=2     | 0.6484 | 0.6569 | +1.3%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=4     | 0.3158 | 0.3268 | +3.5%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=8     | 0.1686 | 0.1717 | +1.9%  | A faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=16    | 0.1238 | 0.1055 | -14.7% | B faster |
| frame-level scheduling vs 64-strip batches (the PR E question) | W=24    | 0.0859 | 0.0939 | +9.4%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=1     | 0.9624 | 0.9313 | -3.2%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=2     | 0.6484 | 0.6129 | -5.5%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=4     | 0.3158 | 0.3406 | +7.9%  | A faster |
| frame-level scheduling vs 256-strip batches                    | W=8     | 0.1686 | 0.1609 | -4.5%  | B faster |
| frame-level scheduling vs 256-strip batches                    | W=16    | 0.1238 | 0.1044 | -15.6% | B faster |
| frame-level scheduling vs 256-strip batches                    | W=24    | 0.0859 | 0.0889 | +3.6%  | A faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=1     | 0.9280 | 0.4676 | -49.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=2     | 0.6944 | 0.3089 | -55.5% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=4     | 0.4469 | 0.2021 | -54.8% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=8     | 0.3099 | 0.1461 | -52.9% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=16    | 0.2724 | 0.1291 | -52.6% | B faster |
| float32 vs uint16 movie allocation (the PR C payload question) | W=24    | 0.2688 | 0.1281 | -52.3% | B faster |

**Exact ordered pixel equality against the production reference, every worker count and every repeat**

| arm                        | verdict |
|----------------------------|---------|
| decode_place_u16_natural   | PASS    |
| openperframe_handle_to_f32 | PASS    |
| persistent_handle_to_f32   | PASS    |
| persistent_handle_to_u16   | PASS    |
| production_image_read      | PASS    |
| strip_batch_to_f32_b256    | PASS    |
| strip_batch_to_f32_b64     | PASS    |

**Parallel efficiency vs W=1** (speedup / workers; 100% would be linear)

| arm                            | W=1  | W=2 | W=4 | W=8 | W=16 | W=24 |
|--------------------------------|------|-----|-----|-----|------|------|
| pread_whole_file               | 100% | 64% | 32% | 16% | 8%   | 4%   |
| pread_strip_extents            | 100% | 74% | 73% | 71% | 50%  | 11%  |
| tiff_dirscan_persistent        | 100% | 39% | 17% | 8%  | 4%   | 1%   |
| tiff_open_per_frame_meta       | 100% | 60% | 27% | 14% | 6%   | 2%   |
| tiff_read_raw_strip            | 100% | 69% | 51% | 31% | 14%  | 6%   |
| tiff_decode_only               | 100% | 77% | 75% | 68% | 46%  | 30%  |
| decode_place_u16_natural       | 100% | 76% | 74% | 70% | 46%  | 29%  |
| persistent_handle_to_u16       | 100% | 75% | 73% | 70% | 47%  | 47%  |
| persistent_handle_to_f32       | 100% | 74% | 76% | 71% | 49%  | 47%  |
| openperframe_handle_to_f32     | 100% | 79% | 76% | 74% | 51%  | 49%  |
| strip_batch_to_f32_b64         | 100% | 71% | 71% | 68% | 55%  | 41%  |
| strip_batch_to_f32_b256        | 100% | 76% | 68% | 72% | 56%  | 44%  |
| convert_u16_to_f32_resident    | 100% | 61% | 56% | 29% | 17%  | 10%  |
| alloc_first_touch_f32          | 100% | 67% | 52% | 37% | 21%  | 14%  |
| alloc_first_touch_f32_malloc   | 100% | 67% | 53% | 37% | 21%  | 15%  |
| alloc_first_touch_f32_perframe | 100% | 76% | 67% | 52% | 26%  | 15%  |
| alloc_first_touch_u16          | 100% | 76% | 58% | 40% | 23%  | 15%  |
| production_image_read          | 100% | 80% | 75% | 75% | 50%  | 53%  |
| omp_dispatch_only              | 100% | 50% | 17% | 4%  | 11%  | 2%   |


### Regime 2b - tmpfs (/dev/shm), 4-movie subset

mask `72-95` (24 vCPU) · median of 3 per movie · 4 movies, summed. Per-movie min/max show how much one movie can mislead: `20170629_00021` sits at the low end of this set.

**Read the per-arm totals, not the small differences between them.** Each arm in this phase is a separate process invocation, so arms did not run back-to-back under the same machine conditions the way they do in the representative-movie phase. Differences of a few percent here are interference, not work: any link below that is reported as `n/a`. The fine-grained attribution comes from the representative-movie phase, where every arm is measured inside one process; this phase exists to confirm that the large components keep their magnitude across all 24 movies.

| arm                      | W=8  set total (per-movie range) | W=24  set total (per-movie range) |
|--------------------------|----------------------------------|-----------------------------------|
| persistent_handle_to_f32 | 0.690  (0.1673-0.1756)           | 0.438  (0.0976-0.1169)            |
| pread_strip_extents      | 0.060  (0.0147-0.0154)           | 0.025  (0.0059-0.0066)            |
| production_image_read    | 1.097  (0.2433-0.2879)           | 0.633  (0.1287-0.1832)            |
| tiff_decode_only         | 0.594  (0.1436-0.1555)           | 0.325  (0.0697-0.1120)            |
| tiff_read_raw_strip      | 0.067  (0.0163-0.0172)           | 0.094  (0.0215-0.0279)            |

**Exact ordered pixel equality against the production reference, every movie, every worker count, every repeat**

| arm                      | verdict |
|--------------------------|---------|
| persistent_handle_to_f32 | PASS    |
| production_image_read    | PASS    |


### Regime 3 - cold, per-file page-cache eviction, local ext4

`posix_fadvise(POSIX_FADV_DONTNEED)` on the movie before every repeat. This evicts that file's clean pages only; it does not clear LibTIFF, allocator or CPU cache state, so it is a cold-*file* arm, not a cold machine.

| arm                      | W=1    | W=8   | W=24  |
|--------------------------|--------|-------|-------|
| persistent_handle_to_f32 | 28.067 | 5.332 | 3.496 |
| pread_strip_extents      | 8.559  | 2.024 | 1.842 |
| pread_whole_file         | 2.673  | 2.626 | 2.649 |
| production_image_read    | 45.407 | 8.182 | 4.540 |
| tiff_decode_only         | 24.616 | 4.788 | 2.930 |
| tiff_read_raw_strip      | 8.167  | 2.293 | 2.172 |
