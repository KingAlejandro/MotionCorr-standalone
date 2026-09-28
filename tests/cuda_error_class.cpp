// Issue #69 -- unit tests for the two predicates behind the poisoned-context and
// retry decisions in motioncorr_runner.cpp:
//   cudaErrorPoisonsContext()  -- is this error code one that kills the context?
//   cudaRetryVerdictFor()      -- given what the failing stage RECORDED and what the
//                                 last-error slot reports now, is a retry permitted?
//
// The second exists because absence of a pending error is not proof of a usable
// context: a helper that returns false has already consumed its error and reset the
// slot.
//
// Needs the CUDA headers for the cudaError_t enumerators, but needs no device: the
// classifier is a pure predicate over an error code and performs no CUDA call. That is
// exactly why it lives in a header instead of an anonymous namespace in the runner.
//
// It is not a substitute for a real poisoned context. The fault matrix cannot
// synthesise an illegal address or an ECC fault, so the production branch this
// predicate drives is still only exercised by argument, not by a real fault. This test
// covers the predicate, and says so.

#include "src/acc/cuda/cuda_error_class.h"

#include <cstdio>
#include <vector>

namespace {

struct Case {
    cudaError_t code;
    bool poisons;
    const char *why;
};

const Case CASES[] = {
    // Documented as leaving the context unusable for the rest of the process.
    {cudaErrorIllegalAddress,       true,  "kernel dereferenced an invalid address"},
    {cudaErrorLaunchFailure,        true,  "kernel faulted during execution"},
    {cudaErrorLaunchTimeout,        true,  "kernel exceeded the launch timeout"},
    {cudaErrorHardwareStackError,   true,  "device stack corruption"},
    {cudaErrorIllegalInstruction,   true,  "illegal instruction executed on device"},
    {cudaErrorMisalignedAddress,    true,  "misaligned device access"},
    {cudaErrorInvalidAddressSpace,  true,  "instruction used the wrong address space"},
    {cudaErrorInvalidPc,            true,  "invalid program counter"},
    {cudaErrorECCUncorrectable,     true,  "uncorrectable ECC error"},
    {cudaErrorContextIsDestroyed,   true,  "context already destroyed"},
    {cudaErrorDeviceUninitialized,  true,  "context invalid or not initialised"},
    {cudaErrorAssert,               true,  "device-side assert tripped"},
#if CUDART_VERSION >= 11060
    {cudaErrorExternalDevice,       true,  "external device reported a fatal error"},
#endif

    // Recoverable: the context survives, so an alternative path may legitimately run.
    // cudaErrorMemoryAllocation is the one that matters -- classifying it as poisoning
    // would turn every ordinary OOM into a whole-movie abort and remove a working
    // fallback.
    {cudaSuccess,                   false, "no error at all must never abort a movie"},
    {cudaErrorMemoryAllocation,     false, "an allocation that did not fit is recoverable"},
    {cudaErrorInvalidValue,         false, "a bad argument does not poison the context"},
    {cudaErrorInvalidDevice,        false, "device selection error, context not poisoned"},
    {cudaErrorNotSupported,         false, "unsupported operation, context not poisoned"},
    {cudaErrorInsufficientDriver,   false, "environmental, not a property of this context"},
    {cudaErrorNoDevice,             false, "environmental, not a property of this context"},
#if CUDART_VERSION >= 11010
    {cudaErrorUnsupportedPtxVersion, false, "toolchain mismatch; deterministic, not sticky"},
#endif
};

} // namespace

// ---------------------------------------------------------------------------------
// Retry-verdict controls (issue #69, after the lost-error review).
//
// The hazard: a stage's error handler CONSUMES the CUDA error -- it reads it, logs it,
// and returns false -- which resets the host thread's last-error slot. A later
// cudaGetLastError() then returns cudaSuccess even though the failure was fatal.
// Deciding recoverability from that later read turns a dead context into a permitted
// retry. These cases pin the decision to the status the failing stage recorded.
// ---------------------------------------------------------------------------------
struct RetryCase {
    cudaError_t      recorded;      // what the failing stage preserved
    cufftResult      recorded_cufft;
    cudaError_t      pending;       // what cudaGetLastError() reports afterwards
    CudaRetryVerdict expect;
    const char      *why;
};

const RetryCase RETRY_CASES[] = {
    // THE negative control the review asked for: a fatal helper that already consumed
    // its error, so the last-error slot is clear. Retry must still be refused.
    {cudaErrorIllegalAddress, CUFFT_SUCCESS, cudaSuccess, CUDA_RETRY_FATAL,
     "fatal error consumed by the helper; cleared last-error slot must not permit retry"},
    {cudaErrorLaunchFailure, CUFFT_SUCCESS, cudaSuccess, CUDA_RETRY_FATAL,
     "launch failure consumed by the helper; cleared slot must not permit retry"},
    {cudaErrorECCUncorrectable, CUFFT_SUCCESS, cudaSuccess, CUDA_RETRY_FATAL,
     "ECC fault consumed by the helper; cleared slot must not permit retry"},

    // The supported recoverable path: an allocation that did not fit. The existing
    // re-attempt is permitted, and must stay permitted -- classifying this as fatal
    // would abort a movie on an ordinary OOM and remove working behaviour.
    {cudaErrorMemoryAllocation, CUFFT_SUCCESS, cudaSuccess, CUDA_RETRY_PERMITTED,
     "recoverable allocation failure recorded; the supported re-attempt is permitted"},
    {cudaErrorMemoryAllocation, CUFFT_SUCCESS, cudaErrorMemoryAllocation, CUDA_RETRY_PERMITTED,
     "recoverable allocation failure, still pending; permitted"},

    // No stage recorded anything -- e.g. the caller's own unchecked allocation declined.
    // Then, and only then, the pending slot is the best available evidence.
    {cudaSuccess, CUFFT_SUCCESS, cudaErrorIllegalAddress, CUDA_RETRY_FATAL,
     "nothing recorded, fatal code still pending; must be refused"},
    {cudaSuccess, CUFFT_SUCCESS, cudaErrorMemoryAllocation, CUDA_RETRY_PERMITTED,
     "nothing recorded, recoverable code pending; permitted"},
    {cudaSuccess, CUFFT_SUCCESS, cudaSuccess, CUDA_RETRY_PERMITTED,
     "nothing recorded and nothing pending; permitted, as before"},

    // A recorded fatal code must win over a clean pending slot -- this is the whole
    // point -- and must not be overridden by a benign later code either.
    {cudaErrorIllegalAddress, CUFFT_SUCCESS, cudaErrorMemoryAllocation, CUDA_RETRY_FATAL,
     "recorded fatal must not be masked by a benign later code"},

    // cuFFT reports library-level failures that do not themselves imply a dead CUDA
    // context, so a cuFFT error alone does not force a fatal verdict.
    {cudaSuccess, CUFFT_EXEC_FAILED, cudaSuccess, CUDA_RETRY_PERMITTED,
     "cuFFT failure alone does not prove the CUDA context is dead"},
    {cudaErrorIllegalAddress, CUFFT_EXEC_FAILED, cudaSuccess, CUDA_RETRY_FATAL,
     "cuFFT failure alongside a recorded fatal CUDA code is still fatal"},
};

int runRetryCases() {
    int failures = 0, fatal = 0, permitted = 0;
    for (const RetryCase &c : RETRY_CASES) {
        const CudaRetryVerdict got = cudaRetryVerdictFor(c.recorded, c.recorded_cufft, c.pending);
        if (c.expect == CUDA_RETRY_FATAL) ++fatal; else ++permitted;
        if (got != c.expect) {
            std::printf("FAIL retry verdict: recorded=%s pending=%s -> %s, expected %s  (%s)\n",
                        cudaGetErrorName(c.recorded), cudaGetErrorName(c.pending),
                        got == CUDA_RETRY_FATAL ? "FATAL" : "PERMITTED",
                        c.expect == CUDA_RETRY_FATAL ? "FATAL" : "PERMITTED", c.why);
            ++failures;
        }
    }
    if (fatal == 0 || permitted == 0) {
        std::printf("FAIL the retry table does not cover both verdicts\n");
        ++failures;
    }
    std::printf("%d retry cases (%d fatal, %d permitted), %d failures\n",
                (int)(sizeof(RETRY_CASES) / sizeof(RETRY_CASES[0])), fatal, permitted, failures);
    return failures;
}

int main() {
    int failures = 0;
    int poisoning = 0, recoverable = 0;
    for (const Case &c : CASES) {
        const bool got = cudaErrorPoisonsContext(c.code);
        if (c.poisons) ++poisoning; else ++recoverable;
        if (got != c.poisons) {
            std::printf("FAIL %-32s expected %s, got %s  (%s)\n",
                        cudaGetErrorName(c.code), c.poisons ? "poisons" : "recoverable",
                        got ? "poisons" : "recoverable", c.why);
            ++failures;
        }
    }

    // Guard against the two ways this predicate could be quietly broken into
    // uselessness: always-true would abort every movie on an ordinary OOM, and
    // always-false would restore the blind retry the issue asks us to remove.
    if (poisoning == 0 || recoverable == 0) {
        std::printf("FAIL the case table does not cover both outcomes\n");
        ++failures;
    }

    std::printf("%d classifier cases (%d poisoning, %d recoverable), %d failures  [CUDART_VERSION %d]\n",
                (int)(sizeof(CASES) / sizeof(CASES[0])), poisoning, recoverable, failures,
                (int)CUDART_VERSION);
    failures += runRetryCases();
    if (failures) return 1;
    std::printf("PASS classifier separates poisoned-context codes from recoverable ones,\n"
                "     and a fatal error already consumed by a helper -- leaving the\n"
                "     last-error slot clear -- still refuses the retry, while a recorded\n"
                "     recoverable allocation failure still permits the supported path.\n"
                "     These cover the predicates only; no real poisoned context is\n"
                "     synthesised anywhere in this suite, and no device is used.\n");
    return 0;
}
