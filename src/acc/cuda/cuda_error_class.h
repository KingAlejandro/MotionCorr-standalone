#ifndef CUDA_ERROR_CLASS_H_
#define CUDA_ERROR_CLASS_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
// cudaRetryVerdictFor takes a cufftResult. Including cufft.h here rather than relying
// on a transitive one: motioncorr_runner.cpp already pulls it in via the other acc/cuda
// headers, so the omission only surfaced when tests/cuda_error_class.cpp included this
// header on its own.
#include <cufft.h>

/**
 * Issue #69: separates a recoverable resource failure from a fatal device execution
 * error.
 *
 * A recoverable failure -- an allocation that did not fit, a plan that could not be
 * created -- leaves the CUDA context usable, so an alternative path may legitimately
 * run. A fatal execution error poisons the context: the CUDA runtime keeps returning
 * the same sticky error for every subsequent call in this process, so retrying is not
 * a fallback, it is a second failure reported from whichever unrelated call touches
 * CUDA next.
 *
 * Returns true only for codes the CUDA runtime documents as leaving the context
 * unusable for the remainder of the process. Everything else, cudaErrorMemoryAllocation
 * in particular, is treated as recoverable.
 *
 * This is a pure predicate over an error code. It performs no CUDA call, never resets a
 * device and never touches state belonging to another process; the GPU may be shared.
 * It lives in a header rather than in a translation unit so it can be unit tested --
 * see tests/cuda_error_class.cpp.
 */
inline bool cudaErrorPoisonsContext(cudaError_t err)
{
    switch (err) {
    case cudaErrorIllegalAddress:
    case cudaErrorLaunchFailure:
    case cudaErrorLaunchTimeout:
    case cudaErrorHardwareStackError:
    case cudaErrorIllegalInstruction:
    case cudaErrorMisalignedAddress:
    case cudaErrorInvalidAddressSpace:
    case cudaErrorInvalidPc:
    case cudaErrorECCUncorrectable:
    case cudaErrorContextIsDestroyed:
    case cudaErrorDeviceUninitialized:
    case cudaErrorAssert:
#if CUDART_VERSION >= 11060
    // Added in CUDA 11.6. CMakeLists sets no CUDA version floor, and this header is
    // included from motioncorr_runner.cpp, so an unguarded reference would break the
    // *production* build on an older toolkit, not just the test.
    case cudaErrorExternalDevice:
#endif
        return true;
    default:
        // Deliberately excluded, though both are sometimes described as fatal:
        //   cudaErrorUnsupportedPtxVersion -- a module-load/toolchain mismatch. It is
        //     reproducible and deterministic, so it will fail the alternative path too,
        //     but it does not make unrelated calls fail, which is what "poisoned" means
        //     here. Treating it as recoverable keeps the existing behaviour and still
        //     ends in a clean nonzero failure.
        //   cudaErrorNotPermitted / cudaErrorSystemNotReady -- environmental, not a
        //     property of this context.
        return false;
    }
}

/**
 * Issue #69: is a retry permitted after a device stage declined to produce a result?
 *
 * The hazard this exists to close: the stage's own error handler CONSUMES the CUDA
 * error -- it reads it, logs it, and returns false. `cudaGetLastError()` is the host
 * thread's last-error slot and is reset by that read, so afterwards it reports
 * `cudaSuccess`. That is not a certificate that the context is healthy; it only means
 * nothing has been recorded since. Deciding recoverability from a later last-error read
 * therefore turns a fatal, already-consumed failure into a permitted retry.
 *
 * So the decision is made from the status the failing stage RECORDED, and the pending
 * slot is consulted only when nothing was recorded -- for example when the caller's own
 * unchecked allocation declined without going through a handler.
 *
 * A cuFFT failure is passed separately because `cufftResult` is not a `cudaError_t`.
 * cuFFT reports library-level failures that do not themselves imply a dead CUDA
 * context, so a cuFFT error alone does not force a fatal verdict; if it corrupted the
 * context, the accompanying CUDA code says so.
 *
 * Pure predicate: performs no CUDA call, resets nothing, touches no other process.
 */
enum CudaRetryVerdict {
    CUDA_RETRY_PERMITTED,   // context believed usable; the caller's existing path may run
    CUDA_RETRY_FATAL        // context unusable; fail this movie cleanly, do not retry
};

inline CudaRetryVerdict cudaRetryVerdictFor(cudaError_t recorded_by_stage,
                                            cufftResult recorded_cufft,
                                            cudaError_t pending_on_thread)
{
    const cudaError_t decisive = (recorded_by_stage != cudaSuccess) ? recorded_by_stage
                                                                    : pending_on_thread;
    (void)recorded_cufft;
    return cudaErrorPoisonsContext(decisive) ? CUDA_RETRY_FATAL : CUDA_RETRY_PERMITTED;
}

#endif // _CUDA_ENABLED
#endif // CUDA_ERROR_CLASS_H_
