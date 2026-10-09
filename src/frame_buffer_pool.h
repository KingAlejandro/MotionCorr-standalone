/***************************************************************************
 * Bounded reuse of full-frame float buffers across movies.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef FRAME_BUFFER_POOL_H_
#define FRAME_BUFFER_POOL_H_

#include <cstddef>
#include <mutex>
#include <vector>

#include "src/multidim_array.h"

/** A small, bounded pool of full-frame float buffers.
 *
 * A full micrograph is tens of MB, above glibc's mmap threshold, so each
 * per-movie host sum or reconstruction buffer was a fresh anonymous mapping:
 * faulted and zeroed by the kernel 4 KiB at a time, then unmapped, on every
 * movie (--profile: ~32 ms per buffer per movie on the tutorial). Retaining
 * a few such buffers avoids that without changing the allocator for the
 * whole process (#155 review).
 *
 * - **Scope.** Only buffers explicitly passed through acquire()/release() are
 *   pooled. Everything else, including per-frame movie storage, keeps the
 *   default allocator behaviour.
 * - **Bound.** At most `capacity` buffers are retained, each exactly the size
 *   of a frame acquire() has been asked for. When the geometry changes, a
 *   release of the current size into a full pool evicts an older size. A release beyond capacity, or of
 *   any other size (an image binned after acquisition, say), frees normally,
 *   so retained bytes never exceed capacity * largest requested frame, and
 *   every retained buffer can be reused.
 * - **Contents.** acquire() returns uninitialised memory, exactly like a
 *   fresh allocation; every caller already zeroes or overwrites it.
 * - **Thread safety.** release() may be called from the output writer
 *   thread; a mutex guards the free list.
 */
class FrameBufferPool
{
public:
	static FrameBufferPool &instance();

	/** Make @p array an uninitialised ny x nx buffer, reusing a retained one
	 * of the same size if available. Replaces whatever @p array held. */
	void acquire(MultidimArray<float> &array, long int ny, long int nx);

	/** Take @p array's buffer back into the pool if there is room and it is
	 * pool-compatible; otherwise free it. @p array is left empty. */
	void release(MultidimArray<float> &array);

	/** Retained bytes, for diagnostics and tests. */
	size_t retainedBytes() const;
	size_t retainedCount() const;

	/** Disable pooling (acquire allocates, release frees). For A/B tests. */
	void setEnabled(bool value);
	bool enabled() const;

	/** Free everything retained. */
	void clear();

	~FrameBufferPool();

private:
	FrameBufferPool();
	FrameBufferPool(const FrameBufferPool &) = delete;
	FrameBufferPool &operator=(const FrameBufferPool &) = delete;

	struct Buffer { float *data; size_t elements; };
	mutable std::mutex mutex;
	std::vector<Buffer> free_list;
	// Element counts acquire() has been asked for. release() only retains a
	// buffer of one of these sizes: anything else (for example an image binned
	// after acquisition) can never be handed out again and would only occupy
	// a slot. Bounded by the number of distinct geometries in a run.
	std::vector<size_t> requested;
	size_t capacity;
	// The geometry acquire() was most recently asked for. Releasing a buffer
	// of this size into a full pool evicts a retained buffer of another size,
	// so a geometry change mid-run does not leave the pool full of buffers no
	// acquisition can use.
	size_t last_requested;
	bool on;
	bool poison;
};

#endif
