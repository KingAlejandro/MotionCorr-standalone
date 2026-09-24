/***************************************************************************
 *
 * Host stage-boundary tracer for MotionCorr performance investigation.
 *
 * Compiled out entirely unless MC_STAGE_TRACE is defined, so production
 * builds are byte-identical to an untraced build. When enabled, each mark
 * costs one clock_gettime(CLOCK_MONOTONIC) (vDSO) plus two stores into a
 * fixed, preallocated array: no locking, no allocation, no I/O until exit.
 *
 * Marks record only host wall-clock boundaries. They do not synchronise
 * CUDA, so an interval may overlap asynchronous device work.
 *
 * NOT thread safe. The mark buffer and its counter are unsynchronised
 * function-local statics, so a mark placed inside an OpenMP region would race.
 * Place marks on either side of a parallel region, never within one.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 ***************************************************************************/
#ifndef MOTIONCORR_STAGE_TRACE_H
#define MOTIONCORR_STAGE_TRACE_H

#ifdef MC_STAGE_TRACE

#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace mc_stage_trace
{
	static const int MAX_MARKS = 512;

	struct Mark
	{
		const char *name;
		double t;
	};

	// Zero-initialised static storage: no dynamic allocation on the traced path.
	inline Mark *marks()
	{
		static Mark storage[MAX_MARKS];
		return storage;
	}

	inline int &count()
	{
		static int n = 0;
		return n;
	}

	inline bool &overflowed()
	{
		static bool over = false;
		return over;
	}

	inline double now()
	{
		struct timespec ts;
		clock_gettime(CLOCK_MONOTONIC, &ts);
		return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
	}

	inline void mark(const char *name);

	// Dump to the path in MC_STAGE_TRACE_OUT, else to stderr. Called once at exit.
	inline void dump()
	{
		mark("atexit_dump");
		const int n = count();
		if (n == 0) return;
		const char *path = getenv("MC_STAGE_TRACE_OUT");
		FILE *out = stderr;
		bool close_out = false;
		if (path != NULL && path[0] != '\0')
		{
			FILE *f = fopen(path, "w");
			if (f != NULL) { out = f; close_out = true; }
		}
		const Mark *m = marks();
		const double t0 = m[0].t;
		fprintf(out, "# MC_STAGE_TRACE marks=%d overflowed=%d\n", n, overflowed() ? 1 : 0);
		fprintf(out, "# index\tname\telapsed_since_first_s\tdelta_from_previous_s\n");
		for (int i = 0; i < n; i++)
		{
			const double prev = (i == 0) ? m[0].t : m[i - 1].t;
			fprintf(out, "MC_STAGE\t%d\t%s\t%.6f\t%.6f\n",
			        i, m[i].name, m[i].t - t0, m[i].t - prev);
		}
		fflush(out);
		if (close_out) fclose(out);
	}

	inline void mark(const char *name)
	{
		const int i = count();
		if (i >= MAX_MARKS) { overflowed() = true; return; }
		Mark *m = marks();
		m[i].name = name;
		m[i].t = now();
		count() = i + 1;
	}

	// Install the exit dump on the first mark of the process.
	inline void begin(const char *name)
	{
		atexit(dump);
		mark(name);
	}
}

#define MC_STAGE(name) ::mc_stage_trace::mark(name)
#define MC_STAGE_BEGIN(name) ::mc_stage_trace::begin(name)

#else /* !MC_STAGE_TRACE */

#define MC_STAGE(name) ((void)0)
#define MC_STAGE_BEGIN(name) ((void)0)

#endif /* MC_STAGE_TRACE */

#endif /* MOTIONCORR_STAGE_TRACE_H */
