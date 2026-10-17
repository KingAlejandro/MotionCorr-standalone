// One CUDA thread decodes one EER fraction (strip bytes) sequentially and scatters its
// electrons into the group's uint16 frame. The decode loop is a bit-for-bit transcription
// of the loops in src/renderEER.cpp (7+4, 7+2 and 8+4 bit layouts), except that every
// bit consumed is bounds-checked against the fraction's own byte length.
#include "eer_device.h"

namespace eerdev {

template <int DET, int UPS>
__device__ __forceinline__ bool target_pixel(uint32_t pos, uint32_t s, uint64_t &idx)
{
	uint32_t x, y;
	uint32_t W;
	if (DET == 4096) {
		const uint32_t x0 = pos & 4095u, y0 = pos >> 12;
		if (UPS == 2)       { x = (x0 << 1) | ((s & 2u) >> 1); y = (y0 << 1) | ((s & 8u) >> 3); W = 8192; }
		else if (UPS == -1) { x = x0 >> 1; y = y0 >> 1; W = 2048; }
		else                { x = x0; y = y0; W = 4096; }
	} else {
		const uint32_t x0 = pos & 2047u, y0 = pos >> 11;
		if (UPS == 2) { x = (x0 << 1) | (s & 1u); y = (y0 << 1) | (s >> 1); W = 4096; }
		else          { x = x0; y = y0; W = 2048; }
	}
	idx = (uint64_t)y * W + x;
	return y < W && x < W; // host DIRECT_A2D_ELEM has no such check
}

template <int RLE, int SYM, int DET, int UPS, bool FLT>
__global__ void decode_kernel(const DecodeParams p)
{
	constexpr uint32_t TOTAL = (uint32_t)DET * (uint32_t)DET;
	constexpr uint32_t SKIP  = (1u << RLE) - 1u;
	constexpr uint32_t XM    = (SYM == 4) ? 0x0Au : 0x03u;
	constexpr uint64_t W     = (DET == 4096) ? (UPS == 2 ? 8192 : UPS == -1 ? 2048 : 4096)
	                                         : (UPS == 2 ? 4096 : 2048);

	const int f = blockIdx.x * blockDim.x + threadIdx.x;
	if (f >= p.nfrac) return;
	const bool rb = p.rollback != 0;
	if (rb && p.d_err[f] == 0) return; // rollback pass touches failed fractions only

	const uint32_t *w = (const uint32_t *)(p.d_bytes + p.d_slot_off[f]);
	const uint64_t group = (uint64_t)((p.f_base + f) / p.grouping);
	unsigned int *out = (unsigned int *)p.d_frames + group * (W * W / 2);   // uint16 view: two pixels per word
	float *outf = (float *)p.d_frames + group * (W * W);                    // float view
	uint64_t remaining = 8ull * p.d_slot_len[f]; // bits of the strip not yet consumed
	uint64_t acc = 0;
	uint32_t nacc = 0, wi = 0;
	uint32_t npix = 0, nel = 0, err = 0;

	for (;;) {
		if (remaining < RLE) { err |= ERR_TRUNCATED; break; }
		if (nacc < RLE) { acc |= (uint64_t)w[wi++] << nacc; nacc += 32; }
		const uint32_t pr = (uint32_t)acc & ((1u << RLE) - 1u);
		acc >>= RLE; nacc -= RLE; remaining -= RLE;
		npix += pr;
		if (npix >= TOTAL) break;
		if (RLE == 7 && pr == SKIP) continue;      // 7-bit: a 127 run carries no symbol
		if (remaining < SYM) { err |= ERR_TRUNCATED; break; }
		if (nacc < SYM) { acc |= (uint64_t)w[wi++] << nacc; nacc += 32; }
		const uint32_t s = ((uint32_t)acc & ((1u << SYM) - 1u)) ^ XM;
		acc >>= SYM; nacc -= SYM; remaining -= SYM;
		if (RLE == 8 && pr == SKIP) continue;      // 8-bit: a 255 run still has its symbol, but no electron
		uint64_t idx;
		if (!target_pixel<DET, UPS>(npix, s, idx) || idx >= p.max_pixel_index) {
			err |= ERR_POSITION_RANGE; break;
		}
		// The rollback pass replays the same deterministic prefix with -1. Counts are integers (float adds of +-1 are exact),
		// and a pixel can only go back to 0 after this fraction added to it, so no borrow crosses the uint16 halves.
		if (FLT) atomicAdd(outf + idx, rb ? -1.0f : 1.0f);
		else     atomicAdd(out + (idx >> 1), rb ? (0u - (1u << ((uint32_t)(idx & 1u) << 4))) : (1u << ((uint32_t)(idx & 1u) << 4)));
		++nel; ++npix;
	}
	if (!err && npix != TOTAL) err |= ERR_RUN_PAST_END; // host: "frame is skipped"
	if (rb) { p.d_nel[f] = 0; return; } // a skipped fraction contributes nothing, as on the host
	p.d_err[f] = err;
	p.d_nel[f] = nel;
}

int frame_dim(int detector, int upsampling)
{
	if (detector == 4096) return upsampling == 1 ? 4096 : upsampling == 2 ? 8192 : upsampling == -1 ? 2048 : -1;
	if (detector == 2048) return upsampling == 1 ? 2048 : upsampling == 2 ? 4096 : -1;
	return -1;
}

template <int RLE, int SYM, int DET, int UPS>
static cudaError_t go(const DecodeParams &p, cudaStream_t s)
{
	const int grid = (p.nfrac + p.block - 1) / p.block;
	if (p.out_float) decode_kernel<RLE, SYM, DET, UPS, true><<<grid, p.block, 0, s>>>(p);
	else             decode_kernel<RLE, SYM, DET, UPS, false><<<grid, p.block, 0, s>>>(p);
	return cudaGetLastError();
}

template <int RLE, int SYM>
static cudaError_t by_mode(const DecodeParams &p, cudaStream_t s)
{
	if (p.detector == 4096) {
		if (p.upsampling == 1)  return go<RLE, SYM, 4096, 1>(p, s);
		if (p.upsampling == 2)  return go<RLE, SYM, 4096, 2>(p, s);
		if (p.upsampling == -1) return go<RLE, SYM, 4096, -1>(p, s);
	} else if (p.detector == 2048) {
		if (p.upsampling == 1) return go<RLE, SYM, 2048, 1>(p, s);
		if (p.upsampling == 2) return go<RLE, SYM, 2048, 2>(p, s);
	}
	return cudaErrorInvalidValue;
}

cudaError_t launch_decode(const DecodeParams &p, cudaStream_t stream)
{
	if (p.nfrac <= 0 || p.grouping <= 0 || p.block <= 0) return cudaErrorInvalidValue;
	if (p.rle_bits == 7 && p.sym_bits == 4) return by_mode<7, 4>(p, stream);
	if (p.rle_bits == 7 && p.sym_bits == 2) return by_mode<7, 2>(p, stream);
	if (p.rle_bits == 8 && p.sym_bits == 4) return by_mode<8, 4>(p, stream);
	return cudaErrorInvalidValue;
}

} // namespace eerdev
