/***************************************************************************
 * Built-in per-stage profile for MotionCorr. See docs/stage_profile.md.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef STAGE_PROFILE_H_
#define STAGE_PROFILE_H_

#include <atomic>
#include <cstdint>
#include <fstream>
#include <map>
#include <sstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

/** Exhaustive, low-overhead stage accounting for one process.
 *
 * Main-thread stages are contiguous: next() closes the current stage and opens
 * the following one, so every moment between beginMovie() and endMovie() is
 * charged to exactly one top-level stage. push()/pop() nest finer sub-stages
 * inside the current one without breaking that property. Each boundary samples
 * wall (CLOCK_MONOTONIC), main-thread CPU (CLOCK_THREAD_CPUTIME_ID) and
 * getrusage(RUSAGE_THREAD) fault/switch counters, and is mirrored as an NVTX
 * range when the build has CUDA, so Nsight lines the stages up with device work.
 *
 * Disabled (the default), every entry point returns after one branch on a plain
 * bool; nothing is sampled, allocated or written.
 *
 * Other threads report whole tasks through addThreadTask(); they never touch the
 * main-thread stack.
 */
class StageProfile
{
public:
	static StageProfile &instance();

	/** Open the JSON-lines output. Empty path leaves profiling disabled. */
	void enable(const std::string &path);
	bool enabled() const { return on; }
	/** True if any profile write, flush or close failed. Products are unaffected. */
	bool writeFailed() const { return write_failed; }

	/** Free-form key/value written into the process record. */
	void setNote(const std::string &key, const std::string &value) { if (on) notes[key] = value; }

	void beginRun();
	void endRun(int n_movies);

	void beginMovie(long int index, const std::string &name);
	void endMovie(bool ok);

	/** Close the current top-level stage and open @p stage. */
	void next(const char *stage);
	/** Nested sub-stage inside the current top-level stage. */
	void push(const char *stage);
	void pop();

	/** Accumulate one task run on another thread (e.g. the output writer).
	 * Fault counts come from RUSAGE_THREAD on Linux; elsewhere they are
	 * process-wide and only indicative. */
	void addThreadTask(const char *thread, const char *task, double wall_ms, double cpu_ms,
	                   long minflt);

	struct Sample
	{
		double wall_s = 0, cpu_s = 0;
		long minflt = 0, majflt = 0, vcsw = 0, ivcsw = 0;
	};
	static Sample sampleThread();

private:
	StageProfile() {}

	struct Acc
	{
		double wall_ms = 0, cpu_ms = 0;
		long minflt = 0, majflt = 0, vcsw = 0, ivcsw = 0, count = 0;
		void add(const Sample &a, const Sample &b);
	};
	struct Open
	{
		const char *name;
		Sample start;
		bool nvtx;
	};

	void closeTop(const Sample &now);
	void checkWritten(const char *what);
	void writeMovie(bool ok, const Sample &end);

	// Set once in enable(), during option parsing, before any worker thread
	// exists; read-only afterwards, so unsynchronised reads are race-free.
	bool on = false;
	bool run_open = false;
	// Formatted records are built here and written whole to out_fd, the
	// descriptor from the exclusive create; the path is never reopened.
	std::ostringstream out;
	int out_fd = -1;
	std::string out_path;
	bool write_failed = false, write_failure_reported = false;

	// Main thread only.
	// Main thread only. Workers never read it: every entry point checks the
	// owner first, and owner is atomic.
	bool in_movie = false;
	// Stage calls from any other thread (OpenMP workers reach the same RCTIC
	// markers) are ignored, so the main-thread stack is never shared.
	// Stored by the main thread in beginMovie() before workers run; atomic so
	// worker reads are race-free.
	std::atomic<std::thread::id> owner{};
	bool onOwner() const { return std::this_thread::get_id() == owner.load(std::memory_order_acquire); }
	long int movie_index = -1;
	std::string movie_name;
	Sample movie_start, run_start;
	const char *top = nullptr;
	Sample top_start;
	std::vector<Open> nested;
	std::vector<std::pair<std::string, Acc> > stages;  // first-seen order
	std::map<std::string, Acc> sub;
	std::map<std::string, std::string> notes;

	// Shared with worker threads.
	std::mutex thread_mutex;
	std::map<std::string, Acc> thread_tasks;
};

/** RAII nested sub-stage. */
class StageScope
{
public:
	explicit StageScope(const char *stage)
		: active(StageProfile::instance().enabled())
	{
		if (active) StageProfile::instance().push(stage);
	}
	~StageScope() { if (active) StageProfile::instance().pop(); }
	StageScope(const StageScope &) = delete;
	StageScope &operator=(const StageScope &) = delete;
private:
	bool active;
};

#define MC_STAGE(name) do { if (StageProfile::instance().enabled()) StageProfile::instance().next(name); } while (0)

#endif
