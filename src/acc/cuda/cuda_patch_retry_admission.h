#ifndef CUDA_PATCH_RETRY_ADMISSION_H_
#define CUDA_PATCH_RETRY_ADMISSION_H_

#include <climits>
#include "src/acc/cuda/cuda_checked_arith.h"

namespace mc_cuda {

// Additional live bytes after a completed resident patch attempt. The download
// stack dies before cudaAlignPatch allocates an equally sized upload stack, so
// count it once, alongside the fresh alignment buffers and actual C2R work area.
// Existing session/preparation/alignment allocations are already excluded from
// cudaMemGetInfo's free bytes and must not be added again. No CUDA dependency:
// the same checked arithmetic is exercised by the host-only regression control.
// On invalid geometry or overflow, leave required unchanged and refuse admission.
inline bool patchRetryRequiredBytes(int patch_w, int patch_h, int n_groups,
                                    int ccf_w, int ccf_h, size_t cufft_work,
                                    size_t &required) {
    if (patch_w <= 0 || patch_h <= 0 || n_groups <= 0 ||
        ccf_w <= 0 || ccf_h <= 0 || ccf_w > patch_w || ccf_h > patch_h ||
        patch_w % 2 || patch_h % 2 || ccf_w % 2 || ccf_h % 2) return false;
    size_t patch_real = 0, patch_comp = 0, ccf_real = 0, ccf_comp = 0;
    if (!mc_checked::mulSize(patch_w, patch_h, patch_real) ||
        !mc_checked::mulSize(patch_w / 2 + 1, patch_h, patch_comp) ||
        !mc_checked::mulSize(ccf_w, ccf_h, ccf_real) ||
        !mc_checked::mulSize(ccf_w / 2 + 1, ccf_h, ccf_comp)) return false;
    // These distances are int expressions in the actual cuFFT plan calls.
    if (patch_real > INT_MAX || patch_comp > INT_MAX ||
        ccf_real > INT_MAX || ccf_comp > INT_MAX) return false;

    size_t total = cufft_work;
    auto add_array = [&](size_t count, size_t elements, size_t element_bytes) {
        size_t bytes = 0;
        return mc_checked::mulSize(count, elements, bytes) &&
               mc_checked::mulSize(bytes, element_bytes, bytes) &&
               mc_checked::addSize(total, bytes, total);
    };
    // CUDA float2/cufftComplex consists of two floats.
    if (!add_array(n_groups, patch_comp, 2 * sizeof(float)) || // upload stack S
        !add_array(1, ccf_comp, 2 * sizeof(float)) ||          // reference
        !add_array(1, ccf_comp, sizeof(float)) ||              // weights
        !add_array(n_groups, ccf_comp, 2 * sizeof(float)) ||   // complex CCFs
        !add_array(n_groups, ccf_real, sizeof(float)) ||       // real CCFs
        !add_array(n_groups, 4, sizeof(float))) return false;  // shift arrays
    required = total;
    return true;
}

} // namespace mc_cuda
#endif // CUDA_PATCH_RETRY_ADMISSION_H_
