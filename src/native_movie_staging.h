#ifndef NATIVE_MOVIE_STAGING_H_
#define NATIVE_MOVIE_STAGING_H_

#include <sys/mman.h>
#include <unistd.h>
#include <vector>

#include "src/image.h"
#include "src/multidim_array.h"

// Issue #95: one self-owned mapping for a movie's native frames, in place of one
// heap allocation per frame. T is the file's own sample type -- unsigned short
// for a 16-bit TIFF, unsigned char for an 8-bit one.
//
// A uint16 frame is nx*ny*2 bytes -- 27.16 MiB for the 3710x3838 tutorial
// geometry -- which is below glibc's DEFAULT_MMAP_THRESHOLD_MAX of 32 MiB. Once
// the dynamic mmap threshold has ratcheted past one frame, the frames are served
// from malloc arenas instead of private mappings, and freeing them only returns
// them to an arena free list. A whole movie is 0.6365 GiB for that geometry and
// is above the cap for any geometry this path accepts, so this mapping is always
// private and release() is a munmap: the kernel reclaims every page, with no
// allocator policy in the path and no process-wide trim. A uint8 movie of the
// same geometry is half that and still far above the cap, so the same argument
// holds; a single uint8 frame is further below the threshold than a uint16 one,
// which is the direction that makes the whole-movie mapping matter more, not
// less. See [[glibc-32mib-mmap-cap-hides-buffer-shrink]] for why per-frame size
// alone is the wrong thing to reason from.
//
// The frames alias slices and do not own their pixels. Image::read reuses a bound
// slice because MultidimArray::coreAllocateReuse() keeps an existing allocation
// whose nzyxdimAlloc already covers the requested frame.
template <typename T>
class NativeMovieStaging {
public:
	NativeMovieStaging() {}
	~NativeMovieStaging() { release(); }
	NativeMovieStaging(const NativeMovieStaging &) = delete;
	NativeMovieStaging &operator=(const NativeMovieStaging &) = delete;

	// Size the mapping for exactly this movie and bind one slice per frame.
	void bind(std::vector<Image<T> > &frames, int n_frames, int ny, int nx)
	{
		release();
		if (n_frames <= 0 || ny <= 0 || nx <= 0)
			REPORT_ERROR("Native movie staging: non-positive movie geometry.");
		pixels_ = (size_t)ny * (size_t)nx;
		// The mapping base is page aligned; a 64-byte slice stride leaves every
		// frame pointer at least as aligned as a separate allocation made it.
		stride_ = (pixels_ * sizeof(T) + 63u) & ~(size_t)63u;
		if (stride_ / sizeof(T) < pixels_ ||
		    stride_ > (size_t)-1 / (size_t)n_frames)
			REPORT_ERROR("Native movie staging: movie size overflows size_t.");
		const size_t want = stride_ * (size_t)n_frames;
		void *p = mmap(NULL, want, PROT_READ | PROT_WRITE,
		               MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (p == MAP_FAILED)
			REPORT_ERROR("Failed to reserve " + integerToString((long int)(want >> 20)) +
			             " MiB of native host movie staging.");
		base_ = (unsigned char *)p;
		bytes_ = want;
		frames.resize(n_frames);
		for (int iframe = 0; iframe < n_frames; iframe++) {
			MultidimArray<T> &a = frames[iframe]();
			a.coreDeallocate();
			a.setDimensions(nx, ny, 1, 1);
			a.data = (T *)(base_ + (size_t)iframe * stride_);
			a.destroyData = false;
			a.nzyxdimAlloc = (long int)pixels_;
		}
		bound_ = &frames;
	}

	// Return the pages holding frames [0, end_exclusive) while the mapping stays
	// alive. The widening fallback consumes frames in ascending order and builds a
	// float movie twice the size, so releasing as it goes keeps that path's
	// high-water mark where one allocation per frame left it. The caller has
	// already cleared each consumed frame, so nothing can read the zeroed pages.
	void discardThrough(int end_exclusive)
	{
		if (base_ == NULL || end_exclusive <= 0) return;
		const size_t page = (size_t)sysconf(_SC_PAGESIZE);
		size_t end = stride_ * (size_t)end_exclusive;
		if (end > bytes_) end = bytes_;
		const size_t aligned_end = (end / page) * page;
		if (aligned_end <= discarded_) return;
		if (madvise(base_ + discarded_, aligned_end - discarded_, MADV_DONTNEED) == 0)
			discarded_ = aligned_end;
	}

	// True while p points into this mapping, i.e. while this object owns it.
	bool owns(const T *p) const
	{
		const unsigned char *q = (const unsigned char *)p;
		return base_ != NULL && q >= base_ && q < base_ + bytes_;
	}

	void release()
	{
		if (bound_ != NULL) {
			for (size_t i = 0; i < bound_->size(); i++) {
				MultidimArray<T> &a = (*bound_)[i]();
				if (a.data == NULL) continue;
				if (owns(a.data)) {
					a.data = NULL; // the mapping owns these pixels, not the Image
					a.nzyxdimAlloc = 0;
				} else {
					// The frame left the mapping, which only happens if something
					// asked for more than bind() reserved: coreAllocateReuse() then
					// allocates privately and leaves destroyData clear, so nothing
					// would ever free it. Hand ownership back rather than drop it.
					a.destroyData = true;
				}
			}
			bound_->clear();
			bound_ = NULL;
		}
		if (base_ != NULL) {
			munmap(base_, bytes_);
			base_ = NULL;
		}
		bytes_ = stride_ = pixels_ = discarded_ = 0;
	}

	size_t bytes() const { return bytes_; }

private:
	unsigned char *base_ = NULL;
	size_t bytes_ = 0;
	size_t stride_ = 0;
	size_t pixels_ = 0;
	size_t discarded_ = 0;
	std::vector<Image<T> > *bound_ = NULL;
};

// The two sample types the compact ingest route accepts. Named rather than
// spelled out at each use so a third type is one line here and not a sweep
// through the runner.
typedef NativeMovieStaging<unsigned short> NativeU16MovieStaging;
typedef NativeMovieStaging<unsigned char>  NativeU8MovieStaging;

#endif // NATIVE_MOVIE_STAGING_H_
