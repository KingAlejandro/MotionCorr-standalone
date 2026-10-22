#include "src/motioncorr_runner.h"
#include "src/renderEER.h"
#include "src/jaz/single_particle/new_ft.h"
#include "src/fftw.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <cstring>
#include <cstdint>
#include <climits>
#include <exception>
#include <limits>
#include <iomanip>
#include <array>

// Compiled only into this test target; CMake extracts the unchanged inline
// production design-matrix/SVD block. No production entry point is added.
ThirdOrderPolynomialModel fitBoundaryProductionAdapter(
    const std::vector<RFLOAT>& frames, const std::vector<RFLOAT>& xs,
    const std::vector<RFLOAT>& ys, const std::vector<RFLOAT>& shifts_x,
    const std::vector<RFLOAT>& shifts_y, int nx, int ny, int& rank, RFLOAT& condition);

void require(bool condition, const std::string &message)
{
    if (!condition) throw std::runtime_error(message);
}

// Independent affine truth and exact rational temporal projection are derived
// in docs/post_rc0/s1/fit_boundary_20261022/{README.md,freeze.py,frozen.json}.
// These are fit-boundary observations, not CCF measurements or movie recovery.
bool fitBoundaryOracle(const std::string& mutation)
{
    require(sizeof(RFLOAT) == sizeof(double), "fit boundary precision budget requires double RFLOAT");
    require(mutation.empty() || mutation == "sign" || mutation == "axis-normalization" ||
            mutation == "frame-origin", "unknown fit boundary mutant");
    constexpr long double coefficient_bound = 1e-7L, field_bound = 2e-5L;
    // P=(T^T T)^-1 T^T, T[f,k]=(f+1/2)^(k+1), evaluated with exact
    // fractions offline. This 3x5 temporal oracle is independent of the native
    // 40/45-by-18 design and Numerical Recipes SVD; no NumPy fit is expected.
    const long double projection[3][5] = {
        {583357.L/606474,119903.L/110268,7775.L/202158,-869603.L/1212948,58451.L/202158},
        {-1792.L/3063,-1778.L/3063,150.L/1021,1792.L/3063,-284.L/1021},
        {25294.L/303237,2077.L/27567,-3610.L/101079,-28357.L/303237,5882.L/101079}
    };
    struct Case {
        const char* name;
        int missing_row, missing_col; // 1-based (iy+1, ix+1), as native logs.
        std::array<long double,5> gx, gy;
        bool exact_global;
    };
    const std::array<long double,5> exact_x = {0,-13.L/16,-26.L/16,-39.L/16,-52.L/16};
    const std::array<long double,5> exact_y = {0,17.L/32,34.L/32,51.L/32,68.L/32};
    const std::vector<Case> cases = {
        {"exact-all9",0,0,exact_x,exact_y,true},
        {"exact-affine-mask",2,1,exact_x,exact_y,true},
        {"exact-noisy-mask",1,3,exact_x,exact_y,true},
        // Decimal globals are literal retained STAR inputs, not pre-write
        // globals. Their member hashes and provenance are in frozen.json.
        {"archive-affine-cpu",0,0,{0,-1,-1.35238L,-1.88095L,-2.88571L},
            {0,.309524L,.733333L,.8L,1.753571L},false},
        {"archive-affine-cuda",2,1,{0,-1.19048L,-1.76190L,-2.39524L,-3.44762L},
            {0,1.1L,1.3L,1.466667L,2.45L},false},
        {"archive-noisy-cpu",0,0,{0,-.90476L,-.90476L,-2.70952L,-3.18452L},
            {0,.898413L,.346032L,1.865079L,1.498413L},false},
        {"archive-noisy-cuda",1,3,{0,-.51190L,-.70714L,-1.72619L,-1.64286L},
            {0,.402778L,.511111L,1.168254L,.152778L},false}
    };
    bool all_pass = true;
    for (const Case& c : cases) {
        std::vector<RFLOAT> frames, xs, ys, shifts_x, shifts_y;
        for (int row=1; row<=3; ++row) for (int col=1; col<=3; ++col) {
            if (row == c.missing_row && col == c.missing_col) continue;
            const int x = 20+42*(col-1), y = 15+32*(row-1);
            // q-forward(q): correction sign; original unbinned pixels per
            // 0-based frame. The two unequal axis normalizations matter.
            const long double rx = -13.L/16 - (.012L*(x-64)-.008L*(y-48))/4;
            const long double ry = 17.L/32 - (.006L*(x-64)-.010L*(y-48))/4;
            std::vector<RFLOAT> lx(5), ly(5), ix(5), iy(5);
            std::vector<int> start={0,1,2,3,4}, size(5,1);
            for (int f=0; f<5; ++f) {
                lx[f] = f*rx-c.gx[f]; ly[f] = f*ry-c.gy[f];
                if (mutation == "sign") { lx[f] = -lx[f]; ly[f] = -ly[f]; }
            }
            // Actual interpolation, as the default non-interpolated production
            // branch uses it to find the first-frame origin. For group=1 this
            // is -.5*E_1. Do not replace it with the analytic expression.
            MotioncorrRunner::interpolateShifts(start,size,lx,ly,5,ix,iy);
            for (int f=0; f<5; ++f) {
                frames.push_back(f + (mutation == "frame-origin" ? 0 : .5));
                xs.push_back(x); ys.push_back(y);
                shifts_x.push_back(lx[f]-ix[0]); shifts_y.push_back(ly[f]-iy[0]);
            }
        }
        require(frames.size() == (c.missing_row ? 40u : 45u), "incorrect observed mask size");
        int rank=0; RFLOAT condition=0;
        ThirdOrderPolynomialModel model = fitBoundaryProductionAdapter(frames,xs,ys,shifts_x,shifts_y,
            mutation == "axis-normalization" ? 96 : 128,
            mutation == "axis-normalization" ? 128 : 96,rank,condition);
        require(rank == 18 && std::isfinite(condition) && condition < 6000,
                std::string(c.name)+": rank/condition admission failed");
        long double temporal[2][3] = {};
        for (int k=0; k<3; ++k) for (int f=0; f<5; ++f) {
            temporal[0][k] += projection[k][f]*(exact_x[f]-c.gx[f]+(exact_x[1]-c.gx[1])/2);
            temporal[1][k] += projection[k][f]*(exact_y[f]-c.gy[f]+(exact_y[1]-c.gy[1])/2);
        }
        long double coefficient_error=0;
        for (int i=0; i<18; ++i) {
            const long double want_x = i<3 ? temporal[0][i] : i==3 ? -48.L/125 : i==9 ? 24.L/125 : 0;
            const long double want_y = i<3 ? temporal[1][i] : i==3 ? -24.L/125 : i==9 ? 6.L/25 : 0;
            require(std::isfinite(model.coeffX(i)) && std::isfinite(model.coeffY(i)), "nonfinite native coefficient");
            coefficient_error = std::max({coefficient_error,std::abs(model.coeffX(i)-want_x),std::abs(model.coeffY(i)-want_y)});
        }
        long double field_error=0, truth_sum=0, truth_max=0;
        size_t count=0;
        // Actual pre-write model evaluation; fixed ROI, every 0-based frame.
        for (int f=0; f<5; ++f) for (int y=12; y<84; ++y) for (int x=12; x<116; ++x) {
            RFLOAT vx,vy;
            require(model.getShiftAt(f,x/128.0-.5,y/96.0-.5,vx,vy)==0, "native model query failed");
            require(std::isfinite(vx) && std::isfinite(vy), "nonfinite native field");
            const long double tx = f*(-13.L/16-(.012L*(x-64)-.008L*(y-48))/4);
            const long double ty = f*(17.L/32-(.006L*(x-64)-.010L*(y-48))/4);
            const long double hx = f*(temporal[0][0]+f*(temporal[0][1]+f*temporal[0][2]));
            const long double hy = f*(temporal[1][0]+f*(temporal[1][1]+f*temporal[1][2]));
            const long double expected_x = tx-exact_x[f]+hx, expected_y = ty-exact_y[f]+hy;
            field_error = std::max(field_error,std::hypot(vx-expected_x,vy-expected_y));
            const long double truth_error = std::hypot(vx+c.gx[f]-tx,vy+c.gy[f]-ty);
            truth_sum += truth_error*truth_error; truth_max = std::max(truth_max,truth_error); ++count;
        }
        const bool pass = coefficient_error<=coefficient_bound && field_error<=field_bound;
        require(mutation.empty() || !pass, std::string(c.name)+": mutant escaped the fixed oracle");
        all_pass &= pass;
        std::cout << std::setprecision(17) << (pass ? "PASS " : "ORACLE REJECT ") << c.name
                  << " mutant=" << (mutation.empty() ? "none" : mutation)
                  << " n=" << frames.size() << " rank=" << rank << " condition=" << condition
                  << " coefficient_max_abs_px=" << coefficient_error << " field_oracle_max_px=" << field_error
                  << " composed_truth_rms_px=" << std::sqrt(truth_sum/count)
                  << " composed_truth_max_px=" << truth_max
                  << (c.exact_global ? " exact-global" : " archived-global-characterization") << '\n';
    }
    return all_pass;
}

int main(int argc, char **argv)
{
    try {
        require(argc >= 2, "Usage: runner_numerics <mode> [input output]");
        if (std::string(argv[1]) == "fit_boundary" || std::string(argv[1]) == "fit_boundary_expect_rejection") {
            const bool expect_rejection = std::string(argv[1]) == "fit_boundary_expect_rejection";
            require(argc == 2 || argc == 3, "fit boundary takes at most one mutant");
            require(!expect_rejection || argc == 3, "expected rejection requires a named mutant");
            const bool accepted = fitBoundaryOracle(argc == 3 ? argv[2] : "");
            if (expect_rejection) {
                require(!accepted, "fit boundary oracle accepted mutant");
                std::cout << "PASS fixed oracle rejected " << argv[2] << '\n';
                return 0;
            }
            return accepted ? 0 : 1;
        }
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
            // Width-agnostic, so the case still builds and still compares bits
            // in a RELION_SINGLE_PRECISION build. There the fused path
            // deliberately delegates to the original four calls, and this case
            // then asserts that delegation is exact -- which is the property
            // that matters in that build.
            auto bits = [](RFLOAT v) {
                static_assert(sizeof(RFLOAT) == sizeof(uint64_t) ||
                              sizeof(RFLOAT) == sizeof(uint32_t),
                              "RFLOAT is expected to be 32- or 64-bit");
                uint64_t u = 0; std::memcpy(&u, &v, sizeof(v)); return u;
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
        if (std::string(argv[1]) == "plot2d_undefined_axis") {
            // Regression for issue #229: MetaDataTable::addToCPlot2D indexed
            // label2offset[xaxis] before checking xaxis == EMDL_UNDEFINED (-1),
            // reading one element before label2offset's storage on every report
            // plot call (MDavg.addToCPlot2D(plot2Db, EMDL_UNDEFINED, label, 1.)).
            struct InspectablePlot2D : CPlot2D {
                using CPlot2D::CPlot2D;
                const std::vector<CDataSet> &dataSets() const { return m_dataSets; }
            };

            const std::vector<RFLOAT> want_y_double = {1.25, 3.5, 0.75, 6.125};
            const std::vector<int> want_y_int = {2, 5, 3, 8};
            MetaDataTable table;
            for (size_t i = 0; i < want_y_double.size(); i++) {
                table.addObject();
                table.setValue(EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL, want_y_double[i]);
                table.setValue(EMDL_IMAGE_OPTICS_GROUP, want_y_int[i]);
                table.setValue(EMDL_MICROGRAPH_NAME, std::string("mic_") + std::to_string(i + 1) + ".mrc");
            }

            InspectablePlot2D plot("summary");
            table.addToCPlot2D(&plot, EMDL_UNDEFINED, EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL, 1.0);
            require(plot.dataSets().size() == 1, "expected 1 dataset after double y plot");
            CDataSet ds_double = plot.dataSets()[0];
            require(ds_double.GetNumberOfDataPointsInSet() == static_cast<int>(want_y_double.size()),
                    "unexpected point count for double y plot");
            for (size_t i = 0; i < want_y_double.size(); i++) {
                CDataPoint pt = ds_double.GetDataPoint(static_cast<int>(i));
                require(pt.GetX() == static_cast<double>(i + 1),
                        "EMDL_UNDEFINED x-axis must produce 1..N at row " + std::to_string(i));
                require(pt.GetY() == static_cast<double>(want_y_double[i]),
                        "unexpected double y value at row " + std::to_string(i));
            }
            require(plot.GetXAxisTitle().empty(), "EMDL_UNDEFINED must leave x-axis title empty");
            require(plot.GetYAxisTitle() == EMDL::label2Str(EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL),
                    "unexpected y-axis title for double y plot");

            table.addToCPlot2D(&plot, EMDL_UNDEFINED, EMDL_IMAGE_OPTICS_GROUP, 1.0);
            require(plot.dataSets().size() == 2, "expected 2 datasets after int y plot");
            CDataSet ds_int = plot.dataSets()[1];
            require(ds_int.GetNumberOfDataPointsInSet() == static_cast<int>(want_y_int.size()),
                    "unexpected point count for int y plot");
            for (size_t i = 0; i < want_y_int.size(); i++) {
                CDataPoint pt = ds_int.GetDataPoint(static_cast<int>(i));
                require(pt.GetX() == static_cast<double>(i + 1),
                        "EMDL_UNDEFINED x-axis must produce 1..N for int y plot at row " + std::to_string(i));
                require(pt.GetY() == static_cast<double>(want_y_int[i]),
                        "unexpected int y value at row " + std::to_string(i));
            }

            table.addToCPlot2D(&plot, EMDL_IMAGE_OPTICS_GROUP, EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL, 1.0);
            require(plot.dataSets().size() == 3, "expected 3 datasets after defined x/y plot");
            CDataSet ds_xy = plot.dataSets()[2];
            for (size_t i = 0; i < want_y_double.size(); i++) {
                CDataPoint pt = ds_xy.GetDataPoint(static_cast<int>(i));
                require(pt.GetX() == static_cast<double>(want_y_int[i]),
                        "defined x-axis value mismatch at row " + std::to_string(i));
                require(pt.GetY() == static_cast<double>(want_y_double[i]),
                        "defined y-axis value mismatch at row " + std::to_string(i));
            }
            require(plot.GetXAxisTitle() == EMDL::label2Str(EMDL_IMAGE_OPTICS_GROUP),
                    "defined x-axis must set x-axis title");

            auto expect_plot_error = [&](EMDLabel x_label, EMDLabel y_label, const char *substr, const char *tag) {
                bool caught = false;
                try {
                    InspectablePlot2D bad_plot;
                    table.addToCPlot2D(&bad_plot, x_label, y_label, 1.0);
                } catch (const RelionError &err) {
                    require(err.msg.find(substr) != std::string::npos,
                            std::string(tag) + ": unexpected error message: " + err.msg);
                    caught = true;
                }
                require(caught, std::string(tag) + ": expected RelionError containing '" + substr + "'");
            };

            expect_plot_error(EMDL_MICROGRAPH_ACCUM_MOTION_EARLY, EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL,
                              "cannot find x-axis label", "missing defined x-label");
            expect_plot_error(EMDL_UNDEFINED, EMDL_MICROGRAPH_ACCUM_MOTION_LATE,
                              "cannot find y-axis label", "missing defined y-label with EMDL_UNDEFINED x-axis");
            expect_plot_error(EMDL_IMAGE_OPTICS_GROUP, EMDL_MICROGRAPH_ACCUM_MOTION_LATE,
                              "cannot find y-axis label", "missing defined y-label with defined x-axis");
            expect_plot_error(EMDL_MICROGRAPH_NAME, EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL,
                              "can only plot x-axis double, int or long int", "non-numeric x-label");
            expect_plot_error(EMDL_UNDEFINED, EMDL_MICROGRAPH_NAME,
                              "can only plot y-axis double, int or long int", "non-numeric y-label");

            std::cout << "PASS addToCPlot2D EMDL_UNDEFINED x-axis and missing-label errors\n";
            return 0;
        }
        if (std::string(argv[1]) == "float_plan_cache") {
            // The ad-hoc float transforms share cached FFTW plans between arrays. Each
            // transform must give the bits a plan made for its own arrays gives, and a
            // plan rebound to new arrays must name those arrays, not the ones it was
            // planned on.
            const int nx = 96, ny = 64;
            const size_t plans_before = NewFFT::cachedFloatPlanCount();
            for (int round = 0; round < 3; round++) {
                MultidimArray<float> real(ny, nx), reference_real(ny, nx);
                MultidimArray<fComplex> cached(ny, nx / 2 + 1), reference(ny, nx / 2 + 1);
                FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(real) {
                    DIRECT_MULTIDIM_ELEM(real, n) = std::sin(0.37f * n) + 0.001f * (n % 17) + round;
                }
                NewFFT::FloatPlan own(real, reference);
                NewFFT::FourierTransform(real, reference, own, NewFFT::FwdOnly);
                NewFFT::FourierTransform(real, cached);
                require(std::memcmp(cached.data, reference.data, sizeof(fComplex) * NZYXSIZE(cached)) == 0,
                        "Cached forward FFT differs from a plan made for the same arrays");
                // The plan made for (real, reference) only accepts those arrays.
                MultidimArray<fComplex> spectrum = cached;
                NewFFT::inverseFourierTransform(spectrum, reference_real, NewFFT::FwdOnly, false);
                NewFFT::inverseFourierTransform(reference, real, own, NewFFT::FwdOnly, false);
                require(std::memcmp(real.data, reference_real.data, sizeof(float) * NZYXSIZE(real)) == 0,
                        "Cached inverse FFT differs from a plan made for the same arrays");
            }
            require(NewFFT::cachedFloatPlanCount() == plans_before + 1,
                    "Three rounds on one geometry must share one cached plan");
            // Arrays that start one float past an aligned address are another FFTW alignment
            // class: they need their own plan, and a repeat of the class reuses it.
            for (int repeat = 0; repeat < 2; repeat++) {
                MultidimArray<float> real_backing(ny * nx + 4), real_view;
                MultidimArray<fComplex> out_backing(ny * (nx / 2 + 1) + 2), ref_backing(ny * (nx / 2 + 1) + 2);
                MultidimArray<fComplex> out_view, ref_view;
                real_view.alias(real_backing);
                real_view.data = real_backing.data + 1;
                real_view.setDimensions(nx, ny, 1, 1);
                out_view.alias(out_backing);
                out_view.data = (fComplex*) ((float*) out_backing.data + 1);
                out_view.setDimensions(nx / 2 + 1, ny, 1, 1);
                ref_view.alias(ref_backing);
                ref_view.data = (fComplex*) ((float*) ref_backing.data + 1);
                ref_view.setDimensions(nx / 2 + 1, ny, 1, 1);
                FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(real_view) {
                    DIRECT_MULTIDIM_ELEM(real_view, n) = std::cos(0.21f * n) + repeat;
                }
                NewFFT::FloatPlan own(real_view, ref_view);
                NewFFT::FourierTransform(real_view, ref_view, own, NewFFT::FwdOnly);
                NewFFT::FourierTransform(real_view, out_view);
                require(std::memcmp(out_view.data, ref_view.data, sizeof(fComplex) * NZYXSIZE(out_view)) == 0,
                        "Cached forward FFT on offset arrays differs from a plan made for them");
                // An FFTW build without SIMD has a single alignment class (always 0); then
                // the offset arrays legitimately share the aligned plan.
                const bool has_classes = fftwf_alignment_of(real_view.data) != fftwf_alignment_of(real_backing.data);
                require(NewFFT::cachedFloatPlanCount() == plans_before + (has_classes ? 2 : 1),
                        "An offset alignment class must add exactly one cached plan, then reuse it");
            }
            MultidimArray<float> a(ny, nx), b(ny, nx), other(ny, nx + 2);
            MultidimArray<fComplex> fa(ny, nx / 2 + 1), fb(ny, nx / 2 + 1);
            NewFFT::FloatPlan planned(a, fa);
            NewFFT::FloatPlan rebound(planned, b, fb);
            require(planned.isCompatible(a) && planned.isCompatible(fa), "Plan does not accept its own arrays");
            require(rebound.isCompatible(b) && rebound.isCompatible(fb), "Rebound plan does not accept the new arrays");
            require(!rebound.isCompatible(a) && !rebound.isCompatible(fa), "Rebound plan still names the original arrays");
            bool rejected = false;
            MultidimArray<fComplex> fother(ny, (nx + 2) / 2 + 1);
            try { NewFFT::FloatPlan wrong(planned, other, fother); } catch (const RelionError&) { rejected = true; }
            require(rejected, "Rebinding a plan to arrays of another size was accepted");
            std::cout << "PASS float plan cache\n";
            return 0;
        }
        if (std::string(argv[1]) == "render_eer") {
            // Render EER groups exactly as MotioncorrRunner does (frames g*G+1 .. (g+1)*G,
            // trailing fractions dropped) and dump the non-zero counts sparsely: one
            // super-resolution frame is up to 8192^2, and synthetic fixtures are sparse.
            // Layout: int64 nx, ny, groups; then per group int64 n, n x int64 index,
            // n x float32 count.
            require(argc == 6, "Usage: runner_numerics render_eer input output upsampling grouping");
            EERRenderer renderer;
            renderer.read(argv[2], textToInteger(argv[4]));
            const int grouping = textToInteger(argv[5]);
            require(grouping > 0, "grouping must be positive");
            const long nx = renderer.getWidth(), ny = renderer.getHeight();
            const long groups = renderer.getNFrames() / grouping;
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open EER dump");
            const long long dims[3] = {nx, ny, groups};
            out.write(reinterpret_cast<const char*>(dims), sizeof(dims));
            MultidimArray<float> frame;
            for (long g = 0; g < groups; g++) {
                renderer.renderFrames(g * grouping + 1, (g + 1) * grouping, frame);
                std::vector<long long> idx;
                std::vector<float> val;
                FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(frame)
                    if (DIRECT_MULTIDIM_ELEM(frame, n) != 0) {
                        idx.push_back(n);
                        val.push_back(DIRECT_MULTIDIM_ELEM(frame, n));
                    }
                const long long count = idx.size();
                out.write(reinterpret_cast<const char*>(&count), sizeof(count));
                out.write(reinterpret_cast<const char*>(idx.data()), sizeof(long long) * count);
                out.write(reinterpret_cast<const char*>(val.data()), sizeof(float) * count);
            }
            out.close();
            require(out.good(), "Failed writing EER dump");
            return 0;
        }
        if (std::string(argv[1]) == "read_tiff_raw") {
            // Dump decoded samples in index order. The row sums the read_tiff
            // mode writes cannot see sample order within a row: swapping the two
            // nibbles of a packed 4-bit byte, for instance, leaves every row sum
            // identical. An optional row bound keeps the dump proportionate to
            // what the caller compares, since one super-resolution frame is
            // 217 MiB.
            require(argc == 4 || argc == 5,
                    "Usage: runner_numerics read_tiff_raw input output [max_rows]");
            Image<float> movie;
            movie.read(argv[2], true, -1, false, true); // all frames, 2D stack
            const long nx = XSIZE(movie()), ny = YSIZE(movie()), nn = NSIZE(movie());
            const long all_rows = ny * nn;
            const long rows = (argc == 5) ? std::min(all_rows, static_cast<long>(textToInteger(argv[4]))) : all_rows;
            require(rows >= 0, "max_rows must not be negative");
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open raw sample output");
            const long dims[3] = {nx, ny, nn};
            out.write(reinterpret_cast<const char*>(dims), sizeof(dims));
            out.write(reinterpret_cast<const char*>(MULTIDIM_ARRAY(movie())),
                      static_cast<std::streamsize>(sizeof(float)) * nx * rows);
            out.close(); // flush before judging success: ~ofstream would swallow it
            require(out.good(), "Failed writing raw samples");
            return 0;
        }

        if (std::string(argv[1]) == "count_eer") {
            require(argc == 6, "Usage: runner_numerics count_eer movie upsampling grouping threads");
            EERRenderer renderer;
            renderer.read(argv[2], textToInteger(argv[3]));
            const int grouping = textToInteger(argv[4]), threads = textToInteger(argv[5]);
            require(grouping > 0 && threads > 0, "grouping and threads must be positive");
            const int groups = renderer.getNFrames() / grouping;
            std::vector<std::exception_ptr> errors(groups);
            long long electrons = 0;
            #pragma omp parallel for num_threads(threads) reduction(+:electrons)
            for (int g = 0; g < groups; g++) {
                try {
                    MultidimArray<float> image;
                    electrons += renderer.renderFrames(g * grouping + 1, (g + 1) * grouping, image);
                } catch (...) {
                    errors[g] = std::current_exception();
                }
            }
            for (const auto &error : errors) if (error) std::rethrow_exception(error);
            std::cout << "electrons " << electrons << '\n';
            return 0;
        }

        if (std::string(argv[1]) == "render_eer_groups") {
            // Render every group of an EER movie the way the runner does: one
            // renderFrames call per group from an OpenMP team, errors captured per
            // group and rethrown on the serial path (#221). Writes, per group, the
            // nonzero pixels as (int64 index, float count) after an int64 header
            // {width, height, groups} and an int64 pair count per group, so a test
            // can compare the decode exactly without writing whole frames.
            require(argc == 7,
                    "Usage: runner_numerics render_eer_groups movie output upsampling grouping threads");
            const int upsampling = textToInteger(argv[4]);
            const int grouping = textToInteger(argv[5]);
            const int threads = textToInteger(argv[6]);
            require(grouping > 0 && threads > 0, "grouping and threads must be positive");
            EERRenderer renderer;
            renderer.read(argv[2], upsampling);
            const int groups = renderer.getNFrames() / grouping;
            std::vector<MultidimArray<float> > images(groups);
            std::vector<std::exception_ptr> errors(groups);
            #pragma omp parallel for num_threads(threads)
            for (int g = 0; g < groups; g++) {
                try {
                    renderer.renderFrames(g * grouping + 1, (g + 1) * grouping, images[g]);
                } catch (...) {
                    errors[g] = std::current_exception();
                }
            }
            for (int g = 0; g < groups; g++)
                if (errors[g]) std::rethrow_exception(errors[g]);
            std::ofstream out(argv[3], std::ios::binary);
            require(out.good(), "Cannot open render output");
            const int64_t head[3] = {renderer.getWidth(), renderer.getHeight(), groups};
            out.write(reinterpret_cast<const char*>(head), sizeof(head));
            for (int g = 0; g < groups; g++) {
                std::vector<std::pair<int64_t, float> > nonzero;
                FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(images[g])
                    if (DIRECT_MULTIDIM_ELEM(images[g], n) != 0)
                        nonzero.emplace_back((int64_t)n, DIRECT_MULTIDIM_ELEM(images[g], n));
                const int64_t count = nonzero.size();
                out.write(reinterpret_cast<const char*>(&count), sizeof(count));
                for (const auto &p : nonzero) {
                    out.write(reinterpret_cast<const char*>(&p.first), sizeof(p.first));
                    out.write(reinterpret_cast<const char*>(&p.second), sizeof(p.second));
                }
            }
            out.close(); // flush before judging success: ~ofstream would swallow it
            require(out.good(), "Failed writing render output");
            return 0;
        }
        if (std::string(argv[1]) == "integer_to_string") {
            // -INT_MIN overflows; the formatted value must still be exact (#221).
            for (int value : {INT_MIN, INT_MIN + 1, -1, 0, 7, INT_MAX})
                require(integerToString(value) == std::to_string(value),
                        "integerToString(" + std::to_string(value) + ") gave " + integerToString(value));
            require(integerToString(INT_MIN, 12) == "-02147483648",
                    "integerToString(INT_MIN, 12) gave " + integerToString(INT_MIN, 12));
            std::cout << "PASS integerToString\n";
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
        if (std::string(argv[1]) == "model_eer") {
            Micrograph parsed(argv[2]);
            std::cout << parsed.getEERUpsampling() << ' ' << parsed.getEERGrouping() << '\n';
            return 0;
        }
        if (std::string(argv[1]) == "model_complete") {
            MotioncorrRunner runner;
            runner.fn_out = std::string(argv[2]) + "/";
            runner.do_dose_weighting = false;
            runner.even_odd_split = false;
            runner.grouping_for_ps = -1;
            std::cout << runner.isMovieComplete(argv[3], 4) << '\n';
            return 0;
        }
        if (std::string(argv[1]) == "model_query") {
            Micrograph parsed(argv[2]);
            RFLOAT x, y;
            const int status = parsed.getShiftAt(std::stod(argv[3]), .25, -.25, x, y);
            std::cout << std::setprecision(17) << status << ' ' << x << ' ' << y << '\n';
            return 0;
        }
        if (std::string(argv[1]) == "model_roundtrip") {
            Micrograph parsed(argv[2]);
            parsed.write(argv[3]);
            return 0;
        }
        if (std::string(argv[1]) == "model_mask") {
            Micrograph parsed(argv[2]);
            if (std::string(argv[3]) == "invalid") {
                // Public in-memory hot-pixel vectors need the same bounds
                // check as saved coordinates, before any mask assignment.
                parsed.hotpixelX.push_back(parsed.getWidth());
                parsed.hotpixelY.push_back(0);
            }
            MultidimArray<bool> mask;
            parsed.fillDefectAndHotpixels(mask);
            long count = 0;
            FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(mask)
                if (DIRECT_MULTIDIM_ELEM(mask, n)) count++;
            std::cout << count << '\n';
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
