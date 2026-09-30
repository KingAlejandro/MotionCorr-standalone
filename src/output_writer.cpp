/***************************************************************************
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#include "src/output_writer.h"

#include <sstream>

#include "src/error.h"

OutputWriter::OutputWriter(bool background)
	: background(background)
{
	if (background)
		worker = std::thread(&OutputWriter::workerLoop, this);
}

OutputWriter::~OutputWriter()
{
	if (!worker.joinable()) return;
	{
		std::lock_guard<std::mutex> lock(mutex);
		stopping = true;
	}
	queued.notify_all();
	worker.join();
}

void OutputWriter::waitIdle(std::unique_lock<std::mutex> &lock)
{
	idle.wait(lock, [this] { return tasks.empty() && !executing; });
}

void OutputWriter::beginMovie(long int movie_index)
{
	if (!background)
	{
		current_movie = movie_index;
		return;
	}
	std::unique_lock<std::mutex> lock(mutex);
	if (current_movie == movie_index) return;
	waitIdle(lock);
	current_movie = movie_index;
}

void OutputWriter::submit(std::function<void()> task)
{
	if (!background)
	{
		// Inline, so a write failure propagates to the caller on the spot and
		// every later product of this movie is skipped by the unwinding --
		// the same shape as the fail-closed behaviour the worker implements.
		task();
		return;
	}
	{
		std::lock_guard<std::mutex> lock(mutex);
		// An earlier product of this movie already failed: everything after it
		// is withheld, including the STAR completion marker.
		if (current_movie == cancelled_movie) return;
		tasks.push_back({current_movie, std::move(task)});
	}
	queued.notify_one();
}

void OutputWriter::drain()
{
	if (!background) return;
	std::unique_lock<std::mutex> lock(mutex);
	waitIdle(lock);
}

std::vector<OutputWriter::Failure> OutputWriter::takeFailures()
{
	std::lock_guard<std::mutex> lock(mutex);
	std::vector<Failure> taken;
	taken.swap(failures);
	return taken;
}

void OutputWriter::workerLoop()
{
	std::unique_lock<std::mutex> lock(mutex);
	while (true)
	{
		queued.wait(lock, [this] { return stopping || !tasks.empty(); });
		if (tasks.empty())
		{
			// Only reachable with stopping set; drain() has already made sure
			// there is nothing left to write.
			return;
		}

		Task task = std::move(tasks.front());
		tasks.pop_front();
		const bool cancelled = (task.movie_index == cancelled_movie);
		executing = true;
		lock.unlock();

		std::string error;
		if (!cancelled)
		{
			try
			{
				task.run();
			}
			catch (RelionError &e)
			{
				std::ostringstream text;
				text << e;
				error = text.str();
			}
			catch (std::exception &e)
			{
				error = e.what();
			}
			catch (...)
			{
				error = "Unknown error while writing an output product";
			}
		}
		// Release the payload -- a whole micrograph for an image task --
		// outside the lock, whether it was written, skipped or failed.
		task.run = nullptr;

		lock.lock();
		executing = false;
		if (!error.empty())
		{
			cancelled_movie = task.movie_index;
			failures.push_back({task.movie_index, error});
		}
		if (tasks.empty()) idle.notify_all();
	}
}
