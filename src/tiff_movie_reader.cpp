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

#include "src/tiff_movie_reader.h"

#include <atomic>
#include <chrono>
#include <omp.h>

static double monotonicSeconds()
{
	using namespace std::chrono;
	return duration<double>(steady_clock::now().time_since_epoch()).count();
}

TiffMovieReader::TiffMovieReader(const FileName &name, int n_readers)
	: name_(name)
{
	const double t0 = monotonicSeconds();

	if (n_readers < 1) n_readers = 1;

	// Handle 0 resolves the layout. openFile reports a missing or unopenable
	// file with the same message Image::read would.
	workers_.reserve(n_readers);
	for (int i = 0; i < n_readers; i++)
	{
		std::unique_ptr<Worker> w(new Worker);
		w->handle.openFile(name);
		if (!w->handle.isTiff || w->handle.ftiff == nullptr)
			REPORT_ERROR(name + ": TiffMovieReader was given a file that is not a TIFF.");
		workers_.push_back(std::move(w));
	}

	fImageHandler &primary = workers_[0]->handle;
	TiffErrorContext *ctx = primary.tiff_err_ctx.get();
	TiffErrorScope scope(ctx);
	readTiffLayout(primary.ftiff, layout_, name, ctx);

	stages_.open_and_layout = monotonicSeconds() - t0;
}

void TiffMovieReader::readFrames(const std::vector<int> &frames, std::vector<Image<float> > &out)
{
	if (out.size() != frames.size())
		REPORT_ERROR("BUG: TiffMovieReader::readFrames was given a mismatched destination.");

	// A handle that failed to reopen after an earlier frame error is closed,
	// and fImageHandler leaves isTiff set, so nothing downstream would notice.
	// Fail here rather than pass a null TIFF* to LibTIFF.
	for (size_t i = 0; i < workers_.size(); i++)
		if (workers_[i]->handle.ftiff == nullptr)
			REPORT_ERROR(name_ + ": TiffMovieReader was reused after a reader handle failed to reopen.");

	const double t0 = monotonicSeconds();

	const int n_frames = (int)frames.size();
	const int n_workers = (int)workers_.size();
	// One slot per requested frame, so the index of a failure is the position
	// in `frames`, not whichever worker happened to fail first.
	std::vector<std::exception_ptr> errors(n_frames);

	// The shared bounded scheduler: a worker takes the next unclaimed position
	// whenever it goes idle, so a slow frame does not stall the others.
	std::atomic<int> next_slot(0);
	// Two counters, three atomics per frame against a decode of milliseconds.
	// They are what makes "N readers" an observable property rather than an
	// assumption: see Stages.
	std::atomic<int> in_flight(0);
	std::atomic<int> peak_in_flight(0);
	std::atomic<int> team_size(0);

	#pragma omp parallel num_threads(n_workers)
	{
		const int tid = omp_get_thread_num();
		if (tid == 0) team_size.store(omp_get_num_threads());
		// A thread beyond the pool would share a handle; num_threads can be
		// reduced by the runtime, never raised, but guard it explicitly since
		// sharing a mutable TIFF* is the one thing this design must not do.
		if (tid < n_workers)
		{
			Worker &w = *workers_[tid];
			// Under LibTIFF < 4.5 the error context is dispatched through a
			// thread_local pointer, so the scope must be installed on the
			// thread that will use this handle. Under >= 4.5 the context is
			// bound to the handle itself and the scope is inert.
			TiffErrorScope scope(w.handle.tiff_err_ctx.get());

			for (;;)
			{
				const int slot = next_slot.fetch_add(1);
				if (slot >= n_frames) break;
				// A worker whose handle is gone must not decode with it.
				if (w.handle.ftiff == nullptr) break;
				const int now_in_flight = in_flight.fetch_add(1) + 1;
				for (int seen = peak_in_flight.load();
				     now_in_flight > seen &&
				     !peak_in_flight.compare_exchange_weak(seen, now_in_flight); ) {}
				// An exception must not leave an OpenMP structured block:
				// the runtime calls std::terminate. Capture per frame and
				// rethrow below, on the serial path.
				try {
					out[slot].readTIFFFrameFromHandle(w.handle.ftiff, layout_, frames[slot],
					                                  w.scratch, name_, w.handle.tiff_err_ctx.get());
					in_flight.fetch_sub(1);
				} catch (...) {
					in_flight.fetch_sub(1);
					errors[slot] = std::current_exception();
					// The reference path gives every frame a fresh handle, so a
					// frame never inherits LibTIFF state left behind by a failed
					// one. Reopen rather than reuse, and if even that fails,
					// leave the frame's own error in place and stop this worker
					// -- the remaining slots are still taken by the others.
					try {
						w.handle.openFile(name_);
					} catch (...) {
						break;
					}
				}
			}
		}
	}

	stages_.read_frames = monotonicSeconds() - t0;
	stages_.omp_team_size = team_size.load();
	stages_.peak_concurrent_readers = peak_in_flight.load();

	for (int slot = 0; slot < n_frames; slot++)
		if (errors[slot]) std::rethrow_exception(errors[slot]);
}
