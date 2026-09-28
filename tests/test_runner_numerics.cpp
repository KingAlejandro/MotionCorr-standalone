#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"
#include "src/fftw.h"
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

void require(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

int main(int argc, char **argv)
{
    try {
        require(argc >= 2, "Usage: runner_numerics <mode> [input output]");
        if (std::string(argv[1]) == "interpolate_recenter") {
            // Regression for issue #97: --interpolate_shifts recentered every frame against
            // interpolated_xshifts[0] *in place*, so iteration zero zeroed the origin that
            // later iterations still needed. Frames 1..n-1 kept their un-recentered absolute
            // values while frame 0 was forced to zero.
            //
            // This exercises the real production methods MotioncorrRunner::interpolateShifts
            // and MotioncorrRunner::recenterShiftsToFirstFrame -- not a retyped copy of their
            // arithmetic. The only arithmetic reproduced locally is the OLD buggy loop, which
            // is the negative control, not the code under test.
            //
            // Every witness is chosen so that interpolation is exactly representable in
            // binary floating point, so expected values are compared with == and no tolerance
            // is needed or used. With equally spaced group centres the interpolation collapses
            // to a straight line, value(f) = x0 + (f - c0) * (x1 - x0) / (c1 - c0), and
            // recentering to frame 0 leaves exactly (f - 0) * slope.
            MotioncorrRunner runner;

            struct Case {
                const char *name;
                std::vector<int> group_start, group_size;
                std::vector<RFLOAT> xshifts, yshifts;
                int n_frames;
                std::vector<RFLOAT> expect_fixed_x;   // after the corrected recentering
                std::vector<RFLOAT> expect_buggy_x;   // what the original in-place loop produced
            };

            const std::vector<Case> cases = {
                // Collinear 3 groups, centres {1,3,5}, slope 1 -> value(f) = f - 1, origin -1.
                // This is the archived reproducer from the issue.
                {"archived witness (slope 1)", {0,2,4}, {2,2,2}, {0,2,4}, {0,0,0}, 6,
                 {0,1,2,3,4,5}, {0,0,1,2,3,4}},
                // Two groups, centres {1,3}, slope 2 -> value(f) = 2f - 2, origin -2.
                {"slope 2, nonzero origin", {0,2}, {2,2}, {0,4}, {0,0}, 6,
                 {0,2,4,6,8,10}, {0,0,2,4,6,8}},
                // Piecewise: centres {1,3,5}, slope 1 then slope 2. value = f-1, then 2f-4.
                {"piecewise slopes 1 then 2", {0,2,4}, {2,2,2}, {0,2,6}, {0,0,0}, 6,
                 {0,1,2,3,5,7}, {0,0,1,2,4,6}},
                // Zero-origin control: centres {1,3}, x1 = 3*x0 makes value(0) exactly 0,
                // so the corrected and original loops MUST agree bit for bit.
                {"zero-origin control (no-op)", {0,2}, {2,2}, {1,3}, {2,6}, 6,
                 {0,1,2,3,4,5}, {0,1,2,3,4,5}},
            };

            for (const Case &c : cases) {
                const std::string tag = std::string("[") + c.name + "] ";
                std::vector<int> gstart = c.group_start, gsize = c.group_size;
                std::vector<RFLOAT> xs = c.xshifts, ys = c.yshifts;
                std::vector<RFLOAT> ix(c.n_frames), iy(c.n_frames);
                runner.interpolateShifts(gstart, gsize, xs, ys, c.n_frames, ix, iy);

                // Negative control: the ORIGINAL in-place loop, reproduced verbatim.
                std::vector<RFLOAT> buggy_x = ix, buggy_y = iy;
                for (int f = 0; f < c.n_frames; f++) {
                    buggy_x[f] -= buggy_x[0];
                    buggy_y[f] -= buggy_y[0];
                }

                // Code under test: the real production method.
                std::vector<RFLOAT> fixed_x = ix, fixed_y = iy;
                MotioncorrRunner::recenterShiftsToFirstFrame(fixed_x, fixed_y);

                require(fixed_x[0] == 0 && fixed_y[0] == 0, tag + "frame 0 must be exactly the origin");
                for (int f = 0; f < c.n_frames; f++) {
                    require(fixed_x[f] == c.expect_fixed_x[f],
                            tag + "corrected X differs at frame " + std::to_string(f) +
                            ": got " + std::to_string((double)fixed_x[f]) +
                            " expected " + std::to_string((double)c.expect_fixed_x[f]));
                    require(buggy_x[f] == c.expect_buggy_x[f],
                            tag + "old-code control X differs at frame " + std::to_string(f) +
                            ": got " + std::to_string((double)buggy_x[f]) +
                            " expected " + std::to_string((double)c.expect_buggy_x[f]));
                }

                // Recentering subtracts one constant from every element, so every relative
                // displacement must survive exactly. Checked with ==, not a tolerance.
                for (int f = 1; f < c.n_frames; f++) {
                    require(fixed_x[f] - fixed_x[f-1] == ix[f] - ix[f-1], tag + "relative X displacement changed");
                    require(fixed_y[f] - fixed_y[f-1] == iy[f] - iy[f-1], tag + "relative Y displacement changed");
                }

                const bool origin_was_zero = (ix[0] == 0 && iy[0] == 0);
                const bool identical = (buggy_x == fixed_x && buggy_y == fixed_y);
                require(origin_was_zero == identical,
                        tag + "old and new output must agree exactly iff the interpolated origin was already zero");
                std::cout << "PASS " << c.name << (origin_was_zero ? " (no-op control)" : " (bug reproduced and fixed)") << "\n";
            }
            std::cout << "PASS issue97 interpolate_recenter\n";
            return 0;
        }
        require(argc == 4, "Usage: runner_numerics bin|model|write_model|read|legacy_mtf|read_tiff input output");
        if (std::string(argv[1]) == "read_tiff") {
            // Dump per-row sums of a decoded TIFF stack. Row sums are exact in
            // double for integer sample values, and any row-striding or Y-flip
            // error relocates whole rows, so this detects those exactly while
            // staying small enough for the large packed-4-bit geometries.
            Image<float> movie;
            movie.read(argv[2], true, -1, false, true); // all frames, 2D stack
            const long nx = XSIZE(movie()), ny = YSIZE(movie()), nn = NSIZE(movie());
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open row-sum output");
            const long dims[3] = {nx, ny, nn};
            out.write(reinterpret_cast<const char*>(dims), sizeof(dims));
            for (long n = 0; n < nn; n++) {
                for (long y = 0; y < ny; y++) {
                    double rowsum = 0.0;
                    for (long x = 0; x < nx; x++)
                        rowsum += DIRECT_NZYX_ELEM(movie(), n, 0, y, x);
                    out.write(reinterpret_cast<const char*>(&rowsum), sizeof(double));
                }
            }
            require(out.good(), "Failed writing row sums");
            return 0;
        }
        if (std::string(argv[1]) == "read") {
            Micrograph parsed(argv[2]);
            return 0;
        }
        if (std::string(argv[1]) == "legacy_mtf") {
            MetaDataTable table;
            table.read(argv[2]);
            int group;
            std::string filename;
            require(table.numberOfObjects() == 1 && table.getValue(EMDL_IMAGE_OPTICS_GROUP, group) && group == 1 &&
                    table.getValue(EMDL_IMAGE_MTF_FILENAME, filename) && filename.empty(),
                    "Legacy empty trailing MTF filename was not preserved");
            return 0;
        }
        MotioncorrRunner runner;
        runner.n_threads = 1;
        if (std::string(argv[1]) == "bin") {
            Image<float> expected, actual;
            expected.read(argv[2]);
            actual.read(argv[3]);
            const int nx = XSIZE(expected()), ny = YSIZE(expected());
            MultidimArray<fComplex> full(ny, nx / 2 + 1), binned(ny / 2, nx / 4 + 1);
            NewFFT::FourierTransform(expected(), full);
            cropInFourierSpace(full, binned);
            expected().reshape(ny / 2, nx / 2);
            NewFFT::inverseFourierTransform(binned, expected());
            require(expected().sameShape(actual()), "Late-binned image has the wrong dimensions");
            float maximum = 0;
            FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(expected()) {
                require(std::isfinite(DIRECT_MULTIDIM_ELEM(actual(), n)), "Nonfinite binned output");
                maximum = std::max(maximum, std::abs(DIRECT_MULTIDIM_ELEM(expected(), n) - DIRECT_MULTIDIM_ELEM(actual(), n)));
            }
            require(maximum == 0, "Late-bin output differs from binning the completed full-size sum: " + std::to_string(maximum));
            std::cout << "PASS exact late-bin sum\n";
        } else {
            runner.fn_out = argv[3];
            runner.angpix = 1;
            runner.voltage = 300;
            runner.dose_per_frame = 1;
            runner.fn_defect = "";
            runner.bin_factor = 2;
            runner.do_own = true;
            Micrograph movie(argv[2], "", 2);
            movie.first_frame = 2;
            auto *poly = new ThirdOrderPolynomialModel;
            poly->coeffX.resize(18);
            poly->coeffY.resize(18);
            for (int i = 0; i < 18; ++i) {
                poly->coeffX(i) = (i + 1) / 16.0;
                poly->coeffY(i) = -(i + 1) / 32.0;
            }
            movie.model = poly;
            for (int frame = 1; frame <= movie.getNframes(); ++frame) movie.setGlobalShift(frame, 1.5, -2.5);
            const FileName output = runner.getOutputFileNames(argv[2]).withoutExtension() + ".star";
            if (std::string(argv[1]) == "write_model") {
                runner.early_binning = false;
                runner.saveModel(movie);
                return 0;
            }
            for (bool early : {false, true}) {
                runner.early_binning = early;
                for (int repeat = 0; repeat < 2; ++repeat) {
                    runner.saveModel(movie);
                    Micrograph restored(output);
                    for (int frame = 2; frame <= 5; ++frame) {
                        RFLOAT localX, localY, x, y;
                        poly->getShiftAt(frame - movie.first_frame, .25, -.25, localX, localY);
                        restored.getShiftAt(frame, .25, -.25, x, y);
                        const RFLOAT scale = early ? 2 : 1;
                        require(x == localX * scale + 1.5 && y == localY * scale - 2.5,
                                "Exported local shifts are not in original-pixel units");
                    }
                    require(poly->coeffX(0) == 1.0 / 16 && poly->coeffY(17) == -18.0 / 32,
                            "Saving mutated the runtime model");
                }
            }
            std::cout << "PASS serialized units and unchanged runtime model\n";
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    } catch (RelionError &error) {
        std::cerr << error;
        return 1;
    }
}
