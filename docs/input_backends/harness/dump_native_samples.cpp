/* Decoded-sample oracle, producer half.
 *
 * Dumps the movie exactly as the compact ingest route stages it: the same
 * Image<T>::read call, the same sample type, the same memory order. What this
 * writes is byte-for-byte what applyGainDefectsAndSumU8/U16 uploads, so a
 * defect anywhere between TIFFReadScanline and the staged buffer is visible
 * here and not only in a corrected image where a gain, an alignment and a dose
 * weight have had a chance to hide it.
 *
 * Deliberately out of tree and not referenced by CMakeLists.txt: it is compiled
 * against the already-built libmotioncorr_core.a so the production decode path
 * is the one under test, not a recompilation of it.
 *
 * Output: little-endian int64 nx, ny, nn, int64 bytes-per-sample, then
 * nx*ny*nn native samples in DIRECT_NZYX_ELEM(n, 0, y, x) order, x fastest.
 *
 * Part of MotionCorr-standalone, derived from RELION. GPL-2.0-or-later.
 */
#include "src/image.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

namespace {

template <typename T>
int dump(const char *movie_path, const char *out_path, int n_frames)
{
	std::vector<Image<T> > frames(n_frames);
	for (int i = 0; i < n_frames; i++)
		frames[i].read(movie_path, true, i, false, true);

	const long nx = XSIZE(frames[0]()), ny = YSIZE(frames[0]());
	std::ofstream out(out_path, std::ios::binary);
	if (!out.good()) { std::cerr << "Cannot open " << out_path << std::endl; return 3; }
	const long long head[4] = {nx, ny, (long long)n_frames, (long long)sizeof(T)};
	out.write(reinterpret_cast<const char *>(head), sizeof(head));
	for (int n = 0; n < n_frames; n++)
		for (long y = 0; y < ny; y++)
			for (long x = 0; x < nx; x++) {
				const T v = DIRECT_A2D_ELEM(frames[n](), y, x);
				out.write(reinterpret_cast<const char *>(&v), sizeof(T));
			}
	out.flush();
	if (!out.good()) { std::cerr << "Failed writing samples" << std::endl; return 3; }
	std::printf("%ld %ld %d %zu\n", nx, ny, n_frames, sizeof(T));
	return 0;
}

} // namespace

int main(int argc, char **argv)
{
	if (argc != 3) {
		std::cerr << "Usage: dump_native_samples <movie> <output.bin>" << std::endl;
		return 2;
	}
	try {
		// Ask the header which sample type the file actually holds, exactly as
		// the runner's routing decision does, rather than taking it from a flag:
		// a dump that chose the wrong type would compare a reinterpretation
		// against the truth and could still agree on a low-count movie.
		Image<float> head;
		head.read(argv[1], false, -1, false, true);
		const int n_frames = (int)NSIZE(head());
		const DataType dt = head.dataType();
		if (dt == UChar)  return dump<unsigned char>(argv[1], argv[2], n_frames);
		if (dt == UShort) return dump<unsigned short>(argv[1], argv[2], n_frames);
		std::cerr << "dump_native_samples: sample type " << (int)dt
		          << " is not one the compact route stages" << std::endl;
		return 4;
	} catch (RelionError &e) {
		std::cerr << "RelionError while reading " << argv[1] << std::endl;
		return 1;
	}
}
