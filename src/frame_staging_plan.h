/***************************************************************************
 *
 * Author: "MotionCorr Standalone contributors"
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/
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

	// Defect pixels the component's OWN repair schedule will hold. buildSchedule
	// allocates bad_x, bad_y, slot_count and, dominating all of them,
	// n_bad * n_frames Draw objects. That is a host allocation this component
	// makes, so omitting it from this component's own budget is exactly the
	// error the budget exists to prevent: with a dense mask n_bad approaches
	// W*H, and a job admitted as O(C*W*H) then allocates O(F*W*H). Found by
	// review; see ADR section 7a.4.
	//
	//   0                     no schedule is built. Today's runner has none,
	//                         so this is the default and reproduces its numbers.
	//   kAllPixelsDefective   worst case: every pixel is a defect.
	//   n > 0                 a declared upper bound.
	//
	// n_bad is NOT knowable at admission: it comes out of hot-pixel detection,
	// which needs the completed sum pass. A staged design must therefore either
	// charge a bound here or re-check after detection. That is a real cost of
	// staging and is argued in the ADR, not hidden.
	long long schedule_defect_pixels = 0;

	// Whether applyChunk's out_replacements buffer is allocated too
	// (n_bad * n_frames floats). Required by the raw-host device path, which
	// records rather than writes.
	bool schedule_records_replacements = false;
};

// Sentinel for Policy::schedule_defect_pixels meaning "every pixel".
const long long kAllPixelsDefective = -1;

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

	// The component's own repair-schedule bookkeeping.
	unsigned long long schedule_host_bytes = 0;

	// True when the staged buffer and the retained real stack are the SAME
	// allocation, so host_bytes charges them once. This happens exactly when
	// the whole movie is staged as decoded floats and the real stack is kept:
	// the runner decodes straight into Iframes (motioncorr_runner.cpp:1409) and
	// never makes a separate staging copy. When this is true,
	// staged_host_bytes + resident_host_bytes DELIBERATELY exceeds host_bytes.
	bool staged_aliases_resident = false;

	unsigned long long h2d_bytes = 0;
	unsigned long long d2h_bytes = 0;

	// Decodes of the encoded input, end to end.
	int input_passes = 0;
};

// Returns false and fills budget.error on any overflow or invalid geometry.
// All products are checked; nothing is computed in a type that could wrap.
bool computeBudget(const Geometry &geom, const Policy &policy, Budget &budget);

// Three-way admission, not two. Adopted from #94's movieio::ByteBudget: a
// calculator that only answers "how many bytes" will happily recommend a chunk
// that can never fit, and evidence that only records success cannot tell "the
// bound held" from "the bound was overridden". This answers the first of the
// three budget outcomes -- inadmissible -- explicitly; waiting for capacity and
// granting over budget (#94's `over_budget_grants`) belong to the caller's
// allocator, not here.
enum class Admission {
	// out_chunk is the largest chunk_frames in [1, n_frames] that fits.
	Fits = 0,
	// Inputs were valid; not even one staged frame fits. This movie can never
	// be admitted under this budget and the caller must fall back or fail.
	Inadmissible,
	// The geometry or policy is malformed. out_error says which. This is a
	// caller bug, NOT a statement about the movie or the budget.
	InvalidInput,
};

// Finds the largest chunk_frames whose resulting host_bytes fits within
// host_budget_bytes, using `policy` for every other term.
//
// The return is tri-state on purpose. Collapsing InvalidInput into
// Inadmissible is the same mistake, one layer up, that this function exists to
// prevent: a caller that mapped both onto "movie exceeds the host budget" would
// log a correct-looking budget decision for every movie on a machine with
// terabytes free, and the misconfiguration would be undiagnosable. Found by
// independent review of an earlier bool-returning version.
//
// out_chunk is written only on Fits. out_error, when non-null, is set to a
// static string on InvalidInput and to nullptr otherwise.
//
// policy.chunk_frames is IGNORED -- this function is choosing that value. A
// negative one is still rejected as InvalidInput rather than quietly accepted,
// so a malformed policy does not become valid by being passed here.
//
// For multiple concurrent workers the caller must divide the host budget by the
// worker count BEFORE calling this. See ADR section 7a.2: sizing each worker
// against the whole host is the failure mode the aggregate bound exists to
// prevent, and nothing here can detect it.
//
// Monotonicity, checked by a test rather than left as prose. host_bytes is
// non-decreasing in chunk_frames on [1, n_frames-1], which is what makes the
// binary search sound. It is NOT monotone across the whole range: when the
// policy aliases (see Budget::staged_aliases_resident) host_bytes DROPS at
// chunk == n_frames, because the staged ring and the retained stack collapse
// into one allocation. This function therefore evaluates chunk == n_frames
// first and only searches [1, n_frames-1]. MonotonicHostBytes asserts both
// halves -- the monotone interval and the alias drop -- so neither can regress
// unnoticed.
Admission largestChunkWithin(const Geometry &geom, const Policy &policy,
                             unsigned long long host_budget_bytes,
                             long long &out_chunk,
                             const char **out_error = nullptr);

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
//           neighbor = Iframes[iframe](y, x);
//           if (host_frames_are_raw && gain) neighbor *= Igain(y, x);   // :1752
//           pbuf[n_ok++] = neighbor;
//       replacement = (n_ok > NUM_MIN_OK) ? pbuf[rand() % n_ok]
//                                         : rnd_gaus(frame_mean, frame_std);
//       if (host_frames_are_raw)                                        // :1769
//           resident_bad_replacements[iframe * n_bad + bad_idx] = replacement;
//       else
//           Iframes[iframe](i, j) = replacement;
//
// The gain multiply and the record-instead-of-write branch are reproduced above
// deliberately: an earlier draft of this comment omitted them, and a mirror
// checked against an abridged transcription proves nothing. applyChunk() takes
// both as explicit parameters.
//
// n_ok counts in-bounds, non-masked neighbours. It reads bBad and the image
// bounds only -- never a pixel value -- so it is identical for every frame. The
// gain multiply happens after n_ok is incremented and cannot reach the branch or
// the draw count. Both the branch taken and the number of random draws consumed
// are therefore fixed by (bad_mask, frame_std) alone.

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
	// order in which the runner *draws* from the RNG. Note this is NOT the
	// layout of the replacement buffer, which is frame-major; see applyChunk.
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
// NUM_MIN_OK is fixed at 6 to match the runner. d_max is 2, or 4 for EER; a
// larger value is rejected, because the runner's D_MAX is `isEER ? 4 : 2` and
// its pbuf is a fixed 100 entries.
//
// Returns false without leaving a partially populated Schedule.
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
// `gain`, when non-null, is a nx*ny gain reference applied to each neighbour
// value as it is gathered, reproducing motioncorr_runner.cpp:1752. Pass it
// exactly when the caller's frames are raw and a gain reference is in use --
// i.e. the runner's `host_frames_are_raw && fn_gain_reference != ""`. Pass null
// when the frames are already gain-corrected. Getting this wrong changes every
// replacement value by a factor of Igain(y, x) and nothing will complain.
//
// `write_in_place` writes the replacement into the masked pixel. Pass false to
// reproduce the runner's raw-host path, which records the value and leaves the
// raw frame untouched so a later whole-frame gain pass is still valid
// (motioncorr_runner.cpp:1769). With false, out_replacements must be non-null.
//
// On failure this function is NOT atomic: it returns false from inside the
// bad-pixel loop, so masked pixels already visited may have been written to
// `frame_data` and to `out_replacements`. A caller must not treat false as
// "nothing happened and I can retry"; the chunk's frames have to be re-staged.
//
// When out_replacements is non-null it must be sized bad.size() * n_frames and
// is filled at **[iframe * n_bad + ibad]** -- frame-major, matching
// `resident_bad_replacements` and every one of its consumers
// (motioncorr_runner.cpp:1770 and :1456, cuda_movie_session.cu:166). This is
// deliberately NOT the same layout as Schedule::draws.
bool applyChunk(const Schedule &sched, const bool *bad_mask,
                int first_frame, int n_chunk_frames,
                float *const *frame_data,
                const float *gain,
                bool write_in_place,
                std::vector<float> *out_replacements);

} // namespace staging
} // namespace motioncorr

#endif // FRAME_STAGING_PLAN_H_
