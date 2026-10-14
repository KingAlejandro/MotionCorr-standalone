/***************************************************************************
 *
 * Author: "Sjors H.W. Scheres"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/
#include "cpu_separate_sum_reference.h"
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>

// Compares actual production streaming reconstruction with the frozen #178
// caller. Includes scratch allocation, float interpolation and accumulation;
// it is a reconstruction-stage benchmark, not a complete movie benchmark.
int main(int argc, char **argv) {
    try {
        if (argc != 7) throw std::runtime_error("usage: cpu_fused_sums_bench nx ny frames threads pairs null|polynomial");
        auto number = [](const char *s) {
            char *end = nullptr;
            long n = std::strtol(s, &end, 10);
            if (!end || *end || n < 1 || n > 100000) throw std::runtime_error("invalid positive dimension/count");
            return static_cast<int>(n);
        };
        const int nx = number(argv[1]), ny = number(argv[2]), count = number(argv[3]);
        const int threads = number(argv[4]), pairs = number(argv[5]);
        const std::string mode = argv[6];
        if (mode != "null" && mode != "polynomial") throw std::runtime_error("invalid model");
        MotioncorrRunner runner; runner.n_threads = threads;
        ThirdOrderPolynomialModel polynomial;
        polynomial.coeffX.initZeros(18); polynomial.coeffY.initZeros(18);
        polynomial.coeffX(0) = 0.37; polynomial.coeffX(4) = 0.013;
        polynomial.coeffX(11) = -0.0003;
        polynomial.coeffY(0) = -0.23; polynomial.coeffY(7) = 0.021;
        polynomial.coeffY(15) = 0.017;
        MotionModel *model = mode == "polynomial" ? &polynomial : nullptr;
        std::vector<Image<float>> frames(count);
        for (int f = 0; f < count; ++f) {
            frames[f]().reshape(ny, nx);
            for (size_t n = 0; n < frames[f]().nzyxdim; ++n)
                frames[f]().data[n] = static_cast<float>((n * 17 + f * 23) % 101) - 50.0f +
                    0.13f * static_cast<float>((n + f) % 7);
        }
        Image<float> base, base_even, base_odd, candidate, even, odd;
        for (auto *image : {&base, &base_even, &base_odd, &candidate, &even, &odd})
            (*image)().initZeros(ny, nx);
        auto run = [&](bool fused) {
            Image<float> &sum = fused ? candidate : base;
            Image<float> &split_even = fused ? even : base_even;
            Image<float> &split_odd = fused ? odd : base_odd;
            // Reinitialize output bytes before each timed reconstruction.
            sum().initZeros(); split_even().initZeros(); split_odd().initZeros();
            std::ostringstream log;
            const auto begin = std::chrono::steady_clock::now();
            if (fused) MotioncorrRunnerTestAccess::stream(runner, sum, &split_even, &split_odd, frames, model, log);
            else MotioncorrRunnerTestAccess::separate(runner, sum, &split_even, &split_odd, frames, model, log);
            return std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
        };
        auto identical = [&] {
            const size_t bytes = base().nzyxdim * sizeof(float);
            return std::memcmp(base().data, candidate().data, bytes) == 0 &&
                std::memcmp(base_even().data, even().data, bytes) == 0 &&
                std::memcmp(base_odd().data, odd().data, bytes) == 0;
        };
        for (int pair = -1; pair < pairs; ++pair) {
            double a, b;
            if (pair % 2 == 0) { a = run(false); b = run(true); }
            else { b = run(true); a = run(false); }
            if (!identical()) throw std::runtime_error("fused reconstruction differs from #178");
            std::cout << std::setprecision(12) << "{\"pair\":" << pair <<
                ",\"warmup\":" << (pair < 0 ? "true" : "false") <<
                ",\"nx\":" << nx << ",\"ny\":" << ny << ",\"frames\":" << count <<
                ",\"threads\":" << threads << ",\"model\":\"" << mode <<
                "\",\"baseline_seconds\":" << a << ",\"candidate_seconds\":" << b <<
                ",\"bitwise_equal\":true}" << std::endl;
        }
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
