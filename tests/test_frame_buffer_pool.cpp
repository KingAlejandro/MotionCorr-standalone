// FrameBufferPool contract (src/frame_buffer_pool.h).
// 1. A released full-frame buffer is reused by the next acquire of the same size.
// 2. Retained count and bytes never exceed the bound, whatever is released.
// 3. Different sizes, small buffers and non-owning arrays are freed, not pooled.
// 4. Disabled pool: acquire allocates, release frees, nothing retained.
// 5. Concurrent release (writer thread) with acquire (main) keeps the bound.
#include "src/frame_buffer_pool.h"

#include <cstdio>
#include <thread>

static int failures = 0;
static void check(bool ok, const char *what)
{
	std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok) failures++;
}

int main()
{
	FrameBufferPool &pool = FrameBufferPool::instance();
	pool.clear();
	pool.setEnabled(true);
	const long ny = 2048, nx = 2048;          // 16 MiB float frame
	static_assert(sizeof(float) == 4, "frame sizes below assume 4-byte floats");
	const size_t frame = (size_t)ny * nx * sizeof(float);

	MultidimArray<float> a;
	pool.acquire(a, ny, nx);
	check(a.data != NULL && YSIZE(a) == ny && XSIZE(a) == nx, "acquire gives an ny x nx buffer");
	float *first = a.data;
	a.initZeros();
	pool.release(a);
	check(a.data == NULL && pool.retainedCount() == 1 && pool.retainedBytes() == frame,
	      "release retains one frame and empties the array");
	MultidimArray<float> b;
	pool.acquire(b, ny, nx);
	check(b.data == first && pool.retainedCount() == 0, "next acquire reuses the retained buffer");
	b.initConstant(1.0f);
	check(DIRECT_MULTIDIM_ELEM(b, (size_t)ny * nx - 1) == 1.0f, "reused buffer is fully writable");

	// Bound: release many; at most capacity retained.
	std::vector<MultidimArray<float> > many(10);
	for (auto &m : many) pool.acquire(m, ny, nx);
	for (auto &m : many) pool.release(m);
	pool.release(b);
	check(pool.retainedCount() <= 4 && pool.retainedBytes() <= 4 * frame,
	      "retained count and bytes stay within the bound");

	// Not pooled: small buffers, other sizes are retained separately but bounded,
	// and non-owning aliases are never taken.
	pool.clear();
	MultidimArray<float> small(64, 64);
	pool.release(small);
	check(pool.retainedCount() == 0, "a small buffer is freed, not pooled");
	MultidimArray<float> owner(ny, nx), alias;
	alias.alias(owner);
	pool.release(alias);
	check(pool.retainedCount() == 0 && owner.data != NULL, "a non-owning alias is never pooled");
	MultidimArray<float> other;
	pool.acquire(other, ny, nx / 2);
	pool.release(other);
	MultidimArray<float> wrong;
	pool.acquire(wrong, ny, nx);
	check(wrong.data != NULL && pool.retainedCount() == 1,
	      "a different-size buffer is not handed out for this geometry");
	pool.release(wrong);

	// Late binning (#162 review): every output is acquired full-frame but
	// written binned. Binned buffers must not be retained: they can never be
	// handed out, and four of them would fill the pool so that real full-frame
	// buffers are then freed instead of reused. Reproduce that sequence: four
	// concurrently-live outputs released binned, then a full-frame release.
	pool.clear();
	{
		std::vector<MultidimArray<float> > outs(4);
		for (auto &o : outs) pool.acquire(o, ny, nx);
		for (auto &o : outs) {
			o.clear();
			o.reshape(ny / 2, nx + 512);       // never requested; 12 MiB, above the 8 MiB floor
			pool.release(o);
		}
	}
	check(pool.retainedCount() == 0, "buffers of a never-requested (binned) size are not retained");
	MultidimArray<float> full;
	pool.acquire(full, ny, nx);
	float *full_ptr = full.data;
	pool.release(full);
	check(pool.retainedCount() == 1 && pool.retainedBytes() == frame,
	      "after binned releases a full-frame buffer is still retained for reuse");
	MultidimArray<float> again;
	pool.acquire(again, ny, nx);
	check(again.data == full_ptr, "and it is the one handed out next");
	pool.release(again);

	// Disabled.
	pool.clear();
	pool.setEnabled(false);
	MultidimArray<float> d;
	pool.acquire(d, ny, nx);
	pool.release(d);
	check(pool.retainedCount() == 0, "disabled pool retains nothing");
	pool.setEnabled(true);

	// Concurrency: writer releases while main acquires.
	pool.clear();
	std::thread writer([&] {
		for (int i = 0; i < 200; i++) {
			MultidimArray<float> w;
			pool.acquire(w, ny, nx);
			pool.release(w);
		}
	});
	for (int i = 0; i < 200; i++) {
		MultidimArray<float> m;
		pool.acquire(m, ny, nx);
		pool.release(m);
	}
	writer.join();
	check(pool.retainedCount() <= 4, "concurrent acquire/release keeps the bound");
	pool.clear();
	check(pool.retainedCount() == 0 && pool.retainedBytes() == 0, "clear frees everything");
	return failures ? 1 : 0;
}
