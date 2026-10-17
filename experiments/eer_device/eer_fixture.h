// Synthetic EER fixtures: BigTIFF writer and stream encoders for the 65000/65001/65002 layouts.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace eerfix {

struct Rng {
	uint64_t s;
	explicit Rng(uint64_t seed) : s(seed) {}
	uint64_t next() { // splitmix64
		uint64_t z = (s += 0x9E3779B97F4A7C15ull);
		z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
		z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
		return z ^ (z >> 31);
	}
	uint32_t below(uint32_t n) { return (uint32_t)(next() % n); }
};

struct Electron { uint32_t pos; uint32_t sym; }; // sym is the logical symbol (after the xor)

struct Layout { int rle_bits; int sym_bits; uint16_t compression; };
Layout layout_for(uint16_t compression);

// Encode strictly increasing electron positions into one fraction's strip bytes.
// extra_overshoot > 0 appends run codes that push n_pix that many pixels past the frame.
// no_terminator omits the code that closes the frame (only meaningful when the last electron is at total-1).
std::vector<uint8_t> encode(const Layout &l, uint32_t total, const std::vector<Electron> &el,
                            uint32_t extra_overshoot = 0, bool no_terminator = false);

// Decode a 7+4 / 7+2 / 8+4 strip with the host renderer's loop (reference for crafting only).
// Returns false if the stream does not close the frame.
bool decode(const Layout &l, uint32_t total, const uint8_t *b, size_t n, std::vector<Electron> &el);

// Random electrons at the given density, always including pixel 0 and total-1 when `edges`.
std::vector<Electron> random_electrons(Rng &r, uint32_t total, double density, int sym_bits, bool edges);

// Write a BigTIFF with one strip per directory, directories first, strips after.
bool write_eer(const std::string &path, int width, int height, uint16_t compression,
               const std::vector<std::vector<uint8_t>> &strips);

} // namespace eerfix
