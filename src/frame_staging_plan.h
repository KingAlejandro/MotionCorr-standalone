#ifndef FRAME_STAGING_PLAN_H_
#define FRAME_STAGING_PLAN_H_

// Bounded frame-staging capacity and repair-ordering components (issue #95).
//
// This translation unit is a *component prototype*. It allocates no pixel
// buffers, owns no device memory, starts no threads and is deliberately not
// wired into MotioncorrRunner: runner integration belongs to #94 per the #66
// execution plan. It exists so the two load-bearing claims of
// agents/designs/issue_95_bounded_frame_staging.md can be tested before any
// production change is proposed.
//
// Claim 1 (capacity): the host high-water of a staged pipeline can be written
//   as a closed, overflow-checked formula whose staged term does not grow with
//   the frame count, and the non-staged terms that remain are named rather
//   than quietly dropped.
//
// Claim 2 (ordering): the hot-pixel repair random-number stream in
//   MotioncorrRunner::executeOwnMotionCorrection is *data-independent*, so it
//   can be materialised in the original order before any frame is resident and
//   then applied chunk by chunk without changing a single replacement value.
//   Claim 2 is the actual blocker for every bounded-staging design; see the
//   ADR for why the loop order otherwise forces full-movie residency.

#include <cstddef>
#include <vector>

namespace motioncorr {
namespace staging {

// ---------------------------------------------------------------------------
// Capacity arithmetic
// ---------------------------------------------------------------------------

struct Geometry {
	long long nx = 0;        // fast axis, pixels
	long long ny = 0;        // slow axis, pixels
	long long n_frames = 0;  // frames actually processed (after frame-range selection)
};

// Which whole-movie stacks a candidate policy keeps. Defaults describe main
// @4c952b3f on the CPU path, so a default-constructed policy reproduces today's
// arithmetic rather than an aspirational one.
struct Policy {
	// 0 (or >= n_frames) means "no staging": the whole movie is resident.
	long long chunk_frames = 0;

	bool retain_host_real_stack = true;      // Iframes
	bool retain_host_fourier_stack = true;   // Fframes
	bool retain_host_aligned_stack = false;  // Irefframes, CPU reconstruction branch
	bool device_resident = false;            // CudaMovieSession d_Iframes + d_Fframes

	// Named, caller-supplied terms. These are *not* optional decoration: a
	// budget that omits decoder scratch, the gain reference, the defect mask,
	// pinned staging, cuFFT workspace and the output images is not a budget.
	long long extra_host_bytes = 0;
	long long extra_device_bytes = 0;

	// How many times the encoded input is decoded end to end. 1 = today.
	// 2 = the replay/two-pass alternative.
	int input_passes = 1;

	// Bytes per staged host sample before float conversion. 4 = decoded float
	// (today). 2 = the compact unsigned-16 upload experiment. Only affects the
	// staged term and the H2D volume, never the resident stacks.
	int staged_bytes_per_sample = 4;
};

struct Budget {
	bool valid = false;
	// Points at a string literal with static lifetime, or null when valid.
	const char *error = nullptr;

	unsigned long long host_bytes = 0;    // sum of every host term below
	unsigned long long device_bytes = 0;

	// The staged term on its own. The acceptance criterion "memory use obeys a
	// declared staging-byte bound as frame count increases" is a statement
	// about this field and nothing else.
	unsigned long long staged_host_bytes = 0;

	// Whole-movie host terms that survive the policy. Reported separately so a
	// staging design cannot claim a saving that a still-resident stack cancels.
	unsigned long long resident_host_bytes = 0;

	unsigned long long h2d_bytes = 0;
	unsigned long long d2h_bytes = 0;

	// Decodes of the encoded input, end to end.
	int input_passes = 0;
};

// Returns false and fills budget.error on any overflow or invalid geometry.
// All products are checked; nothing is computed in a type that could wrap.
bool computeBudget(const Geometry &geom, const Policy &policy, Budget &budget);

// Real and R2C whole-movie array sizes, as published in the #95 task comment:
//   real = 4*F*W*H,  r2c = 8*F*H*(floor(W/2)+1)
// Exposed so the ADR's numbers and the tests share one implementation.
bool realStackBytes(const Geometry &geom, unsigned long long &out);
bool fourierStackBytes(const Geometry &geom, unsigned long long &out);

// ---------------------------------------------------------------------------
// Hot-pixel repair draw schedule
// ---------------------------------------------------------------------------
//
// Mirrors the repair loop at src/motioncorr_runner.cpp:1732 (main @4c952b3f):
//
//   FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY2D(bBad)          // raster order over (i, j)
//     if (!bBad(i, j)) continue;
//     for (iframe = 0; iframe < n_frames; iframe++)
//       n_ok = 0;
//       for (dy = -D_MAX .. D_MAX)
//         for (dx = -D_MAX .. D_MAX)
//           skip out of bounds; skip bBad(y, x);
//           pbuf[n_ok++] = Iframes[iframe](y, x);
//       replacement = (n_ok > NUM_MIN_OK) ? pbuf[rand() % n_ok]
//                                         : rnd_gaus(frame_mean, frame_std);
//
// n_ok counts in-bounds, non-masked neighbours. It reads bBad and the image
// bounds only -- never a pixel value -- so it is identical for every frame, and
// therefore both the branch taken and the number of random draws consumed are
// fixed before any frame is decoded.

enum class DrawKind : unsigned char {
	NeighborSlot = 0,  // take slot `slot` of this pixel's geometric neighbour list
	GaussianValue = 1, // use `value` verbatim
};

struct Draw {
	DrawKind kind = DrawKind::NeighborSlot;
	int slot = 0;
	float value = 0.0f;
};

struct Schedule {
	int nx = 0, ny = 0;
	int n_frames = 0;
	int d_max = 0;

	// Bad pixels in the runner's raster order, so index `ibad` here is the same
	// `bad_idx` the runner uses for its sparse CUDA replacement array.
	std::vector<int> bad_x, bad_y;

	// n_ok per bad pixel. Frame-independent; that is the whole point.
	std::vector<int> slot_count;

	// Size bad_x.size() * n_frames, indexed [ibad * n_frames + iframe] -- the
	// order in which the runner consumes the stream.
	std::vector<Draw> draws;

	// Observability: how many (pixel, frame) decisions took each branch. A test
	// that does not assert on these cannot tell whether it exercised the
	// Gaussian path at all.
	long long n_neighbor_draws = 0;
	long long n_gaussian_draws = 0;
};

// Consumes rand()/rnd_gaus() exactly as the runner's loop does, in the same
// order, so the process RNG ends in the same state. The caller must have
// already called init_random_generator() at the point the runner does; this
// function does not seed.
//
// NUM_MIN_OK is fixed at 6 to match the runner. d_max is 2, or 4 for EER.
bool buildSchedule(const bool *bad_mask, int nx, int ny, int n_frames, int d_max,
                   float frame_mean, float frame_std, Schedule &out);

// Geometric neighbour list for one bad pixel, in the runner's (dy, dx) scan
// order. Depends on bad_mask and the bounds only.
void neighborSlots(const bool *bad_mask, int nx, int ny, int d_max, int i, int j,
                   std::vector<int> &slot_y, std::vector<int> &slot_x);

// Applies the schedule to a contiguous ascending chunk of frames.
// frame_data[k] addresses frame (first_frame + k), nx*ny floats, row-major.
//
// Repair reads only non-masked neighbours and writes only masked pixels, so no
// repair ever reads another repair's output: the (pixel, frame) decisions are
// independent given the schedule, and any chunking of frames yields identical
// values. That property, not the loop order, is what makes staging admissible.
//
// When out_replacements is non-null it must be sized bad.size() * n_frames and
// is filled at [ibad * n_frames + iframe] for the frames in this chunk.
bool applyChunk(const Schedule &sched, const bool *bad_mask,
                int first_frame, int n_chunk_frames,
                float *const *frame_data,
                std::vector<float> *out_replacements);

} // namespace staging
} // namespace motioncorr

#endif // FRAME_STAGING_PLAN_H_
