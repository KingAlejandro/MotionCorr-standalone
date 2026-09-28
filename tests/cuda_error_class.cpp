// Issue #69 -- unit test for the CUDA error classifier behind the poisoned-context
// decision in motioncorr_runner.cpp.
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

    std::printf("%d cases (%d poisoning, %d recoverable), %d failures  [CUDART_VERSION %d]\n",
                (int)(sizeof(CASES) / sizeof(CASES[0])), poisoning, recoverable, failures,
                (int)CUDART_VERSION);
    if (failures) return 1;
    std::printf("PASS classifier separates poisoned-context codes from recoverable ones.\n"
                "     This covers the predicate only; no real poisoned context is\n"
                "     synthesised anywhere in this suite.\n");
    return 0;
}
