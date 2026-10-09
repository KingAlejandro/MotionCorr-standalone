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
 * glibc serves allocations above its mmap threshold from a fresh anonymous
 * mapping and unmaps them on free. The dynamic threshold stops adapting at
 * 32 MiB, and a full micrograph here is 57 MiB, so every movie re-faulted and
 * re-zeroed each such buffer 4 KiB at a time on the main thread while the GPU
 * waited (--profile: ~45 ms per buffer per movie, 13.9k minor faults each).
 *
 * Raising the mmap and trim thresholds lets a freed buffer be reused by the next
 * movie. Two glibc facts constrain how:
 *  - Before 2.35, M_MMAP_THRESHOLD above HEAP_MAX_SIZE/2 (32 MiB on 64-bit) is
 *    rejected with 0. Any successful mallopt setter also disables the dynamic
 *    threshold, so setting only the trim threshold there would pin the mmap
 *    threshold at 128 KiB and make things worse. So the mmap threshold is set
 *    first, and if it is refused nothing else is touched.
 *  - Setting it disables the dynamic threshold process-wide. That is the
 *    intended behaviour here: large buffers stay in the heap.
 * The value covers the largest single full-frame float buffer expected (K3
 * super-resolution 11520x8184 is 377 MB; EER 8K at 4x is 268 MB). Each frame of
 * a float movie is one such buffer, so the whole stack is heap-served too; the
 * compact and nvCOMP ingest paths do not hold a host float movie.
 * Contents are unaffected: every buffer is initialised by the code that uses it,
 * which tests/test_host_buffer_reuse.py checks with MALLOC_PERTURB_.
 *
 * Skipped when MOTIONCORR_MALLOC_DEFAULTS is set to anything but 0/empty, or when
 * the user already chose malloc settings (MALLOC_MMAP_THRESHOLD_,
 * MALLOC_TRIM_THRESHOLD_ or GLIBC_TUNABLES), which this must not override.
 */
static const char *configureHostAllocator()
{
#if defined(__GLIBC__)
	const char *keep = getenv("MOTIONCORR_MALLOC_DEFAULTS");
	if (keep != NULL && keep[0] != '\0' && !(keep[0] == '0' && keep[1] == '\0'))
		return "glibc defaults (MOTIONCORR_MALLOC_DEFAULTS)";
	if (getenv("MALLOC_MMAP_THRESHOLD_") || getenv("MALLOC_TRIM_THRESHOLD_") || getenv("GLIBC_TUNABLES"))
		return "user malloc settings kept";
	const int threshold = 512 << 20;
	if (mallopt(M_MMAP_THRESHOLD, threshold) != 1)
		return "glibc defaults (this glibc refuses a mmap threshold above 32 MiB)";
	if (mallopt(M_TRIM_THRESHOLD, threshold) != 1)
		return "mmap threshold raised; trim threshold unchanged";
	return "full-frame host buffers reused across movies";
#else
	return "platform allocator defaults";
#endif
}

int main(int argc, char *argv[])
{
	const char *allocator_mode = configureHostAllocator();
	MotioncorrRunner prm;
	prm.host_allocator_mode = allocator_mode;

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
