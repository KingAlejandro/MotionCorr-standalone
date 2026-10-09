/***************************************************************************
 * Bounded reuse of full-frame float buffers across movies.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#include "src/frame_buffer_pool.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>

namespace {
// Only buffers at least this large are worth retaining: below glibc's mmap
// threshold the heap already recycles them. Smaller releases free normally.
const size_t kMinPooledBytes = (size_t)8 << 20;

// The movie loop needs at most: host unaligned sum, reconstruction (Iref), and
// even/odd sums when requested. Four covers that with one buffer in flight on
// the writer thread.
const size_t kDefaultCapacity = 4;
}

FrameBufferPool &FrameBufferPool::instance()
{
	static FrameBufferPool pool;
	return pool;
}

FrameBufferPool::FrameBufferPool()
	: capacity(kDefaultCapacity), on(true), poison(false)
{
	const char *env = getenv("MOTIONCORR_FRAME_POOL");
	if (env != NULL && env[0] == '0' && env[1] == '\0') on = false;
	// Test hook: fill every reused buffer with a NaN pattern before handing it
	// out, so a read-before-write cannot hide behind the previous movie's
	// plausible pixels. Products must be identical with and without it.
	const char *p = getenv("MOTIONCORR_FRAME_POOL_POISON");
	poison = (p != NULL && p[0] == '1' && p[1] == '\0');
}

FrameBufferPool::~FrameBufferPool() { clear(); }

void FrameBufferPool::setEnabled(bool value)
{
	std::lock_guard<std::mutex> lock(mutex);
	on = value;
}

bool FrameBufferPool::enabled() const
{
	std::lock_guard<std::mutex> lock(mutex);
	return on;
}

void FrameBufferPool::acquire(MultidimArray<float> &array, long int ny, long int nx)
{
	const size_t elements = (size_t)ny * (size_t)nx;
	// Already holding an owned buffer of exactly this size (for example the
	// unweighted sum when it was not handed to the writer): keep it in place,
	// exactly as reshape() would, instead of freeing and reallocating it.
	if (array.data != NULL && array.destroyData && !array.mmapOn &&
	    (size_t)array.nzyxdimAlloc == elements) {
		{
			std::lock_guard<std::mutex> lock(mutex);
			if (on && std::find(requested.begin(), requested.end(), elements) == requested.end())
				requested.push_back(elements);
		}
		if (poison) std::memset(array.data, 0xFF, elements * sizeof(float));  // quiet NaNs
		array.setDimensions(nx, ny, 1, 1);
		return;
	}
	float *reused = nullptr;
	{
		std::lock_guard<std::mutex> lock(mutex);
		if (on) {
			if (std::find(requested.begin(), requested.end(), elements) == requested.end())
				requested.push_back(elements);
			for (size_t i = 0; i < free_list.size(); i++) {
				if (free_list[i].elements == elements) {
					reused = free_list[i].data;
					free_list.erase(free_list.begin() + i);
					break;
				}
			}
		}
	}
	array.clear();
	if (reused == nullptr) {
		// Fresh, uninitialised, exactly as reshape() would allocate it.
		array.reshape(ny, nx);
		return;
	}
	// Adopt the retained buffer. It was allocated by RELION_ALIGNED_MALLOC for
	// exactly this element count, so the array owns and frees it normally.
	if (poison) std::memset(reused, 0xFF, elements * sizeof(float));  // quiet NaNs
	array.data = reused;
	array.destroyData = true;
	array.nzyxdimAlloc = (long int)elements;
	array.setDimensions(nx, ny, 1, 1);
}

void FrameBufferPool::release(MultidimArray<float> &array)
{
	const size_t elements = (size_t)array.nzyxdimAlloc;
	const bool poolable = array.data != NULL && array.destroyData && !array.mmapOn &&
	                      elements * sizeof(float) >= kMinPooledBytes;
	if (poolable) {
		std::lock_guard<std::mutex> lock(mutex);
		const bool reusable = std::find(requested.begin(), requested.end(), elements) != requested.end();
		if (on && reusable && free_list.size() < capacity) {
			free_list.push_back({array.data, elements});
			// Detach without freeing: the pool owns the buffer now.
			array.data = NULL;
			array.nzyxdimAlloc = 0;
			array.coreInit();
			return;
		}
	}
	array.clear();
}

size_t FrameBufferPool::retainedBytes() const
{
	std::lock_guard<std::mutex> lock(mutex);
	size_t total = 0;
	for (const Buffer &b : free_list) total += b.elements * sizeof(float);
	return total;
}

size_t FrameBufferPool::retainedCount() const
{
	std::lock_guard<std::mutex> lock(mutex);
	return free_list.size();
}

void FrameBufferPool::clear()
{
	std::vector<Buffer> taken;
	{
		std::lock_guard<std::mutex> lock(mutex);
		taken.swap(free_list);
		requested.clear();
	}
	for (const Buffer &b : taken) RELION_ALIGNED_FREE(b.data);
}
