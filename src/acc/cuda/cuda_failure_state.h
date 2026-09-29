#ifndef CUDA_FAILURE_STATE_H_
#define CUDA_FAILURE_STATE_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>

#include "src/acc/cuda/cuda_error_class.h"

/**
 * Issue #69: the failure state a CUDA session preserves across the helper boundary.
 *
 * It tracks TWO independent facts, because conflating them is what the PR107 P1 review
 * found. An earlier version kept only "the first failure", which meant a recoverable
 * `cudaErrorMemoryAllocation` recorded on one patch would suppress the recording of a
 * later `cudaErrorIllegalAddress` on another. Since `HANDLE_ERROR(cudaGetLastError())`
 * *consumes* that fatal code before the record is attempted, the runner's own later
 * last-error read came back clean too, and the retry was permitted on a dead context.
 *
 *   firstError / firstCufftError / firstStage / firstLine
 *       Diagnostic provenance: what ended the *first* stage that failed. First-wins,
 *       so the cause a human reads is the earliest one, not the last.
 *
 *   fatalError / fatalStage / fatalLine
 *       Poisoning state, latched MONOTONICALLY. The first code that poisons the context
 *       is recorded and never afterwards discarded, whatever was recorded before it and
 *       whatever is recorded after. A context does not recover, so this may only ever
 *       go from clean to poisoned.
 *
 * Keeping both means the sticky fatal state cannot be masked by an earlier recoverable
 * failure, while the original diagnostic provenance is still preserved.
 *
 * Pure host state: no CUDA call, no allocation, no device interaction. That is what
 * lets the production object itself be driven through failure sequences in a test.
 */
class CudaFailureState {
public:
    void record(cudaError_t err, const char *stage, int line) {
        if (err == cudaSuccess) return;
        // Monotonic, and deliberately NOT guarded by whether something was recorded
        // before: this is the whole point of the P1 fix.
        if (cudaErrorPoisonsContext(err) && fatal_error_ == cudaSuccess) {
            fatal_error_ = err;
            fatal_stage_ = stage ? stage : "(unknown)";
            fatal_line_ = line;
        }
        if (!hasFailed()) {
            first_error_ = err;
            first_stage_ = stage ? stage : "(unknown)";
            first_line_ = line;
        }
    }

    // cufftResult is not a cudaError_t and cannot itself name a poisoned context. If a
    // cuFFT failure did kill the context, the accompanying CUDA code is what records it.
    void recordCufft(cufftResult res, const char *stage, int line) {
        if (res == CUFFT_SUCCESS) return;
        if (!hasFailed()) {
            first_cufft_error_ = res;
            first_stage_ = stage ? stage : "(unknown)";
            first_line_ = line;
        }
    }

    cudaError_t firstError() const { return first_error_; }
    cufftResult firstCufftError() const { return first_cufft_error_; }
    const char *firstStage() const { return first_stage_; }
    int firstLine() const { return first_line_; }

    cudaError_t fatalError() const { return fatal_error_; }
    const char *fatalStage() const { return fatal_stage_; }
    int fatalLine() const { return fatal_line_; }

    bool hasFailed() const {
        return first_error_ != cudaSuccess || first_cufft_error_ != CUFFT_SUCCESS;
    }
    bool isPoisoned() const { return fatal_error_ != cudaSuccess; }

private:
    cudaError_t first_error_ = cudaSuccess;
    cufftResult first_cufft_error_ = CUFFT_SUCCESS;
    const char *first_stage_ = "";
    int first_line_ = 0;

    cudaError_t fatal_error_ = cudaSuccess;
    const char *fatal_stage_ = "";
    int fatal_line_ = 0;
};

/**
 * Convenience overload: decide from a session's preserved state plus the thread's
 * current last-error slot. The sticky fatal state is consulted first, so a poisoning
 * code observed at any point in the movie outranks both a later clean slot and an
 * earlier recoverable code.
 */
inline CudaRetryDecision cudaRetryDecisionFor(const CudaFailureState &state,
                                              cudaError_t pending_on_thread)
{
    return cudaRetryDecisionFor(state.firstError(), state.fatalError(),
                                state.firstCufftError(), pending_on_thread);
}

#endif // _CUDA_ENABLED
#endif // CUDA_FAILURE_STATE_H_
