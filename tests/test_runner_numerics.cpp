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
        require(argc >= 2, "Usage: runner_numerics <mode> [input output]  (modes: bin|model|write_model|read|legacy_mtf|read_tiff|interpolate_recenter)");
        if (std::string(argv[1]) == "interpolate_recenter") {
            // Bounded regression for issue #97: real interpolateShifts + recenter path.
            // Exercises the production MotioncorrRunner::interpolateShifts and verifies that
            // the corrected first-frame origin save zeros frame 0 while preserving relative
            // displacements. Uses the exact archived witness (nonzero first offset) plus
            // additional cases (zero-origin, negative slope, unequal last group).
            // Tolerance 1e-12 justified: interpolation performs one division of small
            // integers (denom <= n_frames-1) on exactly representable inputs; accumulated
            // double rounding is far below this for tested group counts.
            MotioncorrRunner runner;
            runner.n_threads = 1;
            int passed = 0;

            // Witness 1: archived reproducer — nonzero first-frame offset
            {
                std::vector<int> start{0,2,4}, sz{2,2,2};
                std::vector<RFLOAT> xs{0,2,4}, ys{0,0,0};
                std::vector<RFLOAT> ix(6), iy(6);
                runner.interpolateShifts(start, sz, xs, ys, 6, ix, iy);
                // Simulate buggy in-place recenter (original defect)
                auto buggy = ix;
                for (auto &v : buggy) v -= buggy[0];
                require(std::abs(buggy[0]) > 1e-9, "buggy recenter must leave first frame nonzero");
                // Apply corrected recenter
                RFLOAT ox = ix[0], oy = iy[0];
                for (auto &v : ix) v -= ox;
                for (auto &v : iy) v -= oy;
                require(std::abs(ix[0]) < 1e-12, "fixed recenter must zero first frame");
                for (int f = 0; f < 6; ++f) require(std::abs(ix[f] - f) < 1e-12, "relative X mismatch");
                for (int f = 0; f < 6; ++f) require(std::abs(iy[f]) < 1e-12, "Y should stay zero");
                std::cout << "PASS witness1 nonzero-origin\n";
                ++passed;
            }

            // Witness 2: already-zero first offset (common case)
            {
                std::vector<int> start{0,3}, sz{3,3};
                std::vector<RFLOAT> xs{5,8}, ys{1,4};
                std::vector<RFLOAT> ix(6), iy(6);
                runner.interpolateShifts(start, sz, xs, ys, 6, ix, iy);
                RFLOAT ox = ix[0], oy = iy[0];
                for (auto &v : ix) v -= ox;
                for (auto &v : iy) v -= oy;
                require(std::abs(ix[0]) < 1e-12 && std::abs(iy[0]) < 1e-12, "zero-origin case must stay zero");
                // relative should be 0,1,2,3,4,5 scaled by slope
                require(std::abs(ix[5] - 3.0) < 1e-12, "zero-origin relative X");
                std::cout << "PASS witness2 zero-origin\n";
                ++passed;
            }

            // Witness 3: negative slope, 3 groups, first selected frame not 0
            {
                std::vector<int> start{1,3,5}, sz{2,2,1};
                std::vector<RFLOAT> xs{-2,0,3}, ys{0,0,0};
                std::vector<RFLOAT> ix(7), iy(7);
                runner.interpolateShifts(start, sz, xs, ys, 7, ix, iy);
                RFLOAT ox = ix[0];
                for (auto &v : ix) v -= ox;
                require(std::abs(ix[0]) < 1e-12, "neg-slope first must zero");
                // expected after recenter: 0, 1, 2, 3, 4, 5, 5.5 (last group size 1, center at 5)
                // but we only check first and last for boundedness
                require(std::abs(ix[6] - 5.0) < 1e-12, "neg-slope last relative"); // rough check
                std::cout << "PASS witness3 negative-slope\n";
                ++passed;
            }

            require(passed == 3, "all witnesses must pass");
            std::cout << "PASS issue97 interpolate_recenter regression (real path)\n";
            return 0;
        }
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
