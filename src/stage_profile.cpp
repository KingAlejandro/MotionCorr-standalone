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
#include <sys/resource.h>
#include <sys/time.h>

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
	if (path.empty()) return;
	out.open(path.c_str(), std::ios::out | std::ios::trunc);
	if (!out)
		REPORT_ERROR("Cannot open --profile output " + path);
	out << std::setprecision(6) << std::fixed;
	on = true;
}

void StageProfile::beginRun()
{
	if (!on) return;
	run_start = sampleThread();
}

void StageProfile::beginMovie(long int index, const std::string &name)
{
	if (!on) return;
	if (in_movie) endMovie(false);
	owner = std::this_thread::get_id();
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
	while (!nested.empty()) {
		if (nested.back().nvtx) MC_NVTX_POP();
		sub[std::string(top) + "/" + nested.back().name].add(nested.back().start, now);
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
	if (!on || !in_movie) return;
	if (!onOwner()) return;
	const Sample now = sampleThread();
	closeTop(now);
	top = stage;
	top_start = now;
	MC_NVTX_PUSH(stage);
}

void StageProfile::push(const char *stage)
{
	if (!on || !in_movie) return;
	if (!onOwner()) return;
	nested.push_back({stage, sampleThread(), true});
	MC_NVTX_PUSH(stage);
}

void StageProfile::pop()
{
	if (!on || !in_movie || nested.empty()) return;
	if (!onOwner()) return;
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
	if (!on || !in_movie) return;
	if (!onOwner()) return;
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
	// Independent of the stage chain: the caller-side span from runner entry
	// to exit, sampled by beginMovie()/endMovie() themselves.
	const double span_ms = (end.wall_s - movie_start.wall_s) * 1e3;
	double covered_ms = 0;
	for (const auto &entry : stages) covered_ms += entry.second.wall_ms;
	out << "{\"type\":\"movie\",\"index\":" << movie_index << ",\"name\":" << quoted(movie_name)
	    << ",\"span_ms\":" << span_ms << ",\"uncovered_ms\":" << (span_ms - covered_ms)
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
	out.flush();
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
	if (!on) return;
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
	out << ",\"peak_rss_kb\":" << peak_rss_kb << ",\"threads\":[";
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
	out.flush();
}
