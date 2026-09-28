// Issue #69 -- unit tests for the two predicates behind the poisoned-context and
// retry decisions in motioncorr_runner.cpp:
//   cudaErrorPoisonsContext()  -- is this error code one that kills the context?
//   cudaRetryDecisionFor()     -- given what the failing stage RECORDED and what the
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
#include "src/acc/cuda/cuda_failure_state.h"
#include "src/acc/cuda/cuda_scoped_resources.h"

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

    // The mirror image, and the one that caught a regression introduced by the first
    // version of this fix. The session records the FIRST failure, so a benign early
    // allocation miss on one patch stays recorded for the rest of the movie. If the
    // recorded status were preferred unconditionally, a fatal fault on a LATER patch --
    // still sticky in the pending slot -- would be invisible and retried. Either source
    // alone must be able to force FATAL.
    {cudaErrorMemoryAllocation, CUFFT_SUCCESS, cudaErrorIllegalAddress, CUDA_RETRY_FATAL,
     "a benign recorded failure must not mask a fatal code still pending"},
    {cudaErrorMemoryAllocation, CUFFT_SUCCESS, cudaErrorLaunchFailure, CUDA_RETRY_FATAL,
     "same, for a launch failure pending behind a recorded allocation miss"},

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
        // No sticky fatal in this table; the sticky dimension is covered by the
        // session-state sequences below, which drive the production object.
        const CudaRetryDecision d =
            cudaRetryDecisionFor(c.recorded, cudaSuccess, c.recorded_cufft, c.pending);
        const CudaRetryVerdict got = d.verdict;
        // The decisive code must be one the caller can meaningfully report, and on a
        // fatal verdict it must be the code that actually forced it.
        if (got == CUDA_RETRY_FATAL && !cudaErrorPoisonsContext(d.decisive)) {
            std::printf("FAIL decisive code %s does not itself poison the context (%s)\n",
                        cudaGetErrorName(d.decisive), c.why);
            ++failures;
        }
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


// ---------------------------------------------------------------------------------
// Production session-state regressions (PR107 review P1).
//
// These drive the REAL CudaFailureState that CudaMovieSession holds, through ordered
// failure sequences, rather than feeding synthetic inputs to the predicate. That
// distinction is the point: the defect was not in the predicate, it was that the
// session discarded a later fatal error, so a predicate-only test could not see it.
//
// No CUDA call is made anywhere here -- CudaFailureState is pure host state.
// ---------------------------------------------------------------------------------
int runSessionStateSequences() {
    int failures = 0;

    auto check = [&failures](bool ok, const char *what) {
        if (!ok) { std::printf("FAIL session-state: %s\n", what); ++failures; }
    };

    {
        // THE regression. A recoverable allocation miss is recorded on an early patch
        // and retried successfully. A later patch faults; its handler CONSUMES the
        // fatal code (so the thread's last-error slot is clear afterwards) and records
        // it. Under the old first-wins-only rule the record was discarded and the
        // verdict saw neither source -> retry on a dead context.
        CudaFailureState state;
        state.record(cudaErrorMemoryAllocation, "preparePatchInVram", 700);
        state.record(cudaErrorIllegalAddress, "preparePatchInVram", 742);
        const CudaRetryDecision d = cudaRetryDecisionFor(state, cudaSuccess);
        check(d.verdict == CUDA_RETRY_FATAL,
              "recoverable then consumed fatal then cleared slot must be FATAL");
        check(d.decisive == cudaErrorIllegalAddress,
              "the fatal code must be the decisive one");
        // Diagnostic provenance is still the first failure; poisoning provenance is
        // the fatal one. Both are preserved, which is what makes the message honest.
        check(state.firstError() == cudaErrorMemoryAllocation,
              "first-failure provenance must survive the later fatal record");
        check(state.firstLine() == 700, "first-failure line must be the early one");
        check(state.fatalError() == cudaErrorIllegalAddress, "fatal must be latched");
        check(state.fatalLine() == 742, "fatal line must be the faulting one");
        check(state.isPoisoned(), "state must report poisoned");
    }
    {
        // Monotonic the other way round: a fatal first, then recoverable noise, must
        // not un-poison, and must not have its provenance overwritten.
        CudaFailureState state;
        state.record(cudaErrorLaunchFailure, "computeGlobalForwardFFT", 611);
        state.record(cudaErrorMemoryAllocation, "preparePatchInVram", 700);
        state.record(cudaErrorInvalidValue, "updateDefectPixels", 580);
        const CudaRetryDecision d = cudaRetryDecisionFor(state, cudaSuccess);
        check(d.verdict == CUDA_RETRY_FATAL, "a latched fatal must never be cleared");
        check(state.fatalLine() == 611, "the FIRST fatal must be kept, not the last");
        check(state.firstError() == cudaErrorLaunchFailure,
              "first failure was itself the fatal one");
    }
    {
        // The supported recoverable path must stay permitted, or every ordinary OOM
        // starts aborting movies.
        CudaFailureState state;
        state.record(cudaErrorMemoryAllocation, "preparePatchInVram", 700);
        const CudaRetryDecision d = cudaRetryDecisionFor(state, cudaSuccess);
        check(d.verdict == CUDA_RETRY_PERMITTED, "recoverable only must stay permitted");
        check(!state.isPoisoned(), "recoverable must not mark the state poisoned");
    }
    {
        // A cuFFT failure occupies the first-failure slot but cannot poison; a CUDA
        // fatal recorded afterwards must still latch and decide.
        CudaFailureState state;
        state.recordCufft(CUFFT_EXEC_FAILED, "preparePatchInVram", 745);
        const CudaRetryDecision permitted = cudaRetryDecisionFor(state, cudaSuccess);
        check(permitted.verdict == CUDA_RETRY_PERMITTED,
              "a cuFFT failure alone must not be fatal");
        state.record(cudaErrorECCUncorrectable, "computeGlobalInverseFFT", 660);
        const CudaRetryDecision fatal = cudaRetryDecisionFor(state, cudaSuccess);
        check(fatal.verdict == CUDA_RETRY_FATAL,
              "a fatal recorded after a cuFFT failure must still latch");
        check(state.firstCufftError() == CUFFT_EXEC_FAILED,
              "cuFFT provenance must survive");
    }
    {
        CudaFailureState state;
        const CudaRetryDecision d = cudaRetryDecisionFor(state, cudaSuccess);
        check(d.verdict == CUDA_RETRY_PERMITTED, "a clean session must be permitted");
        check(!state.hasFailed() && !state.isPoisoned(), "clean state must report clean");
    }
    {
        // THE fallback-boundary case (PR107 discussion_r4119570895). Ordered exactly as
        // the production path orders it:
        //   1. the resident attempt is nonconverged, or fails recoverably, so the
        //      session state holds at most a non-fatal code;
        //   2. the health check at that point therefore PERMITS the fallback -- and it
        //      must, because nothing fatal has happened yet;
        //   3. the fallback cudaPreparePatch then hits a fatal fault, consumes it, and
        //      returns false, leaving the thread's last-error slot CLEARED;
        //   4. alignPatch() would re-dispatch CUDA because use_gpu is set.
        // The check after step 3 must refuse, using the status carried out of the
        // helper. A session-state or last-error check alone cannot see it: the session
        // never saw this failure, and the slot is empty.
        CudaFailureState resident;                       // step 1
        resident.record(cudaErrorMemoryAllocation, "preparePatchInVram", 700);
        const CudaRetryDecision before = cudaRetryDecisionFor(resident, cudaSuccess);
        check(before.verdict == CUDA_RETRY_PERMITTED,
              "the pre-fallback check must permit; nothing fatal has happened yet");   // step 2

        CudaFailureState fallback;                       // step 3, a SEPARATE state
        fallback.record(cudaErrorIllegalAddress, "cudaPreparePatch", 361);
        const CudaRetryDecision after = cudaRetryDecisionFor(fallback, cudaSuccess);
        check(after.verdict == CUDA_RETRY_FATAL,
              "the post-fallback check must refuse the CUDA re-dispatch");             // step 4
        check(after.decisive == cudaErrorIllegalAddress,
              "the refusal must name the code the fallback consumed");
        check(fallback.fatalStage() != nullptr && fallback.fatalLine() == 361,
              "the consumed failure's own provenance must be preserved, not the resident one");

        // Discrimination: the resident state must NOT be what drives this, and a
        // last-error read must not be either -- both are clean at this point.
        check(cudaRetryDecisionFor(resident, cudaSuccess).verdict == CUDA_RETRY_PERMITTED,
              "the resident state alone must still read permitted, proving the refusal "
              "came from the carried fallback status and not from the session");
        check(cudaErrorPoisonsContext(cudaSuccess) == false,
              "a cleared last-error slot alone must never justify a fatal verdict");
    }
    {
        // The mirror: a fallback preparation that fails RECOVERABLY must still permit
        // the host path, or an ordinary allocation miss during fallback would start
        // aborting movies.
        CudaFailureState fallback;
        fallback.record(cudaErrorMemoryAllocation, "cudaPreparePatch", 361);
        check(cudaRetryDecisionFor(fallback, cudaSuccess).verdict == CUDA_RETRY_PERMITTED,
              "a recoverable fallback-preparation failure must still permit the host path");
    }
    {
        // Nothing recorded, fatal still pending: the slot is then the only evidence.
        CudaFailureState state;
        const CudaRetryDecision d = cudaRetryDecisionFor(state, cudaErrorIllegalAddress);
        check(d.verdict == CUDA_RETRY_FATAL, "pending fatal with no record must be FATAL");
    }

    std::printf("8 session-state sequences, %d failures\n", failures);
    return failures;
}

// ---------------------------------------------------------------------------------
// Capacity and error controls for the fixed-size scoped owners (PR107 review P2).
// Null slots are skipped by releaseAll, so this exercises counting, capacity refusal
// and idempotency without making a single CUDA call.
// ---------------------------------------------------------------------------------
int runCapacityControls() {
    int failures = 0;
    auto check = [&failures](bool ok, const char *what) {
        if (!ok) { std::printf("FAIL capacity: %s\n", what); ++failures; }
    };

    {
        mc_cuda::ScopedDeviceMemory<8> owner;
        for (int i = 0; i < 8; ++i) check(owner.add(nullptr), "add within capacity must succeed");
        check(owner.count() == 8, "count must track the registrations");
        check(!owner.overflowed(), "a full-but-not-over registry must not report overflow");
        check(!owner.add(nullptr), "add beyond capacity must refuse");
        check(owner.overflowed(), "refusal must set the overflow flag, not drop silently");
        check(owner.count() == 8, "a refused add must not grow the count");
        check(owner.releaseAll() == cudaSuccess, "release of null slots must succeed");
        check(owner.count() == 0, "release must reset the count");
        check(owner.releaseAll() == cudaSuccess, "release must be idempotent");
    }
    {
        mc_cuda::ScopedCudaEvents<8> owner;
        for (int i = 0; i < 8; ++i) check(owner.add(nullptr), "event add within capacity");
        check(!owner.add(nullptr), "event add beyond capacity must refuse");
        check(owner.overflowed(), "event overflow must be reported");
        check(owner.count() == 8, "refused event add must not grow the count");
    }
    {
        // The wrapper's registry holds exactly one.
        mc_cuda::ScopedDeviceMemory<1> owner;
        check(owner.add(nullptr), "single-slot add must succeed");
        check(!owner.add(nullptr), "second add must refuse");
        check(owner.overflowed(), "single-slot overflow must be reported");
    }

    std::printf("3 capacity controls, %d failures\n", failures);
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
    failures += runSessionStateSequences();
    failures += runCapacityControls();
    if (failures) return 1;
    std::printf("PASS classifier separates poisoned-context codes from recoverable ones,\n"
                "     and a fatal error already consumed by a helper -- leaving the\n"
                "     last-error slot clear -- still refuses the retry, while a recorded\n"
                "     recoverable allocation failure still permits the supported path.\n"
                "     A later fatal error is latched monotonically by the production\n"
                "     session state even when an earlier recoverable one was recorded\n"
                "     and the last-error slot has since been cleared. A fatal error\n"
                "     consumed by the FALLBACK preparation, after a permitted\n"
                "     pre-fallback check and with the slot cleared, also refuses the\n"
                "     CUDA re-dispatch.\n"
                "     These cover the predicates only; no real poisoned context is\n"
                "     synthesised anywhere in this suite, and no device is used.\n");
    return 0;
}
