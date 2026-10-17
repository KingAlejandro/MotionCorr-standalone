// Standalone feasibility driver for a device EER renderer (#193 option 2).
// Subcommands: compare, dev-frames, host-frames, fixtures. See README.md.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <map>
#include <omp.h>
#include <sched.h>
#include <sstream>
#include <string>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include <cuda_runtime.h>
#include <tiffio.h>

#include "eer_device.h"
#include "eer_fixture.h"
#include "src/renderEER.h"

// ---------------------------------------------------------------- utilities
#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { \
	fprintf(stderr, "CUDA error %s at %s:%d: %s\n", cudaGetErrorName(e_), __FILE__, __LINE__, cudaGetErrorString(e_)); exit(3); } } while (0)

static double now_s() {
	return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static double self_cpu_s() {
	rusage r; getrusage(RUSAGE_SELF, &r);
	return r.ru_utime.tv_sec + r.ru_utime.tv_usec * 1e-6 + r.ru_stime.tv_sec + r.ru_stime.tv_usec * 1e-6;
}
static std::vector<int> allowed_cpus() {
	cpu_set_t s; CPU_ZERO(&s); sched_getaffinity(0, sizeof(s), &s);
	std::vector<int> v;
	for (int i = 0; i < CPU_SETSIZE; i++) if (CPU_ISSET(i, &s)) v.push_back(i);
	return v;
}
// busy seconds (everything except idle and iowait) summed over the given CPUs, from /proc/stat
static double cpus_busy_s(const std::vector<int> &cpus) {
	std::ifstream f("/proc/stat");
	std::string line; double busy = 0;
	const long hz = sysconf(_SC_CLK_TCK);
	while (std::getline(f, line)) {
		if (line.compare(0, 3, "cpu") != 0 || line.size() < 4 || line[3] == ' ') continue;
		int id = atoi(line.c_str() + 3);
		if (std::find(cpus.begin(), cpus.end(), id) == cpus.end()) continue;
		std::istringstream is(line.substr(line.find(' ')));
		unsigned long long u = 0, n = 0, s = 0, idle = 0, iow = 0, irq = 0, sirq = 0, steal = 0;
		is >> u >> n >> s >> idle >> iow >> irq >> sirq >> steal;
		busy += (double)(u + n + s + irq + sirq + steal) / hz;
	}
	return busy;
}
struct Meter { // wall, own CPU, foreign CPU on the allowed set, over a section
	std::vector<int> cpus; double w0, c0, b0;
	void start() { cpus = allowed_cpus(); w0 = now_s(); c0 = self_cpu_s(); b0 = cpus_busy_s(cpus); }
	void stop(double &wall, double &own_cpu, double &foreign_cores) {
		double w1 = now_s(), c1 = self_cpu_s(), b1 = cpus_busy_s(cpus);
		wall = w1 - w0; own_cpu = c1 - c0;
		foreign_cores = std::max(0.0, ((b1 - b0) - own_cpu) / std::max(wall, 1e-9));
	}
};

struct Stats { std::vector<double> v;
	void add(double x) { v.push_back(x); }
	double med() const { std::vector<double> s = v; std::sort(s.begin(), s.end()); size_t n = s.size();
		return n ? (n % 2 ? s[n / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2])) : 0; }
	double lo() const { return v.empty() ? 0 : *std::min_element(v.begin(), v.end()); }
	double hi() const { return v.empty() ? 0 : *std::max_element(v.begin(), v.end()); }
	std::string json() const { char b[256]; snprintf(b, sizeof b, "{\"n\":%zu,\"median\":%.6g,\"min\":%.6g,\"max\":%.6g,\"values\":[", v.size(), med(), lo(), hi());
		std::string s = b; for (size_t i = 0; i < v.size(); i++) { snprintf(b, sizeof b, "%s%.6g", i ? "," : "", v[i]); s += b; } return s + "]}"; }
};

struct Opts { std::map<std::string, std::string> kv;
	Opts(int argc, char **argv, int from) { for (int i = from; i < argc; i++) { std::string a = argv[i];
		if (a.rfind("--", 0) != 0) { fprintf(stderr, "bad arg %s\n", a.c_str()); exit(2); }
		a = a.substr(2); if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) kv[a] = argv[++i]; else kv[a] = "1"; } }
	std::string s(const char *k, const char *d = "") const { auto it = kv.find(k); return it == kv.end() ? d : it->second; }
	long l(const char *k, long d) const { auto it = kv.find(k); return it == kv.end() ? d : atol(it->second.c_str()); }
};

static std::string json_esc(const std::string &s) { std::string o; for (char c : s) { if (c == '"' || c == '\\') o += '\\'; if ((unsigned char)c >= 32) o += c; else o += ' '; } return o; }

// ---------------------------------------------------------------- TIFF index (LibTIFF, like EERRenderer::read)
struct Seg { uint64_t off, len; };
struct MovieIndex {
	int width = 0, height = 0, rle_bits = 0, sym_bits = 0, nframes = 0;
	uint16_t compression = 0;
	uint64_t file_size = 0;
	std::vector<Seg> segs;
	std::vector<uint32_t> seg_begin;   // per fraction, index into segs; size nframes + 1
	std::vector<uint64_t> frac_len;    // bytes per fraction (all strips)
};
static std::string g_tiff_err;
static void tiff_err_handler(const char *mod, const char *fmt, va_list ap) {
	char b[512]; vsnprintf(b, sizeof b, fmt, ap); g_tiff_err = std::string(mod ? mod : "") + ": " + b;
}
static void tiff_warn_handler(const char *, const char *, va_list) {}

// Same format checks as EERRenderer::read(), plus the checks the host skips (every directory
// must agree with the first, every strip must lie inside the file, the directory walk must be complete).
static bool parse_index(const std::string &path, int ups, MovieIndex &mi, std::string &err)
{
	TIFFSetErrorHandler(tiff_err_handler); TIFFSetWarningHandler(tiff_warn_handler);
	struct stat st;
	if (stat(path.c_str(), &st) != 0) { err = "cannot stat " + path; return false; }
	mi = MovieIndex(); mi.file_size = st.st_size;
	TIFF *cnt = TIFFOpen(path.c_str(), "r");
	if (!cnt) { err = "not a TIFF container (legacy EER is not covered by this experiment): " + g_tiff_err; return false; }
	const int expected = (int)TIFFNumberOfDirectories(cnt);
	TIFFClose(cnt);
	TIFF *t = TIFFOpen(path.c_str(), "r");
	if (!t) { err = "TIFFOpen failed"; return false; }
	uint32_t w = 0, h = 0; uint16_t c = 0;
	TIFFGetField(t, TIFFTAG_IMAGEWIDTH, &w); TIFFGetField(t, TIFFTAG_IMAGELENGTH, &h); TIFFGetField(t, TIFFTAG_COMPRESSION, &c);
	mi.width = w; mi.height = h; mi.compression = c;
	if (c == 65000) { mi.rle_bits = 8; mi.sym_bits = 4; }
	else if (c == 65001) { mi.rle_bits = 7; mi.sym_bits = 4; }
	else if (c == 65002) {
		uint32_t count; uint16_t *rle = nullptr, *sh = nullptr, *sv = nullptr;
		if (!TIFFGetField(t, 65007, &count, (void *)&rle) || !rle || !TIFFGetField(t, 65008, &count, (void *)&sh) || !sh) {
			err = "65002 without the EER depth tags"; TIFFClose(t); return false; }
		if (!TIFFGetField(t, 65009, &count, (void *)&sv) || !sv) sv = sh;
		if (*rle != 7 || *sh != *sv || *sh != 1) { err = "unsupported 65002 depths"; TIFFClose(t); return false; }
		mi.rle_bits = 7; mi.sym_bits = 1 << *sh;
		if (mi.sym_bits == 2 && (ups == -1 || ups >= 3)) { err = "sym_bits 2 needs upsampling 1 or 2"; TIFFClose(t); return false; }
	} else { err = "unknown EER compression " + std::to_string(c); TIFFClose(t); return false; }
	if (mi.width != mi.height || (mi.width != 4096 && mi.width != 2048)) { err = "only 4096x4096 or 2048x2048 EER"; TIFFClose(t); return false; }
	int n = 0;
	do {
		uint32_t w2 = 0, h2 = 0; uint16_t c2 = 0;
		TIFFGetField(t, TIFFTAG_IMAGEWIDTH, &w2); TIFFGetField(t, TIFFTAG_IMAGELENGTH, &h2); TIFFGetField(t, TIFFTAG_COMPRESSION, &c2);
		if ((int)w2 != mi.width || (int)h2 != mi.height || c2 != mi.compression) { err = "directory " + std::to_string(n) + " disagrees with directory 0"; TIFFClose(t); return false; }
		const uint32_t ns = TIFFNumberOfStrips(t);
		uint64_t *offs = nullptr, *bcs = nullptr;
		if (!TIFFGetField(t, TIFFTAG_STRIPOFFSETS, &offs) || !TIFFGetField(t, TIFFTAG_STRIPBYTECOUNTS, &bcs) || !offs || !bcs) {
			err = "directory " + std::to_string(n) + " has no strip table"; TIFFClose(t); return false; }
		mi.seg_begin.push_back((uint32_t)mi.segs.size());
		uint64_t tot = 0;
		for (uint32_t s = 0; s < ns; s++) {
			if (offs[s] > mi.file_size || bcs[s] > mi.file_size - offs[s]) {
				err = "directory " + std::to_string(n) + " strip " + std::to_string(s) + " extends past the end of the file"; TIFFClose(t); return false; }
			mi.segs.push_back({offs[s], bcs[s]}); tot += bcs[s];
		}
		if (tot > 0xFFFFFFF0ull) { err = "fraction larger than 4 GiB"; TIFFClose(t); return false; }
		mi.frac_len.push_back(tot); n++;
	} while (TIFFReadDirectory(t));
	TIFFClose(t);
	mi.seg_begin.push_back((uint32_t)mi.segs.size());
	// LibTIFF replaces a zero or implausible byte count by an estimate that runs to the end of the file. Real EER strips are
	// non-empty and never overlap, so overlapping or empty strips mean the container is damaged: refuse rather than decode.
	{
		std::vector<Seg> sorted = mi.segs;
		std::sort(sorted.begin(), sorted.end(), [](const Seg &a, const Seg &b) { return a.off < b.off; });
		for (size_t i = 0; i < sorted.size(); i++)
			if (sorted[i].len == 0 || (i + 1 < sorted.size() && sorted[i].off + sorted[i].len > sorted[i + 1].off)) {
				err = "strips overlap or are empty (LibTIFF may have estimated a byte count)"; return false; }
	}
	if (n != expected) { err = "directory walk stopped at " + std::to_string(n) + " of " + std::to_string(expected); return false; }
	mi.nframes = n;
	return true;
}

// ---------------------------------------------------------------- packing and reading
struct PackPlan { std::vector<uint64_t> off; std::vector<uint32_t> len; uint64_t total = 0; };
static PackPlan make_plan(const MovieIndex &mi, int nuse) {
	PackPlan p; p.off.resize(nuse); p.len.resize(nuse);
	for (int i = 0; i < nuse; i++) { p.off[i] = p.total; p.len[i] = (uint32_t)mi.frac_len[i]; p.total += (mi.frac_len[i] + 7) & ~7ull; }
	return p;
}
// Read fractions [f0, f1) into dst, where dst corresponds to byte pl.off[f0] of the packed layout.
static bool read_range(int fd, const MovieIndex &mi, const PackPlan &pl, int f0, int f1, int threads, uint8_t *dst, std::string &err)
{
	std::atomic<bool> bad(false); std::atomic<int> next(f0);
	const uint64_t base = pl.off[f0];
	#pragma omp parallel num_threads(threads)
	{
		for (;;) {
			const int i0 = next.fetch_add(8);
			if (i0 >= f1 || bad) break;
			for (int i = i0; i < std::min(f1, i0 + 8); i++) {
				uint8_t *p = dst + (pl.off[i] - base);
				for (uint32_t s = mi.seg_begin[i]; s < mi.seg_begin[i + 1]; s++) {
					uint64_t left = mi.segs[s].len, off = mi.segs[s].off;
					while (left) { ssize_t r = pread(fd, p, left, off); if (r <= 0) { bad = true; break; } p += r; off += r; left -= r; }
				}
				const uint64_t pad = ((mi.frac_len[i] + 7) & ~7ull) - mi.frac_len[i];
				if (pad) memset(dst + (pl.off[i] - base) + mi.frac_len[i], 0, pad);
			}
		}
	}
	if (bad) err = "short read";
	return !bad;
}
static bool read_into(const std::string &path, const MovieIndex &mi, const PackPlan &pl, int nuse, int threads, uint8_t *dst, std::string &err)
{
	int fd = open(path.c_str(), O_RDONLY);
	if (fd < 0) { err = "open failed"; return false; }
	const bool ok = read_range(fd, mi, pl, 0, nuse, threads, dst, err);
	close(fd);
	return ok;
}

// ---------------------------------------------------------------- device session with an allocation ledger
struct Ledger {
	uint64_t live = 0, peak = 0;
	std::vector<std::pair<std::string, uint64_t>> items;
	void add(const std::string &n, uint64_t b) { items.push_back({n, b}); live += b; peak = std::max(peak, live); }
};
struct SessionOpts {
	bool out_float = false;      // float counts (exact) instead of uint16
	bool arena = false;          // compressed strips and tables live in a borrowed d_Fframes-sized arena
	uint64_t cap_override = 0;   // force a smaller compressed-strip capacity (chunking test)
	uint64_t ring_bytes = 64ull << 20; int ring_bufs = 4;
	uint64_t reserve = 4096ull << 20; // declared VRAM the rest of the pipeline needs besides the two resident stacks
	uint64_t vram_limit = 0;     // test hook: pretend the card has this much free VRAM
	bool skip_corrupt = false;   // --on_corrupt skip: a failed fraction is rolled back (host semantics); default: movie fails
};
// Bytes of the resident Fourier stack (cufftComplex, half spectrum) that main's session calls d_Fframes.
static uint64_t fframes_bytes(int ngroups, int dim) { return (uint64_t)ngroups * dim * (dim / 2 + 1) * 8; }
static uint64_t tables_bytes_for(int nuse) { return (20ull * nuse + 255) & ~255ull; } // err, nel, offset, length per fraction

struct Admission { bool ok = true; uint64_t need = 0, free_vram = 0, total_vram = 0; std::string why; };
// Decided before the first cudaMalloc of the experiment: refuse if the movie cannot fit with the declared reserve.
static Admission admit(const SessionOpts &o, uint64_t out_bytes, uint64_t comp_bytes, int nuse, int ngroups, int dim, uint64_t max_slot)
{
	Admission a; CK(cudaFree(0));
	size_t fr, tot; CK(cudaMemGetInfo(&fr, &tot)); a.free_vram = o.vram_limit ? o.vram_limit : fr; a.total_vram = tot;
	const uint64_t F = fframes_bytes(ngroups, dim), T = tables_bytes_for(nuse);
	if (o.arena) {
		a.need = out_bytes + F + o.reserve;               // the two resident stacks + reserve; the decoder adds nothing
		const uint64_t cap = F - T;
		if (max_slot > cap) { a.ok = false; a.why = "largest fraction does not fit the arena"; }
	} else a.need = out_bytes + (o.cap_override ? std::min(comp_bytes, o.cap_override) : comp_bytes) + T + o.reserve;
	if (a.ok && a.need > a.free_vram) { a.ok = false; a.why = "needs more VRAM than is free"; }
	return a;
}
struct Session {
	Ledger led; SessionOpts o;
	uint8_t *d_bytes = nullptr, *d_tables = nullptr; void *d_frames = nullptr; uint8_t *d_alloc_bytes = nullptr, *d_alloc_tables = nullptr;
	uint64_t frame_px = 0, out_bytes = 0, bytes_total = 0, arena_bytes = 0, tables_bytes = 0, cap = 0, host_pinned_bytes = 0, max_slot = 0;
	int nuse = 0, ngroups = 0;
	double t_pinned_alloc = 0, t_dev_alloc = 0;
	size_t free_baseline = 0, free_after_alloc = 0, free_after_decode = 0, total_mem = 0;
	cudaEvent_t e[5];
	std::vector<std::pair<int, int>> dchunks;              // decode chunks [f0, f1)
	std::vector<std::vector<std::pair<int, int>>> rchunks; // ring chunks inside each decode chunk
	std::vector<uint8_t *> ring_buf; std::vector<cudaEvent_t> ring_ev;
	uint32_t *err() const { return (uint32_t *)d_tables; }
	uint32_t *nel() const { return (uint32_t *)d_tables + nuse; }
	uint64_t *off() const { return (uint64_t *)(d_tables + 8ull * nuse); }
	uint32_t *len() const { return (uint32_t *)(d_tables + 16ull * nuse); }

	void setup(const PackPlan &pl, int nuse_, int grouping, int dim) {
		nuse = nuse_; ngroups = (nuse + grouping - 1) / grouping; bytes_total = pl.total; frame_px = (uint64_t)dim * dim;
		out_bytes = (uint64_t)ngroups * frame_px * (o.out_float ? 4 : 2);
		tables_bytes = tables_bytes_for(nuse);
		CK(cudaFree(0)); CK(cudaMemGetInfo(&free_baseline, &total_mem));
		arena_bytes = fframes_bytes(ngroups, dim);
		cap = o.arena ? (arena_bytes - tables_bytes) & ~255ull : (bytes_total + 255) & ~255ull;
		if (o.cap_override) cap = std::min<uint64_t>(cap, o.cap_override & ~255ull);
		// decode chunks: whole fractions, at most `cap` packed bytes each
		for (int i = 0; i < nuse;) {
			int j = i; uint64_t b = 0;
			while (j < nuse && b + ((j + 1 < nuse ? pl.off[j + 1] : pl.total) - pl.off[j]) <= cap) { b += (j + 1 < nuse ? pl.off[j + 1] : pl.total) - pl.off[j]; j++; }
			if (j == i) { fprintf(stderr, "fraction %d does not fit the decode capacity\n", i); exit(5); }
			dchunks.push_back({i, j}); i = j;
		}
		uint64_t ring_max = 8;
		for (auto &d : dchunks) {
			std::vector<std::pair<int, int>> rc;
			for (int i = d.first, st = d.first; i < d.second; i++) {
				const uint64_t end = (i + 1 < nuse ? pl.off[i + 1] : pl.total);
				if (end - pl.off[st] >= o.ring_bytes || i + 1 == d.second) { ring_max = std::max<uint64_t>(ring_max, end - pl.off[st]); rc.push_back({st, i + 1}); st = i + 1; }
			}
			rchunks.push_back(rc);
		}
		for (int i = 0; i < nuse; i++) max_slot = std::max<uint64_t>(max_slot, (i + 1 < nuse ? pl.off[i + 1] : pl.total) - pl.off[i]);
		double t0 = now_s();
		ring_buf.resize(o.ring_bufs); ring_ev.resize(o.ring_bufs);
		for (int k = 0; k < o.ring_bufs; k++) { CK(cudaHostAlloc((void **)&ring_buf[k], ring_max, cudaHostAllocDefault)); CK(cudaEventCreate(&ring_ev[k])); }
		host_pinned_bytes = (uint64_t)o.ring_bufs * ring_max;
		t_pinned_alloc = now_s() - t0; t0 = now_s();
		CK(cudaMalloc(&d_frames, out_bytes)); led.add(o.out_float ? "output frames (float)" : "output frames (uint16)", out_bytes);
		if (o.arena) {
			CK(cudaMalloc((void **)&d_alloc_bytes, arena_bytes)); led.add("d_Fframes-sized arena (borrowed in an integration)", arena_bytes);
			d_bytes = d_alloc_bytes; d_tables = d_alloc_bytes + (arena_bytes - tables_bytes);
		} else {
			const uint64_t nb = std::max<uint64_t>(cap, 256);
			CK(cudaMalloc((void **)&d_alloc_bytes, nb)); led.add("compressed strip buffer", nb);
			CK(cudaMalloc((void **)&d_alloc_tables, tables_bytes)); led.add("fraction tables", tables_bytes);
			d_bytes = d_alloc_bytes; d_tables = d_alloc_tables;
		}
		t_dev_alloc = now_s() - t0;
		CK(cudaMemGetInfo(&free_after_alloc, &total_mem));
		for (auto &x : e) CK(cudaEventCreate(&x));
	}
	void teardown() {
		for (auto &x : e) cudaEventDestroy(x);
		cudaFree(d_frames); cudaFree(d_alloc_bytes); cudaFree(d_alloc_tables);
		for (auto b : ring_buf) cudaFreeHost(b);
		for (auto x : ring_ev) cudaEventDestroy(x);
	}
};

static MovieIndex g_mi_cache; static PackPlan g_plan_cache; // index and plan of the movie under test

struct DevRun { double index_s = 0, read_s = 0, h2d_ms = 0, memset_ms = 0, decode_ms = 0, gpu_phase_s = 0, e2e_s = 0, cpu_s = 0, foreign = 0;
	std::vector<uint32_t> err, nel; bool read_ok = true; std::string msg; };

// One end-to-end device movie: index -> (read chunk k+1 | H2D chunk k) through a small pinned ring -> memset -> decode -> error flags back.
static DevRun device_once(Session &S, const std::string &path, int ups, int grouping, int read_threads, int block, uint64_t max_index, bool with_index)
{
	DevRun r; Meter m; m.start(); const double t0 = now_s();
	MovieIndex mi; std::string err;
	if (with_index) {
		if (!parse_index(path, ups, mi, err)) { r.read_ok = false; r.msg = err; return r; }
		g_plan_cache = make_plan(mi, S.nuse); g_mi_cache = mi;
	}
	const PackPlan &plan = g_plan_cache;
	const double t1 = now_s(); r.index_s = t1 - t0;
	cudaStream_t st = 0;
	int fd = open(path.c_str(), O_RDONLY);
	if (fd < 0) { r.read_ok = false; r.msg = "open failed"; return r; }
	CK(cudaEventRecord(S.e[0], st));
	CK(cudaMemsetAsync(S.d_frames, 0, S.out_bytes, st));
	CK(cudaEventRecord(S.e[1], st));
	int k = 0; std::vector<uint64_t> off_rel; std::vector<uint32_t> len_rel;
	for (size_t d = 0; d < S.dchunks.size(); d++) {
		const int f0 = S.dchunks[d].first, f1 = S.dchunks[d].second; const uint64_t base = plan.off[f0];
		for (auto &rc : S.rchunks[d]) {
			const int slot = k % S.o.ring_bufs;
			if (k >= S.o.ring_bufs) CK(cudaEventSynchronize(S.ring_ev[slot]));
			if (!read_range(fd, g_mi_cache, plan, rc.first, rc.second, read_threads, S.ring_buf[slot], err)) { close(fd); r.read_ok = false; r.msg = err; return r; }
			const uint64_t b0 = plan.off[rc.first], b1 = (rc.second < S.nuse ? plan.off[rc.second] : plan.total);
			CK(cudaMemcpyAsync(S.d_bytes + (b0 - base), S.ring_buf[slot], b1 - b0, cudaMemcpyHostToDevice, st));
			CK(cudaEventRecord(S.ring_ev[slot], st)); k++;
		}
		off_rel.resize(f1 - f0); len_rel.resize(f1 - f0);
		for (int i = f0; i < f1; i++) { off_rel[i - f0] = plan.off[i] - base; len_rel[i - f0] = plan.len[i]; }
		CK(cudaMemcpyAsync(S.off(), off_rel.data(), 8ull * (f1 - f0), cudaMemcpyHostToDevice, st));
		CK(cudaMemcpyAsync(S.len(), len_rel.data(), 4ull * (f1 - f0), cudaMemcpyHostToDevice, st));
		const double tq = now_s();
		if (d + 1 == S.dchunks.size()) { r.read_s = tq - t1; CK(cudaEventRecord(S.e[2], st)); }
		eerdev::DecodeParams p{}; p.d_bytes = S.d_bytes; p.d_slot_off = S.off(); p.d_slot_len = S.len(); p.nfrac = f1 - f0; p.f_base = f0; p.grouping = grouping;
		p.detector = g_mi_cache.width; p.upsampling = ups; p.rle_bits = g_mi_cache.rle_bits; p.sym_bits = g_mi_cache.sym_bits;
		p.d_frames = S.d_frames; p.out_float = S.o.out_float; p.max_pixel_index = max_index ? max_index : S.frame_px;
		p.d_err = S.err() + f0; p.d_nel = S.nel() + f0; p.block = block;
		CK(eerdev::launch_decode(p, st));
		if (S.o.skip_corrupt) { p.rollback = 1; CK(eerdev::launch_decode(p, st)); }
	}
	close(fd);
	const double t2 = now_s();
	CK(cudaEventRecord(S.e[3], st));
	r.err.resize(S.nuse); r.nel.resize(S.nuse);
	CK(cudaMemcpyAsync(r.err.data(), S.err(), 4ull * S.nuse, cudaMemcpyDeviceToHost, st));
	CK(cudaMemcpyAsync(r.nel.data(), S.nel(), 4ull * S.nuse, cudaMemcpyDeviceToHost, st));
	CK(cudaStreamSynchronize(st));
	const double t3 = now_s();
	float a, c; CK(cudaEventElapsedTime(&a, S.e[0], S.e[1])); CK(cudaEventElapsedTime(&c, S.e[2], S.e[3]));
	r.memset_ms = a; r.decode_ms = c; r.gpu_phase_s = t3 - t2; r.e2e_s = t3 - t0;
	double wall, own, foreign; m.stop(wall, own, foreign); r.cpu_s = own; r.foreign = foreign;
	size_t fr, tot; CK(cudaMemGetInfo(&fr, &tot)); S.free_after_decode = fr;
	return r;
}

// ---------------------------------------------------------------- host reference
template <typename T>
static double host_render_timed(const std::string &path, int ups, int grouping, int ngroups, int threads, double &cpu_s, double &foreign, long long &electrons)
{
	omp_set_num_threads(threads);
	std::vector<MultidimArray<T>> imgs(ngroups);
	std::vector<long long> ne(ngroups, 0);
	Meter m; m.start();
	EERRenderer r; r.read(path, ups);
	#pragma omp parallel for num_threads(threads) schedule(static)
	for (int g = 0; g < ngroups; g++) ne[g] = r.renderFrames(g * grouping + 1, (g + 1) * grouping, imgs[g]);
	double wall, own, fc; m.stop(wall, own, fc); cpu_s = own; foreign = fc;
	electrons = 0; for (long long x : ne) electrons += x;
	return wall;
}
static double host_read_only(const std::string &path, int ups) // read() + lazy read of all strips + one fraction rendered
{
	MultidimArray<unsigned short> img; const double t0 = now_s();
	EERRenderer r; r.read(path, ups); r.renderFrames(1, 1, img);
	return now_s() - t0;
}

static uint64_t fnv(const void *p, size_t n) { const uint8_t *b = (const uint8_t *)p; uint64_t h = 1469598103934665603ull; for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 1099511628211ull; } return h; }

// Compare every pixel of every group with EERRenderer::renderFrames<T> (T = float or unsigned short, matching the device output).
template <typename T>
static void verify_groups(Session &S, const DevRun &r, const std::string &path, int ups, int grouping, int ngroups, int dim, int hthreads, bool skip, std::ostringstream &js)
{
	long long mism_px = 0, mism_nel = 0, host_el = 0, dev_el = 0, groups_cmp = 0; uint64_t px = 0;
	uint64_t bad_fr = 0; for (uint32_t e : r.err) bad_fr += e != 0;
	omp_set_num_threads(hthreads);
	EERRenderer host; host.read(path, ups);
	#pragma omp parallel num_threads(hthreads)
	{
		MultidimArray<T> img; std::vector<T> back(S.frame_px);
		#pragma omp for schedule(dynamic, 1)
		for (int g = 0; g < ngroups; g++) {
			long long ne = host.renderFrames(g * grouping + 1, (g + 1) * grouping, img);
			CK(cudaMemcpy(back.data(), (T *)S.d_frames + (uint64_t)g * S.frame_px, S.frame_px * sizeof(T), cudaMemcpyDeviceToHost));
			long long d = 0; for (uint64_t i = 0; i < S.frame_px; i++) d += (back[i] != img.data[i]);
			long long de = 0; for (int f = g * grouping; f < (g + 1) * grouping; f++) de += r.nel[f];
			#pragma omp critical
			{ mism_px += d; mism_nel += (de != ne); host_el += ne; dev_el += de; groups_cmp++; px += S.frame_px;
			  if (YSIZE(img) != dim || XSIZE(img) != dim) mism_px += 1ll << 40; }
		}
	}
	js << ",\"verify\":{\"host_type\":\"" << (sizeof(T) == 4 ? "float" : "uint16") << "\",\"groups_compared\":" << groups_cmp << ",\"pixels_compared\":" << px << ",\"mismatched_pixels\":" << mism_px
	   << ",\"groups_with_electron_count_mismatch\":" << mism_nel << ",\"host_electrons\":" << host_el << ",\"device_electrons\":" << dev_el
	   << ",\"device_failed_fractions\":" << bad_fr << ",\"on_corrupt\":\"" << (skip ? "skip" : "fail") << "\",\"verdict\":\"" << ((mism_px == 0 && mism_nel == 0 && (skip || bad_fr == 0) && groups_cmp == ngroups) ? "EXACT" : "MISMATCH") << "\"}";
}

// ---------------------------------------------------------------- compare
static int cmd_compare(const Opts &o)
{
	const std::string path = o.s("eer"), label = o.s("label", "case");
	const int grouping = (int)o.l("grouping", 40), ups = (int)o.l("upsampling", 1), pairs = (int)o.l("pairs", 8);
	const int rthreads = (int)o.l("read_threads", 8), hthreads = (int)o.l("host_threads", 8), block = (int)o.l("block", 32);
	const bool verify = o.l("verify", 1), timing = o.l("timing", 1), host_timing = o.l("host_timing", 1);
	if (!o.l("spin", 0)) CK(cudaSetDeviceFlags(cudaDeviceScheduleBlockingSync));
	SessionOpts so; so.out_float = o.s("out", "float") == "float"; so.arena = o.l("arena", 1); so.cap_override = (uint64_t)o.l("cap_mib", 0) << 20;
	so.ring_bufs = (int)o.l("ring_bufs", 4); so.ring_bytes = (uint64_t)o.l("ring_mib", 64) << 20;
	so.skip_corrupt = o.s("on_corrupt", "fail") == "skip"; so.reserve = (uint64_t)o.l("reserve_mib", 4096) << 20; so.vram_limit = (uint64_t)o.l("vram_limit_mib", 0) << 20;
	MovieIndex mi; std::string err;
	if (!parse_index(path, ups, mi, err)) { printf("{\"label\":\"%s\",\"error\":\"%s\"}\n", label.c_str(), json_esc(err).c_str()); return 1; }
	const int dim = eerdev::frame_dim(mi.width, ups);
	if (dim < 0) { printf("{\"label\":\"%s\",\"error\":\"unsupported detector/upsampling\"}\n", label.c_str()); return 1; }
	if ((long long)grouping * (ups == -1 ? 4 : 1) > 65535 && !so.out_float) { printf("{\"label\":\"%s\",\"error\":\"grouped counts can exceed uint16\"}\n", label.c_str()); return 1; }
	const int ngroups = mi.nframes / grouping, nuse = ngroups * grouping;
	if (ngroups <= 0) { printf("{\"label\":\"%s\",\"error\":\"no complete group\"}\n", label.c_str()); return 1; }
	const PackPlan plan = make_plan(mi, nuse);
	g_mi_cache = mi; g_plan_cache = plan;
	uint64_t max_slot = 0; for (int i = 0; i < nuse; i++) max_slot = std::max<uint64_t>(max_slot, (i + 1 < nuse ? plan.off[i + 1] : plan.total) - plan.off[i]);
	const uint64_t out_bytes = (uint64_t)ngroups * dim * dim * (so.out_float ? 4 : 2);
	const Admission adm = admit(so, out_bytes, plan.total, nuse, ngroups, dim, max_slot);
	std::ostringstream js;
	js << "{\"label\":\"" << label << "\",\"file\":\"" << json_esc(path) << "\",\"compression\":" << mi.compression << ",\"detector\":" << mi.width
	   << ",\"fractions_total\":" << mi.nframes << ",\"grouping\":" << grouping << ",\"groups\":" << ngroups << ",\"fractions_used\":" << nuse
	   << ",\"remainder_fractions\":" << mi.nframes - nuse << ",\"upsampling\":" << ups << ",\"frame_dim\":" << dim << ",\"block\":" << block
	   << ",\"output\":\"" << (so.out_float ? "float" : "uint16") << "\",\"on_corrupt\":\"" << (so.skip_corrupt ? "skip" : "fail") << "\",\"arena\":" << (so.arena ? 1 : 0) << ",\"ring_bufs\":" << so.ring_bufs << ",\"ring_mib\":" << (so.ring_bytes >> 20)
	   << ",\"read_threads\":" << rthreads << ",\"host_omp_threads\":" << hthreads << ",\"file_size\":" << mi.file_size << ",\"h2d_bytes\":" << plan.total;
	js << ",\"cpus\":\""; for (int c : allowed_cpus()) js << c << ","; js << "\"";
	const char *cvd = getenv("CUDA_VISIBLE_DEVICES"); js << ",\"cuda_visible_devices\":\"" << (cvd ? cvd : "") << "\"";
	js << ",\"admission\":{\"verdict\":\"" << (adm.ok ? "ADMITTED" : "REFUSED") << "\",\"need_bytes\":" << adm.need << ",\"free_vram_bytes\":" << adm.free_vram
	   << ",\"total_vram_bytes\":" << adm.total_vram << ",\"reserve_bytes\":" << so.reserve << ",\"reason\":\"" << adm.why << "\"}";
	if (!adm.ok) { js << ",\"cudaMalloc_calls_by_experiment\":0}"; printf("%s\n", js.str().c_str()); return 5; }
	Session S; S.o = so; S.setup(plan, nuse, grouping, dim);
	js << ",\"pinned_ring_alloc_s\":" << S.t_pinned_alloc << ",\"device_alloc_s\":" << S.t_dev_alloc;
	js << ",\"working_set\":{\"compressed_strips_h2d_bytes\":" << plan.total << ",\"largest_fraction_bytes\":" << max_slot << ",\"tables_bytes\":" << S.tables_bytes
	   << ",\"output_bytes\":" << S.out_bytes << ",\"d_Fframes_equivalent_bytes\":" << S.arena_bytes << ",\"decode_capacity_bytes\":" << S.cap
	   << ",\"decode_chunks\":" << S.dchunks.size() << ",\"fits_in_arena_without_chunking\":" << ((plan.total + S.tables_bytes <= S.arena_bytes) ? 1 : 0) << "}";

	if (verify) {
		DevRun r = device_once(S, path, ups, grouping, rthreads, block, 0, false);
		if (S.o.out_float) verify_groups<float>(S, r, path, ups, grouping, ngroups, dim, hthreads, S.o.skip_corrupt, js);
		else verify_groups<unsigned short>(S, r, path, ups, grouping, ngroups, dim, hthreads, S.o.skip_corrupt, js);
	}
	if (!verify && !timing) { // single device decode, no host comparison (used under compute-sanitizer)
		DevRun r = device_once(S, path, ups, grouping, rthreads, block, 0, true);
		uint64_t bad = 0, el = 0; for (uint32_t e : r.err) bad += e != 0; for (uint32_t n : r.nel) el += n;
		js << ",\"device_once\":{\"read_ok\":" << (r.read_ok ? 1 : 0) << ",\"failed_fractions\":" << bad << ",\"electrons\":" << el << "}";
	}
	if (timing) {
		// A = host EERRenderer render (uint16, the app's compact route), B = device end to end. One discarded warm-up per arm,
		// then `pairs` pairs alternating AB / BA so neither arm always runs first.
		Stats dev_index, dev_read, dev_dec, dev_e2e, dev_cpu, dev_fgn, host_s, host_cpu, host_fgn, diff, ratio; std::vector<std::string> order; long long el = 0;
		{ DevRun w = device_once(S, path, ups, grouping, rthreads, block, 0, true); (void)w; }
		if (host_timing) { double cs, fo; host_render_timed<unsigned short>(path, ups, grouping, ngroups, hthreads, cs, fo, el); }
		for (int i = 0; i < pairs; i++) {
			const bool ab = (i % 2 == 0); order.push_back(ab ? "AB" : "BA");
			double h = 0; DevRun d;
			for (int arm = 0; arm < 2; arm++) {
				const bool is_host = (arm == 0) == ab;
				if (is_host) { if (host_timing) { double cs, fo; h = host_render_timed<unsigned short>(path, ups, grouping, ngroups, hthreads, cs, fo, el); host_s.add(h); host_cpu.add(cs); host_fgn.add(fo); } }
				else {
					d = device_once(S, path, ups, grouping, rthreads, block, 0, true);
					uint64_t bad = 0; for (uint32_t e : d.err) bad += e != 0;
					if (!d.read_ok || bad) { fprintf(stderr, "device run failed: %s bad=%llu\n", d.msg.c_str(), (unsigned long long)bad); return 4; }
					dev_index.add(d.index_s); dev_read.add(d.read_s); dev_dec.add(d.decode_ms / 1e3); dev_e2e.add(d.e2e_s); dev_cpu.add(d.cpu_s); dev_fgn.add(d.foreign);
				}
			}
			if (host_timing) { diff.add(h - d.e2e_s); ratio.add(d.e2e_s / h); }
		}
		js << ",\"pairs\":{\"n\":" << pairs << ",\"order\":[";
		for (size_t i = 0; i < order.size(); i++) js << (i ? "," : "") << "\"" << order[i] << "\"";
		js << "],\"device\":{\"index_s\":" << dev_index.json() << ",\"read_and_h2d_s\":" << dev_read.json() << ",\"decode_s\":" << dev_dec.json()
		   << ",\"end_to_end_s\":" << dev_e2e.json() << ",\"process_cpu_s\":" << dev_cpu.json() << ",\"foreign_cores\":" << dev_fgn.json() << "}";
		if (host_timing) {
			Stats hr; for (int i = 0; i < 3; i++) hr.add(host_read_only(path, ups));
			js << ",\"host\":{\"render_total_s\":" << host_s.json() << ",\"process_cpu_s\":" << host_cpu.json() << ",\"foreign_cores\":" << host_fgn.json()
			   << ",\"read_plus_one_fraction_s\":" << hr.json() << ",\"electrons\":" << el << "}"
			   << ",\"saving_s_host_minus_device\":" << diff.json() << ",\"device_over_host\":" << ratio.json();
		}
		js << "}";
	}
	{
		auto used = [&](size_t fr) { return (long long)S.free_baseline - (long long)fr; };
		js << ",\"memory\":{\"host_pinned_ring_bytes\":" << S.host_pinned_bytes << ",\"ledger_peak_bytes\":" << S.led.peak << ",\"cudaMemGetInfo_used_after_alloc_bytes\":" << used(S.free_after_alloc)
		   << ",\"cudaMemGetInfo_used_after_decode_bytes\":" << used(S.free_after_decode ? S.free_after_decode : S.free_after_alloc) << ",\"ledger\":[";
		for (size_t i = 0; i < S.led.items.size(); i++) js << (i ? "," : "") << "{\"name\":\"" << S.led.items[i].first << "\",\"bytes\":" << S.led.items[i].second << "}";
		js << "]}";
	}
	js << "}";
	printf("%s\n", js.str().c_str()); fflush(stdout);
	S.teardown();
	return 0;
}

// ---------------------------------------------------------------- per-fraction verdicts (fixtures)
static int cmd_dev_frames(const Opts &o)
{
	const std::string path = o.s("eer"); const int ups = (int)o.l("upsampling", 1), block = (int)o.l("block", 32);
	const long clamp = o.l("clamp_div", 0);
	MovieIndex mi; std::string err;
	if (!parse_index(path, ups, mi, err)) { printf("{\"index_error\":\"%s\"}\n", json_esc(err).c_str()); return 1; }
	const int dim = eerdev::frame_dim(mi.width, ups);
	if (dim < 0) { printf("{\"index_error\":\"unsupported\"}\n"); return 1; }
	const int nuse = mi.nframes; const PackPlan plan = make_plan(mi, nuse);
	g_mi_cache = mi; g_plan_cache = plan;
	Session S; S.o.out_float = false; S.o.arena = false; S.setup(plan, nuse, 1, dim);
	DevRun r = device_once(S, path, ups, 1, 4, block, clamp ? (uint64_t)dim * dim / clamp : 0, false);
	std::vector<uint16_t> back(S.frame_px);
	uint64_t beyond_nonzero = 0;
	for (int f = 0; f < nuse; f++) {
		CK(cudaMemcpy(back.data(), (uint16_t *)S.d_frames + (uint64_t)f * S.frame_px, S.frame_px * 2, cudaMemcpyDeviceToHost));
		if (clamp) for (uint64_t i = S.frame_px / clamp; i < S.frame_px; i++) beyond_nonzero += back[i] != 0;
		printf("{\"f\":%d,\"err\":%u,\"nel\":%u,\"hash\":\"%016llx\"}\n", f, r.err[f], r.nel[f], (unsigned long long)fnv(back.data(), S.frame_px * 2));
	}
	if (clamp) printf("{\"clamp_div\":%ld,\"nonzero_pixels_beyond_guard\":%llu}\n", clamp, (unsigned long long)beyond_nonzero);
	S.teardown();
	return 0;
}
static int cmd_host_frames(const Opts &o)
{
	const std::string path = o.s("eer"); const int ups = (int)o.l("upsampling", 1);
	const int first = (int)o.l("first", 0);
	try {
		EERRenderer r; r.read(path, ups);
		const int n = r.getNFrames();
		const int last = (int)o.l("last", n - 1);
		for (int f = first; f <= last && f < n; f++) {
			MultidimArray<unsigned short> img;
			std::ostringstream cap; std::streambuf *old = std::cerr.rdbuf(cap.rdbuf());
			long long ne = 0;
			try { ne = r.renderFrames(f + 1, f + 1, img); } catch (...) { std::cerr.rdbuf(old); throw; }
			std::cerr.rdbuf(old);
			const bool skipped = cap.str().find("skipped") != std::string::npos;
			printf("{\"f\":%d,\"skipped\":%d,\"nel\":%lld,\"hash\":\"%016llx\"}\n", f, skipped, ne, (unsigned long long)fnv(img.data, (size_t)XSIZE(img) * YSIZE(img) * 2));
			fflush(stdout);
		}
	} catch (RelionError &e) { // REPORT_ERROR from the renderer: the host's own fail-closed path
		printf("{\"f\":%d,\"host_error\":\"%s\"}\n", first, json_esc(e.msg).c_str());
		return 0;
	}
	return 0;
}

// ---------------------------------------------------------------- fixtures
static int cmd_fixtures(const Opts &o)
{
	using namespace eerfix;
	const std::string src = o.s("src"), out = o.s("out"); const int N = (int)o.l("nfrac", 48); const uint64_t seed = o.l("seed", 1);
	MovieIndex mi; std::string err;
	if (!parse_index(src, 1, mi, err)) { fprintf(stderr, "%s\n", err.c_str()); return 1; }
	if (mi.compression != 65001 || mi.nframes < N) { fprintf(stderr, "need a 65001 source with >= %d fractions\n", N); return 1; }
	const PackPlan plan = make_plan(mi, N);
	std::vector<uint8_t> raw(plan.total);
	if (!read_into(src, mi, plan, N, 4, raw.data(), err)) { fprintf(stderr, "%s\n", err.c_str()); return 1; }
	std::vector<std::vector<uint8_t>> base(N);
	for (int i = 0; i < N; i++) base[i].assign(raw.begin() + plan.off[i], raw.begin() + plan.off[i] + plan.len[i]);
	const Layout L = layout_for(65001); const uint32_t total = 4096u * 4096u;
	write_eer(out + "/base48.eer", 4096, 4096, 65001, base);

	std::vector<std::vector<uint8_t>> mut = base; std::vector<std::string> what(N, "unmodified");
	std::vector<Electron> el;
	auto set = [&](int i, std::vector<uint8_t> v, const char *w) { mut[i] = std::move(v); what[i] = w; };
	set(4, std::vector<uint8_t>(base[4].begin(), base[4].begin() + base[4].size() / 2), "strip cut to 50%");
	set(5, std::vector<uint8_t>(base[5].begin(), base[5].begin() + base[5].size() * 9 / 10), "strip cut to 90%");
	set(6, std::vector<uint8_t>(base[6].begin(), base[6].begin() + 3), "strip cut to 3 bytes");
	set(7, std::vector<uint8_t>(base[7].begin(), base[7].begin() + 1), "strip cut to 1 byte");
	decode(L, total, base[8].data(), base[8].size(), el); set(8, encode(L, total, el, 5), "run codes overshoot the frame by 5 pixels");
	decode(L, total, base[9].data(), base[9].size(), el); if (el.back().pos != total - 1) el.push_back({total - 1, 3});
	set(9, encode(L, total, el), "valid; electron at the last pixel");
	decode(L, total, base[10].data(), base[10].size(), el); { std::vector<uint8_t> v = encode(L, total, el); Rng r(seed + 10); for (int k = 0; k < 64; k++) v.push_back((uint8_t)r.next()); set(10, v, "valid; 64 random bytes after the closing code"); }
	set(11, std::vector<uint8_t>(1000, 0xFF), "1000 bytes of 127-skip codes, frame never closed");
	decode(L, total, base[12].data(), base[12].size(), el); if (el.back().pos != total - 1) el.push_back({total - 1, 3});
	set(12, encode(L, total, el, 0, true), "electron at the last pixel, no closing code");
	for (int i = 13; i < N; i++) {
		Rng r(seed * 1000 + i); std::vector<uint8_t> v = base[i]; const int type = (i - 13) % 5; const uint32_t len = (uint32_t)v.size();
		if (type <= 2) { const int k = type == 0 ? 1 : type == 1 ? 8 : 64; for (int j = 0; j < k; j++) { uint32_t b = r.below(len * 8); v[b >> 3] ^= (uint8_t)(1u << (b & 7)); }
			set(i, v, type == 0 ? "1 random bit flip" : type == 1 ? "8 random bit flips" : "64 random bit flips"); }
		else if (type == 3) { uint32_t s = r.below(len - 16); for (int j = 0; j < 16; j++) v[s + j] = (uint8_t)r.next(); set(i, v, "16 contiguous random bytes"); }
		else { uint32_t s = r.below(len - 64); for (int j = 0; j < 64; j++) v[s + j] = 0; set(i, v, "64 contiguous zero bytes"); }
	}
	write_eer(out + "/mut48.eer", 4096, 4096, 65001, mut);
	{ std::ofstream m(out + "/mut48.manifest.json"); m << "{\"source\":\"" << json_esc(src) << "\",\"seed\":" << seed << ",\"fractions\":[";
	  for (int i = 0; i < N; i++) m << (i ? "," : "") << "{\"f\":" << i << ",\"mutation\":\"" << what[i] << "\"}"; m << "]}\n"; }
	{ auto v = base; v[N - 1].resize(v[N - 1].size() / 2); write_eer(out + "/trunc_last.eer", 4096, 4096, 65001, v); }
	{ auto v = base; v[7].clear(); write_eer(out + "/empty_strip.eer", 4096, 4096, 65001, v); } // LibTIFF replaces a zero byte count by an estimate
	{ write_eer(out + "/trunc_file.eer", 4096, 4096, 65001, base);
	  struct stat st; stat((out + "/trunc_file.eer").c_str(), &st);
	  if (truncate((out + "/trunc_file.eer").c_str(), st.st_size - base[N - 1].size() / 2) != 0) return 1; }
	// synthetic parity files for the encodings the corpus does not contain, and for 2K detectors
	for (uint16_t comp : {65000, 65001, 65002})
		for (int det : {4096, 2048}) {
			const Layout l = layout_for(comp); const uint32_t tot = (uint32_t)det * det; Rng r(seed * 77 + comp + det);
			std::vector<std::vector<uint8_t>> v;
			for (int i = 0; i < 12; i++) v.push_back(encode(l, tot, random_electrons(r, tot, i % 3 == 0 ? 0.002 : 0.015, l.sym_bits, i % 2 == 0)));
			write_eer(out + "/syn_" + std::to_string(comp) + "_" + std::to_string(det) + ".eer", det, det, comp, v);
		}
	printf("fixtures written to %s\n", out.c_str());
	return 0;
}

int main(int argc, char **argv)
{
	if (argc < 2) { fprintf(stderr, "usage: eer_device_exp compare|dev-frames|host-frames|fixtures [--key value ...]\n"); return 2; }
	const std::string c = argv[1]; Opts o(argc, argv, 2);
	if (c == "compare") return cmd_compare(o);
	if (c == "dev-frames") return cmd_dev_frames(o);
	if (c == "host-frames") return cmd_host_frames(o);
	if (c == "fixtures") return cmd_fixtures(o);
	fprintf(stderr, "unknown command %s\n", c.c_str()); return 2;
}
