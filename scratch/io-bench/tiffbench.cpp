// Isolates MotionCorr's movie-read cost from its alternatives.
// Mode A replicates the runner exactly; B and C are candidate replacements.
// All modes must produce the same checksum or the comparison is meaningless.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
#include <chrono>
#include <unistd.h>
#include <fcntl.h>
#include <omp.h>
#include <zlib.h>
#include <tiffio.h>

static double now_s() {
	using namespace std::chrono;
	return duration<double>(steady_clock::now().time_since_epoch()).count();
}

// ---------------------------------------------------------------- mode A
// Exactly what src/motioncorr_runner.cpp:1346 does today: one TIFFOpen per
// frame, a full IFD chain walk inside every open, then a separate Y-flip pass
// with scalar element swaps (src/rwTIFF.h).
static double readMovieAsRunnerDoes(const std::string &path, int nframes, int J,
                                    std::vector<std::vector<float>> &out)
{
	double t0 = now_s();
	#pragma omp parallel for num_threads(J) schedule(dynamic)
	for (int f = 0; f < nframes; f++) {
		TIFF *tif = TIFFOpen(path.c_str(), "r");
		if (!tif) { fprintf(stderr, "open failed\n"); exit(1); }
		uint32_t width, length;
		TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &width);
		TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &length);
		uint16_t bps; TIFFGetFieldDefaulted(tif, TIFFTAG_BITSPERSAMPLE, &bps);
		// The redundant part: readTIFF counts directories on every single read.
		long n = 1;
		while (TIFFSetDirectory(tif, n) != 0) n++;
		TIFFSetDirectory(tif, 0);

		TIFFSetDirectory(tif, f);
		std::vector<float> &dst = out[f];
		dst.resize((size_t)width * length);
		tsize_t stripSize = TIFFStripSize(tif);
		tstrip_t nstrips = TIFFNumberOfStrips(tif);
		tdata_t buf = _TIFFmalloc(stripSize);
		size_t have = 0;
		for (tstrip_t s = 0; s < nstrips; s++) {
			tsize_t got = TIFFReadEncodedStrip(tif, s, buf, stripSize);
			if (got == -1) { fprintf(stderr, "strip read failed\n"); exit(1); }
			size_t got_n = (size_t)got * 8 / bps;
			const uint16_t *src = (const uint16_t*)buf;
			for (size_t i = 0; i < got_n; i++) dst[have + i] = (float)src[i];
			have += got_n;
		}
		_TIFFfree(buf);
		TIFFClose(tif);

		// The separate scalar Y-flip pass, as written today.
		float tmp;
		const long ylim = length / 2;
		for (long y1 = 0; y1 < ylim; y1++) {
			const long y2 = length - 1 - y1;
			for (long x = 0; x < (long)width; x++) {
				tmp = dst[y1 * width + x];
				dst[y1 * width + x] = dst[y2 * width + x];
				dst[y2 * width + x] = tmp;
			}
		}
	}
	return now_s() - t0;
}

// ---------------------------------------------------------------- mode B
// Same libtiff decode, but one handle per thread reused across frames, no
// directory recount, and the flip folded into the strip loop.
static double readMovieOneHandlePerThread(const std::string &path, int nframes, int J,
                                          std::vector<std::vector<float>> &out)
{
	double t0 = now_s();
	#pragma omp parallel num_threads(J)
	{
		TIFF *tif = TIFFOpen(path.c_str(), "r");
		if (!tif) { fprintf(stderr, "open failed\n"); exit(1); }
		#pragma omp for schedule(dynamic)
		for (int f = 0; f < nframes; f++) {
			TIFFSetDirectory(tif, f);
			uint32_t width, length;
			TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &width);
			TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &length);
			uint16_t bps; TIFFGetFieldDefaulted(tif, TIFFTAG_BITSPERSAMPLE, &bps);
			std::vector<float> &dst = out[f];
			dst.resize((size_t)width * length);
			tsize_t stripSize = TIFFStripSize(tif);
			tstrip_t nstrips = TIFFNumberOfStrips(tif);
			tdata_t buf = _TIFFmalloc(stripSize);
			size_t have = 0;
			for (tstrip_t s = 0; s < nstrips; s++) {
				tsize_t got = TIFFReadEncodedStrip(tif, s, buf, stripSize);
				size_t got_n = (size_t)got * 8 / bps;
				const uint16_t *src = (const uint16_t*)buf;
				// Write straight to the flipped row; no second pass.
				size_t row = have / width;
				size_t frow = length - 1 - row;
				float *o = dst.data() + frow * width;
				for (size_t i = 0; i < got_n; i++) o[i] = (float)src[i];
				have += got_n;
			}
			_TIFFfree(buf);
		}
		TIFFClose(tif);
	}
	return now_s() - t0;
}

// ---------------------------------------------------------------- mode C
struct FrameDir { std::vector<uint64_t> off; std::vector<uint64_t> cnt; uint32_t w, h, rps; };

// Minimal classic-TIFF IFD parse; enough for the single-sample deflate movies
// the tutorial dataset ships. Bails out loudly on anything else.
static bool parseIFDs(const std::string &path, std::vector<FrameDir> &frames, uint16_t &comp)
{
	FILE *fp = fopen(path.c_str(), "rb");
	if (!fp) return false;
	uint8_t hdr[8];
	if (fread(hdr, 1, 8, fp) != 8) { fclose(fp); return false; }
	if (hdr[0] != 'I' || hdr[1] != 'I') { fclose(fp); fprintf(stderr, "only little-endian classic TIFF\n"); return false; }
	uint32_t next; memcpy(&next, hdr + 4, 4);
	auto readArr = [&](uint16_t type, uint32_t num, const uint8_t *inl, std::vector<uint64_t> &v) {
		size_t esz = (type == 3) ? 2 : 4;
		v.resize(num);
		if (esz * num <= 4) {
			for (uint32_t i = 0; i < num; i++)
				v[i] = (esz == 2) ? *(const uint16_t*)(inl + 2 * i) : *(const uint32_t*)(inl + 4 * i);
		} else {
			uint32_t o; memcpy(&o, inl, 4);
			std::vector<uint8_t> raw(esz * num);
			long save = ftell(fp);
			fseek(fp, o, SEEK_SET);
			if (fread(raw.data(), 1, esz * num, fp) != esz * num) { fprintf(stderr, "short IFD array\n"); exit(1); }
			fseek(fp, save, SEEK_SET);
			for (uint32_t i = 0; i < num; i++)
				v[i] = (esz == 2) ? *(const uint16_t*)(raw.data() + 2 * i) : *(const uint32_t*)(raw.data() + 4 * i);
		}
	};
	comp = 0;
	while (next) {
		fseek(fp, next, SEEK_SET);
		uint16_t nent; if (fread(&nent, 2, 1, fp) != 1) break;
		std::vector<uint8_t> ent(12 * nent);
		if (fread(ent.data(), 1, 12 * nent, fp) != 12u * nent) break;
		if (fread(&next, 4, 1, fp) != 1) next = 0;
		FrameDir fd{}; fd.rps = 0xFFFFFFFF;
		uint16_t bps = 0, spp = 1, sfmt = 1, predictor = 1;
		for (uint16_t i = 0; i < nent; i++) {
			const uint8_t *e = ent.data() + 12 * i;
			uint16_t tag, type; uint32_t num;
			memcpy(&tag, e, 2); memcpy(&type, e + 2, 2); memcpy(&num, e + 4, 4);
			const uint8_t *val = e + 8;
			switch (tag) {
			case 256: fd.w = *(const uint32_t*)val; if (type == 3) fd.w = *(const uint16_t*)val; break;
			case 257: fd.h = *(const uint32_t*)val; if (type == 3) fd.h = *(const uint16_t*)val; break;
			case 258: bps = *(const uint16_t*)val; break;
			case 259: comp = *(const uint16_t*)val; break;
			case 273: readArr(type, num, val, fd.off); break;
			case 277: spp = *(const uint16_t*)val; break;
			case 278: fd.rps = (type == 3) ? *(const uint16_t*)val : *(const uint32_t*)val; break;
			case 279: readArr(type, num, val, fd.cnt); break;
			case 317: predictor = *(const uint16_t*)val; break;
			case 339: sfmt = *(const uint16_t*)val; break;
			}
		}
		if (bps != 16 || spp != 1 || sfmt != 1 || predictor != 1) {
			fprintf(stderr, "unsupported layout bps=%u spp=%u sfmt=%u pred=%u\n", bps, spp, sfmt, predictor);
			fclose(fp); return false;
		}
		frames.push_back(std::move(fd));
	}
	fclose(fp);
	return !frames.empty();
}

// Flat parallel decode over every (frame, strip) pair: one pread + one inflate
// per strip, straight into the flipped destination row as float.
static double readMovieStripParallel(const std::string &path, int J,
                                     std::vector<FrameDir> &dirs,
                                     std::vector<std::vector<float>> &out)
{
	double t0 = now_s();
	const int nframes = (int)dirs.size();
	struct Job { int f; uint32_t s; };
	std::vector<Job> jobs;
	for (int f = 0; f < nframes; f++) {
		out[f].resize((size_t)dirs[f].w * dirs[f].h);
		for (uint32_t s = 0; s < dirs[f].off.size(); s++) jobs.push_back({f, s});
	}
	int fd = open(path.c_str(), O_RDONLY);
	if (fd < 0) { fprintf(stderr, "open failed\n"); exit(1); }
	#pragma omp parallel num_threads(J)
	{
		std::vector<uint8_t> cbuf, ubuf;
		z_stream zs{};
		inflateInit(&zs);
		#pragma omp for schedule(static)
		for (size_t j = 0; j < jobs.size(); j++) {
			const int f = jobs[j].f;
			const uint32_t s = jobs[j].s;
			const FrameDir &d = dirs[f];
			const size_t csz = d.cnt[s];
			const uint32_t rows = (d.rps == 0xFFFFFFFF) ? d.h
			                    : (uint32_t)std::min<uint64_t>(d.rps, d.h - (uint64_t)s * d.rps);
			const size_t usz = (size_t)rows * d.w * 2;
			if (cbuf.size() < csz) cbuf.resize(csz);
			if (ubuf.size() < usz) ubuf.resize(usz);
			ssize_t got = pread(fd, cbuf.data(), csz, (off_t)d.off[s]);
			if (got != (ssize_t)csz) { fprintf(stderr, "short pread\n"); exit(1); }
			inflateReset(&zs);
			zs.next_in = cbuf.data();   zs.avail_in = (uInt)csz;
			zs.next_out = ubuf.data();  zs.avail_out = (uInt)usz;
			int rc = inflate(&zs, Z_FINISH);
			if (rc != Z_STREAM_END || zs.total_out != usz) {
				fprintf(stderr, "inflate rc=%d out=%lu want=%zu\n", rc, zs.total_out, usz);
				exit(1);
			}
			const uint16_t *src = (const uint16_t*)ubuf.data();
			for (uint32_t r = 0; r < rows; r++) {
				const uint32_t row = (d.rps == 0xFFFFFFFF ? 0 : s * d.rps) + r;
				float *o = out[f].data() + (size_t)(d.h - 1 - row) * d.w;
				const uint16_t *i16 = src + (size_t)r * d.w;
				for (uint32_t x = 0; x < d.w; x++) o[x] = (float)i16[x];
			}
		}
		inflateEnd(&zs);
	}
	close(fd);
	return now_s() - t0;
}

static double checksum(const std::vector<std::vector<float>> &v) {
	double s = 0;
	for (const auto &f : v) { double p = 0; for (float x : f) p += x; s += p; }
	return s;
}

int main(int argc, char **argv) {
	if (argc < 4) { fprintf(stderr, "usage: %s <mode A|B|C> <threads> <tiff> [tiff...]\n", argv[0]); return 2; }
	const char mode = argv[1][0];
	const int J = atoi(argv[2]);
	TIFFSetWarningHandler(NULL);

	double total = 0, csum = 0;
	size_t bytes_out = 0;
	for (int a = 3; a < argc; a++) {
		std::string path = argv[a];
		std::vector<FrameDir> dirs; uint16_t comp = 0;
		if (!parseIFDs(path, dirs, comp)) { fprintf(stderr, "parse failed %s\n", path.c_str()); return 1; }
		const int nframes = (int)dirs.size();
		std::vector<std::vector<float>> out(nframes);
		double t = 0;
		if      (mode == 'A') t = readMovieAsRunnerDoes(path, nframes, J, out);
		else if (mode == 'B') t = readMovieOneHandlePerThread(path, nframes, J, out);
		else if (mode == 'C') t = readMovieStripParallel(path, J, dirs, out);
		else { fprintf(stderr, "bad mode\n"); return 2; }
		total += t;
		csum += checksum(out);
		for (auto &f : out) bytes_out += f.size() * sizeof(float);
		if (a == 3) fprintf(stderr, "  [%s] frames=%d %ux%u rps=%u comp=%u\n",
		                    path.c_str(), nframes, dirs[0].w, dirs[0].h, dirs[0].rps, comp);
	}
	printf("mode=%c threads=%d movies=%d total_s=%.3f per_movie_s=%.3f float_MB=%.1f checksum=%.6e\n",
	       mode, J, argc - 3, total, total / (argc - 3), bytes_out / 1048576.0, csum);
	return 0;
}
