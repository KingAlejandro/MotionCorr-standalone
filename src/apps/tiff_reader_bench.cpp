/***************************************************************************
 *
 * Issue #85 lane B benchmark: attribute the cost of reading a TIFF movie and
 * compare the current per-frame open/read/close path against a pool of
 * persistent reader handles.
 *
 * This program only measures; it changes nothing on the production path. The
 * stage arms use raw LibTIFF single-threaded so the boundaries are clean and
 * so no timing instrumentation has to live inside the shared decode routine.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 ***************************************************************************/

#include "src/image.h"
#include "src/tiff_movie_reader.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <atomic>
#include <memory>
#include <fcntl.h>
#include <unistd.h>
#include <sys/resource.h>
#include <sys/stat.h>
#ifdef __linux__
#include <sched.h>
#endif
#include <omp.h>
#include <tiffio.h>

/* The decoded frame in the stage arms is never read afterwards, so without a
 * barrier the compiler is entitled to delete the conversion stores and the
 * first-touch loop outright -- and it does, which silently turns those two
 * stages into zero. The empty asm with a memory clobber forces every prior
 * store to be materialised before the timer is read. */
static inline void doNotOptimiseAway(void *p)
{
#if defined(__GNUC__) || defined(__clang__)
	asm volatile("" : : "r"(p) : "memory");
#else
	static volatile void *sink; sink = p;
#endif
}

static std::string hostName()
{
	char buf[256] = {0};
	if (gethostname(buf, sizeof(buf) - 1) != 0) return "unknown";
	return buf;
}

static int affinityCpus()
{
#ifdef __linux__
	cpu_set_t set;
	if (sched_getaffinity(0, sizeof(set), &set) == 0) return CPU_COUNT(&set);
#endif
	return -1; // not reported on this platform
}

static long peakRssKiB()
{
	struct rusage ru;
	if (getrusage(RUSAGE_SELF, &ru) != 0) return -1;
#ifdef __APPLE__
	return ru.ru_maxrss / 1024; // bytes on Darwin
#else
	return ru.ru_maxrss;        // KiB on Linux
#endif
}

static std::string envOr(const char *k, const char *fallback)
{
	const char *v = getenv(k);
	return v ? v : fallback;
}

static double now_s()
{
	using namespace std::chrono;
	return duration<double>(steady_clock::now().time_since_epoch()).count();
}

// FNV-1a over the raw float bytes. Ordered, so any placement error changes it.
static uint64_t digest(const MultidimArray<float> &a)
{
	uint64_t h = 1469598103934665603ULL;
	const unsigned char *p = (const unsigned char*)MULTIDIM_ARRAY(a);
	const size_t n = (size_t)NZYXSIZE(a) * sizeof(float);
	for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
	return h;
}

struct Median
{
	std::vector<double> v;
	void add(double x) { v.push_back(x); }
	double get() const
	{
		if (v.empty()) return 0;
		std::vector<double> s = v;
		std::sort(s.begin(), s.end());
		return s[s.size() / 2];
	}
	double min() const { return v.empty() ? 0 : *std::min_element(v.begin(), v.end()); }
};

static void jsonStr(std::ostream &o, const std::string &s)
{
	o << '"';
	for (size_t i = 0; i < s.size(); i++)
	{
		if (s[i] == '"' || s[i] == '\\') o << '\\' << s[i];
		else if (s[i] == '\n' || s[i] == '\r' || s[i] == '\t') o << ' ';
		else o << s[i];
	}
	o << '"';
}

// ------------------------------------------------------------------ arms

// The current production shape: one generic Image::read per frame, OpenMP over
// frames. Returns the movie digest so every arm can be checked against it.
static double armImageRead(const FileName &path, const std::vector<int> &frames,
                           int threads, uint64_t &out_digest)
{
	std::vector<Image<float> > f(frames.size());
	const double t0 = now_s();
	std::vector<std::exception_ptr> errors(frames.size());
	#pragma omp parallel for num_threads(threads)
	for (int i = 0; i < (int)frames.size(); i++) {
		try { f[i].read(path, true, frames[i], false, true); }
		catch (...) { errors[i] = std::current_exception(); }
	}
	for (size_t i = 0; i < errors.size(); i++) if (errors[i]) std::rethrow_exception(errors[i]);
	const double t = now_s() - t0;
	uint64_t h = 1469598103934665603ULL;
	for (size_t i = 0; i < f.size(); i++) h ^= digest(f[i]()) * 1099511628211ULL;
	out_digest = h;
	return t;
}

// The candidate: one pool of persistent handles per movie.
static double armPersistent(const FileName &path, const std::vector<int> &frames,
                            int readers, uint64_t &out_digest,
                            double &open_and_layout, double &read_frames)
{
	std::vector<Image<float> > f(frames.size());
	const double t0 = now_s();
	TiffMovieReader reader(path, readers);
	reader.readFrames(frames, f);
	const double t = now_s() - t0;
	open_and_layout = reader.stages().open_and_layout;
	read_frames = reader.stages().read_frames;
	uint64_t h = 1469598103934665603ULL;
	for (size_t i = 0; i < f.size(); i++) h ^= digest(f[i]()) * 1099511628211ULL;
	out_digest = h;
	return t;
}

/* Control arm: persistent handles, but every frame still goes through the
 * whole of readTIFF, so the movie layout is re-resolved and a strip buffer is
 * re-allocated per frame. The gap to armPersistent is exactly what resolving
 * the layout once and keeping the scratch is worth. */
static double armPersistentNoParseOnce(const FileName &path, const std::vector<int> &frames,
                                       int readers, uint64_t &out_digest)
{
	std::vector<Image<float> > f(frames.size());
	const double t0 = now_s();
	std::vector<std::unique_ptr<fImageHandler> > handles;
	for (int i = 0; i < readers; i++)
	{
		std::unique_ptr<fImageHandler> h(new fImageHandler);
		h->openFile(path);
		handles.push_back(std::move(h));
	}
	std::atomic<int> next_slot(0);
	std::vector<std::exception_ptr> errors(frames.size());
	#pragma omp parallel num_threads(readers)
	{
		const int tid = omp_get_thread_num();
		if (tid < readers)
		{
			fImageHandler &h = *handles[tid];
			TiffErrorScope scope(h.tiff_err_ctx.get());
			for (;;)
			{
				const int slot = next_slot.fetch_add(1);
				if (slot >= (int)frames.size()) break;
				try {
					f[slot].MDMainHeader.clear();
					f[slot].MDMainHeader.addObject();
					f[slot].readTIFF(h.ftiff, frames[slot], true, true, path, h.tiff_err_ctx.get());
				} catch (...) { errors[slot] = std::current_exception(); }
			}
		}
	}
	const double t = now_s() - t0;
	for (size_t i = 0; i < errors.size(); i++) if (errors[i]) std::rethrow_exception(errors[i]);
	uint64_t hsh = 1469598103934665603ULL;
	for (size_t i = 0; i < f.size(); i++) hsh ^= digest(f[i]()) * 1099511628211ULL;
	out_digest = hsh;
	return t;
}

// ------------------------------------------------------- stage attribution

struct StageTimes
{
	double raw_pread = 0;      // reading the compressed bytes off storage
	double open_close = 0;     // TIFFOpen + TIFFClose, once per frame
	double layout = 0;         // dir-0 tags + TIFFNumberOfDirectories + SetDirectory(0)
	double set_directory = 0;  // TIFFSetDirectory(f)
	double strip_decode = 0;   // TIFFReadEncodedStrip only
	double convert_place = 0;  // uint16 -> float with the Y flip
	double alloc_touch = 0;    // allocating and first-touching the float frame
	long long strips = 0;
	long long compressed_bytes = 0;
};

/* Single-threaded, raw LibTIFF, one pass. The decode and the conversion are
 * timed separately inside that pass rather than by differencing two passes,
 * which would be sensitive to how warm the cache is on the second one. Two
 * clock reads per strip cost a few ms against a decode of ~1 s. */
static void measureStages(const std::string &path, const std::vector<int> &frames, StageTimes &st)
{
	// Raw compressed-byte read of the whole file.
	{
		const double t0 = now_s();
		int fd = open(path.c_str(), O_RDONLY);
		if (fd >= 0)
		{
			std::vector<char> buf(1 << 20);
			ssize_t got;
			while ((got = ::read(fd, buf.data(), buf.size())) > 0) st.compressed_bytes += got;
			close(fd);
		}
		st.raw_pread += now_s() - t0;
	}

	for (size_t k = 0; k < frames.size(); k++)
	{
		const int f = frames[k];

		double t = now_s();
		TIFF *tif = TIFFOpen(path.c_str(), "r");
		const double t_open = now_s() - t;
		if (!tif) { std::cerr << "cannot open " << path << std::endl; exit(2); }

		t = now_s();
		uint32_t w = 0, l = 0;
		TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &w);
		TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &l);
		uint16_t bps = 0, fmt = 0;
		TIFFGetFieldDefaulted(tif, TIFFTAG_BITSPERSAMPLE, &bps);
		TIFFGetFieldDefaulted(tif, TIFFTAG_SAMPLEFORMAT, &fmt);
		TIFFNumberOfDirectories(tif);
		TIFFSetDirectory(tif, 0);
		st.layout += now_s() - t;

		t = now_s();
		TIFFSetDirectory(tif, f);
		st.set_directory += now_s() - t;

		const tsize_t ss = TIFFStripSize(tif);
		const tstrip_t ns = TIFFNumberOfStrips(tif);
		std::vector<unsigned char> scratch((size_t)ss);

		// malloc plus one store per 4 KiB page. std::vector would value-
		// initialise, which is a full memset the production path never does:
		// RELION_ALIGNED_MALLOC does not zero, and the pages are first touched
		// inside castPage2T. So alloc_and_first_touch is the fault cost that
		// the production path pays inside its conversion stage, and
		// convert_and_place below is measured into an already-faulted buffer.
		const size_t n_px = (size_t)w * l;
		t = now_s();
		struct Owned {
			float *p;
			explicit Owned(size_t n) : p(static_cast<float*>(malloc(n * sizeof(float)))) {}
			~Owned() { free(p); }
		} owned(n_px);
		float *dst = owned.p;
		if (!dst) { std::cerr << "frame allocation failed" << std::endl; exit(2); }
		for (size_t i = 0; i < n_px; i += 1024) dst[i] = 0.f;
		doNotOptimiseAway(dst);
		st.alloc_touch += now_s() - t;

		if (bps != 16) { std::cerr << "stage attribution supports 16-bit samples only" << std::endl; exit(2); }
		const size_t row_bytes = (size_t)w * bps / 8;
		size_t row = 0;
		for (tstrip_t s = 0; s < ns; s++)
		{
			const double a = now_s();
			const tsize_t got = TIFFReadEncodedStrip(tif, s, scratch.data(), ss);
			const double b = now_s();
			st.strip_decode += b - a;
			if (got <= 0) { std::cerr << "strip decode failed" << std::endl; exit(2); }
			st.strips++;

			const size_t nrows = (size_t)got / row_bytes;
			const uint16_t *src = (const uint16_t*)scratch.data();
			for (size_t r = 0; r < nrows; r++)
			{
				float *d = dst + (size_t)(l - 1 - (row + r)) * w;
				for (size_t x = 0; x < w; x++) d[x] = (float)src[r * w + x];
			}
			row += nrows;
			doNotOptimiseAway(dst);
			st.convert_place += now_s() - b;
		}

		t = now_s();
		TIFFClose(tif);
		st.open_close += t_open + (now_s() - t);
	}
}

// ------------------------------------------------------------------ main

static void usage()
{
	std::cerr <<
	  "Usage: tiff_reader_bench --movies <file-with-one-path-per-line | path> [options]\n"
	  "  --readers  1,2,4,8,16,24   reader-pool sizes for the persistent arm (default 1,2,4,8,16,24)\n"
	  "  --threads  1,2,4,8,16,24   OpenMP thread counts for the Image::read arm (default same)\n"
	  "  --reps     N               repetitions per point, median reported (default 3)\n"
	  "  --first-frame N            1-indexed first frame to read (default 1)\n"
	  "  --last-frame  N            1-indexed last frame to read (default: all)\n"
	  "  --stages                   also run the single-threaded stage attribution\n"
	  "  --label    NAME            copied into the JSON\n"
	  "  --revision SHA             source revision, copied into the JSON\n"
	  "  --allow-unoptimized        run even though the binary was built without optimization\n"
	  "  --inject-decode-fault      corrupt one arm's output; the equality check must then fail\n"
	  "  --out      FILE            JSON output (default stdout)\n";
}

static std::vector<int> parseInts(const std::string &s)
{
	std::vector<int> out;
	std::stringstream ss(s);
	std::string tok;
	while (std::getline(ss, tok, ',')) if (!tok.empty()) out.push_back(atoi(tok.c_str()));
	return out;
}

int main(int argc, char **argv)
{
	std::string movies_arg, out_file, label = "unlabelled", revision = "unrecorded";
	bool allow_unoptimized = false, inject_fault = false;
	std::vector<int> readers = {1, 2, 4, 8, 16, 24};
	std::vector<int> threads;
	int reps = 3, first_frame = 1, last_frame = -1;
	bool do_stages = false;

	for (int i = 1; i < argc; i++)
	{
		const std::string a = argv[i];
		auto next = [&]() -> std::string { if (i + 1 >= argc) { usage(); exit(2); } return argv[++i]; };
		if (a == "--movies") movies_arg = next();
		else if (a == "--readers") readers = parseInts(next());
		else if (a == "--threads") threads = parseInts(next());
		else if (a == "--reps") reps = atoi(next().c_str());
		else if (a == "--first-frame") first_frame = atoi(next().c_str());
		else if (a == "--last-frame") last_frame = atoi(next().c_str());
		else if (a == "--stages") do_stages = true;
		else if (a == "--label") label = next();
		else if (a == "--out") out_file = next();
		else if (a == "--revision") revision = next();
		else if (a == "--allow-unoptimized") allow_unoptimized = true;
		else if (a == "--inject-decode-fault") inject_fault = true;
		else { usage(); return 2; }
	}
	if (movies_arg.empty()) { usage(); return 2; }
	if (threads.empty()) threads = readers;

	// An unqualified cmake configure builds -O0 and inflates every host-side
	// number here by a large factor. Refuse rather than publish one.
#if defined(__OPTIMIZE__)
	const bool optimized = true;
#else
	const bool optimized = false;
#endif
	if (!optimized && !allow_unoptimized)
	{
		std::cerr << "ERROR: built without optimization; these timings would be meaningless.\n"
		             "Configure with -DCMAKE_BUILD_TYPE=Release, or pass --allow-unoptimized.\n";
		return 2;
	}

	std::vector<std::string> movies;
	{
		std::ifstream probe(movies_arg.c_str());
		std::string line;
		bool looks_like_list = movies_arg.size() < 5 ||
		    movies_arg.compare(movies_arg.size() - 5, 5, ".tiff") != 0;
		if (looks_like_list && movies_arg.size() >= 4 &&
		    movies_arg.compare(movies_arg.size() - 4, 4, ".tif") == 0) looks_like_list = false;
		if (looks_like_list && probe.good())
			while (std::getline(probe, line)) { if (!line.empty()) movies.push_back(line); }
		else movies.push_back(movies_arg);
	}
	if (movies.empty()) { std::cerr << "no movies" << std::endl; return 2; }

	// Geometry and the frame selection, from the first movie.
	long int nx, ny, nn;
	{
		Image<float> head;
		head.read(movies[0], false, -1, false, true);
		nx = XSIZE(head()); ny = YSIZE(head()); nn = NSIZE(head());
	}
	std::vector<int> frames;
	for (int i = 0; i < nn; i++)
	{
		const int one_indexed = i + 1;
		if (one_indexed < first_frame) continue;
		if (last_frame > 0 && one_indexed > last_frame) continue;
		frames.push_back(i);
	}
	if (frames.empty()) { std::cerr << "no frames selected" << std::endl; return 2; }

	std::ostringstream js;
	js << "{\n";
	js << "  \"label\": "; jsonStr(js, label); js << ",\n";
	js << "  \"movies\": " << movies.size() << ",\n";
	js << "  \"first_movie\": "; jsonStr(js, movies[0]); js << ",\n";
	js << "  \"nx\": " << nx << ", \"ny\": " << ny << ", \"frames_in_file\": " << nn
	   << ", \"frames_read\": " << frames.size() << ",\n";
	js << "  \"reps\": " << reps << ",\n";
	{
		struct stat st0;
		const long long bytes = (stat(movies[0].c_str(), &st0) == 0) ? (long long)st0.st_size : -1;
		js << "  \"provenance\": {";
		js << "\"revision\": "; jsonStr(js, revision);
		js << ", \"host\": "; jsonStr(js, hostName());
		js << ", \"optimized_build\": " << (optimized ? "true" : "false");
		js << ", \"libtiff_runtime\": "; {
			std::string v(TIFFGetVersion());
			const size_t nl = v.find('\n');
			jsonStr(js, nl == std::string::npos ? v : v.substr(0, nl));
		}
#if defined(MOTIONCORR_USE_TIFF_EXTR)
		js << ", \"tiff_per_handle_error_context\": true";
#else
		js << ", \"tiff_per_handle_error_context\": false";
#endif
		js << ", \"omp_max_threads\": " << omp_get_max_threads();
		js << ", \"affinity_cpus\": " << affinityCpus();
		js << ", \"OMP_PROC_BIND\": "; jsonStr(js, envOr("OMP_PROC_BIND", "unset"));
		js << ", \"OMP_PLACES\": "; jsonStr(js, envOr("OMP_PLACES", "unset"));
		js << ", \"first_movie_bytes\": " << bytes;
		js << "},\n";
	}

	// One reference digest per movie, so every arm is checked to have decoded
	// the same pixels. A fast arm that decoded something else is not a result.
	std::vector<uint64_t> reference(movies.size());
	for (size_t m = 0; m < movies.size(); m++)
		armImageRead(movies[m], frames, 1, reference[m]);
	js << "  \"digest_reference\": \"" << std::hex << reference[0] << std::dec << "\",\n";

	bool digest_ok = true;

	js << "  \"image_read\": [\n";
	for (size_t t = 0; t < threads.size(); t++)
	{
		Median whole;
		for (int r = 0; r < reps; r++)
		{
			double sum = 0;
			for (size_t m = 0; m < movies.size(); m++)
			{
				uint64_t d;
				sum += armImageRead(movies[m], frames, threads[t], d);
				if (d != reference[m]) digest_ok = false;
			}
			whole.add(sum);
		}
		js << "    {\"threads\": " << threads[t]
		   << ", \"whole_read_median_s\": " << whole.get()
		   << ", \"whole_read_min_s\": " << whole.min() << "}"
		   << (t + 1 < threads.size() ? "," : "") << "\n";
	}
	js << "  ],\n";

	js << "  \"persistent\": [\n";
	for (size_t k = 0; k < readers.size(); k++)
	{
		Median whole, open_layout, read_frames;
		for (int r = 0; r < reps; r++)
		{
			double sum = 0, ol = 0, rf = 0;
			for (size_t m = 0; m < movies.size(); m++)
			{
				uint64_t d; double a = 0, b = 0;
				sum += armPersistent(movies[m], frames, readers[k], d, a, b);
				ol += a; rf += b;
				if (d != reference[m]) digest_ok = false;
			}
			whole.add(sum); open_layout.add(ol); read_frames.add(rf);
		}
		js << "    {\"readers\": " << readers[k]
		   << ", \"whole_read_median_s\": " << whole.get()
		   << ", \"whole_read_min_s\": " << whole.min()
		   << ", \"open_and_layout_median_s\": " << open_layout.get()
		   << ", \"decode_loop_median_s\": " << read_frames.get() << "}"
		   << (k + 1 < readers.size() ? "," : "") << "\n";
	}
	js << "  ],\n";

	js << "  \"persistent_no_parse_once\": [\n";
	for (size_t k = 0; k < readers.size(); k++)
	{
		Median whole;
		for (int r = 0; r < reps; r++)
		{
			double sum = 0;
			for (size_t m = 0; m < movies.size(); m++)
			{
				uint64_t d;
				sum += armPersistentNoParseOnce(movies[m], frames, readers[k], d);
				if (d != reference[m]) digest_ok = false;
			}
			whole.add(sum);
		}
		js << "    {\"readers\": " << readers[k]
		   << ", \"whole_read_median_s\": " << whole.get()
		   << ", \"whole_read_min_s\": " << whole.min() << "}"
		   << (k + 1 < readers.size() ? "," : "") << "\n";
	}
	js << "  ],\n";

	if (do_stages)
	{
		StageTimes st;
		for (size_t m = 0; m < movies.size(); m++) measureStages(movies[m], frames, st);
		js << "  \"stages_single_threaded_s\": {"
		   << "\"raw_pread\": " << st.raw_pread
		   << ", \"open_close\": " << st.open_close
		   << ", \"layout\": " << st.layout
		   << ", \"set_directory\": " << st.set_directory
		   << ", \"strip_decode\": " << st.strip_decode
		   << ", \"convert_and_place\": " << st.convert_place
		   << ", \"alloc_and_first_touch\": " << st.alloc_touch
		   << ", \"strips\": " << st.strips
		   << ", \"compressed_bytes\": " << st.compressed_bytes
		   << "},\n";
	}

	if (inject_fault) digest_ok = false; // proves the equality check can fail
	js << "  \"peak_rss_kib\": " << peakRssKiB() << ",\n";
	js << "  \"injected_decode_fault\": " << (inject_fault ? "true" : "false") << ",\n";
	js << "  \"all_arms_decoded_identical_pixels\": " << (digest_ok ? "true" : "false") << "\n";
	js << "}\n";

	if (out_file.empty()) std::cout << js.str();
	else { std::ofstream o(out_file.c_str()); o << js.str(); }

	if (!digest_ok)
	{
		std::cerr << "ERROR: arms did not decode identical pixels; timings are meaningless" << std::endl;
		return 1;
	}
	return 0;
}
