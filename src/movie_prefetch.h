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
//
// Bounded next-movie prefetch (issue #94) and the admission primitives shared
// with the frame/chunk staging work (issue #95).
//
// The whole point of the byte budget is that a queue capacity of one does NOT
// bound memory: at steady state the pipeline owns producer-current + queued +
// consumer-active decoded movies. Bytes are therefore reserved before the
// allocation exists, travel with ownership, and are returned exactly once when
// the allocation is really gone.
//
#ifndef MOVIE_PREFETCH_H_
#define MOVIE_PREFETCH_H_

#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "src/filename.h"
#include "src/image.h"

namespace movieio
{

// ---------------------------------------------------------------------------
// Conservative size arithmetic
// ---------------------------------------------------------------------------

// Page granularity used to charge allocator rounding. Not queried from the OS:
// a fixed, documented 4 KiB is enough for a deliberately conservative estimate
// and keeps the number reproducible across hosts in recorded evidence.
constexpr size_t kPageBytes = 4096;

// Charged per decoded frame on top of its pixels: the Image/MultidimArray
// objects, their vector slot, and slack for the allocator's own bookkeeping.
constexpr size_t kPerFrameOverheadBytes = 4096;

// All of these saturate at SIZE_MAX rather than wrapping. A wrapped estimate
// would under-charge, which is the one direction that breaks the bound.
size_t roundUpToPage(size_t bytes);
size_t saturatingMul(size_t a, size_t b);
size_t saturatingAdd(size_t a, size_t b);

// Upper bound on the host memory one decoded movie adds.
//
//   n_frames * (page-rounded frame bytes + per-frame overhead)
//   + n_io_threads * page-rounded frame bytes
//
// The second term is the decoder scratch: a TIFF strip buffer holds at most one
// frame of raw samples at no more than 4 bytes per pixel, and at most
// n_io_threads of them are live at once. It is a provable bound, not a tuning
// constant. Over-charging only causes earlier backpressure; under-charging
// would make the declared bound false.
size_t estimateDecodedMovieBytes(int nx, int ny, int n_frames, int n_io_threads);

// ---------------------------------------------------------------------------
// ByteBudget: reserve before allocating, transfer on move, release once
// ---------------------------------------------------------------------------

class ByteBudget
{
public:
	// A move-only claim on `bytes` of the budget. Copying is deleted so a
	// double release is unrepresentable rather than merely untested.
	class Reservation
	{
	public:
		Reservation() = default;
		Reservation(Reservation &&other) noexcept;
		Reservation &operator=(Reservation &&other) noexcept;
		Reservation(const Reservation &) = delete;
		Reservation &operator=(const Reservation &) = delete;
		~Reservation();

		// Return the bytes now. Call this only where the allocation really is
		// gone; releasing "on publication" is the bug this class exists to
		// prevent. Idempotent so error paths can be written straightforwardly.
		void release();

		size_t bytes() const { return bytes_; }
		bool held() const { return budget_ != nullptr; }

	private:
		friend class ByteBudget;
		Reservation(ByteBudget *budget, size_t bytes) : budget_(budget), bytes_(bytes) {}
		ByteBudget *budget_ = nullptr;
		size_t bytes_ = 0;
	};

	explicit ByteBudget(size_t limit_bytes) : limit_(limit_bytes) {}
	ByteBudget(const ByteBudget &) = delete;
	ByteBudget &operator=(const ByteBudget &) = delete;

	// True when `bytes` can never be admitted however long the caller waits.
	// Callers must test this before reserve(), because reserve() would
	// otherwise block until cancellation for a request that cannot be served.
	bool tooLargeForBudget(size_t bytes) const { return bytes > limit_; }

	// Blocks until `bytes` fit or the budget is cancelled. Returns an unheld
	// reservation when cancelled, or when the request can never fit.
	Reservation reserve(size_t bytes);

	// Grants `bytes` immediately even if that exceeds the limit, and counts the
	// grant. This is the documented escape hatch for a movie too large for the
	// whole budget: the serial baseline also holds one such movie resident, so
	// refusing it would be a functional regression. It is counted so that
	// "the bound held" and "the bound was overridden N times" stay
	// distinguishable in evidence.
	Reservation reserveForced(size_t bytes);

	void cancel();
	bool cancelled() const;

	size_t limitBytes() const { return limit_; }
	size_t reservedBytes() const;
	size_t peakReservedBytes() const;
	size_t forcedGrants() const;
	// Accumulated time callers spent blocked inside reserve().
	double blockedSeconds() const;

private:
	void returnBytes(size_t bytes);

	mutable std::mutex mutex_;
	std::condition_variable cv_;
	const size_t limit_;
	size_t reserved_ = 0;
	size_t peak_ = 0;
	size_t forced_grants_ = 0;
	double blocked_seconds_ = 0.0;
	bool cancelled_ = false;
};

// ---------------------------------------------------------------------------
// BoundedQueue: count-bounded, cancellable, single-producer single-consumer
// ---------------------------------------------------------------------------

template <typename T>
class BoundedQueue
{
public:
	explicit BoundedQueue(size_t capacity) : capacity_(capacity == 0 ? 1 : capacity) {}

	// Blocks while full. Returns false if cancelled, in which case `item` is
	// left untouched so the caller still owns it (and its reservation).
	bool push(T &&item)
	{
		std::unique_lock<std::mutex> lock(mutex_);
		not_full_.wait(lock, [this] { return cancelled_ || items_.size() < capacity_; });
		if (cancelled_) return false;
		items_.push_back(std::move(item));
		if (items_.size() > peak_occupancy_) peak_occupancy_ = items_.size();
		not_empty_.notify_one();
		return true;
	}

	// Blocks while empty. Returns false once cancelled, or once the producer
	// has finished and the queue has drained.
	bool pop(T &out)
	{
		std::unique_lock<std::mutex> lock(mutex_);
		not_empty_.wait(lock, [this] { return cancelled_ || finished_ || !items_.empty(); });
		if (cancelled_ || items_.empty()) return false;
		out = std::move(items_.front());
		items_.pop_front();
		not_full_.notify_one();
		return true;
	}

	// Producer is done. Waiting consumers drain and then see false.
	void finish()
	{
		std::lock_guard<std::mutex> lock(mutex_);
		finished_ = true;
		not_empty_.notify_all();
	}

	// Wakes everyone and drops queued items, releasing their reservations.
	void cancel()
	{
		std::deque<T> drained;
		{
			std::lock_guard<std::mutex> lock(mutex_);
			cancelled_ = true;
			drained.swap(items_);
			not_empty_.notify_all();
			not_full_.notify_all();
		}
		// Destroy outside the lock: an item's destructor takes the budget mutex.
		drained.clear();
	}

	size_t size() const
	{
		std::lock_guard<std::mutex> lock(mutex_);
		return items_.size();
	}

	size_t peakOccupancy() const
	{
		std::lock_guard<std::mutex> lock(mutex_);
		return peak_occupancy_;
	}

private:
	mutable std::mutex mutex_;
	std::condition_variable not_full_, not_empty_;
	std::deque<T> items_;
	const size_t capacity_;
	size_t peak_occupancy_ = 0;
	bool cancelled_ = false;
	bool finished_ = false;
};

// ---------------------------------------------------------------------------
// Shared movie loader: one implementation for serial and prefetched reads
// ---------------------------------------------------------------------------

struct MovieGeometry
{
	int nx = 0, ny = 0, nn = 0;
};

// True when this movie can be prefetched at all. EER and compressed MRC keep
// decoder state that is consumed after the decode stage -- the EER gain
// reference is resolved through the live renderer -- so they stay on the
// in-line serial path and are declared unrun for prefetch, not supported.
bool isPrefetchableMovie(const FileName &fn);

// Header-only probe. Throws RelionError on a damaged or unreadable header.
MovieGeometry probeGeometry(const FileName &fn);

// 0-indexed frames kept by --first_frame_sum / --last_frame_sum. Pure function
// of the run-wide options and the frame count, so the producer and the serial
// path cannot disagree about which frames a movie has.
std::vector<int> selectFrames(int nn, int first_frame_sum, int last_frame_sum);

// Decodes exactly `frames` into `out`, sized to frames.size(). Read errors from
// inside the OpenMP region are captured per frame and the lowest failing frame
// index is rethrown serially, so the reported error does not depend on the
// OpenMP schedule. `out` may be partially filled when this throws.
void decodeFrames(const FileName &fn, const std::vector<int> &frames,
                  int n_io_threads, std::vector<Image<float> > &out);

// ---------------------------------------------------------------------------
// Prefetch record and producer
// ---------------------------------------------------------------------------

struct MoviePrefetchRecord
{
	enum class Mode
	{
		Decoded,    // frames are in hand and the reservation is charged
		LoadInline, // consumer must load this one itself (unsupported format,
		            // or larger than the whole budget)
		Failed      // probe/decode threw; `error` is the movie-tagged outcome
	};

	long index = -1;
	FileName filename;
	Mode mode = Mode::LoadInline;
	MovieGeometry geometry;
	std::vector<int> frames;
	std::vector<Image<float> > Iframes;
	std::exception_ptr error;
	ByteBudget::Reservation reservation;

	MoviePrefetchRecord() = default;
	MoviePrefetchRecord(MoviePrefetchRecord &&) = default;
	MoviePrefetchRecord &operator=(MoviePrefetchRecord &&) = default;
	MoviePrefetchRecord(const MoviePrefetchRecord &) = delete;
	MoviePrefetchRecord &operator=(const MoviePrefetchRecord &) = delete;
};

struct PrefetchStats
{
	size_t budget_bytes = 0;
	size_t peak_reserved_bytes = 0;
	size_t peak_queue_occupancy = 0;
	size_t decoded = 0;
	size_t inline_loaded = 0;
	size_t failed = 0;
	size_t forced_grants = 0;
	double producer_budget_blocked_s = 0.0;
	double producer_queue_blocked_s = 0.0;
	double consumer_wait_s = 0.0;
};

class MoviePrefetcher
{
public:
	struct Options
	{
		size_t budget_bytes = 0;   // 0 => 3x the first movie's estimate
		size_t queue_capacity = 1; // decoded movies allowed to sit between the
		                           // producer and the consumer
		int n_io_threads = 1;
		int first_frame_sum = 1;
		int last_frame_sum = -1;
	};

	// Resolves an automatic (0) byte budget to 3x the first probeable movie's
	// estimate -- producer-current + one queued + consumer-active -- before the
	// thread starts, so the budget is immutable for the whole run and needs no
	// synchronisation of its own. A probe that throws here is ignored and left
	// for the producer to report as that movie's tagged failure.
	static size_t resolveBudgetBytes(const std::vector<FileName> &movies, const Options &options);

	MoviePrefetcher(std::vector<FileName> movies, const Options &options);
	MoviePrefetcher(const MoviePrefetcher &) = delete;
	MoviePrefetcher &operator=(const MoviePrefetcher &) = delete;
	// Cancels and joins. Every unwinding path out of the movie loop therefore
	// joins the producer before the shared state it touches is destroyed.
	~MoviePrefetcher();

	void start();

	// Blocks until the next record is available. Returns false when the list is
	// exhausted or the prefetcher was cancelled. Records arrive strictly in
	// movie order.
	bool next(MoviePrefetchRecord &out);

	// Wakes a producer blocked on the budget or on a full queue, and a consumer
	// blocked on an empty queue, then joins.
	void cancelAndJoin();

	// Forced, counted grant for a movie the consumer has to load itself.
	ByteBudget::Reservation reserveInline(size_t bytes);

	PrefetchStats stats() const;
	const ByteBudget &budget() const { return budget_; }

	// Test seams: replace the header probe and the decode so the lifecycle
	// tests can drive every ownership state, including blocked budget and
	// cancellation, without touching the filesystem. Both must be set before
	// start(). Production builds leave them empty and call the real helpers.
	using ProbeFn = std::function<MovieGeometry(const FileName &)>;
	using LoaderFn = std::function<void(const FileName &, MoviePrefetchRecord &, int)>;
	void setProbeForTesting(ProbeFn probe) { probe_ = std::move(probe); }
	void setLoaderForTesting(LoaderFn loader) { loader_ = std::move(loader); }

private:
	void producerLoop();
	void loadOne(const FileName &fn, MoviePrefetchRecord &record);

	std::vector<FileName> movies_;
	Options options_;
	ProbeFn probe_;
	LoaderFn loader_;
	ByteBudget budget_;
	BoundedQueue<MoviePrefetchRecord> queue_;
	std::thread producer_;
	bool started_ = false;
	bool joined_ = false;

	mutable std::mutex stats_mutex_;
	size_t decoded_ = 0, inline_loaded_ = 0, failed_ = 0;
	double producer_queue_blocked_s_ = 0.0;
	double consumer_wait_s_ = 0.0;
};

// Monotonic seconds, for the blocked/wait accounting above.
double monotonicSeconds();

} // namespace movieio

#endif /* MOVIE_PREFETCH_H_ */
