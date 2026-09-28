/* TIFF ingest attribution benchmark (Issue #85, lane A).
 *
 * Splits the production "read movie" stage into the components named in the
 * #85 benchmark contract -- storage read, TIFF directory handling, Deflate,
 * integer->float conversion, Y placement, allocation/first-touch and thread
 * dispatch -- and times each one separately on real tutorial input.
 *
 * This tool only reads. It never writes a TIFF and never changes the
 * production decode path; the production arm calls Image<float>::read()
 * exactly as MotioncorrRunner does, so it measures the shipping code rather
 * than a copy of it.
 *
 * Every arm that materialises pixels is compared against the production
 * reference with an exact ordered comparison over the whole movie. Two weaker
 * comparators (a global double sum and an ordered row-sum vector) run
 * alongside it so --selftest can show which mutation classes each one cannot
 * see. --inject <mode> corrupts a live arm's real output, so a PASS from this
 * harness is falsifiable rather than structural.
 */

#include "src/image.h"

#include <tiffio.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <atomic>

#include <fcntl.h>
#include <sched.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <omp.h>

namespace {

// ---------------------------------------------------------------- utilities

double wallNow()
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

double cpuNow()
{
	struct timespec ts;
	clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
	return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

struct Faults { long minor = 0, major = 0; };

Faults faultsNow()
{
	struct rusage ru;
	getrusage(RUSAGE_SELF, &ru);
	return {ru.ru_minflt, ru.ru_majflt};
}

long maxRssKiB()
{
	struct rusage ru;
	getrusage(RUSAGE_SELF, &ru);
	return ru.ru_maxrss;
}

// The mask actually in force, not the one we asked for. A taskset that failed
// to apply would otherwise be invisible in the retained record.
std::string affinityMask()
{
	cpu_set_t set;
	CPU_ZERO(&set);
	if (sched_getaffinity(0, sizeof(set), &set) != 0) return "unknown";
	std::string out;
	int run_start = -1;
	for (int c = 0; c <= CPU_SETSIZE; c++)
	{
		const bool in = (c < CPU_SETSIZE) && CPU_ISSET(c, &set);
		if (in && run_start < 0) run_start = c;
		if (!in && run_start >= 0)
		{
			if (!out.empty()) out += ",";
			out += std::to_string(run_start);
			if (c - 1 != run_start) out += "-" + std::to_string(c - 1);
			run_start = -1;
		}
	}
	return out.empty() ? "none" : out;
}

int affinityCount()
{
	cpu_set_t set;
	CPU_ZERO(&set);
	if (sched_getaffinity(0, sizeof(set), &set) != 0) return -1;
	return CPU_COUNT(&set);
}

std::string jsonEscape(const std::string &s)
{
	std::string out;
	for (char c : s)
	{
		if (c == '"' || c == '\\') { out += '\\'; out += c; }
		else if (c == '\n') out += "\\n";
		else if (c == '\r') continue;
		else out += c;
	}
	return out;
}

// Fraction of a file currently resident in the page cache, via mincore() over
// a temporary mapping. posix_fadvise(DONTNEED) returns 0 when the advice was
// accepted, not when pages were actually dropped -- on tmpfs it drops nothing
// and returns 0 -- so a cold arm that only checks the return value has no
// evidence it was cold. This measures residency instead of asserting it.
double residentFraction(const std::string &path)
{
	int fd = open(path.c_str(), O_RDONLY);
	if (fd < 0) return -1.0;
	struct stat st;
	if (fstat(fd, &st) != 0 || st.st_size <= 0) { close(fd); return -1.0; }
	void *m = mmap(nullptr, (size_t)st.st_size, PROT_READ, MAP_SHARED, fd, 0);
	close(fd);
	if (m == MAP_FAILED) return -1.0;
	const size_t pages = ((size_t)st.st_size + 4095) / 4096;
	std::vector<unsigned char> vec(pages);
	double frac = -1.0;
	if (mincore(m, (size_t)st.st_size, vec.data()) == 0)
	{
		size_t n = 0;
		for (unsigned char c : vec) n += (c & 1);
		frac = (double)n / (double)pages;
	}
	munmap(m, (size_t)st.st_size);
	return frac;
}

// Drop this file's clean page-cache pages. Only our file is affected, so a
// cold arm on a shared machine does not evict anyone else's data.
bool evictFileCache(const std::string &path)
{
	int fd = open(path.c_str(), O_RDONLY);
	if (fd < 0) return false;
	(void)fsync(fd); // DONTNEED is a no-op on dirty pages; our inputs are read-only
	const int rc = posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);
	close(fd);
	return rc == 0;
}

size_t fileSize(const std::string &path)
{
	struct stat st;
	if (stat(path.c_str(), &st) != 0) return 0;
	return (size_t)st.st_size;
}

// ------------------------------------------------------------ TIFF geometry

struct TiffGeometry {
	uint32_t width = 0, length = 0;
	uint16_t bits_per_sample = 0, sample_format = 0, compression = 0, predictor = 0;
	uint32_t rows_per_strip = 0;
	tstrip_t strips_per_frame = 0;
	long n_frames = 0;
	size_t strip_size = 0;          // TIFFStripSize of directory 0
	size_t compressed_bytes = 0;    // sum of StripByteCounts over all frames
	size_t max_strip_bytes = 0;     // largest single compressed strip
	size_t decoded_bytes_u16 = 0;
	size_t decoded_bytes_f32 = 0;
	size_t file_bytes = 0;
	bool uniform = true;            // every directory has the same shape
};

// Compressed extents, so the pread arm reads exactly the bytes the decoder
// consumes rather than the whole file.
struct StripExtents {
	std::vector<uint64_t> offset;   // flattened (frame, strip)
	std::vector<uint64_t> bytes;
};

bool probeGeometry(const std::string &path, TiffGeometry &g, StripExtents &ext, std::string &err)
{
	TIFF *t = TIFFOpen(path.c_str(), "r");
	if (!t) { err = "TIFFOpen failed: " + path; return false; }

	g.file_bytes = fileSize(path);
	g.n_frames = (long)TIFFNumberOfDirectories(t);
	if (g.n_frames <= 0) { TIFFClose(t); err = "no TIFF directories"; return false; }

	for (long d = 0; d < g.n_frames; d++)
	{
		if (TIFFSetDirectory(t, (tdir_t)d) == 0)
		{
			TIFFClose(t);
			err = "TIFFSetDirectory failed at " + std::to_string(d);
			return false;
		}
		uint32_t w = 0, l = 0, rps = 0;
		uint16_t bps = 0, sf = 0, comp = 0, pred = 1;
		TIFFGetField(t, TIFFTAG_IMAGEWIDTH, &w);
		TIFFGetField(t, TIFFTAG_IMAGELENGTH, &l);
		TIFFGetFieldDefaulted(t, TIFFTAG_BITSPERSAMPLE, &bps);
		TIFFGetFieldDefaulted(t, TIFFTAG_SAMPLEFORMAT, &sf);
		TIFFGetFieldDefaulted(t, TIFFTAG_COMPRESSION, &comp);
		TIFFGetFieldDefaulted(t, TIFFTAG_ROWSPERSTRIP, &rps);
		TIFFGetFieldDefaulted(t, TIFFTAG_PREDICTOR, &pred);
		const tstrip_t ns = TIFFNumberOfStrips(t);
		const tsize_t ss = TIFFStripSize(t);

		if (d == 0)
		{
			g.width = w; g.length = l; g.bits_per_sample = bps; g.sample_format = sf;
			g.compression = comp; g.rows_per_strip = rps; g.predictor = pred;
			g.strips_per_frame = ns; g.strip_size = (size_t)ss;
		}
		else if (w != g.width || l != g.length || bps != g.bits_per_sample ||
		         sf != g.sample_format || comp != g.compression || ns != g.strips_per_frame)
		{
			g.uniform = false;
		}

		uint64_t *counts = nullptr, *offsets = nullptr;
		if (TIFFGetField(t, TIFFTAG_STRIPBYTECOUNTS, &counts) == 1 &&
		    TIFFGetField(t, TIFFTAG_STRIPOFFSETS, &offsets) == 1)
		{
			for (tstrip_t s = 0; s < ns; s++)
			{
				g.compressed_bytes += counts[s];
				g.max_strip_bytes = std::max(g.max_strip_bytes, (size_t)counts[s]);
				ext.offset.push_back(offsets[s]);
				ext.bytes.push_back(counts[s]);
			}
		}
	}
	TIFFClose(t);

	const size_t px = (size_t)g.width * g.length * (size_t)g.n_frames;
	g.decoded_bytes_u16 = px * 2;
	g.decoded_bytes_f32 = px * 4;
	return true;
}

// ------------------------------------------------------------- comparators
//
// Three oracles of deliberately different strength. The exact one is the gate;
// the other two exist so --selftest can show, per mutation class, which
// comparators are blind to it. A checksum a reordering cannot move is not a
// decode correctness check.

struct Oracles {
	double global_sum = 0.0;          // blind to every permutation
	std::vector<double> row_sums;     // blind to intra-row permutation only
};

Oracles computeOracles(const float *p, size_t nx, size_t ny, size_t nframes)
{
	Oracles o;
	o.row_sums.assign(ny * nframes, 0.0);
	double total = 0.0;
	for (size_t r = 0; r < ny * nframes; r++)
	{
		double s = 0.0;
		const float *row = p + r * nx;
		for (size_t x = 0; x < nx; x++) s += (double)row[x];
		o.row_sums[r] = s;
		total += s;
	}
	o.global_sum = total;
	return o;
}

struct CompareResult {
	bool exact_equal = false;
	bool global_sum_equal = false;
	bool row_sums_equal = false;
	size_t first_diff_index = (size_t)-1;
	float ref_value = 0.0f, got_value = 0.0f;
	size_t n_diff = 0;
};

// with_oracles=false does the exact gate only. The exact gate is cheap
// (memcmp) and runs on every repeat so a flaky arm cannot hide behind a
// single sampled check; the two weaker oracles stream the whole movie twice
// and are evaluated once, on the last repeat.
CompareResult compareAll(const float *ref, const float *got, const Oracles &ref_o,
                         size_t nx, size_t ny, size_t nframes, bool with_oracles = true)
{
	CompareResult r;
	const size_t n = nx * ny * nframes;

	// Exact ordered comparison over the whole movie. memcmp first, then locate
	// the first difference for the record if it fails.
	r.exact_equal = (memcmp(ref, got, n * sizeof(float)) == 0);
	if (!r.exact_equal)
	{
		for (size_t i = 0; i < n; i++)
		{
			if (memcmp(&ref[i], &got[i], sizeof(float)) != 0)
			{
				if (r.first_diff_index == (size_t)-1)
				{
					r.first_diff_index = i;
					r.ref_value = ref[i];
					r.got_value = got[i];
				}
				r.n_diff++;
			}
		}
	}

	if (with_oracles)
	{
		const Oracles got_o = computeOracles(got, nx, ny, nframes);
		r.global_sum_equal = (got_o.global_sum == ref_o.global_sum);
		r.row_sums_equal = (got_o.row_sums == ref_o.row_sums);
	}
	else
	{
		r.global_sum_equal = r.row_sums_equal = r.exact_equal;
	}
	return r;
}

// ---------------------------------------------------------------- mutations
//
// One mutation per failure class the decode path can actually exhibit.

enum class Mutation {
	None,
	Value,          // one pixel altered by 1 ULP      -- conversion/arithmetic slip
	SwapPixInRow,   // two pixels swapped inside a row -- X-stride slip
	SwapRows,       // two rows swapped in a frame     -- strip placement slip
	YFlipFrame,     // one frame's rows reversed       -- Y-flip convention
	SwapFrames,     // two frames swapped              -- directory selection slip
};

const char *mutationName(Mutation m)
{
	switch (m) {
	case Mutation::None:         return "none";
	case Mutation::Value:        return "value_1ulp";
	case Mutation::SwapPixInRow: return "swap_pixels_in_row";
	case Mutation::SwapRows:     return "swap_rows_in_frame";
	case Mutation::YFlipFrame:   return "yflip_one_frame";
	case Mutation::SwapFrames:   return "swap_two_frames";
	}
	return "?";
}

Mutation parseMutation(const std::string &s)
{
	if (s == "none")                return Mutation::None;
	if (s == "value_1ulp")          return Mutation::Value;
	if (s == "swap_pixels_in_row")  return Mutation::SwapPixInRow;
	if (s == "swap_rows_in_frame")  return Mutation::SwapRows;
	if (s == "yflip_one_frame")     return Mutation::YFlipFrame;
	if (s == "swap_two_frames")     return Mutation::SwapFrames;
	std::cerr << "unknown mutation: " << s << "\n";
	exit(2);
}

// Applied away from the edges so no boundary special case masks it.
void applyMutation(float *p, Mutation m, size_t nx, size_t ny, size_t nframes)
{
	const size_t frame = nx * ny;
	float *F = p + (nframes / 2) * frame;
	switch (m)
	{
	case Mutation::None:
		break;
	case Mutation::Value: {
		float &v = F[(ny / 2) * nx + nx / 2];
		v = std::nextafterf(v, v + 1.0f);
		break;
	}
	case Mutation::SwapPixInRow: {
		float *row = F + (ny / 2) * nx;
		std::swap(row[nx / 4], row[3 * nx / 4]);
		break;
	}
	case Mutation::SwapRows: {
		float *a = F + (ny / 4) * nx;
		float *b = F + (3 * ny / 4) * nx;
		for (size_t x = 0; x < nx; x++) std::swap(a[x], b[x]);
		break;
	}
	case Mutation::YFlipFrame: {
		for (size_t y = 0; y < ny / 2; y++)
			for (size_t x = 0; x < nx; x++)
				std::swap(F[y * nx + x], F[(ny - 1 - y) * nx + x]);
		break;
	}
	case Mutation::SwapFrames: {
		if (nframes < 2) break;
		float *a = p;
		float *b = p + (nframes - 1) * frame;
		for (size_t i = 0; i < frame; i++) std::swap(a[i], b[i]);
		break;
	}
	}
}

// -------------------------------------------------------------------- arms

struct Arm {
	std::string name;
	bool produces_pixels = false;
	size_t bytes_in = 0;     // bytes consumed from storage (or from RAM, for conversion)
	size_t bytes_out = 0;    // bytes produced
	std::function<void()> pre;    // untimed: setup the production stage does elsewhere
	std::function<void()> run;
	std::function<void()> post;   // untimed: prepare the comparison buffer
};

// Fresh anonymous pages every time. glibc raises its dynamic mmap threshold
// after a large free, so a malloc/free pair would stop faulting on the second
// iteration and the first-touch arm would silently measure nothing.
void *freshPages(size_t bytes)
{
	void *p = mmap(nullptr, bytes, PROT_READ | PROT_WRITE,
	               MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	return (p == MAP_FAILED) ? nullptr : p;
}

// Keep decode results observable so nothing is optimised away.
volatile uint64_t g_sink = 0;

// Work witness. Arms that skip a frame on a failed open or a failed
// TIFFSetDirectory `continue` silently, so an arm in which everything failed
// would report a very fast time and no error. The non-pixel arms -- including
// tiff_decode_only, which carries the Deflate attribution -- have no exact
// gate to catch that. Each such arm counts the strips it genuinely processed
// and the count is compared against the expected total.
std::atomic<uint64_t> g_strips_done{0};

// Negative control for the witness above. --fault-witness makes the counting
// arms drop one strip from their count, which must turn the run red. A
// witness that has never been observed to fail is not evidence that the arm
// did its work.
bool g_fault_witness = false;

} // namespace

// -------------------------------------------------------------------- main

int main(int argc, char **argv)
{
	std::vector<std::string> movies;
	int repeats = 3;
	std::vector<int> workers;
	std::string regime = "warm";
	std::string out_path, only_arm, inject_arm, tag;
	bool selftest = false;
	Mutation inject = Mutation::None;

	for (int i = 1; i < argc; i++)
	{
		const std::string a = argv[i];
		auto next = [&](const char *what) -> std::string {
			if (i + 1 >= argc) { std::cerr << "missing value for " << what << "\n"; exit(2); }
			return argv[++i];
		};
		if      (a == "--movie")      movies.push_back(next("--movie"));
		else if (a == "--repeats")    repeats = std::stoi(next("--repeats"));
		else if (a == "--regime")     regime = next("--regime");      // warm | cold
		else if (a == "--out")        out_path = next("--out");
		else if (a == "--arm")        only_arm = next("--arm");
		else if (a == "--tag")        tag = next("--tag");
		else if (a == "--selftest")   selftest = true;
		else if (a == "--inject")     inject = parseMutation(next("--inject"));
		else if (a == "--inject-arm") inject_arm = next("--inject-arm");
		else if (a == "--fault-witness") g_fault_witness = true;
		else if (a == "--workers") {
			std::stringstream ss(next("--workers"));
			std::string tok;
			while (std::getline(ss, tok, ',')) if (!tok.empty()) workers.push_back(std::stoi(tok));
		}
		else { std::cerr << "unknown option: " << a << "\n"; return 2; }
	}
	if (movies.empty()) { std::cerr << "need at least one --movie\n"; return 2; }
	int gate_failures = 0;
	if (workers.empty()) workers = {1, 2, 4, 8, 16, 24};
	if (repeats < 1) { std::cerr << "--repeats must be >= 1\n"; return 2; }

	// Unknown private tags in these files are not errors and would otherwise
	// flood the run.
	TIFFSetWarningHandler(nullptr);

	std::ostringstream J;
	J << "{\n";
	J << "  \"tool\": \"tiff_ingest_bench\",\n";
	J << "  \"tag\": \"" << jsonEscape(tag) << "\",\n";
	J << "  \"regime\": \"" << jsonEscape(regime) << "\",\n";
	J << "  \"cpu_mask\": \"" << affinityMask() << "\",\n";
	J << "  \"cpu_mask_count\": " << affinityCount() << ",\n";
	J << "  \"omp_max_threads\": " << omp_get_max_threads() << ",\n";
	J << "  \"repeats\": " << repeats << ",\n";
	J << "  \"libtiff_version\": \"" << jsonEscape(TIFFGetVersion() ? TIFFGetVersion() : "?") << "\",\n";

	// ------------------------------------------------------------ self-test
	//
	// Runs before any timing and establishes what the gate below can see.
	if (selftest)
	{
		const std::string &path = movies.front();
		Image<float> probe;
		probe.read(path, true, -1, false, true);
		const size_t nx = XSIZE(probe()), ny = YSIZE(probe()), nn = NSIZE(probe());
		std::vector<float> ref(MULTIDIM_ARRAY(probe()), MULTIDIM_ARRAY(probe()) + nx * ny * nn);
		const Oracles ref_o = computeOracles(ref.data(), nx, ny, nn);

		J << "  \"selftest\": {\n";
		J << "    \"movie\": \"" << jsonEscape(path) << "\",\n";
		J << "    \"nx\": " << nx << ", \"ny\": " << ny << ", \"nframes\": " << nn << ",\n";
		J << "    \"cases\": [\n";
		const Mutation all[] = {Mutation::None, Mutation::Value, Mutation::SwapPixInRow,
		                        Mutation::SwapRows, Mutation::YFlipFrame, Mutation::SwapFrames};
		bool first = true;
		for (Mutation m : all)
		{
			std::vector<float> mutated = ref;
			applyMutation(mutated.data(), m, nx, ny, nn);
			const CompareResult c = compareAll(ref.data(), mutated.data(), ref_o, nx, ny, nn);
			const bool real = (m != Mutation::None);
			if (!first) J << ",\n";
			first = false;
			J << "      {\"mutation\": \"" << mutationName(m) << "\""
			  << ", \"exact_detects\": "      << (real && !c.exact_equal      ? "true" : "false")
			  << ", \"global_sum_detects\": " << (real && !c.global_sum_equal ? "true" : "false")
			  << ", \"row_sums_detect\": "    << (real && !c.row_sums_equal   ? "true" : "false")
			  << ", \"n_pixels_differing\": " << c.n_diff << "}";
		}
		J << "\n    ]\n  },\n";
	}

	// ------------------------------------------------------------- per movie
	J << "  \"movies\": [\n";
	bool first_movie = true;

	for (const std::string &path : movies)
	{
		TiffGeometry g;
		StripExtents ext;
		std::string err;
		if (!probeGeometry(path, g, ext, err))
		{
			std::cerr << "geometry probe failed for " << path << ": " << err << "\n";
			return 1;
		}
		if (g.bits_per_sample != 16 || g.sample_format != SAMPLEFORMAT_UINT)
		{
			std::cerr << "this harness covers 16-bit unsigned TIFF only; " << path
			          << " is bps=" << g.bits_per_sample << " sf=" << g.sample_format << "\n";
			return 1;
		}

		const size_t nx = g.width, ny = g.length, nn = (size_t)g.n_frames;
		const size_t npix = nx * ny * nn;
		const size_t frame_px = nx * ny;
		const size_t row_bytes = nx * (size_t)g.bits_per_sample / 8;

		// Reference: the production path, decoded once, untimed. This also
		// warms the page cache for the warm regime.
		std::vector<float> ref(npix);
		{
			Image<float> img;
			for (size_t f = 0; f < nn; f++)
			{
				img.read(path, true, (long)f, false, true);
				memcpy(ref.data() + f * frame_px, MULTIDIM_ARRAY(img()), frame_px * sizeof(float));
			}
		}
		const Oracles ref_o = computeOracles(ref.data(), nx, ny, nn);

		// Destinations allocated once and reused, so allocation and first
		// touch show up only in the arms that measure them.
		std::vector<float>    dst_f32(npix);
		std::vector<uint16_t> dst_u16(npix);
		std::vector<uint16_t> src_u16(npix);  // resident input for the conversion arm
		std::vector<Image<float>> prod_frames;  // production arm's Iframes equivalent
		for (size_t i = 0; i < npix; i++) src_u16[i] = (uint16_t)ref[i];

		if (!first_movie) J << ",\n";
		first_movie = false;
		J << "    {\n";
		J << "      \"path\": \"" << jsonEscape(path) << "\",\n";
		J << "      \"file_bytes\": " << g.file_bytes << ",\n";
		J << "      \"nx\": " << nx << ", \"ny\": " << ny << ", \"nframes\": " << nn << ",\n";
		J << "      \"bits_per_sample\": " << g.bits_per_sample
		  << ", \"sample_format\": " << g.sample_format
		  << ", \"compression\": " << g.compression
		  << ", \"predictor\": " << g.predictor << ",\n";
		J << "      \"rows_per_strip\": " << g.rows_per_strip
		  << ", \"strips_per_frame\": " << g.strips_per_frame
		  << ", \"strips_total\": " << (size_t)g.strips_per_frame * nn << ",\n";
		J << "      \"strip_size_bytes\": " << g.strip_size
		  << ", \"max_compressed_strip_bytes\": " << g.max_strip_bytes << ",\n";
		J << "      \"compressed_bytes\": " << g.compressed_bytes
		  << ", \"decoded_bytes_u16\": " << g.decoded_bytes_u16
		  << ", \"decoded_bytes_f32\": " << g.decoded_bytes_f32 << ",\n";
		J << "      \"uniform_directories\": " << (g.uniform ? "true" : "false") << ",\n";
		J << "      \"runs\": [\n";

		bool first_run = true;

		for (int W : workers)
		{
			std::vector<Arm> arms;
			auto add = [&](const char *name, bool pixels, size_t in, size_t out,
			               std::function<void()> run, std::function<void()> post = nullptr,
			               std::function<void()> pre = nullptr) {
				Arm a;
				a.name = name; a.produces_pixels = pixels;
				a.bytes_in = in; a.bytes_out = out;
				a.run = std::move(run); a.post = std::move(post); a.pre = std::move(pre);
				arms.push_back(std::move(a));
			};

			// Attribution chain. Each arm adds exactly one component to the
			// one above it, so the differences are additive:
			//
			//   pread_strip_extents          storage floor
			//   tiff_read_raw_strip          + libtiff strip bookkeeping
			//   tiff_decode_only             + Deflate
			//   decode_place_u16_natural     + destination write
			//   persistent_handle_to_u16     + Y-flipped placement
			//   persistent_handle_to_f32     + int->float widening
			//   openperframe_handle_to_f32   + one TIFFOpen per frame
			//   production_image_read        + Image/fImageHandler lifecycle
			//
			// Persistent arms open one handle per *worker*, inside the
			// parallel region, and reuse it and its strip scratch across
			// every frame that worker is given. That is PR B's structure; a
			// handle opened per frame would measure nothing about persistence.

			// (1) storage: sequential pread of the whole file.
			add("pread_whole_file", false, g.file_bytes, 0, [&] {
				const size_t chunk = 4u << 20;
				std::vector<char> buf(chunk);
				int fd = open(path.c_str(), O_RDONLY);
				if (fd < 0) return;
				size_t off = 0;
				uint64_t acc = 0;
				while (off < g.file_bytes)
				{
					const ssize_t r = pread(fd, buf.data(), std::min(chunk, g.file_bytes - off), (off_t)off);
					if (r <= 0) break;
					acc += (uint64_t)(unsigned char)buf[0];
					off += (size_t)r;
				}
				close(fd);
				g_sink += acc;
			});

			// (2) storage: pread of only the compressed strip extents, one fd
			// per worker -- the access pattern the decoder imposes.
			add("pread_strip_extents", false, g.compressed_bytes, 0, [&] {
				const int nf = (int)nn;
				const size_t spf = (size_t)g.strips_per_frame;
				uint64_t acc = 0;
				#pragma omp parallel num_threads(W) reduction(+:acc)
				{
					std::vector<unsigned char> buf(g.max_strip_bytes + 64);
					int fd = open(path.c_str(), O_RDONLY);
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (fd < 0) continue;
						for (size_t s = 0; s < spf; s++)
						{
							const size_t k = (size_t)f * spf + s;
							if (k >= ext.bytes.size()) break;
							const ssize_t r = pread(fd, buf.data(), (size_t)ext.bytes[k], (off_t)ext.offset[k]);
							if (r > 0) acc += (uint64_t)buf[0];
						}
					}
					if (fd >= 0) close(fd);
				}
				g_sink += acc;
			});

			// (2b) storage floor on the kernel path the decoder actually
			//      takes. LibTIFF's TIFFOpen(path, "r") leaves
			//      TIFFMapFileContents enabled, so every libtiff arm below --
			//      and the production reader -- reaches compressed bytes
			//      through page faults on a MAP_SHARED mapping and issues no
			//      per-strip read syscall. Differencing the pread arms
			//      against a libtiff arm would difference two kernel paths,
			//      which is why that subtraction can go negative. This arm
			//      touches the same strip extents through the same mapping,
			//      so it is the floor the chain can legitimately stand on.
			add("mmap_strip_extents", false, g.compressed_bytes, 0, [&] {
				const int nf = (int)nn;
				const size_t spf = (size_t)g.strips_per_frame;
				uint64_t acc = 0;
				#pragma omp parallel num_threads(W) reduction(+:acc)
				{
					int fd = open(path.c_str(), O_RDONLY);
					unsigned char *base = nullptr;
					if (fd >= 0)
					{
						void *m = mmap(nullptr, g.file_bytes, PROT_READ, MAP_SHARED, fd, 0);
						base = (m == MAP_FAILED) ? nullptr : (unsigned char *)m;
						close(fd);
					}
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!base) continue;
						for (size_t s = 0; s < spf; s++)
						{
							const size_t k = (size_t)f * spf + s;
							if (k >= ext.bytes.size()) break;
							const uint64_t off = ext.offset[k], len = ext.bytes[k];
							if (off + len > g.file_bytes) continue;
							// Touch one byte per 4 KiB page of the extent, which
							// is what a memcpy out of the mapping would fault.
							for (uint64_t o = 0; o < len; o += 4096) acc += base[off + o];
							acc += base[off + len - 1];
						}
					}
					if (base) munmap(base, g.file_bytes);
				}
				g_sink += acc;
			});

			// (3) TIFF directory handling with one persistent handle.
			add("tiff_dirscan_persistent", false, 0, 0, [&] {
				uint64_t acc = 0;
				TIFF *t = TIFFOpen(path.c_str(), "r");
				if (!t) return;
				acc += (uint64_t)TIFFNumberOfDirectories(t);
				for (long d = 0; d < (long)nn; d++)
				{
					if (TIFFSetDirectory(t, (tdir_t)d) == 0) break;
					uint32_t w = 0, l = 0; uint16_t bps = 0, sf = 0;
					TIFFGetField(t, TIFFTAG_IMAGEWIDTH, &w);
					TIFFGetField(t, TIFFTAG_IMAGELENGTH, &l);
					TIFFGetFieldDefaulted(t, TIFFTAG_BITSPERSAMPLE, &bps);
					TIFFGetFieldDefaulted(t, TIFFTAG_SAMPLEFORMAT, &sf);
					acc += w + l + bps + sf + (uint64_t)TIFFNumberOfStrips(t) + (uint64_t)TIFFStripSize(t);
				}
				TIFFClose(t);
				g_sink += acc;
			});

			// (4) TIFF directory handling the production way: one TIFFOpen per
			// frame, header work only. This is the open/metadata overhead
			// Image<float>::read() pays nn times per movie.
			add("tiff_open_per_frame_meta", false, 0, 0, [&] {
				const int nf = (int)nn;
				uint64_t acc = 0;
				#pragma omp parallel for num_threads(W) schedule(static) reduction(+:acc)
				for (int f = 0; f < nf; f++)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					if (!t) continue;
					acc += (uint64_t)TIFFNumberOfDirectories(t);
					if (TIFFSetDirectory(t, (tdir_t)f) != 0)
					{
						uint32_t w = 0, l = 0; uint16_t bps = 0, sf = 0;
						TIFFGetField(t, TIFFTAG_IMAGEWIDTH, &w);
						TIFFGetField(t, TIFFTAG_IMAGELENGTH, &l);
						TIFFGetFieldDefaulted(t, TIFFTAG_BITSPERSAMPLE, &bps);
						TIFFGetFieldDefaulted(t, TIFFTAG_SAMPLEFORMAT, &sf);
						acc += w + l + bps + sf + (uint64_t)TIFFNumberOfStrips(t);
					}
					TIFFClose(t);
				}
				g_sink += acc;
			});

			// (5) persistent handles, TIFFReadRawStrip: libtiff bookkeeping +
			//     storage, no inflate.
			add("tiff_read_raw_strip", false, g.compressed_bytes, 0, [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				uint64_t acc = 0;
				#pragma omp parallel num_threads(W) reduction(+:acc)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.max_strip_bytes + 64);
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadRawStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r > 0) { acc += (uint64_t)buf[0]; g_strips_done++; }
						}
					}
					if (t) TIFFClose(t);
				}
				g_sink += acc;
			});

			// (6) persistent handles, TIFFReadEncodedStrip into reused scratch,
			//     result discarded. (5) -> (6) is the Deflate cost.
			add("tiff_decode_only", false, g.compressed_bytes, 0, [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				uint64_t acc = 0;
				#pragma omp parallel num_threads(W) reduction(+:acc)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.strip_size);
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r > 0) { acc += (uint64_t)buf[0]; g_strips_done++; }
						}
					}
					if (t) TIFFClose(t);
				}
				g_sink += acc;
			});

			// (7) + destination write, natural row order. Verified through an
			//     untimed post-flip, so this arm is not exempt from the gate.
			add("decode_place_u16_natural", true, g.compressed_bytes, g.decoded_bytes_u16,
			    [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				#pragma omp parallel num_threads(W)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.strip_size);
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						uint16_t *out = dst_u16.data() + (size_t)f * frame_px;
						size_t rows_done = 0;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r <= 0) break;
							const size_t nr = (size_t)r / row_bytes;
							for (size_t k = 0; k < nr; k++)
								memcpy(out + (rows_done + k) * nx, buf.data() + k * row_bytes, row_bytes);
							rows_done += nr;
						}
					}
					if (t) TIFFClose(t);
				}
			    },
			    [&] { // untimed: flip into MRC row order and widen for the gate
				for (size_t f = 0; f < nn; f++)
					for (size_t y = 0; y < ny; y++)
						for (size_t x = 0; x < nx; x++)
							dst_f32[f * frame_px + (ny - 1 - y) * nx + x] =
							    (float)dst_u16[f * frame_px + y * nx + x];
			    });

			// (8) + Y-flipped placement. The native uint16 staging
			//     representation PR C would produce.
			add("persistent_handle_to_u16", true, g.compressed_bytes, g.decoded_bytes_u16,
			    [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				#pragma omp parallel num_threads(W)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.strip_size);
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						uint16_t *out = dst_u16.data() + (size_t)f * frame_px;
						size_t rows_done = 0;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r <= 0) break;
							const size_t nr = (size_t)r / row_bytes;
							for (size_t k = 0; k < nr; k++)
								memcpy(out + (ny - 1 - (rows_done + k)) * nx,
								       buf.data() + k * row_bytes, row_bytes);
							rows_done += nr;
						}
					}
					if (t) TIFFClose(t);
				}
			    },
			    [&] { // untimed widening; arm (11) prices this step on its own
				for (size_t i = 0; i < npix; i++) dst_f32[i] = (float)dst_u16[i];
			    });

			// (9) + int->float widening at strip granularity, through the
			//     production castPage2T. This is PR B's target shape.
			add("persistent_handle_to_f32", true, g.compressed_bytes, g.decoded_bytes_f32, [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				#pragma omp parallel num_threads(W)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.strip_size);
					Image<float> caster; // castPage2T only; holds no data
					#pragma omp for schedule(static)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						float *out = dst_f32.data() + (size_t)f * frame_px;
						size_t rows_done = 0;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r <= 0) break;
							const size_t nr = (size_t)r / row_bytes;
							for (size_t k = 0; k < nr; k++)
								caster.castPage2T((char *)buf.data() + k * row_bytes,
								                  out + (ny - 1 - (rows_done + k)) * nx,
								                  UShort, nx);
							rows_done += nr;
						}
					}
					if (t) TIFFClose(t);
				}
			});

			// (10) identical to (9) except the handle and strip scratch are
			//      created per frame instead of per worker. (9) -> (10) is
			//      exactly what a persistent reader pool would remove.
			add("openperframe_handle_to_f32", true, g.compressed_bytes, g.decoded_bytes_f32, [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					if (!t) continue;
					if (TIFFSetDirectory(t, (tdir_t)f) != 0)
					{
						std::vector<unsigned char> buf(g.strip_size);
						Image<float> caster;
						float *out = dst_f32.data() + (size_t)f * frame_px;
						size_t rows_done = 0;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r <= 0) break;
							const size_t nr = (size_t)r / row_bytes;
							for (size_t k = 0; k < nr; k++)
								caster.castPage2T((char *)buf.data() + k * row_bytes,
								                  out + (ny - 1 - (rows_done + k)) * nx,
								                  UShort, nx);
							rows_done += nr;
						}
					}
					TIFFClose(t);
				}
			});

			// (9b) identical to (9) except for the OpenMP schedule. The
			//      strip-batch arms below use schedule(dynamic,1), so
			//      comparing them straight to (9) would change granularity
			//      and scheduling policy at the same time and could not tell
			//      which one paid. This arm isolates the policy: frames are
			//      still the unit of work, but they are handed out
			//      dynamically, which is what absorbs per-frame decode-time
			//      variation when frames compress differently.
			add("persistent_handle_to_f32_dynamic", true, g.compressed_bytes, g.decoded_bytes_f32, [&] {
				const int nf = (int)nn;
				const tstrip_t spf = g.strips_per_frame;
				#pragma omp parallel num_threads(W)
				{
					TIFF *t = TIFFOpen(path.c_str(), "r");
					std::vector<unsigned char> buf(g.strip_size);
					Image<float> caster;
					#pragma omp for schedule(dynamic, 1)
					for (int f = 0; f < nf; f++)
					{
						if (!t || TIFFSetDirectory(t, (tdir_t)f) == 0) continue;
						float *out = dst_f32.data() + (size_t)f * frame_px;
						size_t rows_done = 0;
						for (tstrip_t s = 0; s < spf; s++)
						{
							const tsize_t r = TIFFReadEncodedStrip(t, s, buf.data(), (tsize_t)buf.size());
							if (r <= 0) break;
							const size_t nr = (size_t)r / row_bytes;
							for (size_t k = 0; k < nr; k++)
								caster.castPage2T((char *)buf.data() + k * row_bytes,
								                  out + (ny - 1 - (rows_done + k)) * nx,
								                  UShort, nx);
							rows_done += nr;
						}
					}
					if (t) TIFFClose(t);
				}
			});

			// (10b) strip-batch decode: the same total work as (9), but the
			//       unit of scheduling is a batch of strips rather than a
			//       whole frame. Frame-level parallelism is capped at the
			//       frame count and, at any W that does not divide it,
			//       statically imbalanced -- with 24 frames and W=16, eight
			//       workers get two frames and eight get one. This arm is the
			//       direct test of whether finer granularity recovers that.
			//       Batches are emitted in frame order so a worker usually
			//       stays on the directory it already selected.
			for (size_t batch : {(size_t)64, (size_t)256})
			{
				const std::string nm = "strip_batch_to_f32_b" + std::to_string(batch);
				add(nm.c_str(), true, g.compressed_bytes, g.decoded_bytes_f32, [&, batch] {
					struct Task { int frame; tstrip_t first, count; };
					std::vector<Task> tasks;
					for (int f = 0; f < (int)nn; f++)
						for (tstrip_t s = 0; s < g.strips_per_frame; s += (tstrip_t)batch)
							tasks.push_back({f, s,
								(tstrip_t)std::min((size_t)batch,
								                   (size_t)(g.strips_per_frame - s))});
					const int nt = (int)tasks.size();
					#pragma omp parallel num_threads(W)
					{
						TIFF *t = TIFFOpen(path.c_str(), "r");
						std::vector<unsigned char> buf(g.strip_size);
						Image<float> caster;
						int cur_dir = -1;
						#pragma omp for schedule(dynamic, 1)
						for (int i = 0; i < nt; i++)
						{
							const Task &tk = tasks[i];
							if (!t) continue;
							if (cur_dir != tk.frame)
							{
								if (TIFFSetDirectory(t, (tdir_t)tk.frame) == 0) continue;
								cur_dir = tk.frame;
							}
							float *out = dst_f32.data() + (size_t)tk.frame * frame_px;
							// RowsPerStrip is constant within a directory, so a
							// batch's first row is derivable without decoding
							// the strips before it.
							const size_t rows_per_strip =
								(size_t)g.strip_size / row_bytes;
							size_t row = (size_t)tk.first * rows_per_strip;
							for (tstrip_t k = 0; k < tk.count; k++)
							{
								const tsize_t r = TIFFReadEncodedStrip(
									t, tk.first + k, buf.data(), (tsize_t)buf.size());
								if (r <= 0) break;
								const size_t nr = (size_t)r / row_bytes;
								for (size_t j = 0; j < nr; j++)
									caster.castPage2T((char *)buf.data() + j * row_bytes,
									                  out + (ny - 1 - (row + j)) * nx,
									                  UShort, nx);
								row += nr;
							}
						}
						if (t) TIFFClose(t);
					}
				});
			}

			// (11) conversion only: resident uint16 -> float, no I/O, the same
			//      castPage2T at the same row granularity the decoder uses.
			add("convert_u16_to_f32_resident", false, g.decoded_bytes_u16, g.decoded_bytes_f32, [&] {
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
				{
					Image<float> caster;
					const uint16_t *in = src_u16.data() + (size_t)f * frame_px;
					float *out = dst_f32.data() + (size_t)f * frame_px;
					for (size_t y = 0; y < ny; y++)
						caster.castPage2T((char *)(in + y * nx), out + y * nx, UShort, nx);
				}
			});

			// (12)/(13) allocation + first touch, float and uint16 movie.
			add("alloc_first_touch_f32", false, 0, g.decoded_bytes_f32, [&] {
				const size_t bytes = npix * sizeof(float);
				void *p = freshPages(bytes);
				if (!p) return;
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					memset((char *)p + (size_t)f * frame_px * sizeof(float), 0,
					       frame_px * sizeof(float));
				g_sink += (uint64_t)((char *)p)[0];
				munmap(p, bytes);
			});
			// These do NOT bracket the cost, and the earlier comment saying
			// they did was wrong. glibc caps its dynamic mmap threshold at
			// DEFAULT_MMAP_THRESHOLD_MAX (32 MiB on 64-bit). A frame buffer is
			// 57 MB and a whole movie 1.37 GiB, so every one of these
			// allocations is above the cap and is always serviced by mmap and
			// always freed by munmap, in the malloc arms exactly as in the
			// mmap arm. They therefore all measure the same always-cold-pages
			// regime and agree with each other.
			//
			// That is not a defect in the measurement, it is the finding: the
			// production reader allocates 24 x 57 MB per movie through the
			// same path, so it really does fault in 1.273 GiB of fresh pages
			// for every movie. The cost production actually pays is the
			// production_image_read minus production_image_read_prealloc
			// difference, which is measured directly rather than bracketed.
			add("alloc_first_touch_f32_malloc", false, 0, g.decoded_bytes_f32, [&] {
				const size_t bytes = npix * sizeof(float);
				void *p = malloc(bytes);
				if (!p) return;
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					memset((char *)p + (size_t)f * frame_px * sizeof(float), 0,
					       frame_px * sizeof(float));
				g_sink += (uint64_t)((char *)p)[0];
				free(p);
			});

			// Per-frame allocation at the granularity the production reader
			// uses: 24 separate 57 MB buffers, not one 1.37 GB block.
			add("alloc_first_touch_f32_perframe", false, 0, g.decoded_bytes_f32, [&] {
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
				{
					void *p = malloc(frame_px * sizeof(float));
					if (!p) continue;
					memset(p, 0, frame_px * sizeof(float));
					g_sink += (uint64_t)((char *)p)[0];
					free(p);
				}
			});

			add("alloc_first_touch_u16", false, 0, g.decoded_bytes_u16, [&] {
				const size_t bytes = npix * sizeof(uint16_t);
				void *p = freshPages(bytes);
				if (!p) return;
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					memset((char *)p + (size_t)f * frame_px * sizeof(uint16_t), 0,
					       frame_px * sizeof(uint16_t));
				g_sink += (uint64_t)((char *)p)[0];
				munmap(p, bytes);
			});

			// (14) the production path, scoped to exactly what the
			//      TIMING_READ_MOVIE region contains.
			//
			//      In MotioncorrRunner the per-movie Iframes vector is
			//      resized BEFORE RCTIC(TIMING_READ_MOVIE) -- that only
			//      default-constructs empty Images -- and is destroyed AFTER
			//      RCTOC, at the end of the movie. So the pixel allocation
			//      inside Image::read() belongs to this stage, but neither
			//      the vector resize nor the 1.37 GB deallocation does.
			//      Both go in the untimed pre step; timing them here would
			//      charge this arm a free that production performs during
			//      the previous movie.
			add("production_image_read", true, g.compressed_bytes, g.decoded_bytes_f32,
			    [&] {
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					prod_frames[f].read(path, true, (long)f, false, true); // mmap false, is_2D true
			    },
			    [&] {
				for (size_t f = 0; f < nn; f++)
					memcpy(dst_f32.data() + f * frame_px,
					       MULTIDIM_ARRAY(prod_frames[f]()), frame_px * sizeof(float));
			    },
			    [&] {
				prod_frames.clear();      // frees the previous repeat's frames
				prod_frames.resize(nn);   // constructs empty Images, no pixels
			    });

			// (14b) the production path with its frame buffers already
			//       allocated and faulted in. MultidimArray::coreAllocateReuse
			//       returns immediately when data != NULL and the dimensions
			//       still fit, so the timed read here reuses the buffers the
			//       untimed pre step allocated. (14) minus (14b) is therefore
			//       the allocation and first-touch cost paid inside the real
			//       production reader, measured rather than inferred from a
			//       standalone malloc arm.
			add("production_image_read_prealloc", true, g.compressed_bytes, g.decoded_bytes_f32,
			    [&] {
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					prod_frames[f].read(path, true, (long)f, false, true);
			    },
			    [&] {
				for (size_t f = 0; f < nn; f++)
					memcpy(dst_f32.data() + f * frame_px,
					       MULTIDIM_ARRAY(prod_frames[f]()), frame_px * sizeof(float));
			    },
			    [&] {
				// Allocate and fault the buffers before the timer by doing a
				// throwaway read into them.
				prod_frames.clear();
				prod_frames.resize(nn);
				const int nf = (int)nn;
				#pragma omp parallel for num_threads(W) schedule(static)
				for (int f = 0; f < nf; f++)
					prod_frames[f].read(path, true, (long)f, false, true);
			    });

			// (15) thread dispatch only: the same parallel-for shape with a
			//      trivial body per strip. Bounds how much of the worker-count
			//      curve is scheduling rather than work.
			add("omp_dispatch_only", false, 0, 0, [&] {
				const int nf = (int)nn;
				const size_t spf = (size_t)g.strips_per_frame;
				uint64_t acc = 0;
				#pragma omp parallel for num_threads(W) schedule(static) reduction(+:acc)
				for (int f = 0; f < nf; f++)
					for (size_t s = 0; s < spf; s++) acc += s ^ (size_t)f;
				g_sink += acc;
			});

			const uint64_t expected_strips = (uint64_t)g.strips_per_frame * nn;

			for (const Arm &arm : arms)
			{
				if (!only_arm.empty() && only_arm != arm.name) continue;

				std::vector<double> walls, cpus;
				std::vector<long> minflt, majflt;
				std::vector<double> resident_before;
				std::vector<uint64_t> strips;
				CompareResult last_cmp;
				bool exact_all_repeats = true;

				for (int rep = 0; rep < repeats; rep++)
				{
					if (arm.pre) arm.pre();     // untimed
					if (regime == "cold")
					{
						evictFileCache(path);
						// Witness, not assertion: what fraction of the file is
						// still resident at the instant the timer starts.
						const double f = residentFraction(path);
						if (f >= 0.0) resident_before.push_back(f);
					}
					if (arm.produces_pixels)
					{
						// Poison both destinations so a partial write cannot
						// be masked by the previous arm's correct output.
						std::fill(dst_f32.begin(), dst_f32.end(), -1.0f);
						std::fill(dst_u16.begin(), dst_u16.end(), 0);
					}

					g_strips_done = g_fault_witness ? (uint64_t)-1 : 0;
					const Faults f0 = faultsNow();
					const double w0 = wallNow(), c0 = cpuNow();
					arm.run();
					const double w1 = wallNow(), c1 = cpuNow();
					const Faults f1 = faultsNow();
					walls.push_back(w1 - w0);
					cpus.push_back(c1 - c0);
					strips.push_back(g_strips_done.load());
					minflt.push_back(f1.minor - f0.minor);
					majflt.push_back(f1.major - f0.major);

					if (arm.produces_pixels)
					{
						if (arm.post) arm.post();   // untimed
						// Live fault injection: corrupt this arm's real output
						// so the gate has to fail. Without this, a PASS could
						// come from a comparator that never fires.
						if (inject != Mutation::None &&
						    (inject_arm.empty() || inject_arm == arm.name))
							applyMutation(dst_f32.data(), inject, nx, ny, nn);

						const bool last = (rep == repeats - 1);
						last_cmp = compareAll(ref.data(), dst_f32.data(), ref_o,
						                      nx, ny, nn, last);
						exact_all_repeats = exact_all_repeats && last_cmp.exact_equal;
					}
				}

				std::sort(walls.begin(), walls.end());
				std::sort(cpus.begin(), cpus.end());
				const double wmed = walls[walls.size() / 2];
				const double cmed = cpus[cpus.size() / 2];

				if (!first_run) J << ",\n";
				first_run = false;
				J << "        {\"arm\": \"" << arm.name << "\", \"workers\": " << W
				  << ", \"wall_median_s\": " << wmed
				  << ", \"wall_min_s\": " << walls.front()
				  << ", \"wall_max_s\": " << walls.back()
				  << ", \"cpu_median_s\": " << cmed
				  << ", \"minor_faults_median\": " << (minflt.empty() ? 0 : *(minflt.begin() + minflt.size() / 2))
				  << ", \"major_faults_median\": " << (majflt.empty() ? 0 : *(majflt.begin() + majflt.size() / 2))
				  << ", \"strips_processed\": " << (strips.empty() ? 0 : strips.back())
				  << ", \"strips_expected\": " << expected_strips
				  << ", \"work_witness_ok\": "
				  << ((strips.empty() || strips.back() == 0 ||
				       strips.back() == expected_strips) ? "true" : "false")
				  << ", \"resident_fraction_at_timer_start\": "
				  << (resident_before.empty() ? -1.0
				          : *std::max_element(resident_before.begin(), resident_before.end()))
				  << ", \"bytes_in\": " << arm.bytes_in
				  << ", \"bytes_out\": " << arm.bytes_out;
				if (arm.bytes_in > 0 && wmed > 0)
					J << ", \"in_MBps\": " << (double)arm.bytes_in / wmed / 1.0e6;
				if (arm.bytes_out > 0 && wmed > 0)
					J << ", \"out_MBps\": " << (double)arm.bytes_out / wmed / 1.0e6;
				J << ", \"produces_pixels\": " << (arm.produces_pixels ? "true" : "false");
				if (arm.produces_pixels)
				{
					J << ", \"exact_equal\": "      << (last_cmp.exact_equal ? "true" : "false")
					  << ", \"exact_all_repeats\": " << (exact_all_repeats ? "true" : "false")
					  << ", \"global_sum_equal\": " << (last_cmp.global_sum_equal ? "true" : "false")
					  << ", \"row_sums_equal\": "   << (last_cmp.row_sums_equal ? "true" : "false")
					  << ", \"n_pixels_differing\": " << last_cmp.n_diff;
					if (!last_cmp.exact_equal)
						J << ", \"first_diff_index\": " << last_cmp.first_diff_index
						  << ", \"ref_value\": " << last_cmp.ref_value
						  << ", \"got_value\": " << last_cmp.got_value;
				}
				J << "}";

				// A counting arm that ran but processed the wrong number of
				// strips did not do the work its timing is attributed to.
				if (!strips.empty() && strips.back() != 0 &&
				    strips.back() != expected_strips)
				{
					gate_failures++;
					std::cerr << "  WORK-WITNESS-FAIL [" << arm.name << "] W=" << W
					          << " strips " << strips.back() << " != " << expected_strips
					          << std::endl;
				}
				if (arm.produces_pixels && !exact_all_repeats &&
				    inject == Mutation::None)
					gate_failures++;

				std::cerr << "  [" << arm.name << "] W=" << W
				          << " wall=" << wmed << "s cpu=" << cmed << "s"
				          << (arm.produces_pixels
				                  ? (last_cmp.exact_equal ? " EXACT-OK" : " EXACT-FAIL")
				                  : "")
				          << std::endl;
			}
		}
		J << "\n      ]\n    }";
	}

	J << "\n  ],\n";
	J << "  \"fault_witness_control\": " << (g_fault_witness ? "true" : "false") << ",\n";
	J << "  \"gate_failures\": " << gate_failures << ",\n";
	J << "  \"injected_mutation\": \"" << mutationName(inject) << "\",\n";
	J << "  \"injected_arm\": \"" << jsonEscape(inject_arm) << "\",\n";
	J << "  \"max_rss_kib\": " << maxRssKiB() << ",\n";
	J << "  \"sink\": " << (uint64_t)g_sink << "\n";
	J << "}\n";

	if (!out_path.empty()) { std::ofstream f(out_path); f << J.str(); }
	else std::cout << J.str();

	// Exit status carries the verdict. Without this the gate is advisory: a
	// run with EXACT-FAIL rows still exits 0 and a caller that checks only the
	// exit code would record a clean run. Injection runs are expected to fail
	// the exact gate, so they are excluded above.
	if (gate_failures > 0)
	{
		std::cerr << "FAILED: " << gate_failures
		          << " gate or work-witness failure(s); see the JSON" << std::endl;
		return 1;
	}
	return 0;
}
