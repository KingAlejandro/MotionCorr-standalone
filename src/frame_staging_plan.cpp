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
#include "src/frame_staging_plan.h"

#include "src/funcs.h"

#include <cstdlib>
#include <limits>

namespace motioncorr {
namespace staging {

namespace {

// Matches the runner's NUM_MIN_OK. Not configurable on purpose: a schedule that
// used a different threshold would silently produce a different RNG stream.
const int kNumMinOk = 6;

typedef unsigned long long u64;

const u64 kU64Max = std::numeric_limits<u64>::max();

bool mulChecked(u64 a, u64 b, u64 &out)
{
	if (a != 0 && b > kU64Max / a) return false;
	out = a * b;
	return true;
}

bool addChecked(u64 a, u64 b, u64 &out)
{
	if (a > kU64Max - b) return false;
	out = a + b;
	return true;
}

bool addInto(u64 &acc, u64 term)
{
	return addChecked(acc, term, acc);
}

// Multiply a list of factors with a check at every step.
bool mulAll(const u64 *factors, int n, u64 &out)
{
	u64 acc = 1;
	for (int i = 0; i < n; i++)
		if (!mulChecked(acc, factors[i], acc)) return false;
	out = acc;
	return true;
}

bool geometryOk(const Geometry &geom)
{
	return geom.nx > 0 && geom.ny > 0 && geom.n_frames > 0;
}

} // namespace

bool realStackBytes(const Geometry &geom, unsigned long long &out)
{
	if (!geometryOk(geom)) return false;
	const u64 f[4] = {4ull, (u64)geom.n_frames, (u64)geom.nx, (u64)geom.ny};
	return mulAll(f, 4, out);
}

bool fourierStackBytes(const Geometry &geom, unsigned long long &out)
{
	if (!geometryOk(geom)) return false;
	const u64 nfx = (u64)(geom.nx / 2) + 1ull;
	const u64 f[4] = {8ull, (u64)geom.n_frames, (u64)geom.ny, nfx};
	return mulAll(f, 4, out);
}

bool computeBudget(const Geometry &geom, const Policy &policy, Budget &budget)
{
	budget = Budget();

	if (!geometryOk(geom)) {
		budget.error = "invalid geometry: nx, ny and n_frames must be positive";
		return false;
	}
	if (policy.chunk_frames < 0) {
		budget.error = "invalid policy: chunk_frames must not be negative";
		return false;
	}
	if (policy.input_passes < 1) {
		budget.error = "invalid policy: input_passes must be at least 1";
		return false;
	}
	if (policy.staged_bytes_per_sample < 1) {
		budget.error = "invalid policy: staged_bytes_per_sample must be at least 1";
		return false;
	}
	if (policy.extra_host_bytes < 0 || policy.extra_device_bytes < 0) {
		budget.error = "invalid policy: extra byte terms must not be negative";
		return false;
	}

	// chunk_frames == 0, or any value at or above the frame count, means the
	// whole movie is staged at once -- which is exactly today's behaviour and
	// must produce today's numbers rather than a special case.
	u64 chunk = (policy.chunk_frames == 0)
	          ? (u64)geom.n_frames
	          : (u64)policy.chunk_frames;
	if (chunk > (u64)geom.n_frames) chunk = (u64)geom.n_frames;

	u64 real_stack = 0, fourier_stack = 0;
	if (!realStackBytes(geom, real_stack) || !fourierStackBytes(geom, fourier_stack)) {
		budget.error = "overflow computing whole-movie stack bytes";
		return false;
	}

	// Staged term: chunk_frames frames of nx*ny samples, at the staged sample
	// width. This is the only term the declared bound covers.
	{
		const u64 f[4] = {(u64)policy.staged_bytes_per_sample, chunk,
		                  (u64)geom.nx, (u64)geom.ny};
		if (!mulAll(f, 4, budget.staged_host_bytes)) {
			budget.error = "overflow computing staged host bytes";
			return false;
		}
	}

	// Whole-movie host terms that the policy keeps.
	u64 resident = 0;
	if (policy.retain_host_real_stack && !addInto(resident, real_stack)) {
		budget.error = "overflow accumulating resident host bytes";
		return false;
	}
	if (policy.retain_host_aligned_stack && !addInto(resident, real_stack)) {
		budget.error = "overflow accumulating resident host bytes";
		return false;
	}
	if (policy.retain_host_fourier_stack && !addInto(resident, fourier_stack)) {
		budget.error = "overflow accumulating resident host bytes";
		return false;
	}
	budget.resident_host_bytes = resident;

	u64 host = 0;
	if (!addInto(host, budget.staged_host_bytes) ||
	    !addInto(host, resident) ||
	    !addInto(host, (u64)policy.extra_host_bytes)) {
		budget.error = "overflow accumulating host bytes";
		return false;
	}
	budget.host_bytes = host;

	u64 device = (u64)policy.extra_device_bytes;
	if (policy.device_resident) {
		if (!addInto(device, real_stack) || !addInto(device, fourier_stack)) {
			budget.error = "overflow accumulating device bytes";
			return false;
		}
	}
	budget.device_bytes = device;

	// Transfer volume. One upload of every staged sample per input pass when a
	// device is in play; the D2H term is the unaligned sum only, because on the
	// resident path the frames themselves never come back. A design that adds a
	// full-movie download has to say so by raising extra terms -- it cannot hide
	// here.
	if (policy.device_resident) {
		const u64 f[4] = {(u64)policy.staged_bytes_per_sample, (u64)geom.n_frames,
		                  (u64)geom.nx, (u64)geom.ny};
		u64 per_pass = 0;
		if (!mulAll(f, 4, per_pass) ||
		    !mulChecked(per_pass, (u64)policy.input_passes, budget.h2d_bytes)) {
			budget.error = "overflow computing host-to-device bytes";
			return false;
		}
		const u64 g[3] = {4ull, (u64)geom.nx, (u64)geom.ny};
		if (!mulAll(g, 3, budget.d2h_bytes)) {
			budget.error = "overflow computing device-to-host bytes";
			return false;
		}
	}

	budget.input_passes = policy.input_passes;
	budget.valid = true;
	budget.error = nullptr;
	return true;
}

namespace {

// The single definition of the runner's neighbour scan: (dy, dx) ascending,
// skipping out-of-bounds and masked cells. Slot k emitted here is pbuf[k] in
// motioncorr_runner.cpp:1741. Both the count and the coordinate list go through
// this, so the two cannot drift apart.
template <typename Visit>
inline void forEachSlot(const bool *bad_mask, int nx, int ny, int d_max,
                        int i, int j, Visit visit)
{
	for (int dy = -d_max; dy <= d_max; dy++) {
		const int y = i + dy;
		if (y < 0 || y >= ny) continue;
		for (int dx = -d_max; dx <= d_max; dx++) {
			const int x = j + dx;
			if (x < 0 || x >= nx) continue;
			if (bad_mask[(size_t)y * nx + x]) continue;
			visit(y, x);
		}
	}
}

// n_ok for one bad pixel, without materialising the slot list.
int countSlots(const bool *bad_mask, int nx, int ny, int d_max, int i, int j)
{
	int n_ok = 0;
	forEachSlot(bad_mask, nx, ny, d_max, i, j, [&](int, int) { n_ok++; });
	return n_ok;
}

} // namespace

bool largestChunkWithin(const Geometry &geom, const Policy &policy,
                        unsigned long long host_budget_bytes,
                        long long &out_chunk)
{
	if (!geometryOk(geom)) return false;

	// The staged term is linear in the chunk and every other term is constant,
	// so binary search is sound. It is used rather than a closed-form divide
	// because computeBudget owns the overflow checks and the term list, and a
	// second copy of that arithmetic here is exactly how the two drift apart.
	Policy probe = policy;
	long long lo = 1, hi = geom.n_frames, best = 0;

	probe.chunk_frames = 1;
	Budget b;
	if (!computeBudget(geom, probe, b) || b.host_bytes > host_budget_bytes)
		return false; // inadmissible: not even one staged frame fits

	while (lo <= hi) {
		const long long mid = lo + (hi - lo) / 2;
		probe.chunk_frames = mid;
		if (computeBudget(geom, probe, b) && b.host_bytes <= host_budget_bytes) {
			best = mid;
			lo = mid + 1;
		} else {
			hi = mid - 1;
		}
	}

	if (best < 1) return false;
	out_chunk = best;
	return true;
}

void neighborSlots(const bool *bad_mask, int nx, int ny, int d_max, int i, int j,
                   std::vector<int> &slot_y, std::vector<int> &slot_x)
{
	slot_y.clear();
	slot_x.clear();
	forEachSlot(bad_mask, nx, ny, d_max, i, j, [&](int y, int x) {
		slot_y.push_back(y);
		slot_x.push_back(x);
	});
}

bool buildSchedule(const bool *bad_mask, int nx, int ny, int n_frames, int d_max,
                   float frame_mean, float frame_std, Schedule &out)
{
	out = Schedule();
	if (!bad_mask || nx <= 0 || ny <= 0 || n_frames <= 0 || d_max < 0) return false;
	// The runner's D_MAX is `isEER ? 4 : 2` and its pbuf is a fixed 100 entries
	// (motioncorr_runner.cpp:1525, :1737). Refuse anything the runner could not
	// itself produce rather than silently modelling a wider neighbourhood.
	if (d_max > 4) return false;

	out.nx = nx;
	out.ny = ny;
	out.n_frames = n_frames;
	out.d_max = d_max;

	// Raster order, matching FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY2D over bBad.
	for (int i = 0; i < ny; i++)
		for (int j = 0; j < nx; j++)
			if (bad_mask[(size_t)i * nx + j]) {
				out.bad_y.push_back(i);
				out.bad_x.push_back(j);
			}

	const size_t n_bad = out.bad_x.size();
	out.slot_count.resize(n_bad);

	// Guard the product before reserving; a pathological mask on a large movie
	// would otherwise overflow size_t on 32-bit or allocate silently here.
	if (n_bad != 0 &&
	    (size_t)n_frames > std::numeric_limits<size_t>::max() / n_bad / sizeof(Draw)) {
		// Leave nothing half-populated behind: a caller that ignores the return
		// value must not find a Schedule with a plausible geometry and no draws.
		out = Schedule();
		return false;
	}
	out.draws.resize(n_bad * (size_t)n_frames);

	// One pass in exactly the runner's (bad pixel, frame) order. Every rand()
	// and rnd_gaus() below lands at the same position in the stream as the
	// corresponding call in the runner, so the process RNG ends identically.
	// No pixel value is read.
	for (size_t ibad = 0; ibad < n_bad; ibad++) {
		const int n_ok = countSlots(bad_mask, nx, ny, d_max, out.bad_y[ibad], out.bad_x[ibad]);
		out.slot_count[ibad] = n_ok;

		for (int iframe = 0; iframe < n_frames; iframe++) {
			Draw &d = out.draws[ibad * (size_t)n_frames + iframe];
			if (n_ok > kNumMinOk) {
				d.kind = DrawKind::NeighborSlot;
				d.slot = rand() % n_ok;
				d.value = 0.0f;
				out.n_neighbor_draws++;
			} else {
				d.kind = DrawKind::GaussianValue;
				d.slot = -1;
				// Call the real generator rather than reimplementing Box-Muller:
				// rnd_gaus() caches its second deviate across calls and returns
				// mu without consuming the stream when sigma == 0, and a
				// reimplementation would have to reproduce both to stay in step.
				d.value = rnd_gaus(frame_mean, frame_std);
				out.n_gaussian_draws++;
			}
		}
	}

	return true;
}

bool applyChunk(const Schedule &sched, const bool *bad_mask,
                int first_frame, int n_chunk_frames,
                float *const *frame_data,
                const float *gain,
                bool write_in_place,
                std::vector<float> *out_replacements)
{
	if (!bad_mask || !frame_data) return false;
	if (first_frame < 0 || n_chunk_frames < 0) return false;
	if (first_frame > sched.n_frames - n_chunk_frames) return false;
	// Recording is the only effect when the frames are left raw; a caller that
	// asks for neither has asked for nothing and is more likely mistaken than
	// deliberate.
	if (!write_in_place && !out_replacements) return false;

	const size_t n_bad = sched.bad_x.size();
	if (sched.bad_y.size() != n_bad) return false;
	if (sched.slot_count.size() != n_bad) return false;
	if (sched.draws.size() != n_bad * (size_t)sched.n_frames) return false;
	if (out_replacements && out_replacements->size() != n_bad * (size_t)sched.n_frames)
		return false;

	const int nx = sched.nx, ny = sched.ny;
	std::vector<int> slot_y, slot_x;

	for (size_t ibad = 0; ibad < n_bad; ibad++) {
		const int i = sched.bad_y[ibad], j = sched.bad_x[ibad];
		const int n_ok = sched.slot_count[ibad];

		// Only the neighbour branch needs the coordinate list.
		bool need_slots = false;
		for (int k = 0; k < n_chunk_frames && !need_slots; k++)
			need_slots = sched.draws[ibad * (size_t)sched.n_frames + first_frame + k].kind
			           == DrawKind::NeighborSlot;
		if (need_slots) {
			neighborSlots(bad_mask, nx, ny, sched.d_max, i, j, slot_y, slot_x);
			if ((int)slot_y.size() != n_ok) return false; // mask changed since build
		}

		for (int k = 0; k < n_chunk_frames; k++) {
			const int iframe = first_frame + k;
			const Draw &d = sched.draws[ibad * (size_t)sched.n_frames + iframe];

			float replacement;
			if (d.kind == DrawKind::NeighborSlot) {
				if (d.slot < 0 || d.slot >= n_ok) return false;
				const size_t off = (size_t)slot_y[d.slot] * nx + slot_x[d.slot];
				replacement = frame_data[k][off];
				// motioncorr_runner.cpp:1752: raw host frames are multiplied by
				// the gain as each neighbour is gathered, one float multiply,
				// after n_ok has already been incremented.
				if (gain) replacement *= gain[off];
			} else {
				replacement = d.value;
			}

			if (write_in_place) frame_data[k][(size_t)i * nx + j] = replacement;
			// Frame-major, matching resident_bad_replacements and all three of
			// its consumers. Not the layout of Schedule::draws.
			if (out_replacements)
				(*out_replacements)[(size_t)iframe * n_bad + ibad] = replacement;
		}
	}

	return true;
}

} // namespace staging
} // namespace motioncorr
