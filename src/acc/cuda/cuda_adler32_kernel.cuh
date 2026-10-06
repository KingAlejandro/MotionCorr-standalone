// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef CUDA_ADLER32_KERNEL_CUH_
#define CUDA_ADLER32_KERNEL_CUH_

#include "src/acc/cuda/cuda_adler32.h"
#include <cuda_runtime.h>
#include <nvcomp.h>

// Actual ingestion kernel, also included by the focused native test. One 256-
// thread block per strip, with the final strip's own expected size. Rejected
// outputs are not touched, and their Adler slot is left unchanged. Host code
// rejects the complete batch on status/length before consulting any Adler slot.
static __global__ void adler32StripsKernel(
    const unsigned char *decomp_base, size_t strip_pitch_bytes,
    size_t full_strip_bytes, size_t last_strip_bytes, int strips_per_frame,
    const nvcompStatus_t *statuses, const size_t *actual_sizes,
    uint32_t *out_adler, size_t n_chunks) {
    const size_t chunk = blockIdx.x;
    if (chunk >= n_chunks) return;
    const int strip_in_frame = (int)(chunk % (size_t)strips_per_frame);
    const size_t row_bytes = strip_in_frame == strips_per_frame - 1
        ? last_strip_bytes : full_strip_bytes;
    // Uniform per block: every thread returns before pointer arithmetic, loads
    // or a barrier for a failed/short chunk, even if its output pointer is invalid.
    if (!mc_tiff_adler::accepted(statuses[chunk], nvcompSuccess,
                                 actual_sizes[chunk], row_bytes)) return;
    const unsigned char *row = decomp_base + chunk * strip_pitch_bytes;
    mc_tiff_adler::Lane lane(row_bytes, threadIdx.x, blockDim.x);
    for (size_t i = threadIdx.x; i < row_bytes; i += blockDim.x) lane.add(row[i]);
    __shared__ uint32_t s_d[256], s_w[256];
    s_d[threadIdx.x] = lane.bytes();
    s_w[threadIdx.x] = lane.weighted();
    __syncthreads();
    for (unsigned stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) {
            s_d[threadIdx.x] += s_d[threadIdx.x + stride];
            s_w[threadIdx.x] += s_w[threadIdx.x + stride];
        }
        __syncthreads();
    }
    if (threadIdx.x == 0)
        out_adler[chunk] = mc_tiff_adler::finish(row_bytes, s_d[0], s_w[0]);
}
#endif
