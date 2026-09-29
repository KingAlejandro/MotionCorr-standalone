/* Issue #95: ownership contract for the native uint16 movie staging.
 *
 * Two things have to hold for the compact-ingest path to be memory-neutral on the
 * degraded no-gain route, and both are checked here without a GPU:
 *
 *   1. The frames alias one mapping and Image::read's coreAllocateReuse() keeps
 *      that slice instead of allocating a private buffer per frame. If that broke,
 *      the reader would silently go back to one allocation per frame and the
 *      staging object would own memory nobody reads.
 *   2. release() returns the payload to the operating system. That is the property
 *      the regression was about: freeing per-frame heap storage only returned it to
 *      a malloc arena, and the float movie a non-converging patch downloads
 *      afterwards was added on top of it.
 *
 * The resident-set assertions need /proc, so they run on Linux. The test reports
 * explicitly when an arm could not be observed rather than passing silently, and
 * it self-checks that the instrument can see the payload at all before asserting
 * anything about its release.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "src/native_u16_staging.h"

namespace {

int failures = 0;

void check(bool ok, const std::string &what)
{
	std::printf("%-6s %s\n", ok ? "ok" : "FAIL", what.c_str());
	if (!ok) failures++;
}

#ifdef __linux__
const bool kCanMeasureRss = true;
long rss_kb()
{
	std::FILE *f = std::fopen("/proc/self/statm", "r");
	if (!f) return -1;
	long total = 0, resident = 0;
	const int n = std::fscanf(f, "%ld %ld", &total, &resident);
	std::fclose(f);
	if (n != 2) return -1;
	return resident * (sysconf(_SC_PAGESIZE) / 1024);
}
#else
const bool kCanMeasureRss = false;
long rss_kb() { return -1; }
#endif

const int kFrames = 16;
const int kNx = 2048;
const int kNy = 2048;                       // 8 MiB per frame, 128 MiB per movie
const size_t kPixels = (size_t)kNx * kNy;
const long kPayloadKb = (long)((kPixels * sizeof(unsigned short) * kFrames) / 1024);

void touch(unsigned short *p, size_t n, unsigned short seed)
{
	for (size_t i = 0; i < n; i += 2048 / sizeof(unsigned short))
		p[i] = (unsigned short)(seed + i);
}

// What Image<unsigned short>::readData does to the destination array before the
// decoder writes into it: set the frame shape, then ask for storage.
void reader_would_allocate(MultidimArray<unsigned short> &a)
{
	a.setDimensions(kNx, kNy, 1, 1);
	a.coreAllocateReuse();
}

// Diagnostic: the allocation shape this change replaced -- one heap buffer per
// frame, sized so glibc's dynamic mmap threshold has already ratcheted past it.
long retained_by_per_frame_heap_kb()
{
	void *warm = malloc(kPixels * sizeof(unsigned short));
	if (warm) { std::memset(warm, 1, 4096); free(warm); }   // ratchet the threshold
	const long before = rss_kb();
	std::vector<unsigned short *> frames(kFrames, NULL);
	for (int i = 0; i < kFrames; i++) {
		frames[i] = (unsigned short *)RELION_ALIGNED_MALLOC(kPixels * sizeof(unsigned short));
		if (!frames[i]) return -1;
		std::memset(frames[i], i + 1, kPixels * sizeof(unsigned short));
	}
	const long peak = rss_kb();
	for (int i = 0; i < kFrames; i++) RELION_ALIGNED_FREE(frames[i]);
	const long after = rss_kb();
	if (before < 0 || peak < 0 || after < 0) return -1;
	std::printf("       [control] per-frame heap: grew %ld kB, retained %ld kB after free\n",
	            peak - before, after - before);
	return after - before;
}

} // namespace

int main()
{
	std::printf("native uint16 staging contract: %d frames of %dx%d (%ld kB payload)\n",
	            kFrames, kNx, kNy, kPayloadKb);

	std::vector<Image<unsigned short> > frames;
	NativeU16MovieStaging staging;

	// --- 1. aliasing and the reader's reuse contract -------------------------
	staging.bind(frames, kFrames, kNy, kNx);
	check(frames.size() == (size_t)kFrames, "bind() sizes the frame vector");
	check(staging.bytes() >= kPixels * sizeof(unsigned short) * kFrames,
	      "mapping covers the whole movie");

	bool shape_ok = true, owned_ok = true, ordered_ok = true, reuse_ok = true;
	unsigned short *prev = NULL;
	for (int i = 0; i < kFrames; i++) {
		MultidimArray<unsigned short> &a = frames[i]();
		if (XSIZE(a) != kNx || YSIZE(a) != kNy || NSIZE(a) != 1 || ZSIZE(a) != 1) shape_ok = false;
		if (a.destroyData || a.nzyxdimAlloc != (long int)kPixels || a.data == NULL) owned_ok = false;
		if (prev != NULL && !(a.data > prev)) ordered_ok = false;
		prev = a.data;
		unsigned short *before = a.data;
		reader_would_allocate(a);                      // what Image::read will do
		if (a.data != before) reuse_ok = false;
	}
	check(shape_ok, "every frame carries the movie geometry");
	check(owned_ok, "frames alias the mapping (destroyData=false, nzyxdimAlloc set)");
	check(ordered_ok, "frame slices are laid out in ascending order");
	check(reuse_ok, "Image::read's coreAllocateReuse() keeps the bound slice");

	// --- 2. the alias is real storage ----------------------------------------
	for (int i = 0; i < kFrames; i++)
		for (size_t p = 0; p < kPixels; p += 4096)
			DIRECT_MULTIDIM_ELEM(frames[i](), p) = (unsigned short)(i * 7 + 1);
	bool readback_ok = true;
	for (int i = 0; i < kFrames; i++)
		for (size_t p = 0; p < kPixels; p += 4096)
			if (DIRECT_MULTIDIM_ELEM(frames[i](), p) != (unsigned short)(i * 7 + 1))
				readback_ok = false;
	check(readback_ok, "writes through the alias read back per frame");

	// --- 3. incremental release keeps later frames intact ---------------------
	for (int i = 0; i < kFrames; i++) touch(frames[i]().data, kPixels, (unsigned short)(i + 1));
	const int kept_from = kFrames / 2;
	for (int i = 0; i < kept_from; i++) frames[i].clear();
	staging.discardThrough(kept_from);
	bool tail_intact = true;
	for (int i = kept_from; i < kFrames; i++) {
		unsigned short *p = frames[i]().data;
		if (p == NULL) { tail_intact = false; break; }
		for (size_t q = 0; q < kPixels; q += 2048 / sizeof(unsigned short))
			if (p[q] != (unsigned short)((i + 1) + q)) { tail_intact = false; break; }
		if (!tail_intact) break;
	}
	check(tail_intact, "discardThrough() leaves unconsumed frames byte-intact");

	// --- 4. release returns the payload to the operating system ---------------
	staging.release();
	check(frames.empty(), "release() clears the frame vector");
	staging.release();
	check(true, "release() is idempotent");

	if (!kCanMeasureRss) {
		std::printf("SKIP   resident-set assertions need /proc; not run on this platform\n");
	} else {
		const long base = rss_kb();
		std::vector<Image<unsigned short> > f2;
		NativeU16MovieStaging s2;
		s2.bind(f2, kFrames, kNy, kNx);
		for (int i = 0; i < kFrames; i++)
			std::memset(f2[i]().data, i + 3, kPixels * sizeof(unsigned short));
		const long peak = rss_kb();
		const long grew = peak - base;
		// Instrument self-check: if the sampler cannot see the payload arrive, an
		// assertion about it leaving would be green for the wrong reason.
		check(grew > (kPayloadKb * 9) / 10,
		      "instrument sees the mapping arrive (" + std::to_string(grew) + " kB of "
		      + std::to_string(kPayloadKb) + " kB)");
		s2.release();
		const long retained = rss_kb() - base;
		check(retained < kPayloadKb / 10,
		      "release() returns the payload (" + std::to_string(retained)
		      + " kB retained of " + std::to_string(kPayloadKb) + " kB)");

		const long control = retained_by_per_frame_heap_kb();
		if (control < 0) {
			std::printf("       [control] per-frame heap arm could not be measured\n");
		} else if (control < kPayloadKb / 10) {
			std::printf("       [control] NOTE: this host's allocator also returns per-frame heap\n"
			            "       storage, so the assertion above is not discriminating here; the\n"
			            "       discriminating evidence is the 24-movie A/B in docs/issue95_staging\n");
		} else {
			std::printf("       [control] per-frame heap retains %ld kB of %ld kB, so the\n"
			            "       assertion above can fail for the defect it covers\n",
			            control, kPayloadKb);
		}
	}

	std::printf("%s (%d failures)\n", failures ? "FAILED" : "PASSED", failures);
	return failures ? 1 : 0;
}
