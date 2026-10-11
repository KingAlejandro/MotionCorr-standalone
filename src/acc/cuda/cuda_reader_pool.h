#ifndef CUDA_READER_POOL_H_
#define CUDA_READER_POOL_H_

#include <condition_variable>
#include <functional>
#include <mutex>
#include <system_error>
#include <thread>
#include <vector>

namespace mc_cuda {

/**
 * A small team of host threads that sleeps between jobs.
 *
 * The nvCOMP ingest reads one chunk of the movie per job while the GPU decodes
 * the previous chunk. It used to open an OpenMP parallel region per chunk.
 * libgomp keeps a team's threads busy-waiting after a region ends
 * (GOMP_SPINCOUNT, 300000 iterations by default, unbounded under
 * OMP_WAIT_POLICY=active), so on an 8-CPU lane the idle readers competed with the
 * thread that submits GPU work and strip read grew by 5-11 ms per chunk;
 * OMP_WAIT_POLICY=passive recovered it (docs/nvcomp_ingest_pipeline.md).
 * These threads block on a condition variable between jobs, so they use no CPU
 * while the GPU works, whatever the process-wide wait policy is.
 *
 * runTeam(f) calls f(tid) once on every thread of the team, tid 0 being the
 * caller, and returns when all of them are done. It returns false if any call
 * threw. One caller issues jobs one at a time. The destructor joins every
 * helper. Header-only and device-free so it can be tested without a GPU.
 */
class ChunkReaderPool {
public:
    explicit ChunkReaderPool(int threads) {
        const int want = threads > 1 ? threads : 1;
        try {
            for (int tid = 1; tid < want; tid++)
                helpers_.emplace_back([this, tid] { helperLoop(tid); });
        } catch (const std::system_error &) {
            // Fewer threads than asked is a slower team, not a failed one.
        }
    }
    ~ChunkReaderPool() {
        {
            std::lock_guard<std::mutex> lock(m_);
            stop_ = true;
        }
        cv_work_.notify_all();
        for (auto &t : helpers_) t.join();
    }
    ChunkReaderPool(const ChunkReaderPool &) = delete;
    ChunkReaderPool &operator=(const ChunkReaderPool &) = delete;

    /** Team size including the caller. */
    int threads() const { return (int)helpers_.size() + 1; }

    bool runTeam(const std::function<void(int)> &f) {
        {
            std::lock_guard<std::mutex> lock(m_);
            job_ = &f;
            pending_ = (int)helpers_.size();
            failed_ = false;
            generation_++;
        }
        cv_work_.notify_all();
        bool caller_ok = true;
        try { f(0); } catch (...) { caller_ok = false; }
        std::unique_lock<std::mutex> lock(m_);
        cv_done_.wait(lock, [this] { return pending_ == 0; });
        // job_ is left pointing at f: a helper reads it only after a new generation,
        // and every generation sets it first.
        return caller_ok && !failed_;
    }

private:
    void helperLoop(int tid) {
        unsigned seen = 0;
        for (;;) {
            const std::function<void(int)> *job = nullptr;
            {
                std::unique_lock<std::mutex> lock(m_);
                cv_work_.wait(lock, [&] { return stop_ || generation_ != seen; });
                if (stop_) return;
                seen = generation_;
                job = job_;
            }
            bool ok = true;
            try { (*job)(tid); } catch (...) { ok = false; }
            {
                std::lock_guard<std::mutex> lock(m_);
                if (!ok) failed_ = true;
                if (--pending_ == 0) cv_done_.notify_one();
            }
        }
    }

    std::vector<std::thread> helpers_;
    std::mutex m_;
    std::condition_variable cv_work_, cv_done_;
    const std::function<void(int)> *job_ = nullptr;
    unsigned generation_ = 0;
    int pending_ = 0;
    bool failed_ = false;
    bool stop_ = false;
};

} // namespace mc_cuda

#endif
