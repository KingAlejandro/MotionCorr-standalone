#include "src/acc/cuda/cuda_context_warmup.h"
#include "src/stage_profile.h"

#include <exception>
#include <utility>

namespace mc_cuda {

cudaError_t ContextWarmup::createPrimaryContext(int device_id) {
    const cudaError_t set = cudaSetDevice(device_id);
    if (set != cudaSuccess) return set;
    return cudaFree(0);
}

ContextWarmup::~ContextWarmup() { join(); }

void ContextWarmup::start(int device_id, Operation op) noexcept {
    if (launched_) return;
    launched_ = true;
    try {
        // outcome_ is written only by the helper until join(); the join is the
        // happens-before edge that makes it readable afterwards.
        thread_ = std::thread([this, device_id, op = std::move(op)]() {
            const StageProfile::Sample begin = StageProfile::sampleThread();
            outcome_.started = true;
            try {
                outcome_.error = op(device_id);
            } catch (const std::exception &e) {
                outcome_.threw = true;
                outcome_.what = e.what();
            } catch (...) {
                outcome_.threw = true;
                outcome_.what = "unrecognised exception";
            }
            const StageProfile::Sample end = StageProfile::sampleThread();
            outcome_.wall_ms = (end.wall_s - begin.wall_s) * 1e3;
            outcome_.cpu_ms = (end.cpu_s - begin.cpu_s) * 1e3;
            outcome_.minflt = end.minflt - begin.minflt;
        });
    } catch (...) {
        // No thread, so no warm-up. The main thread creates the context itself.
    }
}

const ContextWarmup::Outcome &ContextWarmup::join() noexcept {
    if (thread_.joinable()) {
        try { thread_.join(); } catch (...) {}
    }
    return outcome_;
}

}  // namespace mc_cuda
