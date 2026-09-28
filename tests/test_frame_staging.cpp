// Tests for the issue #95 bounded frame-staging components.
//
// The two things under test are the two load-bearing claims of
// agents/designs/issue_95_bounded_frame_staging.md:
//
//  1. the capacity formula is overflow-checked and reproduces the published
//     geometries exactly, and its staged term does not grow with frame count;
//  2. the hot-pixel repair draw schedule reproduces the runner's replacement
//     values and RNG stream bit-for-bit under any frame chunking.
//
// Claim 2 is checked differentially against a transcription of the production
// loop (referenceRepair below, from src/motioncorr_runner.cpp:1732 at main
// @4c952b3f). A differential test is only worth anything if it can fail, so
// every fixture is also run against a deliberately broken implementation
// (brokenRepair) and the harness asserts that the comparison rejects it.

#include "src/frame_staging_plan.h"
#include "src/funcs.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

using namespace motioncorr::staging;

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool cond, const std::string &what)
{
	g_checks++;
	if (!cond) {
		g_failures++;
		std::fprintf(stderr, "FAIL: %s\n", what.c_str());
	}
}

// --------------------------------------------------------------------------
// Fixtures
// --------------------------------------------------------------------------

struct Movie {
	int nx = 0, ny = 0, n_frames = 0;
	std::vector<float> data;   // n_frames * ny * nx
	// A real bool array. std::vector<bool> is the bitset specialisation and has
	// no data(), and reinterpret_cast-ing an unsigned char buffer to bool* is an
	// aliasing violation, so own the storage directly.
	std::unique_ptr<bool[]> mask;
	std::vector<float> gain;   // ny * nx; empty means "no gain reference"
	float mean = 0.0f, stddev = 0.0f;
	int d_max = 2;
	// Mirrors the runner's host_frames_are_raw: raw frames take the gain multiply
	// on gather and record the replacement instead of writing it.
	bool raw_host = false;
	std::string name;

	float *frame(int f) { return data.data() + (size_t)f * ny * nx; }
	const float *frame(int f) const { return data.data() + (size_t)f * ny * nx; }
	const bool *badMask() const { return mask.get(); }
	const float *gainPtr() const { return gain.empty() ? nullptr : gain.data(); }
	size_t badCount() const {
		size_t n = 0;
		for (size_t i = 0; i < (size_t)ny * nx; i++) if (mask[i]) n++;
		return n;
	}

	Movie() = default;
	Movie(const Movie &o) { *this = o; }
	Movie &operator=(const Movie &o) {
		// Without this, reset() below frees the old mask and std::copy then
		// reads from the freshly allocated, uninitialised buffer -- leaving a
		// mask of indeterminate bools, which is the exact hazard the
		// unique_ptr<bool[]> change was made to remove. No call site
		// self-assigns today; this keeps it that way by construction.
		if (this == &o) return *this;
		nx = o.nx; ny = o.ny; n_frames = o.n_frames;
		data = o.data; gain = o.gain;
		mean = o.mean; stddev = o.stddev; d_max = o.d_max;
		raw_host = o.raw_host; name = o.name;
		mask.reset(new bool[(size_t)ny * nx]);
		std::copy(o.mask.get(), o.mask.get() + (size_t)ny * nx, mask.get());
		return *this;
	}
};

// Deterministic, independent of the process RNG that the schedule consumes.
float syntheticPixel(int f, int y, int x)
{
	unsigned h = 2166136261u;
	h = (h ^ (unsigned)f) * 16777619u;
	h = (h ^ (unsigned)y) * 16777619u;
	h = (h ^ (unsigned)x) * 16777619u;
	return (float)(h % 65536u) * 0.5f - 1000.0f;
}

Movie makeMovie(const std::string &name, int nx, int ny, int n_frames, int d_max,
                float mean, float stddev)
{
	Movie m;
	m.name = name;
	m.nx = nx; m.ny = ny; m.n_frames = n_frames; m.d_max = d_max;
	m.mean = mean; m.stddev = stddev;
	m.data.resize((size_t)n_frames * ny * nx);
	m.mask.reset(new bool[(size_t)ny * nx]);
	std::fill(m.mask.get(), m.mask.get() + (size_t)ny * nx, false);
	for (int f = 0; f < n_frames; f++)
		for (int y = 0; y < ny; y++)
			for (int x = 0; x < nx; x++)
				m.data[((size_t)f * ny + y) * nx + x] = syntheticPixel(f, y, x);
	return m;
}

// A gain reference that is neither 1 nor uniform, so an omitted or misindexed
// multiply cannot cancel out.
void addGain(Movie &m)
{
	m.gain.resize((size_t)m.ny * m.nx);
	for (int y = 0; y < m.ny; y++)
		for (int x = 0; x < m.nx; x++)
			m.gain[(size_t)y * m.nx + x] = 0.75f + 0.5f * (float)((y * 7 + x * 13) % 11) / 11.0f;
	m.raw_host = true;
}

void markBad(Movie &m, int y, int x)
{
	if (y < 0 || y >= m.ny || x < 0 || x >= m.nx) return;
	m.mask[(size_t)y * m.nx + x] = true;
}

void markBlock(Movie &m, int y0, int x0, int h, int w)
{
	for (int y = y0; y < y0 + h; y++)
		for (int x = x0; x < x0 + w; x++)
			markBad(m, y, x);
}

// --------------------------------------------------------------------------
// Reference: transcription of the production repair loop
// --------------------------------------------------------------------------
//
// Transcribed from src/motioncorr_runner.cpp:1732-1775, INCLUDING the
// _CUDA_ENABLED raw-host branches at :1753 (gain multiply on gather) and :1770
// (record to resident_bad_replacements instead of writing the frame). An
// earlier draft of this oracle omitted both, which made the differential test
// structurally blind to them.
//
// Note the limit of the intentional-bug control in the evidence report: bugs
// were injected into the component, never into this oracle, so the control
// cannot detect drift between this transcription and the runner. That has to be
// checked by reading, and was.

const int kNumMinOk = 6;
const int kPbufSize = 100;

// out_replacements, when non-null, uses the runner's frame-major layout:
// [iframe * n_bad + bad_idx], as at motioncorr_runner.cpp:1770.
void referenceRepair(Movie &m, std::vector<float> *out_replacements = nullptr)
{
	// The raw-host branch records instead of writing, so it has nowhere to put
	// its result without a buffer. Refuse rather than dereference null: an
	// oracle that segfaults is the worst way for a future fixture to fail.
	if (m.raw_host && !out_replacements) {
		check(false, m.name + ": referenceRepair needs a buffer for a raw-host movie");
		return;
	}
	const bool *bBad = m.badMask();
	const int nx = m.nx, ny = m.ny, D_MAX = m.d_max;
	const float *gain = m.raw_host ? m.gainPtr() : nullptr;
	const size_t n_bad = m.badCount();
	size_t bad_idx = 0;
	for (int i = 0; i < ny; i++) {
		for (int j = 0; j < nx; j++) {
			if (!bBad[(size_t)i * nx + j]) continue;
			for (int iframe = 0; iframe < m.n_frames; iframe++) {
				float pbuf[kPbufSize];
				int n_ok = 0;
				for (int dy = -D_MAX; dy <= D_MAX; dy++) {
					const int y = i + dy;
					if (y < 0 || y >= ny) continue;
					for (int dx = -D_MAX; dx <= D_MAX; dx++) {
						const int x = j + dx;
						if (x < 0 || x >= nx) continue;
						if (bBad[(size_t)y * nx + x]) continue;
						float neighbor = m.frame(iframe)[(size_t)y * nx + x];
						if (gain) neighbor *= gain[(size_t)y * nx + x];
						pbuf[n_ok] = neighbor;
						n_ok++;
					}
				}
				float replacement;
				if (n_ok > kNumMinOk) replacement = pbuf[rand() % n_ok];
				else replacement = rnd_gaus(m.mean, m.stddev);
				if (m.raw_host) {
					// The raw frame is deliberately left alone so the later
					// whole-frame gain pass stays valid.
					(*out_replacements)[(size_t)iframe * n_bad + bad_idx] = replacement;
				} else {
					m.frame(iframe)[(size_t)i * nx + j] = replacement;
					if (out_replacements)
						(*out_replacements)[(size_t)iframe * n_bad + bad_idx] = replacement;
				}
			}
			bad_idx++;
		}
	}
}

// Deliberately broken: iterates frame-major and redraws per chunk, which is the
// naive way to chunk this loop. It must not match the reference.
void brokenRepair(Movie &m, int chunk)
{
	const bool *bBad = m.badMask();
	const int nx = m.nx, ny = m.ny, D_MAX = m.d_max;
	for (int base = 0; base < m.n_frames; base += chunk) {
		const int last = (base + chunk < m.n_frames) ? base + chunk : m.n_frames;
		for (int iframe = base; iframe < last; iframe++) {
			for (int i = 0; i < ny; i++) {
				for (int j = 0; j < nx; j++) {
					if (!bBad[(size_t)i * nx + j]) continue;
					float pbuf[kPbufSize];
					int n_ok = 0;
					for (int dy = -D_MAX; dy <= D_MAX; dy++) {
						const int y = i + dy;
						if (y < 0 || y >= ny) continue;
						for (int dx = -D_MAX; dx <= D_MAX; dx++) {
							const int x = j + dx;
							if (x < 0 || x >= nx) continue;
							if (bBad[(size_t)y * nx + x]) continue;
							pbuf[n_ok] = m.frame(iframe)[(size_t)y * nx + x];
							n_ok++;
						}
					}
					float replacement;
					if (n_ok > kNumMinOk) replacement = pbuf[rand() % n_ok];
					else replacement = rnd_gaus(m.mean, m.stddev);
					m.frame(iframe)[(size_t)i * nx + j] = replacement;
				}
			}
		}
	}
}

// --------------------------------------------------------------------------
// Candidate: schedule built up front, applied chunk by chunk
// --------------------------------------------------------------------------

bool scheduledRepair(Movie &m, int chunk, Schedule &sched_out,
                     std::vector<float> *replacements)
{
	if (!buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, m.d_max,
	                   m.mean, m.stddev, sched_out))
		return false;

	if (replacements)
		replacements->assign(sched_out.bad_x.size() * (size_t)m.n_frames, 0.0f);

	// Mirror the runner: raw host frames take the gain on gather and are not
	// written; gain-corrected frames are written in place with no gain.
	const float *gain = m.raw_host ? m.gainPtr() : nullptr;
	const bool write_in_place = !m.raw_host;

	for (int base = 0; base < m.n_frames; base += chunk) {
		int n = chunk;
		if (base + n > m.n_frames) n = m.n_frames - base;
		std::vector<float*> ptrs(n);
		for (int k = 0; k < n; k++) ptrs[k] = m.frame(base + k);
		if (!applyChunk(sched_out, m.badMask(), base, n, ptrs.data(),
		                gain, write_in_place, replacements))
			return false;
	}
	return true;
}

// The RNG tail after each run, so "same values" is not mistaken for "same
// stream". A design that consumed a different number of draws would leave the
// process generator somewhere else and corrupt whatever runs next.
std::vector<int> rngTail(int n = 8)
{
	std::vector<int> t(n);
	for (int i = 0; i < n; i++) t[i] = rand();
	return t;
}

// --------------------------------------------------------------------------
// Claim 2
// --------------------------------------------------------------------------

void runOrderingCase(Movie proto, const std::vector<int> &chunks, int seed,
                     bool expect_neighbor, bool expect_gaussian)
{
	Movie ref = proto;
	std::vector<float> ref_replacements(proto.badCount() * (size_t)proto.n_frames, 0.0f);
	init_random_generator(seed);
	referenceRepair(ref, &ref_replacements);
	const std::vector<int> ref_tail = rngTail();

	for (size_t c = 0; c < chunks.size(); c++) {
		const int chunk = chunks[c];
		const std::string tag = proto.name + " chunk=" + std::to_string(chunk);

		Movie cand = proto;
		Schedule sched;
		std::vector<float> replacements;
		init_random_generator(seed);
		const bool ok = scheduledRepair(cand, chunk, sched, &replacements);
		const std::vector<int> cand_tail = rngTail();

		check(ok, tag + ": scheduled repair returned true");
		if (!ok) continue;

		// For a raw-host movie neither the oracle nor the component writes a
		// frame, so comparing the two frame buffers compares two pristine
		// copies of `proto` and cannot fail under any implementation error.
		// Assert the property that is actually true and actually at risk --
		// that the raw frames come back untouched -- and leave the value check
		// to the replacement comparison below, which carries the gain.
		if (proto.raw_host) {
			check(std::memcmp(cand.data.data(), proto.data.data(),
			                  proto.data.size() * sizeof(float)) == 0,
			      tag + ": raw host frames are left untouched");
		} else {
			check(std::memcmp(cand.data.data(), ref.data.data(),
			                  ref.data.size() * sizeof(float)) == 0,
			      tag + ": every repaired pixel is bit-identical to the reference loop");
		}
		check(cand_tail == ref_tail, tag + ": process RNG left in the same state");

		// The recorded sparse values are what the resident CUDA path uploads, so
		// compare them against the runner's OWN buffer, in the runner's own
		// frame-major layout. Comparing them against the component's frames in
		// the component's own layout would only prove self-consistency and
		// would not notice a transposed buffer.
		check(replacements == ref_replacements,
		      tag + ": recorded sparse replacements match the reference, "
		            "in the runner's frame-major layout");

		// Observability: assert the fixture actually reached the branch it was
		// built for, rather than passing because nothing happened.
		if (expect_neighbor)
			check(sched.n_neighbor_draws > 0, tag + ": exercised the neighbour branch");
		if (expect_gaussian)
			check(sched.n_gaussian_draws > 0, tag + ": exercised the Gaussian branch");

		// Deliberately NOT asserted here: that the branch kind is constant
		// across frames for a given bad pixel, and that the two draw counters
		// sum to n_bad * n_frames. Both are tautologies over buildSchedule's own
		// loop nesting -- it computes n_ok once per bad pixel, outside the frame
		// loop, and increments exactly one counter per iteration. They would
		// pass no matter what the production loop did. The frame-independence of
		// n_ok is genuinely covered by the comparison against referenceRepair
		// above, which recomputes n_ok per frame from real pixel data.
	}

	// Negative control. The naive chunking must be rejected by the same
	// comparison that passed above -- otherwise the comparison proves nothing.
	//
	// badCount() > 1, not > 0: with a single bad pixel, frame-major and
	// pixel-major iteration visit the (pixel, frame) pairs in the SAME order, so
	// brokenRepair legitimately matches the reference and this control would
	// invert. The raw-host fixtures are excluded because brokenRepair models the
	// in-place write path only.
	if (proto.n_frames > 1 && proto.badCount() > 1 && !proto.raw_host) {
		for (int broken_chunk = 1; broken_chunk <= 2; broken_chunk++) {
			Movie bad = proto;
			init_random_generator(seed);
			brokenRepair(bad, broken_chunk);
			check(std::memcmp(bad.data.data(), ref.data.data(),
			                  ref.data.size() * sizeof(float)) != 0,
			      proto.name + " broken_chunk=" + std::to_string(broken_chunk)
			      + ": negative control (naive frame-major chunking) is detected");
		}
	}
}

// --------------------------------------------------------------------------
// Claim 1
// --------------------------------------------------------------------------

void runCapacityChecks()
{
	const unsigned long long GiB = 1024ull * 1024ull * 1024ull;

	// Published tutorial geometry, #95 task comment: real+Fourier ~2.547 GiB.
	{
		Geometry g; g.nx = 3710; g.ny = 3838; g.n_frames = 24;
		unsigned long long real = 0, r2c = 0;
		check(realStackBytes(g, real), "tutorial real stack computed");
		check(fourierStackBytes(g, r2c), "tutorial Fourier stack computed");
		check(real == 1366942080ull, "tutorial real = 4*24*3710*3838");
		check(r2c == 1367678976ull, "tutorial r2c = 8*24*3838*1856");
		const double gib = (double)(real + r2c) / (double)GiB;
		check(std::fabs(gib - 2.547) < 0.001, "tutorial real+Fourier is 2.547 GiB");

		// The CPU reconstruction branch keeps a second real stack (Irefframes).
		Policy p;
		p.retain_host_aligned_stack = true;
		Budget b;
		check(computeBudget(g, p, b), "tutorial CPU-reconstruction budget computed");
		check(b.resident_host_bytes == 2ull * real + r2c,
		      "tutorial CPU reconstruction keeps two real stacks plus the Fourier stack");
		const double gib3 = (double)b.resident_host_bytes / (double)GiB;
		check(std::fabs(gib3 - 3.820) < 0.001,
		      "tutorial CPU-reconstruction resident high-water is 3.820 GiB, not 2.547");
	}

	// Published large geometry: ~40.005 GiB.
	{
		Geometry g; g.nx = 8192; g.ny = 8192; g.n_frames = 80;
		unsigned long long real = 0, r2c = 0;
		check(realStackBytes(g, real) && fourierStackBytes(g, r2c),
		      "8192^2 x80 stacks computed");
		const double gib = (double)(real + r2c) / (double)GiB;
		check(std::fabs(gib - 40.005) < 0.001, "8192^2 x80 real+Fourier is 40.005 GiB");
	}

	// A default policy must reproduce today's numbers exactly, so the formula
	// cannot be tuned to flatter a staged design.
	{
		Geometry g; g.nx = 3710; g.ny = 3838; g.n_frames = 24;
		Policy p; Budget b;
		check(computeBudget(g, p, b), "default policy budget computed");
		unsigned long long real = 0, r2c = 0;
		realStackBytes(g, real); fourierStackBytes(g, r2c);
		check(b.staged_host_bytes == real, "chunk 0 stages the whole movie");
		// The previous revision asserted `real + r2c + real` here and called it
		// "today's numbers". It was not: the runner decodes straight into
		// Iframes, so the staged movie and the retained real stack are one
		// allocation. The old expectation enshrined a double count that
		// contradicted this component's own ADR phase table.
		check(b.staged_aliases_resident,
		      "the whole-movie float policy aliases the retained real stack");
		check(b.host_bytes == real + r2c,
		      "default policy charges Iframes once, not twice");
		check(b.staged_host_bytes + b.resident_host_bytes > b.host_bytes,
		      "the alias is visible: the parts deliberately over-sum the whole");
		check(b.schedule_host_bytes == 0,
		      "today's runner builds no repair schedule, so none is charged");
		check(b.input_passes == 1, "default policy decodes the input once");
	}

	// The declared bound: staged bytes must be flat in frame count.
	{
		Policy p;
		p.chunk_frames = 4;
		p.retain_host_real_stack = false;
		p.retain_host_fourier_stack = false;
		unsigned long long first = 0;
		bool flat = true;
		for (long long F = 4; F <= 4096; F *= 2) {
			Geometry g; g.nx = 4096; g.ny = 4096; g.n_frames = F;
			Budget b;
			if (!computeBudget(g, p, b)) { flat = false; break; }
			if (first == 0) first = b.staged_host_bytes;
			else if (b.staged_host_bytes != first) flat = false;
		}
		check(flat, "staged host bytes are constant as frame count grows 4 -> 4096");
		check(first == 4ull * 4 * 4096 * 4096, "staged bound is 4*C*W*H");
	}

	// A chunk at or above the frame count degenerates to the whole movie
	// rather than to a larger number.
	{
		Geometry g; g.nx = 64; g.ny = 32; g.n_frames = 7;
		Policy p; p.chunk_frames = 99;
		Budget b;
		check(computeBudget(g, p, b), "oversized chunk accepted");
		check(b.staged_host_bytes == 4ull * 7 * 64 * 32, "oversized chunk clamps to the movie");
	}

	// Compact upload halves the staged term and the H2D volume -- and nothing
	// else. This is arithmetic, not a runtime claim.
	{
		Geometry g; g.nx = 3710; g.ny = 3838; g.n_frames = 24;
		Policy p; p.chunk_frames = 2; p.device_resident = true;
		p.retain_host_real_stack = false;
		Budget wide, compact;
		check(computeBudget(g, p, wide), "float staged budget computed");
		p.staged_bytes_per_sample = 2;
		check(computeBudget(g, p, compact), "uint16 staged budget computed");
		check(compact.staged_host_bytes * 2 == wide.staged_host_bytes,
		      "compact staging halves the staged host term");
		check(compact.h2d_bytes * 2 == wide.h2d_bytes,
		      "compact staging halves the host-to-device volume");
		check(compact.device_bytes == wide.device_bytes,
		      "compact staging does not change device residency");
	}

	// Replay doubles the decode count and the upload volume; a design that
	// claims otherwise has to change this number.
	{
		Geometry g; g.nx = 512; g.ny = 512; g.n_frames = 16;
		Policy p; p.chunk_frames = 1; p.device_resident = true;
		p.retain_host_real_stack = false;
		Budget one, two;
		check(computeBudget(g, p, one), "single-pass budget computed");
		p.input_passes = 2;
		check(computeBudget(g, p, two), "two-pass budget computed");
		check(two.h2d_bytes == 2 * one.h2d_bytes, "replay doubles the upload volume");
		check(two.staged_host_bytes == one.staged_host_bytes,
		      "replay does not change the staged bound");
	}

	// Three-way admission: fits, inadmissible, or malformed input -- and the
	// three must stay distinguishable. Collapsing the last two is the defect
	// this enum exists to prevent.
	{
		Geometry g; g.nx = 1024; g.ny = 1024; g.n_frames = 40;
		Policy p;
		p.retain_host_real_stack = false;
		p.retain_host_fourier_stack = false;
		const unsigned long long frame_bytes = 4ull * 1024 * 1024;
		long long chunk = -1;
		const char *err = reinterpret_cast<const char*>(1); // must be cleared

		check(largestChunkWithin(g, p, 10 * frame_bytes, chunk, &err) == Admission::Fits,
		      "a budget of 10 frames fits");
		check(chunk == 10, "largest admissible chunk is exactly 10 frames");
		check(err == nullptr, "a successful call clears the error out-param");

		chunk = -1;
		check(largestChunkWithin(g, p, 10 * frame_bytes + frame_bytes / 2, chunk)
		      == Admission::Fits, "a budget of 10.5 frames fits");
		check(chunk == 10, "a part-frame surplus does not buy another frame");

		// Under one staged frame: inadmissible, NOT "chunk 0" and NOT invalid.
		chunk = -1; err = nullptr;
		check(largestChunkWithin(g, p, frame_bytes - 1, chunk, &err)
		      == Admission::Inadmissible,
		      "a budget under one frame is Inadmissible");
		check(chunk == -1, "an inadmissible result leaves the caller's chunk untouched");
		check(err == nullptr, "Inadmissible is not reported as an input error");

		// A malformed policy must NOT masquerade as an inadmissible movie: the
		// budget here is enormous, so anything but InvalidInput would tell a
		// caller the movie is too big for a host with terabytes free.
		{
			Policy bad = p; bad.input_passes = 0;
			long long c2 = -1; const char *e2 = nullptr;
			check(largestChunkWithin(g, bad, 1ull << 40, c2, &e2)
			      == Admission::InvalidInput,
			      "a malformed policy is InvalidInput, not Inadmissible");
			check(e2 != nullptr, "InvalidInput reports a reason");
			check(c2 == -1, "InvalidInput leaves the caller's chunk untouched");

			Policy neg = p; neg.chunk_frames = -1;
			check(largestChunkWithin(g, neg, 1ull << 40, c2) == Admission::InvalidInput,
			      "a negative chunk_frames is rejected even though the field is ignored");

			Geometry bg; bg.nx = 0; bg.ny = 8; bg.n_frames = 8;
			check(largestChunkWithin(bg, p, 1ull << 40, c2) == Admission::InvalidInput,
			      "a malformed geometry is InvalidInput");
		}

		// Constant terms count: the same movie and budget flip to inadmissible
		// once a resident stack is charged.
		Policy heavy = p;
		heavy.retain_host_fourier_stack = true;
		chunk = -1;
		check(largestChunkWithin(g, heavy, 10 * frame_bytes, chunk) == Admission::Inadmissible,
		      "a retained Fourier stack makes the same budget inadmissible");

		// Never more than the movie, however large the budget.
		chunk = -1;
		check(largestChunkWithin(g, p, 1ull << 40, chunk) == Admission::Fits
		      && chunk == g.n_frames,
		      "a huge budget clamps to the frame count");

		// Extra named terms are charged, not ignored.
		Policy withextra = p;
		withextra.extra_host_bytes = (long long)(5 * frame_bytes);
		chunk = -1;
		check(largestChunkWithin(g, withextra, 10 * frame_bytes, chunk) == Admission::Fits
		      && chunk == 5, "extra host terms reduce the admissible chunk");

		// The compact-upload parameter, which the ADR's variant C turns on and
		// which was previously untested here.
		Policy compact = p; compact.staged_bytes_per_sample = 2;
		chunk = -1;
		check(largestChunkWithin(g, compact, 10 * frame_bytes, chunk) == Admission::Fits
		      && chunk == 20, "halving the sample width doubles the admissible chunk");

		Policy dev = p; dev.device_resident = true;
		chunk = -1;
		check(largestChunkWithin(g, dev, 10 * frame_bytes, chunk) == Admission::Fits
		      && chunk == 10, "device residency does not consume the host budget");
	}

	// The binary search is only sound if host_bytes is non-decreasing in
	// chunk_frames on [1, n_frames-1]. It is NOT monotone across the whole
	// range: an aliasing policy drops at chunk == n_frames. Assert both halves,
	// so neither the monotone interval nor the alias can regress unnoticed.
	{
		Geometry g; g.nx = 97; g.ny = 61; g.n_frames = 64;
		Policy policies[6];
		policies[1].staged_bytes_per_sample = 2;
		policies[2].retain_host_aligned_stack = true;
		policies[2].device_resident = true;
		policies[3].extra_host_bytes = 1234567;
		policies[3].input_passes = 2;
		policies[4].schedule_defect_pixels = 4096;          // schedule charged
		policies[5].schedule_defect_pixels = kAllPixelsDefective;
		policies[5].retain_host_real_stack = false;

		bool monotone = true;
		for (int k = 0; k < 6 && monotone; k++) {
			unsigned long long prev = 0;
			for (long long c = 1; c <= g.n_frames - 1; c++) {
				Policy p = policies[k];
				p.chunk_frames = c;
				Budget b;
				if (!computeBudget(g, p, b) || b.host_bytes < prev) { monotone = false; break; }
				prev = b.host_bytes;
			}
		}
		check(monotone,
		      "host_bytes is non-decreasing in chunk_frames on [1, n_frames-1] "
		      "for every policy shape");

		// The schedule term must not depend on the chunk at all -- it is sized
		// by the defect count and the frame count, both chunk-independent.
		{
			Policy p = policies[4];
			unsigned long long first = 0;
			bool flat = true;
			for (long long c = 1; c <= g.n_frames; c++) {
				p.chunk_frames = c;
				Budget b;
				if (!computeBudget(g, p, b)) { flat = false; break; }
				if (c == 1) first = b.schedule_host_bytes;
				else if (b.schedule_host_bytes != first) flat = false;
			}
			check(flat && first > 0, "the schedule charge is independent of the chunk");
		}

		// The alias drop at the top of the range, which is why the search
		// evaluates n_frames separately instead of binary-searching through it.
		{
			Policy p; // default: aliases
			Budget last_partial, whole;
			p.chunk_frames = g.n_frames - 1;
			check(computeBudget(g, p, last_partial), "penultimate chunk budget computed");
			p.chunk_frames = g.n_frames;
			check(computeBudget(g, p, whole), "whole-movie budget computed");
			check(!last_partial.staged_aliases_resident && whole.staged_aliases_resident,
			      "the alias appears only at the full frame count");
			check(whole.host_bytes < last_partial.host_bytes,
			      "host_bytes DROPS at chunk == n_frames for an aliasing policy");
		}

		// And the search must still find that drop rather than walk past it.
		{
			Policy p;
			Budget whole;
			p.chunk_frames = g.n_frames;
			computeBudget(g, p, whole);
			long long chunk = -1;
			check(largestChunkWithin(g, p, whole.host_bytes, chunk) == Admission::Fits
			      && chunk == g.n_frames,
			      "the search finds the aliased whole-movie point a monotone search would miss");
		}
	}

	// --- Review finding: the repair schedule is a host allocation this
	// component makes, and was omitted from its own budget. A dense mask makes
	// it dominate. Each control below also computes what the OLD model said,
	// and asserts the two disagree -- otherwise the control proves nothing.
	{
		Geometry g; g.nx = 256; g.ny = 256; g.n_frames = 64;
		const unsigned long long frame_bytes = 4ull * 256 * 256;

		Policy staged;               // the staged shape: no resident stacks
		staged.chunk_frames = 2;
		staged.retain_host_real_stack = false;
		staged.retain_host_fourier_stack = false;

		Policy dense = staged;       // same, but a fully defective mask
		dense.schedule_defect_pixels = kAllPixelsDefective;

		Budget without_sched, with_sched;
		check(computeBudget(g, staged, without_sched), "staged budget computed");
		check(computeBudget(g, dense, with_sched), "dense-defect budget computed");

		check(without_sched.schedule_host_bytes == 0,
		      "no declared defects means no schedule charge");
		const unsigned long long n_bad = 256ull * 256ull;
		const unsigned long long expect =
		    n_bad * 3ull * sizeof(int) + n_bad * 64ull * sizeof(Draw);
		check(with_sched.schedule_host_bytes == expect,
		      "the schedule charge is 3 ints per defect plus one Draw per (defect, frame)");

		// The whole point: the omitted term dwarfs the staged term it was
		// omitted next to. O(C*W*H) admitted, O(F*W*H) allocated.
		check(with_sched.schedule_host_bytes > 10 * without_sched.host_bytes,
		      "with a dense mask the schedule dwarfs the staged chunk it was omitted beside");

		// Discrimination: a budget sized for the staged chunk admits under the
		// old model and must be REJECTED under the corrected one.
		const unsigned long long small = without_sched.host_bytes + frame_bytes;
		check(without_sched.host_bytes <= small,
		      "old model: the dense job fits this budget (it ignored the schedule)");
		long long chunk = -1;
		check(largestChunkWithin(g, dense, small, chunk) == Admission::Inadmissible,
		      "corrected model: the dense job is Inadmissible against the same budget");
		check(chunk == -1, "the rejected dense job leaves the caller's chunk untouched");

		// And it is admitted again once the budget genuinely covers the schedule.
		chunk = -1;
		check(largestChunkWithin(g, dense, with_sched.host_bytes + 8 * frame_bytes, chunk)
		      == Admission::Fits && chunk >= 2,
		      "a budget that does cover the schedule admits the dense job");

		// Recording the replacements costs a float per entry on top.
		Policy rec = dense; rec.schedule_records_replacements = true;
		Budget with_rec;
		check(computeBudget(g, rec, with_rec), "recording budget computed");
		check(with_rec.schedule_host_bytes - with_sched.schedule_host_bytes
		      == n_bad * 64ull * sizeof(float),
		      "recording replacements adds exactly one float per (defect, frame)");

		// A declared bound is charged proportionally, not rounded to worst case.
		Policy bounded = staged; bounded.schedule_defect_pixels = 1024;
		Budget bb;
		check(computeBudget(g, bounded, bb), "bounded-defect budget computed");
		check(bb.schedule_host_bytes
		      == 1024ull * 3ull * sizeof(int) + 1024ull * 64ull * sizeof(Draw),
		      "a declared defect bound is charged exactly, not rounded up");
		check(bb.schedule_host_bytes < with_sched.schedule_host_bytes,
		      "a bound below worst case costs less than worst case");
	}

	// --- Review finding: the no-staging policy double-counted Iframes, so a
	// budget that actually fits could be rejected.
	{
		Geometry g; g.nx = 512; g.ny = 512; g.n_frames = 32;
		unsigned long long real = 0, r2c = 0;
		realStackBytes(g, real); fourierStackBytes(g, r2c);

		Policy nostage; // defaults: whole movie, real + Fourier retained
		Budget b;
		check(computeBudget(g, nostage, b), "no-staging budget computed");
		check(b.staged_aliases_resident, "no-staging policy aliases");
		check(b.host_bytes == real + r2c, "no-staging host bytes are real + r2c");

		// A budget that fits the true live set but NOT the old double count.
		const unsigned long long fits = real + r2c;
		const unsigned long long old_model = real + r2c + real;
		check(old_model > fits,
		      "old model: this budget was reported as too small");
		long long chunk = -1;
		check(largestChunkWithin(g, nostage, fits, chunk) == Admission::Fits,
		      "corrected model: the same budget admits the whole movie");
		check(chunk == g.n_frames, "and admits it at the full frame count");

		// One byte short must still be rejected, so the fix is not just slack.
		chunk = -1;
		check(largestChunkWithin(g, nostage, fits - 1, chunk) == Admission::Inadmissible,
		      "one byte below the true live set is still Inadmissible");

		// The alias is specific: a partial chunk is a genuinely separate ring,
		// and a compact upload is a genuinely separate narrower buffer.
		Policy partial = nostage; partial.chunk_frames = 4;
		Budget pb;
		check(computeBudget(g, partial, pb) && !pb.staged_aliases_resident,
		      "a partial chunk does not alias the retained stack");
		check(pb.host_bytes == 4ull * 4 * 512 * 512 + real + r2c,
		      "a partial ring is charged on top of the retained stack");

		Policy compact = nostage; compact.staged_bytes_per_sample = 2;
		Budget cb;
		check(computeBudget(g, compact, cb) && !cb.staged_aliases_resident,
		      "a compact uint16 staging buffer does not alias the float stack");

		Policy nostack = nostage; nostack.retain_host_real_stack = false;
		Budget nb;
		check(computeBudget(g, nostack, nb) && !nb.staged_aliases_resident,
		      "with no retained real stack there is nothing to alias");
		check(nb.host_bytes == real + r2c,
		      "staging the whole movie without retaining it costs the same one stack");
	}

	// Overflow and invalid input must be rejected, not wrapped.
	{
		Budget b;
		Geometry huge; huge.nx = 4000000000ll; huge.ny = 4000000000ll; huge.n_frames = 4000000000ll;
		Policy p;
		check(!computeBudget(huge, p, b), "overflowing geometry rejected");
		check(b.error != nullptr, "overflow reports an error string");

		Geometry zero; zero.nx = 0; zero.ny = 8; zero.n_frames = 8;
		check(!computeBudget(zero, p, b), "zero width rejected");

		Geometry g; g.nx = 8; g.ny = 8; g.n_frames = 8;
		Policy neg; neg.chunk_frames = -1;
		check(!computeBudget(g, neg, b), "negative chunk rejected");
		Policy zp; zp.input_passes = 0;
		check(!computeBudget(g, zp, b), "zero input passes rejected");
		Policy nb; nb.extra_host_bytes = -1;
		check(!computeBudget(g, nb, b), "negative extra host bytes rejected");
	}
}

// --------------------------------------------------------------------------
// Rejection paths
// --------------------------------------------------------------------------

// The test harness's own Movie copy is hand-written, so it gets a test too:
// without the self-assignment guard, operator= frees the mask and then copies
// from the freshly allocated, uninitialised buffer, leaving a mask of
// indeterminate bools driving buildSchedule.
void runHarnessChecks()
{
	Movie m = makeMovie("self-assign", 12, 10, 3, 2, 1.0f, 1.0f);
	markBad(m, 4, 4); markBad(m, 7, 2); markBlock(m, 1, 1, 2, 2);
	const size_t before = m.badCount();
	const std::vector<float> data_before = m.data;

	Movie &alias = m;
	m = alias; // self-assignment through a reference, which is how it happens

	check(m.badCount() == before, "self-assignment preserves the defect mask");
	check(m.data == data_before, "self-assignment preserves the frame data");
	check(m.nx == 12 && m.ny == 10 && m.n_frames == 3,
	      "self-assignment preserves the geometry");

	// And the mask must still be usable, not indeterminate.
	Schedule sched;
	init_random_generator(4);
	check(buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, m.d_max,
	                    m.mean, m.stddev, sched),
	      "a self-assigned movie still builds a schedule");
	check(sched.bad_x.size() == before,
	      "the schedule sees exactly the defects the mask had before");

	// A normal copy must be a deep copy: mutating the source must not move the
	// destination's mask.
	Movie copy = m;
	markBad(m, 9, 9);
	check(copy.badCount() == before && m.badCount() == before + 1,
	      "Movie copy is deep, not aliased");
}

void runRejectionChecks()
{
	Movie m = makeMovie("reject", 16, 16, 4, 2, 1.0f, 1.0f);
	markBad(m, 5, 5); markBad(m, 9, 9);
	Schedule sched;
	init_random_generator(1);
	check(buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, m.d_max,
	                    m.mean, m.stddev, sched), "reject fixture schedule built");

	const size_t n_bad = sched.bad_x.size();
	std::vector<float> reps(n_bad * (size_t)m.n_frames, 0.0f);
	std::vector<float*> ptrs(1);
	ptrs[0] = m.frame(0);

	check(!applyChunk(sched, nullptr, 0, 1, ptrs.data(), nullptr, true, &reps),
	      "applyChunk rejects a null mask");
	check(!applyChunk(sched, m.badMask(), 0, 1, nullptr, nullptr, true, &reps),
	      "applyChunk rejects null frame pointers");
	check(!applyChunk(sched, m.badMask(), -1, 1, ptrs.data(), nullptr, true, &reps),
	      "applyChunk rejects a negative first frame");
	check(!applyChunk(sched, m.badMask(), 4, 1, ptrs.data(), nullptr, true, &reps),
	      "applyChunk rejects a chunk past the last frame");
	check(!applyChunk(sched, m.badMask(), 0, 5, ptrs.data(), nullptr, true, &reps),
	      "applyChunk rejects a chunk longer than the movie");
	check(!applyChunk(sched, m.badMask(), 0, 1, ptrs.data(), nullptr, false, nullptr),
	      "applyChunk rejects record-only with nowhere to record");
	{
		std::vector<float> wrong(reps.size() + 1, 0.0f);
		check(!applyChunk(sched, m.badMask(), 0, 1, ptrs.data(), nullptr, true, &wrong),
		      "applyChunk rejects a mis-sized replacement buffer");
	}
	{
		// A mask that lost a defect after the schedule was built changes n_ok,
		// so the slot list no longer matches and the call must refuse rather
		// than index a stale slot.
		Movie changed = m;
		changed.mask[(size_t)9 * changed.nx + 9] = false;
		std::vector<float*> p2(1); p2[0] = changed.frame(0);
		check(!applyChunk(sched, changed.badMask(), 0, 1, p2.data(), nullptr, true, &reps),
		      "applyChunk rejects a mask that changed since the schedule was built");
	}
	{
		Schedule broken = sched;
		broken.bad_y.pop_back();
		check(!applyChunk(broken, m.badMask(), 0, 1, ptrs.data(), nullptr, true, &reps),
		      "applyChunk rejects a schedule with inconsistent bad_y");
	}
	{
		Schedule broken = sched;
		broken.draws[0].slot = 999;
		std::vector<float> r2(reps.size(), 0.0f);
		check(!applyChunk(broken, m.badMask(), 0, 1, ptrs.data(), nullptr, true, &r2),
		      "applyChunk rejects an out-of-range neighbour slot");
	}

	// buildSchedule rejections, and no half-populated Schedule on failure.
	{
		Schedule out;
		// Populate `out` with a real schedule first. Asserting emptiness on a
		// freshly default-constructed Schedule would hold even if the reset at
		// the top of buildSchedule were deleted, so it would not observe the
		// fix it is written for.
		init_random_generator(2);
		check(buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, m.d_max,
		                    m.mean, m.stddev, out) && !out.draws.empty(),
		      "pre-populated a schedule so the reset below is observable");
		check(!buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, 5,
		                     m.mean, m.stddev, out),
		      "buildSchedule rejects d_max above the runner's maximum of 4");
		check(out.bad_x.empty() && out.draws.empty() && out.n_frames == 0,
		      "a rejected buildSchedule clears a previously populated result");
		check(!buildSchedule(nullptr, m.nx, m.ny, m.n_frames, 2, m.mean, m.stddev, out),
		      "buildSchedule rejects a null mask");
		check(!buildSchedule(m.badMask(), 0, m.ny, m.n_frames, 2, m.mean, m.stddev, out),
		      "buildSchedule rejects zero width");
		check(!buildSchedule(m.badMask(), m.nx, m.ny, 0, 2, m.mean, m.stddev, out),
		      "buildSchedule rejects zero frames");
		check(!buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, -1, m.mean, m.stddev, out),
		      "buildSchedule rejects a negative d_max");
	}

	// The two computeBudget rejections not covered by runCapacityChecks.
	{
		Geometry g; g.nx = 8; g.ny = 8; g.n_frames = 8;
		Budget b;
		Policy zero_sample; zero_sample.staged_bytes_per_sample = 0;
		check(!computeBudget(g, zero_sample, b), "zero staged sample width rejected");
		Policy neg_dev; neg_dev.extra_device_bytes = -1;
		check(!computeBudget(g, neg_dev, b), "negative extra device bytes rejected");
	}
}

} // namespace

int main()
{
	runHarnessChecks();
	runCapacityChecks();
	runRejectionChecks();

	const std::vector<int> chunks = {1, 2, 3, 5, 24};

	// Sparse isolated defects: every pixel has a full 5x5 neighbourhood, so
	// n_ok = 24 and the neighbour branch is taken throughout.
	{
		Movie m = makeMovie("sparse-24f", 64, 48, 24, 2, 100.0f, 7.5f);
		markBad(m, 10, 10); markBad(m, 20, 33); markBad(m, 41, 5); markBad(m, 30, 30);
		runOrderingCase(m, chunks, 1, true, false);
	}

	// A solid 5x5 block. Its centre sees no good neighbour at all, so the
	// Gaussian branch is reachable; the surrounding ring keeps the neighbour
	// branch live in the same fixture. Odd frame count on purpose: an even one
	// hides an index that is wrong by a factor of two in the frame stride.
	{
		Movie m = makeMovie("block5x5-13f", 40, 40, 13, 2, -12.25f, 3.0f);
		markBlock(m, 15, 15, 5, 5);
		runOrderingCase(m, {1, 2, 4, 13}, 7, true, true);
	}

	// Corner and edge defects, where the neighbourhood is clipped by the image
	// bounds rather than by the mask.
	{
		Movie m = makeMovie("corners-9f", 32, 24, 9, 2, 5.0f, 1.0f);
		markBad(m, 0, 0); markBad(m, 0, 1); markBad(m, 1, 0);
		markBad(m, 23, 31); markBad(m, 23, 30);
		markBad(m, 0, 16); markBad(m, 12, 0);
		runOrderingCase(m, {1, 2, 4, 9}, 11, true, true);
	}

	// Non-square, EER neighbourhood radius.
	{
		Movie m = makeMovie("nonsquare-eer-7f", 57, 29, 7, 4, 0.5f, 2.5f);
		markBlock(m, 10, 20, 9, 9);
		markBad(m, 3, 3);
		runOrderingCase(m, {1, 2, 3, 7}, 13, true, true);
	}

	// sigma == 0: rnd_gaus returns mu without consuming the stream. A schedule
	// that assumed a fixed number of draws per Gaussian would desynchronise
	// here and nowhere else.
	{
		Movie m = makeMovie("zero-sigma-5f", 24, 24, 5, 2, 42.0f, 0.0f);
		markBlock(m, 8, 8, 5, 5);
		markBad(m, 2, 20);
		runOrderingCase(m, {1, 2, 5}, 3, true, true);
	}

	// Single frame, and a mask with no defects at all.
	{
		Movie m = makeMovie("single-frame", 16, 16, 1, 2, 1.0f, 1.0f);
		markBad(m, 8, 8);
		runOrderingCase(m, {1}, 5, true, false);

		Movie empty = makeMovie("no-defects", 16, 16, 4, 2, 1.0f, 1.0f);
		runOrderingCase(empty, {1, 4}, 5, false, false);
	}

	// Raw host frames with a gain reference: the runner's _CUDA_ENABLED path,
	// where each neighbour is multiplied by Igain on gather and the replacement
	// is recorded instead of written. An applyChunk that drops the gain, or
	// writes the raw frame, diverges here and nowhere else.
	{
		Movie m = makeMovie("raw-gain-11f", 36, 28, 11, 2, 9.0f, 2.0f);
		addGain(m);
		markBad(m, 7, 7); markBad(m, 14, 21); markBlock(m, 18, 8, 5, 5);
		runOrderingCase(m, {1, 2, 3, 11}, 17, true, true);

		// And the raw frames must come back untouched, which the frame memcmp
		// inside runOrderingCase cannot distinguish from "correctly written".
		Movie cand = m;
		Schedule sched;
		std::vector<float> reps;
		init_random_generator(17);
		check(scheduledRepair(cand, 2, sched, &reps),
		      "raw-gain: record-only application succeeded");
		check(std::memcmp(cand.data.data(), m.data.data(),
		                  m.data.size() * sizeof(float)) == 0,
		      "raw-gain: raw host frames are left untouched, as the runner leaves them");
		bool any_nonzero = false;
		for (size_t i = 0; i < reps.size(); i++) if (reps[i] != 0.0f) any_nonzero = true;
		check(any_nonzero, "raw-gain: replacements were actually recorded");
	}

	// Gain is not inert. Both arms are record-only with write_in_place = false,
	// so the ONLY difference between them is the gain pointer. An earlier
	// version varied raw_host, which toggled write_in_place too; that version
	// was sound only because written pixels are masked and never re-read --
	// i.e. it leaned on the very invariant this suite exists to establish.
	{
		Movie m = makeMovie("gain-matters", 36, 28, 6, 2, 9.0f, 2.0f);
		addGain(m);
		// All three defects have a full 5x5 neighbourhood, so n_ok = 24 > 6 and
		// every draw takes the neighbour branch. A Gaussian draw would be
		// gain-independent and would dilute the comparison.
		markBad(m, 7, 7); markBad(m, 14, 21); markBad(m, 3, 30);

		Schedule sched;
		init_random_generator(23);
		check(buildSchedule(m.badMask(), m.nx, m.ny, m.n_frames, m.d_max,
		                    m.mean, m.stddev, sched), "gain-matters: schedule built");
		check(sched.n_gaussian_draws == 0,
		      "gain-matters: every draw is a neighbour draw, so gain reaches all of them");

		auto run = [&](const float *gain, std::vector<float> &out) {
			out.assign(sched.bad_x.size() * (size_t)m.n_frames, 0.0f);
			Movie work = m;
			for (int base = 0; base < m.n_frames; base += 2) {
				int n = (base + 2 <= m.n_frames) ? 2 : m.n_frames - base;
				std::vector<float*> ptrs(n);
				for (int k = 0; k < n; k++) ptrs[k] = work.frame(base + k);
				if (!applyChunk(sched, m.badMask(), base, n, ptrs.data(),
				                gain, /*write_in_place=*/false, &out))
					return false;
			}
			return true;
		};

		std::vector<float> with_gain, without;
		check(run(m.gainPtr(), with_gain), "gain-matters: gain arm ran");
		check(run(nullptr, without), "gain-matters: no-gain arm ran");
		check(with_gain != without,
		      "gain-matters: dropping the gain multiply changes the replacements");
	}

	std::fprintf(stderr, "%d checks, %d failures\n", g_checks, g_failures);
	return g_failures == 0 ? 0 : 1;
}
