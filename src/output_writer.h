/***************************************************************************
 * Background writer for a movie's output products.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef OUTPUT_WRITER_H_
#define OUTPUT_WRITER_H_

#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

/** Writes one movie's output products on a background thread.
 *
 * Writing the corrected micrographs is ~2 s of a 29 s 24-movie CUDA run and
 * depends on nothing the next movie computes, so it runs while the main thread
 * starts that movie. Three properties constrain the implementation:
 *
 *  - **Order.** A single worker draining a FIFO, so products appear in the
 *    order the serial code wrote them. The per-movie STAR is the resume
 *    completion marker that MotioncorrRunner::isMovieComplete() looks for, and
 *    it is submitted after the images, so it can only land once they are
 *    written and closed.
 *
 *  - **Fail closed.** The first task of a movie that throws cancels that
 *    movie's remaining tasks -- the STAR among them -- and records the movie
 *    as failed. A movie whose image write failed therefore leaves no
 *    completion marker, which is what tests/test_write_faults.py asserts.
 *
 *  - **Bounded memory.** beginMovie() blocks until the previous movie's tasks
 *    have drained, so at most one movie's products are resident beyond what
 *    the serial path holds.
 *
 * Construct with background=false to run every task inline on the calling
 * thread, which restores the serial path exactly, exceptions included.
 */
class OutputWriter
{
public:
	struct Failure
	{
		long int movie_index;
		std::string message;
	};

	explicit OutputWriter(bool background);
	~OutputWriter();

	OutputWriter(const OutputWriter &) = delete;
	OutputWriter &operator=(const OutputWriter &) = delete;

	/** Open the group of products belonging to @p movie_index.
	 *
	 * Blocks until the previous group has finished. Calling it again with the
	 * index already open does nothing, so the first submit() of each movie can
	 * call it unconditionally and the wait then happens as late as possible --
	 * that late wait is what buys the overlap.
	 */
	void beginMovie(long int movie_index);

	/** Queue one product write for the open group. */
	void submit(std::function<void()> task);

	/** Block until every queued product is written and closed. */
	void drain();

	/** Failures recorded so far, in completion order; clears the list. */
	std::vector<Failure> takeFailures();

	/** True if this instance runs tasks on a background thread. */
	bool isBackground() const { return background; }

private:
	struct Task
	{
		long int movie_index;
		std::function<void()> run;
	};

	void workerLoop();
	void waitIdle(std::unique_lock<std::mutex> &lock);

	const bool background;
	std::mutex mutex;
	std::condition_variable queued;   // worker waits here for work or for stop
	std::condition_variable idle;     // producer waits here for the queue to empty
	std::deque<Task> tasks;
	std::vector<Failure> failures;
	long int current_movie = -1;
	long int cancelled_movie = -1;
	bool executing = false;
	bool stopping = false;
	std::thread worker;               // declared last: started once the rest is live
};

#endif
