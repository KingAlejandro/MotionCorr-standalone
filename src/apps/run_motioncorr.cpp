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

/* Host allocator policy (docs/host_buffer_reuse.md).
 *
 * Default: unchanged glibc behaviour. Full-frame per-movie buffers are reused
 * through a bounded, scoped pool instead (src/frame_buffer_pool.h), so no
 * process-wide allocator setting is needed and other allocations, including
 * per-frame movie storage, keep their normal release behaviour.
 *
 * MOTIONCORR_MALLOC_REUSE=1 opts in to raising glibc's mmap and trim
 * thresholds to 512 MiB. That keeps every large freed allocation in the heap
 * (including float movie frames), which can retain hundreds of MB that
 * M_TRIM_THRESHOLD does not cap: it only triggers trimming of the top-most
 * free chunk. It is kept for measurement and for hosts that want it.
 *  - glibc < 2.35 refuses a mmap threshold above 32 MiB, and any successful
 *    setter disables the dynamic threshold. So the mmap threshold is set first,
 *    and if it is refused nothing else is touched.
 *  - Never applied over user settings (MALLOC_MMAP_THRESHOLD_,
 *    MALLOC_TRIM_THRESHOLD_, GLIBC_TUNABLES).
 */
static const char *configureHostAllocator()
{
#if defined(__GLIBC__)
	const char *opt = getenv("MOTIONCORR_MALLOC_REUSE");
	if (opt == NULL || !(opt[0] == '1' && opt[1] == '\0'))
		return "glibc defaults; full-frame buffers pooled";
	if (getenv("MALLOC_MMAP_THRESHOLD_") || getenv("MALLOC_TRIM_THRESHOLD_") || getenv("GLIBC_TUNABLES"))
		return "user malloc settings kept; full-frame buffers pooled";
	const int threshold = 512 << 20;
	if (mallopt(M_MMAP_THRESHOLD, threshold) != 1)
		return "glibc defaults (this glibc refuses a mmap threshold above 32 MiB); full-frame buffers pooled";
	if (mallopt(M_TRIM_THRESHOLD, threshold) != 1)
		return "mmap threshold raised (MOTIONCORR_MALLOC_REUSE); trim threshold unchanged";
	return "mmap/trim thresholds raised (MOTIONCORR_MALLOC_REUSE)";
#else
	return "platform allocator defaults; full-frame buffers pooled";
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
