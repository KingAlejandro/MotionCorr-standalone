/* Evidence harness for PR #90 (issue #85): dump a decoded movie buffer in full.
 *
 * The in-tree TIFF check (tests/test_tiff_read.py, via runner_numerics
 * read_tiff) compares per-row sums. Review on PR #90 records that row sums
 * cannot prove ordered-pixel or packed-nibble layout: any permutation within a
 * row leaves every row sum unchanged. This harness writes the decoded buffer
 * itself, in memory order, so the same decode can be compared pixel by pixel
 * between two builds.
 *
 * It is deliberately out of tree. It is not referenced by CMakeLists.txt and is
 * compiled by build_harness.sh against the already-built libmotioncorr_core.a,
 * so the product binary's compiled paths are identical to the code head.
 *
 * Output: little-endian, int64 nx, ny, nn, then nx*ny*nn float32 pixels in
 * DIRECT_NZYX_ELEM(n, 0, y, x) order, x fastest.
 *
 * Part of MotionCorr-standalone, derived from RELION. GPL-2.0-or-later.
 */
#include "src/image.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>

int main(int argc, char **argv)
{
    if (argc != 3) {
        std::cerr << "Usage: dump_decoded_movie <movie> <output.bin>" << std::endl;
        return 2;
    }
    try {
        Image<float> movie;
        // Same call the in-tree read_tiff helper uses: all frames, 2D stack.
        movie.read(argv[1], true, -1, false, true);

        const long nx = XSIZE(movie()), ny = YSIZE(movie()), nn = NSIZE(movie());
        std::ofstream out(argv[2], std::ios::binary);
        if (!out.good()) {
            std::cerr << "Cannot open output " << argv[2] << std::endl;
            return 3;
        }
        const long dims[3] = {nx, ny, nn};
        out.write(reinterpret_cast<const char*>(dims), sizeof(dims));

        // Write row by row rather than one block, so the dump is defined by the
        // documented element accessor and not by any assumption that the
        // MultidimArray is contiguous.
        for (long n = 0; n < nn; n++)
            for (long y = 0; y < ny; y++)
                for (long x = 0; x < nx; x++) {
                    const float v = DIRECT_NZYX_ELEM(movie(), n, 0, y, x);
                    out.write(reinterpret_cast<const char*>(&v), sizeof(float));
                }

        out.flush();
        if (!out.good()) {
            std::cerr << "Failed writing pixels" << std::endl;
            return 3;
        }
        std::cout << "dims " << nx << " " << ny << " " << nn
                  << " pixels " << (nx * ny * nn) << std::endl;
        return 0;
    } catch (RelionError &err) {
        // RelionError does not derive from std::exception, so it needs its own
        // handler for the named-failure evidence to record the message.
        std::cerr << "EXCEPTION: RelionError: " << err.msg
                  << " (" << err.file << ":" << err.line << ")" << std::endl;
        return 4;
    } catch (const std::exception &err) {
        std::cerr << "EXCEPTION: " << err.what() << std::endl;
        return 4;
    } catch (...) {
        std::cerr << "EXCEPTION: unknown" << std::endl;
        return 4;
    }
}
