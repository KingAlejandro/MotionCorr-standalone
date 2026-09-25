#ifdef FFTW_LOCK_STATS
#include "src/jaz/single_particle/fftw_lock_stats.h"
#include <cstdio>

namespace FFTWLockStats {
	std::atomic<long long> wait_ns_create(0), held_ns_create(0), n_create(0);
	std::atomic<long long> wait_ns_destroy(0), held_ns_destroy(0), n_destroy(0);
	std::atomic<long long> max_wait_ns(0);

	void dump() {
		std::fprintf(stderr,
			"\n=== FFTW_LOCK_STATS (critical(FourierTransformer_fftw_plan)) ===\n"
			"plan_create   : n=%lld  wait=%.4f s  held=%.4f s\n"
			"plan_destroy  : n=%lld  wait=%.4f s  held=%.4f s\n"
			"TOTAL         : n=%lld  wait=%.4f s  held=%.4f s  (wait+held=%.4f s)\n"
			"max_single_wait: %.6f s\n"
			"=== END FFTW_LOCK_STATS ===\n",
			n_create.load(), wait_ns_create.load()/1e9, held_ns_create.load()/1e9,
			n_destroy.load(), wait_ns_destroy.load()/1e9, held_ns_destroy.load()/1e9,
			n_create.load()+n_destroy.load(),
			(wait_ns_create.load()+wait_ns_destroy.load())/1e9,
			(held_ns_create.load()+held_ns_destroy.load())/1e9,
			(wait_ns_create.load()+wait_ns_destroy.load()+held_ns_create.load()+held_ns_destroy.load())/1e9,
			max_wait_ns.load()/1e9);
	}

	struct Dumper { ~Dumper() { dump(); } };
	static Dumper the_dumper;
}
#endif
