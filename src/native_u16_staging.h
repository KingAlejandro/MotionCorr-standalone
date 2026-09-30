#ifndef NATIVE_U16_STAGING_H_
#define NATIVE_U16_STAGING_H_

#include <sys/mman.h>
#include <unistd.h>
#include <vector>

#include "src/image.h"
#include "src/multidim_array.h"

// Issue #95: one self-owned mapping for a movie's native uint16 frames, in place
// of one heap allocation per frame.
//
// A frame is nx*ny*2 bytes -- 27.16 MiB for the 3710x3838 tutorial geometry --
// which is below glibc's DEFAULT_MMAP_THRESHOLD_MAX of 32 MiB. Once the dynamic
// mmap threshold has ratcheted past one frame, the frames are served from malloc
// arenas instead of private mappings, and freeing them only returns them to an
// arena free list. A whole movie is 0.6365 GiB for that geometry and is above the
// cap for any geometry this path accepts, so this mapping is always private and
// release() is a munmap: the kernel reclaims every page, with no allocator policy
// in the path and no process-wide trim.
//
// The frames alias slices and do not own their pixels. Image::read reuses a bound
// slice because MultidimArray::coreAllocateReuse() keeps an existing allocation
// whose nzyxdimAlloc already covers the requested frame.
class NativeU16MovieStaging {
public:
	NativeU16MovieStaging() {}
	~NativeU16MovieStaging() { release(); }
	NativeU16MovieStaging(const NativeU16MovieStaging &) = delete;
	NativeU16MovieStaging &operator=(const NativeU16MovieStaging &) = delete;

	// Size the mapping for exactly this movie and bind one slice per frame.
	void bind(std::vector<Image<unsigned short> > &frames, int n_frames, int ny, int nx)
	{
		release();
		if (n_frames <= 0 || ny <= 0 || nx <= 0)
			REPORT_ERROR("Native uint16 staging: non-positive movie geometry.");
		pixels_ = (size_t)ny * (size_t)nx;
		// The mapping base is page aligned; a 64-byte slice stride leaves every
		// frame pointer at least as aligned as a separate allocation made it.
		stride_ = (pixels_ * sizeof(unsigned short) + 63u) & ~(size_t)63u;
		if (stride_ / sizeof(unsigned short) < pixels_ ||
		    stride_ > (size_t)-1 / (size_t)n_frames)
			REPORT_ERROR("Native uint16 staging: movie size overflows size_t.");
		const size_t want = stride_ * (size_t)n_frames;
		void *p = mmap(NULL, want, PROT_READ | PROT_WRITE,
		               MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (p == MAP_FAILED)
			REPORT_ERROR("Failed to reserve " + integerToString((long int)(want >> 20)) +
			             " MiB of native uint16 host staging.");
		base_ = (unsigned char *)p;
		bytes_ = want;
		frames.resize(n_frames);
		for (int iframe = 0; iframe < n_frames; iframe++) {
			MultidimArray<unsigned short> &a = frames[iframe]();
			a.coreDeallocate();
			a.setDimensions(nx, ny, 1, 1);
			a.data = (unsigned short *)(base_ + (size_t)iframe * stride_);
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
	bool owns(const unsigned short *p) const
	{
		const unsigned char *q = (const unsigned char *)p;
		return base_ != NULL && q >= base_ && q < base_ + bytes_;
	}

	void release()
	{
		if (bound_ != NULL) {
			for (size_t i = 0; i < bound_->size(); i++) {
				MultidimArray<unsigned short> &a = (*bound_)[i]();
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
	std::vector<Image<unsigned short> > *bound_ = NULL;
};

#endif // NATIVE_U16_STAGING_H_
