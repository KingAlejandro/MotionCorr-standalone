/* Issue #26 diagnostic instrumentation: measure the real cost of
   #pragma omp critical(FourierTransformer_fftw_plan).
   Enabled only when FFTW_LOCK_STATS is defined. Not for production builds. */
#ifndef FFTW_LOCK_STATS_H
#define FFTW_LOCK_STATS_H

#ifdef FFTW_LOCK_STATS
#include <atomic>
#include <cstdio>
#include <omp.h>

namespace FFTWLockStats {
	extern std::atomic<long long> wait_ns_create, held_ns_create, n_create;
	extern std::atomic<long long> wait_ns_destroy, held_ns_destroy, n_destroy;
	extern std::atomic<long long> max_wait_ns;

	inline void add(double a, double b, double c, int is_create) {
		long long w = (long long)((b - a) * 1e9);
		long long h = (long long)((c - b) * 1e9);
		if (is_create) {
			wait_ns_create += w; held_ns_create += h; n_create += 1;
		} else {
			wait_ns_destroy += w; held_ns_destroy += h; n_destroy += 1;
		}
		long long prev = max_wait_ns.load();
		while (w > prev && !max_wait_ns.compare_exchange_weak(prev, w)) {}
	}
	void dump();
}

#define FLS_WAIT_BEGIN() double _fls_a = omp_get_wtime()
#define FLS_ENTER()      double _fls_b = omp_get_wtime()
#define FLS_EXIT(create) do { double _fls_c = omp_get_wtime(); \
                              FFTWLockStats::add(_fls_a, _fls_b, _fls_c, (create)); } while (0)
#else
#define FLS_WAIT_BEGIN() do {} while (0)
#define FLS_ENTER()      do {} while (0)
#define FLS_EXIT(create) do {} while (0)
#endif

#endif
