// Device-free control for the nvCOMP ingest reader team (cuda_reader_pool.h).
//
// The team replaced a per-chunk OpenMP parallel region whose idle threads spun in
// libgomp between chunks. Two properties matter and neither is visible from a
// correct decode:
//   1. runTeam() runs the job once on every thread and returns only when all of
//      them are done, on every call, and reports a throwing job as failure.
//   2. Helper threads do not burn CPU between jobs. That is the whole reason the
//      class exists, so it is measured: the process CPU time over a quiet period
//      with a live 8-thread team must be a small fraction of 8 threads' worth.
// CMake also compiles this file against two one-line mutants of the header (a
// helper that spins instead of sleeping, and a runTeam that does not wait for the
// helpers); both must fail it.

#include "src/acc/cuda/cuda_reader_pool.h"

#include <sys/resource.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>

static int failures = 0;
static void check(bool cond, const char *what) {
    if (!cond) { std::printf("FAIL: %s\n", what); failures++; }
}

static double cpuSeconds() {
    rusage ru;
    getrusage(RUSAGE_SELF, &ru);
    return ru.ru_utime.tv_sec + ru.ru_stime.tv_sec +
           1e-6 * (ru.ru_utime.tv_usec + ru.ru_stime.tv_usec);
}

// Job state lives in statics: with the no-wait mutant a helper is still running when
// runTeam returns, and it must not write to a dead stack frame, or the mutant would
// end in a SIGSEGV instead of a clean, attributable check failure.
static std::atomic<int> g_hits[8];
static std::atomic<int> g_work;
static std::function<void(int)> g_job = [](int tid) {
    g_hits[tid]++;
    // A little uneven work so that threads finish at different times.
    std::this_thread::sleep_for(std::chrono::microseconds(50 * (tid + 1)));
    g_work++;
};

static void testEveryThreadRunsOnceAndJoins() {
    mc_cuda::ChunkReaderPool pool(8);
    check(pool.threads() == 8, "team size includes the caller");
    for (int round = 0; round < 200; round++) {
        for (auto &h : g_hits) h = 0;
        g_work = 0;
        const bool ok = pool.runTeam(g_job);
        check(ok, "healthy job reports success");
        // Read straight after return: any thread still running here is a bug.
        const int done = g_work.load();
        check(done == 8, "runTeam returned before every thread finished");
        for (int t = 0; t < 8; t++)
            if (done == 8) check(g_hits[t].load() == 1, "each tid runs exactly once per job");
        if (done != 8) {   // let the stragglers finish before the next round
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            if (failures > 3) return;
        }
    }
}

static void testFailureIsReportedAndPoolSurvives() {
    mc_cuda::ChunkReaderPool pool(4);
    check(!pool.runTeam([](int tid) { if (tid == 2) throw std::runtime_error("x"); }),
          "a throwing helper is a failed job");
    check(!pool.runTeam([](int tid) { if (tid == 0) throw std::runtime_error("x"); }),
          "a throwing caller is a failed job");
    std::atomic<int> n(0);
    check(pool.runTeam([&](int) { n++; }) && n.load() == 4,
          "the pool is reusable after a failed job");
}

static void testSingleThread() {
    mc_cuda::ChunkReaderPool pool(1);
    int n = 0;
    check(pool.threads() == 1 && pool.runTeam([&](int tid) { n += 1 + tid; }) && n == 1,
          "a one-thread team runs the job on the caller");
}

static void testIdleHelpersDoNotSpin() {
    mc_cuda::ChunkReaderPool pool(8);
    std::atomic<int> n(0);
    check(pool.runTeam([&](int) { n++; }), "warm-up job");
    const double cpu0 = cpuSeconds();
    const auto t0 = std::chrono::steady_clock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(400));
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    const double cpu = cpuSeconds() - cpu0;
    std::printf("idle 8-thread team: %.3f cpu-s over %.3f s wall\n", cpu, wall);
    // Seven spinning helpers would use about 7 x wall. Sleeping ones use well
    // under a hundredth of that; 0.25 x wall leaves room for a noisy host.
    check(cpu < 0.25 * wall, "idle helpers consumed CPU between jobs");
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    testEveryThreadRunsOnceAndJoins();
    // A pool that does not join leaves helpers running jobs whose captures are gone;
    // stop here with a clean failure rather than let later tests crash on them.
    if (failures) { std::printf("%d failure(s)\n", failures); return 1; }
    testFailureIsReportedAndPoolSurvives();
    testSingleThread();
    testIdleHelpersDoNotSpin();
    if (failures) { std::printf("%d failure(s)\n", failures); return 1; }
    std::printf("reader pool: all checks passed\n");
    return 0;
}
