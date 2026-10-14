// Device-free controls for mc_cuda::ContextWarmup, the helper thread that
// creates the CUDA primary context while host setup runs.
//
// The operation is injected, so no GPU is needed: what is under test is the
// thread contract, not the CUDA call. The end-to-end behaviour of the real
// runner under a failed or slow warm-up is tests/run_warmup_failure_controls.py.
//
//   cuda_context_warmup                  all checks must pass
//   cuda_context_warmup --expect-mismatch  exit 0 only if a check fails (compiled mutants)
#include "src/acc/cuda/cuda_context_warmup.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

using mc_cuda::ContextWarmup;

namespace {
int g_failures = 0;
void check(bool ok, const char *what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++g_failures;
    }
}
void sleepMs(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

void successRunsOnceOffThread() {
    std::atomic<int> calls{0};
    std::thread::id op_thread;
    int seen_device = -1;
    ContextWarmup warm;
    warm.start(3, [&](int device) {
        ++calls;
        op_thread = std::this_thread::get_id();
        seen_device = device;
        sleepMs(20);
        return cudaSuccess;
    });
    const ContextWarmup::Outcome &out = warm.join();
    check(out.started && out.ok(), "success: outcome ok");
    check(calls == 1, "success: operation ran exactly once");
    check(op_thread != std::this_thread::get_id(), "success: operation ran off the calling thread");
    check(seen_device == 3, "success: operation got the device id");
    check(out.wall_ms >= 15, "success: wall time recorded for the helper");
    check(warm.joined(), "success: joined after join()");
    // Idempotent, same outcome, no second run.
    const ContextWarmup::Outcome &again = warm.join();
    check(&again == &out && calls == 1, "join twice: same outcome, no second run");
    warm.start(3, [&](int) { ++calls; return cudaSuccess; });
    check(calls == 1, "start twice: second start is a no-op");
}

void errorStatusIsRecordedNotRaised() {
    ContextWarmup warm;
    warm.start(0, [](int) { return cudaErrorMemoryAllocation; });
    bool raised = false;
    try { warm.join(); } catch (...) { raised = true; }
    const ContextWarmup::Outcome &out = warm.join();
    check(!raised, "error: join does not throw");
    check(out.started && !out.threw, "error: ran, did not throw");
    check(out.error == cudaErrorMemoryAllocation, "error: status carried to the outcome");
    check(!out.ok(), "error: outcome is not ok");
}

void exceptionsStayOnTheHelper() {
    {
        ContextWarmup warm;
        warm.start(0, [](int) -> cudaError_t { throw std::runtime_error("boom"); });
        const ContextWarmup::Outcome &out = warm.join();
        check(out.threw && out.what == "boom" && !out.ok(), "throw: std::exception captured with its text");
    }
    {
        ContextWarmup warm;
        warm.start(0, [](int) -> cudaError_t { throw 7; });
        const ContextWarmup::Outcome &out = warm.join();
        check(out.threw && !out.ok(), "throw: non-std exception captured");
    }
}

void neverStartedIsHarmless() {
    ContextWarmup warm;
    const ContextWarmup::Outcome &out = warm.join();
    check(!out.started && !out.ok() && warm.joined(), "never started: join is a no-op, not ok");
}

// Stack unwinding out of the owner while the helper is still running must join
// it. Run in a child: destroying a joinable std::thread is std::terminate, and
// the parent has to observe that rather than die with it.
int unwindChild() {
    std::atomic<bool> finished{false};
    try {
        ContextWarmup warm;
        warm.start(0, [&](int) { sleepMs(200); finished = true; return cudaSuccess; });
        throw std::runtime_error("REPORT_ERROR unwinding past a running warm-up");
    } catch (const std::runtime_error &) {
        // The helper's lambda captured `finished` by reference; reading it here is
        // only defined because the destructor joined before we got here.
        return finished ? 0 : 3;
    }
}

void destructorJoinsOnUnwind() {
    const pid_t pid = fork();
    if (pid == 0) _exit(unwindChild());
    int status = 0;
    waitpid(pid, &status, 0);
    check(WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "unwind: the destructor joined the running helper before the handler ran");
}

void joinWaitsForTheOperation() {
    std::atomic<bool> done{false};
    ContextWarmup warm;
    warm.start(0, [&](int) { sleepMs(100); done = true; return cudaSuccess; });
    warm.join();
    check(done, "join returns only after the operation finished");
}
}  // namespace

int main(int argc, char **argv) {
    const bool expect_mismatch = argc > 1 && std::strcmp(argv[1], "--expect-mismatch") == 0;
    successRunsOnceOffThread();
    errorStatusIsRecordedNotRaised();
    exceptionsStayOnTheHelper();
    neverStartedIsHarmless();
    destructorJoinsOnUnwind();
    joinWaitsForTheOperation();
    if (expect_mismatch) {
        std::printf("%s: %d check(s) failed as the mutant should\n", g_failures ? "OK" : "MUTANT SURVIVED",
                    g_failures);
        return g_failures ? 0 : 1;
    }
    if (g_failures) return 1;
    std::printf("PASS context warm-up contract\n");
    return 0;
}
