// Standalone device EER renderer (#193 option 2, feasibility experiment).
// Not part of the main build and not used by src/.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cuda_runtime.h>

namespace eerdev {

// Per-fraction failure bits. A failed fraction means the whole movie is rejected.
enum : uint32_t {
	ERR_TRUNCATED     = 1u, // the strip ended before the frame's last run code
	ERR_RUN_PAST_END  = 2u, // the run codes overshoot the frame (host: warning + frame skipped)
	ERR_POSITION_RANGE = 4u // decoded position maps outside the output frame (guard, see --clamp)
};

struct DecodeParams {
	const uint8_t  *d_bytes;     // packed fractions; every slot 8-byte aligned and zero padded
	const uint64_t *d_slot_off;  // byte offset of each fraction's slot
	const uint32_t *d_slot_len;  // valid bytes in each slot
	int       nfrac;
	int       grouping;          // fractions per output frame
	int       detector;          // 2048 or 4096
	int       upsampling;        // -1, 1 or 2
	int       rle_bits;          // 7 or 8
	int       sym_bits;          // 4 or 2
	void     *d_frames;          // output frames (uint16 or float per out_float), zeroed by the caller
	int       out_float;         // 1: float counts (exact: integer adds), 0: uint16 counts
	int       rollback;          // 1: second pass, re-decode only failed fractions and subtract what they added (host skip semantics)
	int       f_base;            // global index of this launch's first fraction (group = (f_base + f) / grouping)
	uint64_t  max_pixel_index;   // pixel-index guard; normally the frame's pixel count
	uint32_t *d_err;             // per fraction of this launch
	uint32_t *d_nel;             // per fraction of this launch: electrons rendered
	int       block;             // threads per block (one fraction per thread)
};

// Output frame side in pixels, or -1 for a combination EERRenderer rejects or this experiment does not cover.
int frame_dim(int detector, int upsampling);

cudaError_t launch_decode(const DecodeParams &p, cudaStream_t stream);

} // namespace eerdev
