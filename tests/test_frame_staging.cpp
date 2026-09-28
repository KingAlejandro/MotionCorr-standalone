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

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
	std::vector<float> data;          // n_frames * ny * nx
	std::vector<unsigned char> mask;  // ny * nx, std::vector<bool> has no data()
	float mean = 0.0f, stddev = 0.0f;
	int d_max = 2;
	std::string name;

	float *frame(int f) { return data.data() + (size_t)f * ny * nx; }
	const bool *badMask() const { return reinterpret_cast<const bool*>(mask.data()); }
	size_t badCount() const {
		size_t n = 0;
		for (size_t i = 0; i < mask.size(); i++) if (mask[i]) n++;
		return n;
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
	m.mask.assign((size_t)ny * nx, 0);
	for (int f = 0; f < n_frames; f++)
		for (int y = 0; y < ny; y++)
			for (int x = 0; x < nx; x++)
				m.data[((size_t)f * ny + y) * nx + x] = syntheticPixel(f, y, x);
	static_assert(sizeof(bool) == sizeof(unsigned char), "bool must be byte sized");
	return m;
}

void markBad(Movie &m, int y, int x)
{
	if (y < 0 || y >= m.ny || x < 0 || x >= m.nx) return;
	m.mask[(size_t)y * m.nx + x] = 1;
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

const int kNumMinOk = 6;
const int kPbufSize = 100;

void referenceRepair(Movie &m)
{
	const bool *bBad = m.badMask();
	const int nx = m.nx, ny = m.ny, D_MAX = m.d_max;
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

	for (int base = 0; base < m.n_frames; base += chunk) {
		int n = chunk;
		if (base + n > m.n_frames) n = m.n_frames - base;
		std::vector<float*> ptrs(n);
		for (int k = 0; k < n; k++) ptrs[k] = m.frame(base + k);
		if (!applyChunk(sched_out, m.badMask(), base, n, ptrs.data(), replacements))
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
	init_random_generator(seed);
	referenceRepair(ref);
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

		check(cand.data.size() == ref.data.size(), tag + ": frame buffer sizes agree");
		check(std::memcmp(cand.data.data(), ref.data.data(),
		                  ref.data.size() * sizeof(float)) == 0,
		      tag + ": every repaired pixel is bit-identical to the reference loop");
		check(cand_tail == ref_tail, tag + ": process RNG left in the same state");

		// The recorded sparse values must agree with what landed in the frames,
		// because the resident CUDA path uploads those rather than the frames.
		bool sparse_ok = true;
		for (size_t ibad = 0; ibad < sched.bad_x.size() && sparse_ok; ibad++)
			for (int f = 0; f < proto.n_frames; f++) {
				const float in_frame = cand.frame(f)[(size_t)sched.bad_y[ibad] * proto.nx
				                                     + sched.bad_x[ibad]];
				if (replacements[ibad * (size_t)proto.n_frames + f] != in_frame) {
					sparse_ok = false;
					break;
				}
			}
		check(sparse_ok, tag + ": recorded sparse replacements match the frame contents");

		// Observability: assert the fixture actually reached the branch it was
		// built for, rather than passing because nothing happened.
		if (expect_neighbor)
			check(sched.n_neighbor_draws > 0, tag + ": exercised the neighbour branch");
		if (expect_gaussian)
			check(sched.n_gaussian_draws > 0, tag + ": exercised the Gaussian branch");
		check(sched.n_neighbor_draws + sched.n_gaussian_draws
		      == (long long)sched.bad_x.size() * proto.n_frames,
		      tag + ": every (pixel, frame) decision is accounted for");

		// n_ok is frame-independent: that is the claim the whole design rests
		// on, so check it directly rather than inferring it from the values.
		bool uniform = true;
		for (size_t ibad = 0; ibad < sched.bad_x.size(); ibad++) {
			const DrawKind k0 = sched.draws[ibad * (size_t)proto.n_frames].kind;
			for (int f = 1; f < proto.n_frames; f++)
				if (sched.draws[ibad * (size_t)proto.n_frames + f].kind != k0) uniform = false;
		}
		check(uniform, tag + ": branch choice is constant across frames for each bad pixel");
	}

	// Negative control. The naive chunking must be rejected by the same
	// comparison that passed above -- otherwise the comparison proves nothing.
	// Chunk 1 with more than one frame is enough to reorder the stream.
	if (proto.n_frames > 1 && proto.badCount() > 0) {
		Movie bad = proto;
		init_random_generator(seed);
		brokenRepair(bad, 1);
		check(std::memcmp(bad.data.data(), ref.data.data(),
		                  ref.data.size() * sizeof(float)) != 0,
		      proto.name + ": negative control (naive frame-major chunking) is detected");
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
		check(b.host_bytes == real + r2c + real,
		      "default policy charges the staged movie and both resident stacks");
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

} // namespace

int main()
{
	runCapacityChecks();

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

	std::fprintf(stderr, "%d checks, %d failures\n", g_checks, g_failures);
	return g_failures == 0 ? 0 : 1;
}
