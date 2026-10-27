// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef MOTIONCORR_CUDA_HERMITIAN_CUH
#define MOTIONCORR_CUDA_HERMITIAN_CUH

#include <cuda_runtime.h>
#include <cufft.h>

namespace mc_cuda {
// C2R requires conjugate pairs on the self-conjugate x columns. Fractional
// shifts (and CCF cropping) break that invariant. Project only consumption
// scratch, matching FFTW's real inverse, without changing resident spectra.
// One thread owns both members of a pair: in-place reads cannot race writes.
static __global__ void projectHermitianColumnsKernel(cufftComplex *data, int nx, int ny) {
    const int y = blockIdx.x * blockDim.x + threadIdx.x;
    if (y > ny / 2) return;
    const int x = blockIdx.y == 0 ? 0 : nx / 2;
    const size_t stride = (size_t)ny * (nx / 2 + 1);
    cufftComplex *frame = data + (size_t)blockIdx.z * stride;
    const size_t a = (size_t)y * (nx / 2 + 1) + x;
    const size_t b = (size_t)((ny - y) % ny) * (nx / 2 + 1) + x;
    const cufftComplex u = frame[a], v = frame[b];
    if (a == b) { if (u.y != 0.0f) frame[a].y = 0.0f; return; }
    // Preserve already Hermitian pairs, including their real bits.
    if (u.x == v.x && u.y == -v.y) return;
    const cufftComplex h = make_cuFloatComplex(0.5f * u.x + 0.5f * v.x,
                                             0.5f * u.y - 0.5f * v.y);
    frame[a] = h;
    frame[b] = make_cuFloatComplex(h.x, -h.y);
}

static inline cudaError_t projectHermitianColumns(cufftComplex *data, int nx, int ny, int batch = 1) {
    const dim3 grid((ny / 2 + 1 + 255) / 256, nx % 2 == 0 && nx > 1 ? 2 : 1, batch);
    projectHermitianColumnsKernel<<<grid, 256>>>(data, nx, ny);
    return cudaGetLastError();
}
} // namespace mc_cuda
#endif
