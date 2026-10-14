// Link-only witness for the real runner's array-bound CCF plans. Not production
// instrumentation: wrappers deliberately serialize their bookkeeping.
#include <fftw3.h>
#include <omp.h>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>

namespace {
struct Entry { void *input; void *output; unsigned flags; int worker = -1; int executions = 0; bool active = false; };
std::mutex mutex;
std::map<fftwf_plan, Entry> plans;
int reused = 0;
bool failed = false;
struct Finish {
    ~Finish() {
        if (failed || !plans.empty() || reused == 0) {
            std::fprintf(stderr, "CCF lifetime FAIL: reused=%d live=%zu invalid=%d\n", reused, plans.size(), failed);
            std::_Exit(86);
        }
        std::fprintf(stderr, "CCF lifetime PASS: reused=%d live=0\n", reused);
    }
} finish;
}
extern "C" {
fftwf_plan __real_fftwf_plan_dft_c2r(int, const int *, fftwf_complex *, float *, unsigned);
void __real_fftwf_execute_dft_c2r(fftwf_plan, fftwf_complex *, float *);
void __real_fftwf_destroy_plan(fftwf_plan);
fftwf_plan __wrap_fftwf_plan_dft_c2r(int rank, const int *n, fftwf_complex *in, float *out, unsigned flags) {
    auto p = __real_fftwf_plan_dft_c2r(rank, n, in, out, flags);
    std::lock_guard<std::mutex> lock(mutex);
    if (p) plans.emplace(p, Entry{in,out,flags});
    return p;
}
void __wrap_fftwf_execute_dft_c2r(fftwf_plan p, fftwf_complex *in, float *out) {
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto it = plans.find(p);
        if (it == plans.end()) { failed = true; }
        else {
            auto &e = it->second;
            // The tested runner uses array-specific ESTIMATE plans throughout.
            if (e.input != in || e.output != out || e.active ||
                (e.executions && e.worker != omp_get_thread_num()) ||
                e.flags != FFTW_ESTIMATE) failed = true;
            e.worker = omp_get_thread_num(); e.active = true; ++e.executions;
        }
    }
    __real_fftwf_execute_dft_c2r(p,in,out);
    std::lock_guard<std::mutex> lock(mutex);
    auto it=plans.find(p);
    if (it != plans.end()) it->second.active=false;
}
void __wrap_fftwf_destroy_plan(fftwf_plan p) {
    {
        std::lock_guard<std::mutex> lock(mutex);
        auto it=plans.find(p);
        if (it != plans.end()) {
            if (it->second.active) failed=true;
            if (it->second.executions > 1) ++reused;
            plans.erase(it);
        }
    }
    __real_fftwf_destroy_plan(p);
}
}
