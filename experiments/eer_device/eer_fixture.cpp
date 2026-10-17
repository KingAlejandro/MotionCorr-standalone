#include "eer_fixture.h"
#include <cstdio>
#include <cstring>

namespace eerfix {

Layout layout_for(uint16_t c)
{
	if (c == 65000) return {8, 4, c};
	if (c == 65002) return {7, 2, c};
	return {7, 4, 65001};
}

namespace {
struct BitWriter {
	std::vector<uint8_t> out;
	uint64_t nbits = 0;
	void put(uint32_t v, int n) {
		for (int i = 0; i < n; i++, nbits++) {
			if ((nbits & 7) == 0) out.push_back(0);
			if ((v >> i) & 1u) out.back() |= (uint8_t)(1u << (nbits & 7));
		}
	}
};
}

std::vector<uint8_t> encode(const Layout &l, uint32_t total, const std::vector<Electron> &el,
                            uint32_t extra_overshoot, bool no_terminator)
{
	BitWriter bw;
	const uint32_t skip = (1u << l.rle_bits) - 1u;
	const uint32_t xm = (l.sym_bits == 4) ? 0x0Au : 0x03u;
	auto code = [&](uint32_t p, uint32_t s_stored, bool with_sym) {
		bw.put(p, l.rle_bits);
		if (with_sym) bw.put(s_stored, l.sym_bits);
	};
	// 7-bit skip codes have no symbol; 8-bit ones do.
	const bool skip_has_sym = (l.rle_bits == 8);
	uint32_t prev = 0;
	for (const Electron &e : el) {
		uint32_t g = e.pos - prev;
		while (g >= skip) { code(skip, 0, skip_has_sym); g -= skip; }
		code(g, e.sym ^ xm, true);
		prev = e.pos + 1;
	}
	if (!no_terminator) {
		uint32_t rem = total - prev + extra_overshoot;
		while (rem > skip) { code(skip, 0, skip_has_sym); rem -= skip; }
		code(rem, 0, true);
	}
	return bw.out;
}

bool decode(const Layout &l, uint32_t total, const uint8_t *b, size_t n, std::vector<Electron> &el)
{
	el.clear();
	uint64_t pos = 0, nbits = 8ull * n;
	auto get = [&](int k, uint32_t &v) {
		if (pos + k > nbits) return false;
		v = 0;
		for (int i = 0; i < k; i++, pos++) v |= (uint32_t)((b[pos >> 3] >> (pos & 7)) & 1u) << i;
		return true;
	};
	const uint32_t skip = (1u << l.rle_bits) - 1u;
	const uint32_t xm = (l.sym_bits == 4) ? 0x0Au : 0x03u;
	uint32_t npix = 0, p, s;
	for (;;) {
		if (!get(l.rle_bits, p)) return false;
		npix += p;
		if (npix >= total) return npix == total;
		if (l.rle_bits == 7 && p == skip) continue;
		if (!get(l.sym_bits, s)) return false;
		if (l.rle_bits == 8 && p == skip) continue;
		el.push_back({npix, s ^ xm});
		npix++;
	}
}

std::vector<Electron> random_electrons(Rng &r, uint32_t total, double density, int sym_bits, bool edges)
{
	std::vector<Electron> el;
	const uint32_t smax = (1u << sym_bits);
	uint64_t thr = (uint64_t)(density * 4294967296.0);
	for (uint32_t i = 0; i < total; i++) {
		const bool force = edges && (i == 0 || i == total - 1);
		if (force || (r.next() & 0xFFFFFFFFull) < thr) el.push_back({i, r.below(smax)});
	}
	return el;
}

namespace {
void w16(FILE *f, uint16_t v) { fwrite(&v, 2, 1, f); }
void w64(FILE *f, uint64_t v) { fwrite(&v, 8, 1, f); }
struct Ent { uint16_t tag, type; uint64_t count, value; };
}

bool write_eer(const std::string &path, int width, int height, uint16_t compression,
               const std::vector<std::vector<uint8_t>> &strips)
{
	FILE *f = fopen(path.c_str(), "wb");
	if (!f) return false;
	const bool detailed = (compression == 65002);
	const int nent = detailed ? 11 : 8;
	const uint64_t isz = 8 + 20ull * nent + 8;
	const uint64_t n = strips.size();
	const uint64_t strip0 = 16 + n * isz;
	fwrite("II", 1, 2, f); w16(f, 43); w16(f, 8); w16(f, 0); w64(f, 16);
	uint64_t so = strip0;
	for (uint64_t i = 0; i < n; i++) {
		std::vector<Ent> e = {
			{256, 4, 1, (uint64_t)width}, {257, 4, 1, (uint64_t)height}, {258, 3, 1, 8},
			{259, 3, 1, compression}, {273, 16, 1, so}, {277, 3, 1, 1},
			{278, 4, 1, (uint64_t)height}, {279, 16, 1, strips[i].size()}};
		if (detailed) { e.push_back({65007, 3, 1, 7}); e.push_back({65008, 3, 1, 1}); e.push_back({65009, 3, 1, 1}); }
		w64(f, e.size());
		for (const Ent &x : e) { w16(f, x.tag); w16(f, x.type); w64(f, x.count); w64(f, x.value); }
		w64(f, i + 1 < n ? 16 + (i + 1) * isz : 0);
		so += strips[i].size();
	}
	for (const auto &s : strips)
		if (!s.empty() && fwrite(s.data(), 1, s.size(), f) != s.size()) { fclose(f); return false; }
	return fclose(f) == 0;
}

} // namespace eerfix
