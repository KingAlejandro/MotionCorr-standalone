/***************************************************************************
 * Built-in per-stage profile for MotionCorr. See docs/stage_profile.md.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#include "src/stage_profile.h"

#include <ctime>
#include <iomanip>
#include <sstream>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

#ifdef _CUDA_ENABLED
// NVTX3 is header-only and a no-op unless a tool (Nsight) is attached.
#include <nvtx3/nvToolsExt.h>
#define MC_NVTX_PUSH(n) nvtxRangePushA(n)
#define MC_NVTX_POP() nvtxRangePop()
#else
#define MC_NVTX_PUSH(n) ((void)0)
#define MC_NVTX_POP() ((void)0)
#endif

#include "src/error.h"

namespace {

double clockSeconds(clockid_t id)
{
	timespec ts;
	if (clock_gettime(id, &ts) != 0) return 0.0;
	return ts.tv_sec + 1e-9 * ts.tv_nsec;
}

// JSON string escaping for movie names and stage labels.
std::string quoted(const std::string &s)
{
	std::string r = "\"";
	for (char c : s) {
		switch (c) {
		case '"': r += "\\\""; break;
		case '\\': r += "\\\\"; break;
		case '\n': r += "\\n"; break;
		case '\t': r += "\\t"; break;
		default:
			if ((unsigned char)c < 0x20) {
				char buf[8];
				std::snprintf(buf, sizeof buf, "\\u%04x", (unsigned char)c);
				r += buf;
			} else {
				r += c;
			}
		}
	}
	return r + "\"";
}

}  // namespace

StageProfile &StageProfile::instance()
{
	static StageProfile profile;
	return profile;
}

StageProfile::Sample StageProfile::sampleThread()
{
	Sample s;
	s.wall_s = clockSeconds(CLOCK_MONOTONIC);
	s.cpu_s = clockSeconds(CLOCK_THREAD_CPUTIME_ID);
	rusage r;
#ifdef RUSAGE_THREAD
	if (getrusage(RUSAGE_THREAD, &r) == 0)
#else
	if (getrusage(RUSAGE_SELF, &r) == 0)
#endif
	{
		s.minflt = r.ru_minflt;
		s.majflt = r.ru_majflt;
		s.vcsw = r.ru_nvcsw;
		s.ivcsw = r.ru_nivcsw;
	}
	return s;
}

void StageProfile::Acc::add(const Sample &a, const Sample &b)
{
	wall_ms += (b.wall_s - a.wall_s) * 1e3;
	cpu_ms += (b.cpu_s - a.cpu_s) * 1e3;
	minflt += b.minflt - a.minflt;
	majflt += b.majflt - a.majflt;
	vcsw += b.vcsw - a.vcsw;
	ivcsw += b.ivcsw - a.ivcsw;
	count++;
}

void StageProfile::enable(const std::string &path)
{
	if (path.empty() || on) return;
	// Exclusive creation: a diagnostic must never clobber an existing file.
	// --profile is parsed before inputs are read or validated, so a mistyped
	// path, or a symlink/hard link to an input, would otherwise be truncated
	// before anything could reject it. O_EXCL also refuses an existing symlink
	// at the path, whatever it points to.
	const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
	if (fd < 0) {
		const int err = errno;
		if (err == EEXIST)
			REPORT_ERROR("--profile output " + path + " already exists; refusing to overwrite it. "
			             "Choose a new file name or remove the old profile.");
		REPORT_ERROR("Cannot create --profile output " + path + ": " + std::strerror(err));
	}
	::close(fd);
	// The file is ours and empty; reopen it as a stream for formatted output.
	out.open(path.c_str(), std::ios::out | std::ios::trunc);
	if (!out)
		REPORT_ERROR("Cannot open --profile output " + path);
	out << std::setprecision(6) << std::fixed;
	out_path = path;
	on = true;
}

void StageProfile::checkWritten(const char *what)
{
	// A full filesystem or quota failure must not leave a silently truncated
	// profile. Stream state is sticky, so checking after each flush covers
	// every insertion before it. Reported once; products are unaffected.
	if (!out.flush() || out.fail()) {
		write_failed = true;
		if (!write_failure_reported) {
			write_failure_reported = true;
			std::cerr << "ERROR: writing the --profile output " << out_path << " failed (" << what
			          << "); the profile is incomplete. Products are unaffected." << std::endl;
		}
	}
}

void StageProfile::beginRun()
{
	if (!on) return;
	run_start = sampleThread();
	run_open = true;
}

void StageProfile::beginMovie(long int index, const std::string &name)
{
	if (!on) return;
	if (in_movie) endMovie(false);
	owner.store(std::this_thread::get_id(), std::memory_order_release);
	in_movie = true;
	movie_index = index;
	movie_name = name;
	stages.clear();
	sub.clear();
	nested.clear();
	movie_start = sampleThread();
	MC_NVTX_PUSH("movie");
	top = "setup";
	top_start = movie_start;
	MC_NVTX_PUSH(top);
}

void StageProfile::closeTop(const Sample &now)
{
	if (!top) return;
	// Nested ranges still open belong to the stage being closed; an exception
	// path can leave them, so close them here to keep NVTX balanced.
	// Keys match pop(): top, then every enclosing nested name, then this one.
	while (!nested.empty()) {
		if (nested.back().nvtx) MC_NVTX_POP();
		std::string key = std::string(top) + "/";
		for (size_t i = 0; i + 1 < nested.size(); i++) key += std::string(nested[i].name) + "/";
		sub[key + nested.back().name].add(nested.back().start, now);
		nested.pop_back();
	}
	MC_NVTX_POP();
	bool found = false;
	for (auto &entry : stages) {
		if (entry.first == top) { entry.second.add(top_start, now); found = true; break; }
	}
	if (!found) {
		stages.emplace_back(top, Acc());
		stages.back().second.add(top_start, now);
	}
	top = nullptr;
}

void StageProfile::next(const char *stage)
{
	if (!on || !onOwner() || !in_movie) return;
	const Sample now = sampleThread();
	closeTop(now);
	top = stage;
	top_start = now;
	MC_NVTX_PUSH(stage);
}

void StageProfile::push(const char *stage)
{
	if (!on || !onOwner() || !in_movie) return;
	nested.push_back({stage, sampleThread(), true});
	MC_NVTX_PUSH(stage);
}

void StageProfile::pop()
{
	// Owner check first: OpenMP workers reach the same markers and nested is
	// owner-only. Reading nested.empty() before this check raced with the
	// owner's push_back (ThreadSanitizer, #154 review).
	if (!on || !onOwner() || !in_movie || nested.empty()) return;
	const Sample now = sampleThread();
	MC_NVTX_POP();
	const Open o = nested.back();
	nested.pop_back();
	std::string key = top ? std::string(top) + "/" : std::string();
	for (const Open &parent : nested) key += std::string(parent.name) + "/";
	sub[key + o.name].add(o.start, now);
}

void StageProfile::endMovie(bool ok)
{
	if (!on || !onOwner() || !in_movie) return;
	const Sample now = sampleThread();
	closeTop(now);
	MC_NVTX_POP();  // movie
	writeMovie(ok, now);
	in_movie = false;
}

void StageProfile::writeMovie(bool ok, const Sample &end)
{
	Acc total;
	total.add(movie_start, end);
	out << "{\"type\":\"movie\",\"index\":" << movie_index << ",\"name\":" << quoted(movie_name)
	    << ",\"ok\":" << (ok ? "true" : "false")
	    << ",\"wall_ms\":" << total.wall_ms << ",\"cpu_ms\":" << total.cpu_ms
	    << ",\"minflt\":" << total.minflt << ",\"majflt\":" << total.majflt
	    << ",\"vcsw\":" << total.vcsw << ",\"ivcsw\":" << total.ivcsw << ",\"stages\":[";
	bool first = true;
	for (const auto &entry : stages) {
		const Acc &a = entry.second;
		out << (first ? "" : ",") << "{\"name\":" << quoted(entry.first)
		    << ",\"n\":" << a.count << ",\"wall_ms\":" << a.wall_ms << ",\"cpu_ms\":" << a.cpu_ms
		    << ",\"minflt\":" << a.minflt << ",\"majflt\":" << a.majflt
		    << ",\"vcsw\":" << a.vcsw << ",\"ivcsw\":" << a.ivcsw << "}";
		first = false;
	}
	out << "],\"sub\":[";
	first = true;
	for (const auto &entry : sub) {
		const Acc &a = entry.second;
		out << (first ? "" : ",") << "{\"name\":" << quoted(entry.first)
		    << ",\"n\":" << a.count << ",\"wall_ms\":" << a.wall_ms << ",\"cpu_ms\":" << a.cpu_ms
		    << ",\"minflt\":" << a.minflt << "}";
		first = false;
	}
	out << "]}\n";
	checkWritten("movie record");
}

void StageProfile::addThreadTask(const char *thread, const char *task, double wall_ms,
                                 double cpu_ms, long minflt)
{
	if (!on) return;
	std::lock_guard<std::mutex> lock(thread_mutex);
	Acc &a = thread_tasks[std::string(thread) + "/" + task];
	a.wall_ms += wall_ms;
	a.cpu_ms += cpu_ms;
	a.minflt += minflt;
	a.count++;
}

void StageProfile::endRun(int n_movies)
{
	if (!on || !run_open) return;
	run_open = false;
	if (in_movie) endMovie(false);
	const Sample now = sampleThread();
	rusage self;
	getrusage(RUSAGE_SELF, &self);
	const double proc_cpu_ms = (self.ru_utime.tv_sec + self.ru_stime.tv_sec) * 1e3
	                         + (self.ru_utime.tv_usec + self.ru_stime.tv_usec) * 1e-3;
	out << "{\"type\":\"process\",\"movies\":" << n_movies
	    << ",\"run_wall_ms\":" << (now.wall_s - run_start.wall_s) * 1e3
	    << ",\"main_cpu_ms\":" << (now.cpu_s - run_start.cpu_s) * 1e3
	    << ",\"process_cpu_ms\":" << proc_cpu_ms
	    << ",\"process_minflt\":" << self.ru_minflt << ",\"process_majflt\":" << self.ru_majflt;
#ifdef __APPLE__
	const long peak_rss_kb = self.ru_maxrss / 1024;  // bytes on macOS
#else
	const long peak_rss_kb = self.ru_maxrss;         // KiB on Linux
#endif
	out << ",\"peak_rss_kb\":" << peak_rss_kb;
	for (const auto &note : notes) out << "," << quoted(note.first) << ":" << quoted(note.second);
	out << ",\"threads\":[";
	std::lock_guard<std::mutex> lock(thread_mutex);
	bool first = true;
	for (const auto &entry : thread_tasks) {
		const Acc &a = entry.second;
		out << (first ? "" : ",") << "{\"name\":" << quoted(entry.first) << ",\"n\":" << a.count
		    << ",\"wall_ms\":" << a.wall_ms << ",\"cpu_ms\":" << a.cpu_ms
		    << ",\"minflt\":" << a.minflt << "}";
		first = false;
	}
	out << "]}\n";
	checkWritten("process record");
	out.close();
	if (out.fail()) checkWritten("close");
}
