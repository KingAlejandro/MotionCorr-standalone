#ifndef CUDA_ERROR_CLASS_H_
#define CUDA_ERROR_CLASS_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>

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
    case cudaErrorExternalDevice:
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

#endif // _CUDA_ENABLED
#endif // CUDA_ERROR_CLASS_H_
