/***************************************************************************
 *
 * Author: "Sjors H.W. Scheres"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/
#include <exception>
#include <src/motioncorr_runner.h>
#if defined(__GLIBC__)
#include <malloc.h>
#endif

/* Keep full-frame host buffers in the heap across movies (docs/host_buffer_reuse.md).
 *
 * glibc serves any allocation above its mmap threshold from a fresh anonymous
 * mapping and returns it to the kernel on free. The dynamic threshold stops
 * adapting at 32 MiB, and a full micrograph here is 57 MiB, so every movie
 * re-faulted and re-zeroed each such buffer 4 KiB at a time on the main thread
 * while the GPU waited: --profile measured ~45 ms per buffer per movie for the
 * host sum and reconstruction buffers alone, 13.9k minor faults each.
 *
 * Raising the mmap and trim thresholds above the largest per-movie buffer lets
 * a freed buffer be reused by the next movie of the same geometry. Contents are
 * still initialised by the code that allocates them; only where the pages come
 * from changes. A movie-sized frame stack (the --ingest float path) stays above
 * the threshold and keeps its own mapping. Must run before the first large
 * allocation. MOTIONCORR_MALLOC_DEFAULTS=1 keeps glibc's defaults for comparison.
 */
static void configureHostAllocator()
{
#if defined(__GLIBC__)
	const char *keep = getenv("MOTIONCORR_MALLOC_DEFAULTS");
	if (keep != NULL && keep[0] == '1') return;
	const int threshold = 256 << 20;
	(void)mallopt(M_MMAP_THRESHOLD, threshold);
	(void)mallopt(M_TRIM_THRESHOLD, threshold);
#endif
}

int main(int argc, char *argv[])
{
	configureHostAllocator();
	MotioncorrRunner prm;

	try
	{
		prm.read(argc, argv);
		prm.initialise();
		prm.run();
	}
	catch (RelionError XE)
	{
		//prm.usage();
		std::cerr << XE;
		return RELION_EXIT_FAILURE;
	}
	// Without these, anything that is not a RelionError (std::bad_alloc from a
	// 1.37 GB frame buffer, for instance) escapes main and calls std::terminate,
	// so no failure exit code is written and a RELION pipeliner job is left
	// marked Running for ever.
	catch (std::exception &e)
	{
		std::cerr << "ERROR: " << e.what() << std::endl;
		return RELION_EXIT_FAILURE;
	}
	catch (...)
	{
		std::cerr << "ERROR: unrecognised exception" << std::endl;
		return RELION_EXIT_FAILURE;
	}

	return RELION_EXIT_SUCCESS;
}
