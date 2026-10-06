#ifndef CUDA_ALIGNPATCH_FREQUENCY_SUPPORT_H_
#define CUDA_ALIGNPATCH_FREQUENCY_SUPPORT_H_

#if defined(__CUDACC__)
#define MC_FREQUENCY_HOST_DEVICE __host__ __device__
#else
#define MC_FREQUENCY_HOST_DEVICE
#endif

namespace mc_cuda {
// For a valid original-layout Fourier pixel (x, y), test membership in the
// exact set read by computeReferenceKernel/computeCCFKernel. This describes an
// index selection, not a Fourier resize: the crop's midpoint row is positive.
// Keeping this pure permits independent host enumeration of the reader mapping.
MC_FREQUENCY_HOST_DEVICE inline bool frequencyIsInCcfSupport(
    int x, int y, int full_ny, int ccf_nfx, int ccf_ny)
{
    const int half = ccf_ny / 2;
    return x < ccf_nfx && (y <= half || y > full_ny - ccf_ny + half);
}
} // namespace mc_cuda

#undef MC_FREQUENCY_HOST_DEVICE
#endif
