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
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/

#include "src/movie_prefetch.h"

#include <algorithm>
#include <chrono>
#include <limits>

#include "src/error.h"
#include "src/renderEER.h"

namespace movieio
{

double monotonicSeconds()
{
	using clock = std::chrono::steady_clock;
	return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

// ---------------------------------------------------------------------------
// Conservative size arithmetic
// ---------------------------------------------------------------------------

size_t saturatingMul(size_t a, size_t b)
{
	if (a == 0 || b == 0) return 0;
	if (a > std::numeric_limits<size_t>::max() / b) return std::numeric_limits<size_t>::max();
	return a * b;
}

size_t saturatingAdd(size_t a, size_t b)
{
	if (a > std::numeric_limits<size_t>::max() - b) return std::numeric_limits<size_t>::max();
	return a + b;
}

size_t roundUpToPage(size_t bytes)
{
	if (bytes == 0) return 0;
	const size_t remainder = bytes % kPageBytes;
	if (remainder == 0) return bytes;
	return saturatingAdd(bytes, kPageBytes - remainder);
}

size_t estimateDecodedMovieBytes(int nx, int ny, int n_frames, int n_io_threads)
{
	// No selected frames means nothing is allocated, and zero is the honest
	// charge. A nonpositive geometry with frames to read is different: the
	// allocation size is unknowable, and returning zero would admit the movie
	// entirely off-budget, so charge the maximum and let the caller fall back.
	if (n_frames <= 0) return 0;
	if (nx <= 0 || ny <= 0) return std::numeric_limits<size_t>::max();
	if (n_io_threads < 1) n_io_threads = 1;

	const size_t frame_bytes = roundUpToPage(
		saturatingMul(saturatingMul((size_t)nx, (size_t)ny), sizeof(float)));
	const size_t per_frame = saturatingAdd(frame_bytes, kPerFrameOverheadBytes);
	const size_t frames_total = saturatingMul(per_frame, (size_t)n_frames);
	const size_t scratch = saturatingMul(frame_bytes, (size_t)n_io_threads);
	return saturatingAdd(frames_total, scratch);
}

// ---------------------------------------------------------------------------
// ByteBudget
// ---------------------------------------------------------------------------

ByteBudget::Reservation::Reservation(Reservation &&other) noexcept
	: budget_(other.budget_), bytes_(other.bytes_)
{
	other.budget_ = nullptr;
	other.bytes_ = 0;
}

ByteBudget::Reservation &ByteBudget::Reservation::operator=(Reservation &&other) noexcept
{
	if (this != &other)
	{
		release();
		budget_ = other.budget_;
		bytes_ = other.bytes_;
		other.budget_ = nullptr;
		other.bytes_ = 0;
	}
	return *this;
}

ByteBudget::Reservation::~Reservation()
{
	release();
}

void ByteBudget::Reservation::release()
{
	if (budget_ == nullptr) return;
	ByteBudget *const budget = budget_;
	const size_t bytes = bytes_;
	// Clear first: returnBytes() notifies waiters, and this object must already
	// look released if anything observes it from there.
	budget_ = nullptr;
	bytes_ = 0;
	budget->returnBytes(bytes);
}

ByteBudget::Reservation ByteBudget::reserve(size_t bytes)
{
	if (bytes > limit_) return Reservation(); // never admissible; caller falls back
	std::unique_lock<std::mutex> lock(mutex_);
	if (reserved_ + bytes > limit_ && !cancelled_)
	{
		const double t0 = monotonicSeconds();
		cv_.wait(lock, [&] { return cancelled_ || reserved_ + bytes <= limit_; });
		blocked_seconds_ += monotonicSeconds() - t0;
	}
	if (cancelled_) return Reservation();
	reserved_ += bytes;
	if (reserved_ > peak_) peak_ = reserved_;
	return Reservation(this, bytes);
}

ByteBudget::Reservation ByteBudget::reserveForced(size_t bytes)
{
	std::lock_guard<std::mutex> lock(mutex_);
	// Count only grants that genuinely break the bound. An in-line load of an
	// EER movie that fits comfortably is not an override, and counting it as
	// one would make the field useless for the question it exists to answer.
	if (reserved_ + bytes > limit_) over_budget_grants_++;
	reserved_ += bytes;
	if (reserved_ > peak_) peak_ = reserved_;
	return Reservation(this, bytes);
}

void ByteBudget::setReleaseObserverForTesting(ReleaseObserver observer)
{
	std::lock_guard<std::mutex> lock(mutex_);
	release_observer_ = std::move(observer);
}

void ByteBudget::returnBytes(size_t bytes)
{
	ReleaseObserver observer;
	size_t reserved_after = 0;
	{
		std::lock_guard<std::mutex> lock(mutex_);
		// A release of more than is held would mean a reservation was returned
		// twice; the move-only handle makes that unrepresentable, and this
		// keeps the counter honest rather than wrapping if it ever happened.
		reserved_ -= std::min(bytes, reserved_);
		reserved_after = reserved_;
		observer = release_observer_;
	}
	// Invoked after the bytes are back but before anyone is woken, which is the
	// exact instant a release-ordering bug is observable. Outside the mutex, so
	// the observer cannot deadlock against it. Empty in production.
	if (observer) observer(bytes, reserved_after);
	cv_.notify_all();
}

void ByteBudget::cancel()
{
	{
		std::lock_guard<std::mutex> lock(mutex_);
		cancelled_ = true;
	}
	cv_.notify_all();
}

bool ByteBudget::cancelled() const
{
	std::lock_guard<std::mutex> lock(mutex_);
	return cancelled_;
}

size_t ByteBudget::reservedBytes() const
{
	std::lock_guard<std::mutex> lock(mutex_);
	return reserved_;
}

size_t ByteBudget::peakReservedBytes() const
{
	std::lock_guard<std::mutex> lock(mutex_);
	return peak_;
}

size_t ByteBudget::overBudgetGrants() const
{
	std::lock_guard<std::mutex> lock(mutex_);
	return over_budget_grants_;
}

double ByteBudget::blockedSeconds() const
{
	std::lock_guard<std::mutex> lock(mutex_);
	return blocked_seconds_;
}

// ---------------------------------------------------------------------------
// Shared loader
// ---------------------------------------------------------------------------

bool isPrefetchableMovie(const FileName &fn)
{
	// A POSITIVE whitelist, not "everything except the two formats we know
	// about". `Image` accepts SPIDER, IMAGIC, raw and several other stacks, and
	// a negative check silently pushes each new one across an unvalidated
	// thread boundary and onto byte accounting derived for these readers. Only
	// the formats this change actually validated are admitted; everything else
	// takes the in-line path, which is the unchanged serial behaviour.
	//
	// getFileFormat() is the same resolution Image::openFile uses: lowercased,
	// and honouring an explicit "name.dat:mrcs" override, so the whitelist
	// matches the reader that will really run rather than the literal suffix.
	// A "#"-style raw specifier resolves to "raw" and is therefore excluded.
	const FileName format = fn.getFileFormat();
	const bool whitelisted = (format == "mrc" || format == "mrcs" ||
	                          format == "tif" || format == "tiff");
	if (!whitelisted) return false;

	// Belt and braces. These cannot match the whitelist today -- EER resolves
	// to "eer"/"ecc" and a compressed stack to "bz2"/"xz"/"zst" -- but both
	// have their own predicates with their own notions of what they own, and
	// re-admitting either through a future whitelist entry must stay
	// impossible rather than merely unlikely.
	if (EERRenderer::isEER(fn)) return false;
	if (CompressedMRCReader::isCompressedMRC(fn)) return false;
	return true;
}

MovieGeometry probeGeometry(const FileName &fn)
{
	Image<float> Ihead;
	Ihead.read(fn, false, -1, false, true); // header only, select_img -1, mmap false, is_2D true
	MovieGeometry geometry;
	geometry.nx = XSIZE(Ihead());
	geometry.ny = YSIZE(Ihead());
	geometry.nn = NSIZE(Ihead());
	return geometry;
}

std::vector<int> selectFrames(int nn, int first_frame_sum, int last_frame_sum)
{
	std::vector<int> frames;
	for (int i = 0; i < nn; i++)
	{
		// For users, all numbers are 1-indexed. Internally they are 0-indexed.
		const int frame = i + 1;
		if (frame < first_frame_sum) continue;
		if (last_frame_sum > 0 && frame > last_frame_sum) continue;
		frames.push_back(i);
	}
	return frames;
}

void decodeFrames(const FileName &fn, const std::vector<int> &frames,
                  int n_io_threads, std::vector<Image<float> > &out)
{
	const int n_frames = (int)frames.size();
	out.clear();
	out.resize(n_frames);
	if (n_io_threads < 1) n_io_threads = 1;

	// Every reader here can REPORT_ERROR on a damaged movie, and an exception
	// that leaves an OpenMP structured block is undefined behaviour: the
	// runtime calls std::terminate. Capture per frame and rethrow serially.
	std::vector<std::exception_ptr> read_errors(n_frames);
	#pragma omp parallel for num_threads(n_io_threads)
	for (int iframe = 0; iframe < n_frames; iframe++)
	{
		try
		{
			out[iframe].read(fn, true, frames[iframe], false, true); // mmap false, is_2D true
		}
		catch (...)
		{
			read_errors[iframe] = std::current_exception();
		}
	}
	// Report the lowest frame index rather than whichever thread failed first,
	// so the error a user sees does not depend on the OpenMP schedule.
	for (int iframe = 0; iframe < n_frames; iframe++)
	{
		if (read_errors[iframe]) std::rethrow_exception(read_errors[iframe]);
	}
}

// ---------------------------------------------------------------------------
// MoviePrefetcher
// ---------------------------------------------------------------------------

size_t MoviePrefetcher::resolveBudgetBytes(const std::vector<FileName> &movies,
                                           const Options &options)
{
	if (options.budget_bytes > 0) return options.budget_bytes;

	for (const FileName &fn : movies)
	{
		if (!isPrefetchableMovie(fn)) continue;
		try
		{
			const MovieGeometry geometry = probeGeometry(fn);
			const std::vector<int> frames =
				selectFrames(geometry.nn, options.first_frame_sum, options.last_frame_sum);
			const size_t estimate = estimateDecodedMovieBytes(
				geometry.nx, geometry.ny, (int)frames.size(), options.n_io_threads);
			if (estimate == 0) continue;
			// Fixed at three estimates -- producer-current, one queued and
			// consumer-active -- and deliberately NOT scaled by the queue
			// capacity. Scaling it would mean raising a count limit silently
			// raises the memory ceiling, and a large enough queue would
			// disable the default bound entirely, while the CLI still promises
			// "3x the first movie". A larger queue under the automatic budget
			// simply cannot fill, because bytes, not slots, are the bound.
			return saturatingMul(estimate, 3);
		}
		catch (...)
		{
			// Leave it for the producer to report as this movie's tagged
			// failure; do not turn a damaged first movie into a batch abort
			// here, where there is nowhere to attribute it.
			continue;
		}
	}
	// Nothing probeable. Any nonzero limit works: every movie will take the
	// inline or failed path anyway. Zero would make tooLargeForBudget() true
	// for every request, which is the same outcome by a less obvious route.
	return 1;
}

MoviePrefetcher::MoviePrefetcher(std::vector<FileName> movies, const Options &options)
	: movies_(std::move(movies)),
	  options_(options),
	  budget_(resolveBudgetBytes(movies_, options)),
	  queue_(options.queue_capacity)
{
}

MoviePrefetcher::~MoviePrefetcher()
{
	cancelAndJoin();
}

void MoviePrefetcher::start()
{
	if (started_) return;
	started_ = true;
	producer_ = std::thread(&MoviePrefetcher::producerLoop, this);
}

void MoviePrefetcher::cancelAndJoin()
{
	if (!started_ || joined_) { joined_ = true; return; }
	joined_ = true;
	// Order matters: the producer may be blocked on either resource, and
	// cancelling only one of them leaves it asleep on the other.
	budget_.cancel();
	queue_.cancel();
	if (producer_.joinable()) producer_.join();
}

void MoviePrefetcher::loadOne(const FileName &fn, MoviePrefetchRecord &record)
{
	// Geometry and the frame selection are already on the record: the producer
	// needs them to size the reservation before anything is allocated.
	if (loader_)
	{
		loader_(fn, record, options_.n_io_threads);
		return;
	}
	decodeFrames(fn, record.frames, options_.n_io_threads, record.Iframes);
}

void MoviePrefetcher::producerLoop()
{
	try
	{
		producerLoopBody();
	}
	catch (...)
	{
		// Not a decode error -- those are caught per movie and published as a
		// tagged record. This is the bookkeeping itself failing (an allocation
		// inside the queue, a lock_guard, a FileName copy). Letting it leave a
		// std::thread function calls std::terminate, killing the process with
		// no diagnostic and no exit code, which is precisely the failure mode
		// the OpenMP capture above exists to prevent. Capture it so the
		// consumer can report it as a run failure instead.
		std::lock_guard<std::mutex> lock(stats_mutex_);
		producer_fatal_ = std::current_exception();
	}
	// Always: a consumer waiting on an empty queue must be released even when
	// the producer died.
	queue_.finish();
}

std::exception_ptr MoviePrefetcher::producerFatalError() const
{
	std::lock_guard<std::mutex> lock(stats_mutex_);
	return producer_fatal_;
}

void MoviePrefetcher::producerLoopBody()
{
	for (size_t imic = 0; imic < movies_.size(); imic++)
	{
		if (budget_.cancelled()) break;

		MoviePrefetchRecord record;
		record.index = (long)imic;
		record.filename = movies_[imic];

		if (!isPrefetchableMovie(record.filename))
		{
			// Unsupported decoder state; the consumer loads it in line.
			record.mode = MoviePrefetchRecord::Mode::LoadInline;
		}
		else
		{
			try
			{
				record.geometry = probe_ ? probe_(record.filename)
				                         : probeGeometry(record.filename);
				record.frames = selectFrames(record.geometry.nn, options_.first_frame_sum,
				                             options_.last_frame_sum);
				const size_t estimate = estimateDecodedMovieBytes(
					record.geometry.nx, record.geometry.ny, (int)record.frames.size(),
					options_.n_io_threads);

				if (budget_.tooLargeForBudget(estimate))
				{
					// Cannot ever be admitted. Publishing a marker keeps the
					// movie order intact and lets the consumer fall back to a
					// serial load through the same loader.
					record.mode = MoviePrefetchRecord::Mode::LoadInline;
				}
				else
				{
					// Reserve BEFORE allocating or decoding. This is the whole
					// point: by the time the frames exist the bytes are already
					// charged, so active + queued + producer-current is bounded.
					record.reservation = budget_.reserve(estimate);
					if (!record.reservation.held()) break; // cancelled
					loadOne(record.filename, record);
					record.mode = MoviePrefetchRecord::Mode::Decoded;
				}
			}
			catch (...)
			{
				record.mode = MoviePrefetchRecord::Mode::Failed;
				record.error = std::current_exception();
				// The partial frames really are gone, so returning the bytes
				// here is an actual release, not an early one.
				record.Iframes.clear();
				record.reservation.release();
			}
		}

		{
			std::lock_guard<std::mutex> lock(stats_mutex_);
			switch (record.mode)
			{
			case MoviePrefetchRecord::Mode::Decoded:    decoded_++; break;
			case MoviePrefetchRecord::Mode::LoadInline: inline_loaded_++; break;
			case MoviePrefetchRecord::Mode::Failed:     failed_++; break;
			}
		}

		const double t0 = monotonicSeconds();
		const bool pushed = queue_.push(std::move(record));
		{
			std::lock_guard<std::mutex> lock(stats_mutex_);
			producer_queue_blocked_s_ += monotonicSeconds() - t0;
		}
		if (!pushed) break; // cancelled; `record` still owns its reservation
	}
}

bool MoviePrefetcher::next(MoviePrefetchRecord &out)
{
	const double t0 = monotonicSeconds();
	const bool got = queue_.pop(out);
	{
		std::lock_guard<std::mutex> lock(stats_mutex_);
		consumer_wait_s_ += monotonicSeconds() - t0;
	}
	return got;
}

ByteBudget::Reservation MoviePrefetcher::reserveInline(size_t bytes)
{
	return budget_.reserveForced(bytes);
}

PrefetchStats MoviePrefetcher::stats() const
{
	PrefetchStats s;
	s.budget_bytes = budget_.limitBytes();
	s.peak_reserved_bytes = budget_.peakReservedBytes();
	s.peak_queue_occupancy = queue_.peakOccupancy();
	s.over_budget_grants = budget_.overBudgetGrants();
	s.producer_budget_blocked_s = budget_.blockedSeconds();
	std::lock_guard<std::mutex> lock(stats_mutex_);
	s.decoded = decoded_;
	s.inline_loaded = inline_loaded_;
	s.failed = failed_;
	s.producer_queue_blocked_s = producer_queue_blocked_s_;
	s.consumer_wait_s = consumer_wait_s_;
	return s;
}

} // namespace movieio
