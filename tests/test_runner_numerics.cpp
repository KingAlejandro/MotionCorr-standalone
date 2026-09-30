#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"
#include "src/fftw.h"
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <cstring>
#include <cstdint>
#include <limits>

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
            // Exercises the real production methods MotioncorrRunner::interpolateShifts and
            // MotioncorrRunner::recenterShiftsToFirstFrame -- not a retyped copy of their
            // arithmetic. The only arithmetic reproduced locally is the OLD buggy loop, which
            // is the negative control, not the code under test.
            //
            // Every witness is exactly representable in binary floating point, so expected
            // values are compared with == and no tolerance is needed or used. With equally
            // spaced group centres the interpolation collapses to a straight line,
            // value(f) = x0 + (f - c0)*(x1 - x0)/(c1 - c0), and recentering leaves f*slope.
            // Cases 2 and 3 carry a nonzero interpolated origin on BOTH axes, so the
            // origin_y half of the fix is exercised and not merely implied.
            struct Case {
                const char *name;
                std::vector<int> group_start, group_size;
                std::vector<RFLOAT> xshifts, yshifts;
                int n_frames;
                std::vector<RFLOAT> expect_fixed_x, expect_buggy_x;
                std::vector<RFLOAT> expect_fixed_y, expect_buggy_y;
            };

            const std::vector<Case> cases = {
                // The archived reproducer from the issue. Centres {1,3,5}, collinear slope 1,
                // so value(f) = f - 1 and the origin is -1. Y is deliberately all-zero here so
                // this case reproduces the archived stdout exactly; Y is covered by cases 2-3.
                {"archived witness, slope 1 (X only)", {0,2,4}, {2,2,2}, {0,2,4}, {0,0,0}, 6,
                 {0,1,2,3,4,5}, {0,0,1,2,3,4},
                 {0,0,0,0,0,0}, {0,0,0,0,0,0}},
                // Centres {1,3}. X slope +2 -> value 2f-2, origin -2.
                // Y slope -1.5 -> value -1.5f+1.5, origin +1.5. Nonzero origin on both axes,
                // opposite signs, and -1.5/-4.5/-7.5 are dyadic so still exact.
                {"slope +2 X / -1.5 Y, nonzero origin both axes", {0,2}, {2,2}, {0,4}, {0,-3}, 6,
                 {0,2,4,6,8,10},        {0,0,2,4,6,8},
                 {0,-1.5,-3,-4.5,-6,-7.5}, {0,0,-1.5,-3,-4.5,-6}},
                // Unequal last group (sizes 2,2,4 -> centres {1,3,6}), negative X slopes
                // -1 then -2, and a Y that goes slope +1 then flat. Origins -> X +1, Y -1.
                {"unequal last group, negative X slope, piecewise", {0,2,4}, {2,2,4}, {0,-2,-8}, {0,2,2}, 8,
                 {0,-1,-2,-3,-5,-7,-9,-11}, {0,0,-1,-2,-4,-6,-8,-10},
                 {0,1,2,3,3,3,3,3},         {0,0,1,2,2,2,2,2}},
                // Zero-origin control: centres {1,3} with x1 = 3*x0 makes value(0) exactly 0
                // on both axes, so the corrected and original loops MUST agree bit for bit.
                {"zero-origin control (no-op)", {0,2}, {2,2}, {1,3}, {2,6}, 6,
                 {0,1,2,3,4,5},  {0,1,2,3,4,5},
                 {0,2,4,6,8,10}, {0,2,4,6,8,10}},
            };

            for (const Case &c : cases) {
                const std::string tag = std::string("[") + c.name + "] ";
                std::vector<int> gstart = c.group_start, gsize = c.group_size;
                std::vector<RFLOAT> xs = c.xshifts, ys = c.yshifts;
                std::vector<RFLOAT> ix(c.n_frames), iy(c.n_frames);
                MotioncorrRunner::interpolateShifts(gstart, gsize, xs, ys, c.n_frames, ix, iy);

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
                            tag + "corrected X at frame " + std::to_string(f) + ": got " +
                            std::to_string((double)fixed_x[f]) + " expected " +
                            std::to_string((double)c.expect_fixed_x[f]));
                    require(fixed_y[f] == c.expect_fixed_y[f],
                            tag + "corrected Y at frame " + std::to_string(f) + ": got " +
                            std::to_string((double)fixed_y[f]) + " expected " +
                            std::to_string((double)c.expect_fixed_y[f]));
                    require(buggy_x[f] == c.expect_buggy_x[f],
                            tag + "old-code control X at frame " + std::to_string(f) + ": got " +
                            std::to_string((double)buggy_x[f]) + " expected " +
                            std::to_string((double)c.expect_buggy_x[f]));
                    require(buggy_y[f] == c.expect_buggy_y[f],
                            tag + "old-code control Y at frame " + std::to_string(f) + ": got " +
                            std::to_string((double)buggy_y[f]) + " expected " +
                            std::to_string((double)c.expect_buggy_y[f]));
                }

                // Recentering subtracts one constant from every element, so every relative
                // displacement must survive exactly. Checked with ==, not a tolerance.
                for (int f = 1; f < c.n_frames; f++) {
                    require(fixed_x[f] - fixed_x[f-1] == ix[f] - ix[f-1], tag + "relative X displacement changed");
                    require(fixed_y[f] - fixed_y[f-1] == iy[f] - iy[f-1], tag + "relative Y displacement changed");
                }

                // Pins both the intended change and the no-op case, per axis.
                require((ix[0] == 0) == (buggy_x == fixed_x), tag + "X: old==new iff X origin was already zero");
                require((iy[0] == 0) == (buggy_y == fixed_y), tag + "Y: old==new iff Y origin was already zero");
                const bool noop = (ix[0] == 0 && iy[0] == 0);
                std::cout << "PASS " << c.name << (noop ? " (no-op control)" : " (bug reproduced and fixed)") << "\n";
            }

            // Degenerate input must not read element zero of an empty vector.
            {
                std::vector<RFLOAT> ex, ey;
                MotioncorrRunner::recenterShiftsToFirstFrame(ex, ey);
                require(ex.empty() && ey.empty(), "empty input must stay empty");
                std::cout << "PASS empty-input guard\n";
            }
            std::cout << "PASS issue97 interpolate_recenter\n";
            return 0;
        }
        if (std::string(argv[1]) == "mrc_stats") {
            // The MRC header's amin/amax/amean/arms used to come from four
            // separate full traversals (computeMin, computeMax, computeAvg,
            // computeStddev). computeMinMaxAvgStddev merges them into one, so
            // it has to reproduce all four *to the bit* -- these four numbers
            // are published header fields at offsets 76/80/84/216, and a
            // parity gate compares them.
            //
            // Compared as raw bit patterns, not with ==: NaN != NaN would let a
            // NaN-for-number substitution through, and -0.0 == +0.0 would hide
            // a sign flip.
            auto bits = [](RFLOAT v) {
                static_assert(sizeof(RFLOAT) == sizeof(uint64_t), "expects 64-bit RFLOAT");
                uint64_t u; std::memcpy(&u, &v, sizeof(u)); return u;
            };
            const float qnan = std::numeric_limits<float>::quiet_NaN();
            const float finf = std::numeric_limits<float>::infinity();

            struct Case { const char *name; std::vector<float> v; };
            std::vector<Case> cases = {
                {"empty", {}},
                {"single element", {3.5f}},
                // size 2 is the only size for which the Bessel factor
                // N/(N-1) is not 1 under integer division.
                {"two elements", {-1.25f, 4.75f}},
                {"three elements", {2.0f, -8.0f, 5.5f}},
                // The discriminating case for the naive fusion: seed the
                // minimum from the type's maximum and track it under an
                // `else if`, as computeStats does, and a strictly increasing
                // array never updates it at all. Checked against computeStats
                // below.
                {"strictly increasing", {1.0f, 2.0f, 3.0f, 4.0f, 5.0f}},
                {"strictly decreasing", {5.0f, 4.0f, 3.0f, 2.0f, 1.0f}},
                {"constant", std::vector<float>(1000, -2.75f)},
                {"all negative", {-1.0f, -7.0f, -3.0f, -2.0f}},
                {"NaN in the middle", {1.0f, qnan, -4.0f, 9.0f}},
                {"NaN first", {qnan, 1.0f, -4.0f}},
                {"infinities", {finf, -finf, 0.0f, 1.0f}},
                {"negative zero", {-0.0f, 0.0f}},
            };
            // A large pseudo-random block, so the summation order actually has
            // room to matter: a reassociated or vectorised sum will not land on
            // the same double here, while it would on a handful of elements.
            {
                std::vector<float> big(1 << 18);
                uint32_t state = 0x13572468u;
                for (size_t i = 0; i < big.size(); i++) {
                    state = state * 1664525u + 1013904223u;
                    big[i] = static_cast<float>(static_cast<int32_t>(state)) * 1e-6f;
                }
                cases.push_back({"262144 pseudo-random", big});
            }

            bool naive_fusion_distinguished = false;
            for (const Case &c : cases) {
                MultidimArray<float> a;
                if (!c.v.empty()) {
                    a.resize(1, 1, 1, (long int)c.v.size());
                    for (size_t i = 0; i < c.v.size(); i++) DIRECT_MULTIDIM_ELEM(a, i) = c.v[i];
                }
                const float want_min = a.computeMin(), want_max = a.computeMax();
                const RFLOAT want_avg = a.computeAvg(), want_stddev = a.computeStddev();

                float got_min, got_max; RFLOAT got_avg, got_stddev;
                a.computeMinMaxAvgStddev(got_min, got_max, got_avg, got_stddev);

                require(bits(got_min) == bits(want_min), std::string("min differs: ") + c.name);
                require(bits(got_max) == bits(want_max), std::string("max differs: ") + c.name);
                require(bits(got_avg) == bits(want_avg), std::string("avg differs: ") + c.name);
                require(bits(got_stddev) == bits(want_stddev), std::string("stddev differs: ") + c.name);

                // Negative control: computeStats is the obvious thing to reuse
                // and is wrong here. If it ever agreed on every case, this test
                // would no longer be able to reject that mistake, so demand
                // that at least one case separates them. Five of the cases do;
                // the full mutation record, including one mutation these cases
                // deliberately do NOT reject because it is equivalent, is in
                // docs/output_timing_20260930/mutants.txt.
                if (!c.v.empty()) {
                    RFLOAT s_avg = 0, s_stddev = 0; float s_min = 0, s_max = 0;
                    a.computeStats(s_avg, s_stddev, s_min, s_max);
                    if (bits(s_min) != bits(want_min) || bits(s_max) != bits(want_max))
                        naive_fusion_distinguished = true;
                }
            }
            require(naive_fusion_distinguished,
                    "no case separates computeStats' else-if min tracking from computeMin; "
                    "the test cannot reject that fusion mistake");
            std::cout << "PASS fused MRC header statistics (" << cases.size() << " cases)\n";
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
