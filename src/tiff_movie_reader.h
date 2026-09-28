/***************************************************************************
 *
 * Author: MotionCorr standalone contributors
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 ***************************************************************************/

#ifndef TIFF_MOVIE_READER_H
#define TIFF_MOVIE_READER_H

#include "src/image.h"
#include <memory>
#include <vector>

/** Persistent-handle TIFF movie reader (issue #85 lane B experiment).
 *
 * The ordinary path runs one generic image open/read/close lifecycle per
 * frame: every Image::read opens the file, resolves the movie layout, walks
 * the IFD chain, decodes one directory and closes again. This reader opens a
 * small fixed pool of handles once per movie and reuses them.
 *
 * Each worker owns
 *   - its own TIFF handle, and therefore its own descriptor and its own
 *     directory cursor: no shared mutable TIFF directory state;
 *   - its own LibTIFF error context, bound to that handle;
 *   - its own strip scratch, grown on demand and kept for the movie.
 * The only shared mutable object is the frame-index counter. The movie layout
 * is resolved once, before any worker runs, and is read-only afterwards.
 *
 * Decoding goes through Image<float>::readTIFFFrameFromHandle, which is the
 * same layout application and strip loop Image::read uses, so the decoded
 * pixels, the per-frame validation and the error text are the ordinary
 * reader's by construction.
 *
 * Opt-in only (--persistent_tiff_readers). To remove the experiment: delete
 * this file pair and tiff_reader_bench/test_tiff_persistent_reader with their
 * CMake entries, drop the flag and the branch in
 * MotioncorrRunner::executeOwnMotionCorrection, and revert src/rwTIFF.h,
 * src/rwTIFF_layout.h and the image.h include to origin/main.
 */
/** True when Image::_read would route `name` to readTIFF for a movie frame.
 *
 * Mirrors the ordered dispatch chain in Image::_read, not just the extension:
 * a name only reaches readTIFF after the SPIDER, compressed-MRC, MRC-stack
 * and STK branches have declined it. Testing for "tif" alone would claim, for
 * example, ".stif", which _read sends to readMRC through its contains("st")
 * branch. is_2D is true at the movie read site, so the "mrc" branch applies.
 */
inline bool tiffMovieReaderApplies(const FileName &name)
{
	FileName ext = name.getFileFormat();
	if (ext == "gain") ext = "tif"; // the rewrite fImageHandler::openFile does
	if (ext.contains("spi") || ext.contains("xmp") || ext.contains("stk") || ext.contains("vol"))
		return false;
	if (ext.contains("bz2") || ext.contains("xz") || ext.contains("zst"))
		return false;
	if (ext.contains("mrcs") || ext.contains("mrc") || ext.contains("st"))
		return false;
	return ext.contains("tif");
}

class TiffMovieReader
{
public:
	/** Opens n_readers handles on `name` and resolves the movie layout.
	 *
	 * Throws RelionError with the same text Image::read would produce on a
	 * damaged file. n_readers is clamped to at least 1.
	 */
	TiffMovieReader(const FileName &name, int n_readers);

	long int xSize()   const { return layout_.xDim; }
	long int ySize()   const { return layout_.yDim; }
	long int nFrames() const { return layout_.nDim; }
	int      nReaders() const { return (int)workers_.size(); }

	/** Decode `frames` (0-indexed directory numbers) into out[0..frames.size()).
	 *
	 * Callable more than once on the same reader. If a handle failed to reopen
	 * after an earlier frame error the pool is dead and this throws rather
	 * than handing a closed handle to LibTIFF.
	 *
	 * `out` must already hold frames.size() images; each is left exactly as a
	 * single-frame Image::read would leave it. Destinations are disjoint, so
	 * `frames` must not repeat an index.
	 *
	 * If several frames fail, the failure belonging to the lowest position in
	 * `frames` is rethrown, matching the ordering the serial rethrow loop in
	 * the runner guarantees today.
	 */
	void readFrames(const std::vector<int> &frames, std::vector<Image<float> > &out);

	/** Wall-clock attribution in seconds. Read by the benchmark only. */
	struct Stages
	{
		double open_and_layout = 0; // constructor: opening handles, resolving the layout
		double read_frames = 0;     // readFrames wall clock, pool start to join
		// Achieved concurrency of the last readFrames. Without these a caller
		// cannot tell a pool of N handles used at once from one handle used N
		// times in a row: the decoded pixels are identical either way, so the
		// reader-count axis of any test over them observes nothing.
		int omp_team_size = 0;            // threads the runtime actually gave
		int peak_concurrent_readers = 0;  // most frames decoding simultaneously
	};
	const Stages &stages() const { return stages_; }

private:
	// One persistent reader. fImageHandler gives the handle its own descriptor
	// and its own TiffErrorContext, opened exactly as Image::read opens one.
	struct Worker
	{
		fImageHandler handle;
		TiffStripScratch scratch;
	};

	FileName name_;
	TiffMovieLayout layout_;
	// unique_ptr because fImageHandler and TiffStripScratch are non-copyable
	// and must not move once a TIFF handle holds a pointer into the context.
	std::vector<std::unique_ptr<Worker> > workers_;
	Stages stages_;
};

#endif
