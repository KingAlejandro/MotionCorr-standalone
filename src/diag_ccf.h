// S1.3 DIAGNOSTIC ONLY (branch diag/s1-ccf-ties, never merged).
// Per-frame CCF peak records for CPU and CUDA patch alignment, written to the
// file named by MC_DIAG_CCF, and optional raw dumps of the CCF maps and their
// input spectra for the patches named by MC_DIAG_MAP_PATCHES ("iy,ix;iy,ix",
// 1-based; "g" = global) into the directory MC_DIAG_MAPS.
// Everything here reads values the alignment already computed. No alignment
// arithmetic, selection or control flow changes.
#ifndef MC_DIAG_CCF_H
#define MC_DIAG_CCF_H

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

// Patch label for the next alignment call: 0-based iy*patch_x+ix, -1 = global.
inline int g_diag_patch = -1;
inline int g_diag_patch_x = 1;
// First patch index of the current batched chunk.
inline int g_diag_batch_base = 0;

inline const char *diagCcfPath() { static const char *p = std::getenv("MC_DIAG_CCF"); return p; }
inline const char *diagMapDir() { static const char *p = std::getenv("MC_DIAG_MAPS"); return p; }

inline void diagPatchYX(int patch, int &iy, int &ix) {
	iy = patch < 0 ? 0 : patch / g_diag_patch_x + 1;
	ix = patch < 0 ? 0 : patch % g_diag_patch_x + 1;
}

// True when maps should be dumped for this patch label.
inline bool diagDumpMaps(int patch) {
	if (!diagMapDir()) return false;
	const char *list = std::getenv("MC_DIAG_MAP_PATCHES");
	if (!list) return false;
	int iy, ix; diagPatchYX(patch, iy, ix);
	const std::string want = patch < 0 ? std::string("g") : std::to_string(iy) + "," + std::to_string(ix);
	std::string s(list), tok;
	size_t a = 0;
	while (a <= s.size()) {
		size_t b = s.find(';', a);
		if (b == std::string::npos) b = s.size();
		if (s.substr(a, b - a) == want) return true;
		a = b + 1;
	}
	return false;
}

inline float diagCcfAt(const float *I, int ccf_nx, int ccf_ny, int sx, int sy) {
	int iy = ((sy % ccf_ny) + ccf_ny) % ccf_ny, ix = ((sx % ccf_nx) + ccf_nx) % ccf_nx;
	return I[(size_t)iy * ccf_nx + ix];
}

struct DiagCcfStat {
	float maxval = -1e30f;
	int cpu_x = 0, cpu_y = 0;    // first maximum in CPU search order (signed y, then x)
	int lane_x = 0, lane_y = 0;  // 256-lane strided strict '>' scan + tree reduction (production CUDA)
	int ties = 0;                // ordinals whose value == maxval exactly
	// Second peak: best 8-neighbour local maximum outside the 3x3 around the
	// selected peak (sel_x, sel_y).
	float second = -1e30f;
	int second_x = 0, second_y = 0;
	int n_local_max = 0;
	// Subpixel inputs at the selected peak.
	float sel = 0, vpx = 0, vnx = 0, vpy = 0, vny = 0;
};

// Same ordinal enumeration as findPeakAndInterpolateKernel and alignPatch.
// sel_* < -1e8 means "use the CPU-rule maximum".
inline DiagCcfStat diagCcfStat(const float *I, int ccf_nx, int ccf_ny, int search_range,
                               int sel_x, int sel_y, int lanes = 256) {
	DiagCcfStat s;
	const int range_len = 2 * search_range + 1, total = range_len * range_len;
	auto val = [&](int idx, int &sx, int &sy) {
		sy = idx / range_len - search_range; sx = idx % range_len - search_range;
		return diagCcfAt(I, ccf_nx, ccf_ny, sx, sy);
	};
	for (int idx = 0; idx < total; idx++) {
		int sx, sy; float v = val(idx, sx, sy);
		if (v > s.maxval) { s.maxval = v; s.cpu_x = sx; s.cpu_y = sy; }
	}
	std::vector<float> lm(lanes, -1e30f); std::vector<int> lx(lanes, 0), ly(lanes, 0);
	for (int t = 0; t < lanes; t++)
		for (int idx = t; idx < total; idx += lanes) {
			int sx, sy; float v = val(idx, sx, sy);
			if (v > lm[t]) { lm[t] = v; lx[t] = sx; ly[t] = sy; }
		}
	for (int stride = lanes / 2; stride > 0; stride >>= 1)
		for (int t = 0; t < stride; t++)
			if (lm[t + stride] > lm[t]) { lm[t] = lm[t + stride]; lx[t] = lx[t + stride]; ly[t] = ly[t + stride]; }
	s.lane_x = lx[0]; s.lane_y = ly[0];
	if (sel_x < -100000000) { sel_x = s.cpu_x; sel_y = s.cpu_y; }
	for (int idx = 0; idx < total; idx++) {
		int sx, sy; float v = val(idx, sx, sy);
		if (v == s.maxval) s.ties++;
		if (std::abs(sx - sel_x) <= 1 && std::abs(sy - sel_y) <= 1) continue;
		bool is_max = true;
		for (int dy = -1; dy <= 1 && is_max; dy++)
			for (int dx = -1; dx <= 1; dx++)
				if ((dx || dy) && diagCcfAt(I, ccf_nx, ccf_ny, sx + dx, sy + dy) > v) { is_max = false; break; }
		if (!is_max) continue;
		s.n_local_max++;
		if (v > s.second) { s.second = v; s.second_x = sx; s.second_y = sy; }
	}
	s.sel = diagCcfAt(I, ccf_nx, ccf_ny, sel_x, sel_y);
	s.vpx = diagCcfAt(I, ccf_nx, ccf_ny, sel_x + 1, sel_y);
	s.vnx = diagCcfAt(I, ccf_nx, ccf_ny, sel_x - 1, sel_y);
	s.vpy = diagCcfAt(I, ccf_nx, ccf_ny, sel_x, sel_y + 1);
	s.vny = diagCcfAt(I, ccf_nx, ccf_ny, sel_x, sel_y - 1);
	return s;
}

// One record per patch, iteration and frame. cur_x/cur_y are the backend's own
// per-frame candidate shift for this iteration, before re-referencing to frame 0.
inline void diagCcfWrite(const char *tag, int patch, int iter, int frame, const DiagCcfStat &s,
                         int sel_x, int sel_y, double cur_x, double cur_y, const char *note) {
	static std::mutex mu;
	std::lock_guard<std::mutex> lock(mu);
	FILE *f = std::fopen(diagCcfPath(), "a");
	if (!f) return;
	int iy, ix; diagPatchYX(patch, iy, ix);
	std::fprintf(f, "%s %d %d it %d fr %d sel %d %d max %.9g cpu %d %d lane %d %d ties %d "
	             "p2 %.9g %d %d nlm %d sub %.9g %.9g %.9g %.9g %.9g cur %.17g %.17g %s\n",
	             tag, iy, ix, iter, frame + 1, sel_x, sel_y, s.maxval, s.cpu_x, s.cpu_y, s.lane_x, s.lane_y,
	             s.ties, s.second, s.second_x, s.second_y, s.n_local_max,
	             s.sel, s.vpx, s.vnx, s.vpy, s.vny, cur_x, cur_y, note);
	std::fclose(f);
}

// S1.3b DIAGNOSTIC ONLY: global-trajectory capture and override.
// MC_DIAG_GLOBAL_SHIFTS_OUT=<file> writes the global trajectory exactly (%.17g).
// MC_DIAG_GLOBAL_SHIFTS=<file> (same format) replaces it: the frames receive an
// extra Fourier shift by (injected - own), frames with an exactly zero
// difference are left untouched, and the injected values are what the run
// records. Injecting a run's own file is therefore a no-op.
inline void diagGlobalShiftsOut(const std::vector<double> &x, const std::vector<double> &y) {
	const char *p = std::getenv("MC_DIAG_GLOBAL_SHIFTS_OUT");
	if (!p) return;
	if (FILE *f = std::fopen(p, "w")) {
		for (size_t i = 0; i < x.size(); i++) std::fprintf(f, "%zu %.17g %.17g\n", i + 1, x[i], y[i]);
		std::fclose(f);
	}
}
// Returns false when no override is requested. Fails loudly on a malformed file.
inline bool diagGlobalShiftsIn(size_t n, std::vector<double> &x, std::vector<double> &y) {
	const char *p = std::getenv("MC_DIAG_GLOBAL_SHIFTS");
	if (!p) return false;
	FILE *f = std::fopen(p, "r");
	if (!f) { std::fprintf(stderr, "MC_DIAG_GLOBAL_SHIFTS: cannot open %s\n", p); std::abort(); }
	x.assign(n, 0.0); y.assign(n, 0.0);
	size_t i, got = 0; double a, b;
	while (std::fscanf(f, "%zu %lf %lf", &i, &a, &b) == 3) {
		if (i < 1 || i > n) { std::fprintf(stderr, "MC_DIAG_GLOBAL_SHIFTS: frame %zu out of range\n", i); std::abort(); }
		x[i - 1] = a; y[i - 1] = b; got++;
	}
	std::fclose(f);
	if (got != n) { std::fprintf(stderr, "MC_DIAG_GLOBAL_SHIFTS: %zu rows for %zu frames\n", got, n); std::abort(); }
	return true;
}
// Defined in cuda_alignpatch.cu: the production fourierShiftKernel applied to a
// resident full-spectrum movie, frames 2..n, shift (dx, dy) px per frame.
void cudaDiagApplyGlobalDelta(void *d_Fframes, int n_frames, int nx, int ny, const double *dx, const double *dy);

// S1.3c DIAGNOSTIC ONLY: before a cuFFT C2R of a shifted half spectrum, project
// the kx = 0 and kx = nx/2 columns onto their Hermitian part,
// F(ky) <- (F(ky) + conj F(-ky)) / 2 (FFTW's effective treatment; #253).
// MC_DIAG_C2R_HERMITIAN_GLOBAL=1: global inverse FFT (cuda_movie_session.cu).
// MC_DIAG_C2R_HERMITIAN_DW=1: dose-weighted product C2R (cuda_realspace_dw.cu).
inline bool diagC2rHermitianGlobal() { static const bool on = std::getenv("MC_DIAG_C2R_HERMITIAN_GLOBAL") != nullptr; return on; }
inline bool diagC2rHermitianDw() { static const bool on = std::getenv("MC_DIAG_C2R_HERMITIAN_DW") != nullptr; return on; }
// Defined in cuda_alignpatch.cu; launched on the legacy default stream.
void cudaDiagHermitianEdgeColumns(void *d_half, int nx, int ny);

// S1.3c-null DIAGNOSTIC ONLY: a perturbation of h(y)'s size but not its shape.
// MC_DIAG_NULL_ROWS=<seed>: after the global inverse C2R and the DW product
// C2R, add sigma * s(y) to every pixel of row y, where s(y) = +-1 from a hash of
// (seed, site, frame, y) and sigma is the rms over rows of h(y) =
// -Im(sum_ky F(nx/2, ky) exp(2 pi i ky y / ny)), the row term cuFFT adds at
// 4096^2 (#253), computed from that frame's spectrum before the C2R.
inline unsigned diagNullSeed() { static const char *p = std::getenv("MC_DIAG_NULL_ROWS"); static const unsigned s = p ? (unsigned)std::strtoul(p, nullptr, 10) : 0u; return s; }
// Defined in cuda_alignpatch.cu (legacy default stream; synchronous).
float cudaDiagNyquistRowTermRms(const void *d_half, int nx, int ny);
void cudaDiagAddSignedRows(float *d_real, int nx, int ny, float sigma, unsigned seed, int site, int frame);

// Raw little-endian dumps: <dir>/<tag>_p<iy>_<ix>_c<call>_it<iter>_<kind>.bin
// kind "in": n_frames x ccf_nfy x ccf_nfx complex float, the CCF window of the
// spectra entering this iteration; "map": n_frames x ccf_ny x ccf_nx float;
// "wt": ccf_nfy x ccf_nfx float. An index line records the dimensions.
inline int diagNextCall() { static int c = 0; return ++c; }
inline void diagDumpRaw(const char *tag, int patch, int call, int iter, const char *kind,
                        const void *data, size_t bytes, int n_frames, int dim_y, int dim_x) {
	static std::mutex mu;
	std::lock_guard<std::mutex> lock(mu);
	int iy, ix; diagPatchYX(patch, iy, ix);
	char name[512];
	std::snprintf(name, sizeof(name), "%s/%s_p%d_%d_c%d_it%d_%s.bin", diagMapDir(), tag, iy, ix, call, iter, kind);
	if (FILE *f = std::fopen(name, "wb")) { std::fwrite(data, 1, bytes, f); std::fclose(f); }
	std::string idx = std::string(diagMapDir()) + "/index.txt";
	if (FILE *f = std::fopen(idx.c_str(), "a")) {
		std::fprintf(f, "%s %s %d %d %d %d %s %d %d %d\n", name, tag, iy, ix, call, iter, kind, n_frames, dim_y, dim_x);
		std::fclose(f);
	}
}

#endif
