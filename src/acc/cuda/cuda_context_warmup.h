/***************************************************************************
 * One-time CUDA context creation on a helper thread.
 *
 * The first CudaMovieSession::initialize() of a process pays for creating the
 * device's primary context (~150 ms on an A100) on the critical path, although
 * nothing in the host-side setup before it depends on the device. ContextWarmup
 * runs `cudaSetDevice(d); cudaFree(0)` on another thread while that host setup
 * proceeds.
 *
 * The contract (docs/multi_gpu/startup_costs/context_warmup.md):
 *  - It may only do what the main thread would do anyway. Its outcome is
 *    information; it never gates, skips or redirects anything on the main
 *    thread, which performs its own cudaGetDeviceCount/cudaSetDevice/... exactly
 *    as it would without a warm-up.
 *  - Nothing crosses the thread boundary except the Outcome: no exception, no
 *    CUDA last-error slot (that is per-thread and dies with the thread).
 *  - The thread is joined on every path: join() is idempotent and the
 *    destructor joins, so unwinding a REPORT_ERROR out of the owner cannot reach
 *    a joinable std::thread (an unconditional std::terminate).
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef CUDA_CONTEXT_WARMUP_H_
#define CUDA_CONTEXT_WARMUP_H_

#include <cuda_runtime.h>
#include <functional>
#include <string>
#include <thread>

namespace mc_cuda {

class ContextWarmup {
public:
    struct Outcome {
        bool started = false;     // a helper thread ran the operation
        bool threw = false;       // the operation threw; captured, not propagated
        cudaError_t error = cudaSuccess;  // what the operation returned
        std::string what;         // exception text when threw
        // Helper-thread cost of the operation, for --profile.
        double wall_ms = 0, cpu_ms = 0;
        long minflt = 0;
        bool ok() const { return started && !threw && error == cudaSuccess; }
    };

    // Takes the device id; returns the CUDA status of the work it did.
    using Operation = std::function<cudaError_t(int device_id)>;

    // cudaSetDevice(device_id) then cudaFree(0): the idiom that creates the
    // primary context. The only operation production starts.
    static cudaError_t createPrimaryContext(int device_id);

    ContextWarmup() = default;
    ContextWarmup(const ContextWarmup &) = delete;
    ContextWarmup &operator=(const ContextWarmup &) = delete;
    ~ContextWarmup();

    // Launches the helper thread. noexcept: if no thread can be created the
    // warm-up simply does not happen and join() reports started == false.
    // Starting twice is a no-op.
    void start(int device_id, Operation op = &ContextWarmup::createPrimaryContext) noexcept;

    // Waits for the helper thread. Idempotent and noexcept. The returned
    // reference stays valid for the object's lifetime.
    const Outcome &join() noexcept;

    bool joined() const { return !thread_.joinable(); }

private:
    std::thread thread_;
    bool launched_ = false;
    Outcome outcome_;
};

}  // namespace mc_cuda

#endif  // CUDA_CONTEXT_WARMUP_H_
