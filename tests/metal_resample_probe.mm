#define UInt MacUInt
#define Boolean MacBoolean
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#undef UInt
#undef Boolean

#include "src/acc/metal/metal_resample.h"
#include <iostream>
#include <iomanip>
#include <vector>
#include <cmath>
#include <chrono>
#include <random>
#include <cassert>

// Reference CPU implementation of ThirdOrderPolynomial realSpaceInterpolation
static void cpuRealSpaceInterpolation(
    std::vector<float> &Isum,
    const std::vector<float> &Iframes,
    const float *coeffX,
    const float *coeffY,
    int nx, int ny, int n_frames,
    const float *frame_weights = nullptr
) {
    Isum.assign((size_t)nx * ny, 0.0f);
    const size_t frame_stride = (size_t)nx * ny;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        const float z = (float)iframe;
        const float z2 = z * z;
        const float z3 = z * z2;

        const float x_C0 = coeffX[0]  * z + coeffX[1]  * z2 + coeffX[2]  * z3;
        const float x_C1 = coeffX[3]  * z + coeffX[4]  * z2 + coeffX[5]  * z3;
        const float x_C2 = coeffX[6]  * z + coeffX[7]  * z2 + coeffX[8]  * z3;
        const float x_C3 = coeffX[9]  * z + coeffX[10] * z2 + coeffX[11] * z3;
        const float x_C4 = coeffX[12] * z + coeffX[13] * z2 + coeffX[14] * z3;
        const float x_C5 = coeffX[15] * z + coeffX[16] * z2 + coeffX[17] * z3;

        const float y_C0 = coeffY[0]  * z + coeffY[1]  * z2 + coeffY[2]  * z3;
        const float y_C1 = coeffY[3]  * z + coeffY[4]  * z2 + coeffY[5]  * z3;
        const float y_C2 = coeffY[6]  * z + coeffY[7]  * z2 + coeffY[8]  * z3;
        const float y_C3 = coeffY[9]  * z + coeffY[10] * z2 + coeffY[11] * z3;
        const float y_C4 = coeffY[12] * z + coeffY[13] * z2 + coeffY[14] * z3;
        const float y_C5 = coeffY[15] * z + coeffY[16] * z2 + coeffY[17] * z3;

        const float *frame_ptr = Iframes.data() + (size_t)iframe * frame_stride;
        const float weight = (frame_weights != nullptr) ? frame_weights[iframe] : 1.0f;

        for (int iy = 0; iy < ny; iy++) {
            const float y = (float)iy / (float)ny - 0.5f;
            for (int ix = 0; ix < nx; ix++) {
                const float x = (float)ix / (float)nx - 0.5f;
                bool valid = true;

                float x_fitted, y_fitted;
                if (iframe == 0) {
                    x_fitted = (float)ix;
                    y_fitted = (float)iy;
                } else {
                    float x_shift = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
                    float y_shift = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;
                    x_fitted = (float)ix - x_shift;
                    y_fitted = (float)iy - y_shift;
                }

                int x0 = (int)floor(x_fitted);
                int y0 = (int)floor(y_fitted);
                const int x1 = x0 + 1;
                const int y1 = y0 + 1;

                if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
                if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
                if (x1 >= nx || x0 >= nx - 1) { x0 = nx - 1; valid = false; }
                if (y1 >= ny || y0 >= ny - 1) { y0 = ny - 1; valid = false; }

                if (!valid) {
                    Isum[iy * nx + ix] += frame_ptr[y0 * nx + x0] * weight;
                    continue;
                }

                const float fx = x_fitted - (float)x0;
                const float fy = y_fitted - (float)y0;

                const float d00 = frame_ptr[y0 * nx + x0];
                const float d01 = frame_ptr[y0 * nx + x1];
                const float d10 = frame_ptr[y1 * nx + x0];
                const float d11 = frame_ptr[y1 * nx + x1];

                const float dx0 = d00 + (d01 - d00) * fx;
                const float dx1 = d10 + (d11 - d10) * fx;
                const float val = dx0 + (dx1 - dx0) * fy;

                Isum[iy * nx + ix] += val * weight;
            }
        }
    }
}

struct ParityStats {
    double max_diff;
    double mean_diff;
    double rmse;
    double rel_rmse;
    double cpu_norm;
    double max_val;
    double min_val;
    bool passed_component_parity;
};

static ParityStats evaluateParity(
    const std::vector<float> &gpu_out,
    const std::vector<float> &cpu_out,
    double component_rel_rmse_thresh = 0.001,
    double component_max_diff_thresh = 5.0
) {
    assert(gpu_out.size() == cpu_out.size());
    size_t n = gpu_out.size();

    double max_d = 0.0;
    double sum_d = 0.0;
    double sum_sq_d = 0.0;
    double sum_sq_cpu = 0.0;
    double max_v = -1e30, min_v = 1e30;

    for (size_t i = 0; i < n; i++) {
        double g = (double)gpu_out[i];
        double c = (double)cpu_out[i];
        double diff = std::abs(g - c);

        if (diff > max_d) max_d = diff;
        sum_d += diff;
        sum_sq_d += diff * diff;
        sum_sq_cpu += c * c;

        if (c > max_v) max_v = c;
        if (c < min_v) min_v = c;
    }

    double mean_d = sum_d / n;
    double rmse = std::sqrt(sum_sq_d / n);
    double cpu_norm = std::sqrt(sum_sq_cpu / n);
    double rel_rmse = (cpu_norm > 1e-12) ? (rmse / cpu_norm) : 0.0;

    bool pass = (rel_rmse <= component_rel_rmse_thresh) && (max_d <= component_max_diff_thresh);

    return {max_d, mean_d, rmse, rel_rmse, cpu_norm, max_v, min_v, pass};
}

int main(int argc, char **argv) {
    std::cout << "=================================================================" << std::endl;
    std::cout << "  MotionCorr Metal GPU Resampling Test Harness (Issue #35 Phase 2)" << std::endl;
    std::cout << "=================================================================" << std::endl;

    const int nx = 512;
    const int ny = 512;
    const int n_frames = 16;
    const size_t total_pixels = (size_t)nx * ny * n_frames;

    std::cout << "Test Configuration:" << std::endl;
    std::cout << "  Dimensions: " << nx << " x " << ny << std::endl;
    std::cout << "  Frames:     " << n_frames << std::endl;
    std::cout << "  Total Pixels to Resample: " << total_pixels << std::endl;

    // Generate synthetic frames with structured background and Gaussian features
    std::vector<float> Iframes(total_pixels);
    std::mt19937 rng(42);
    std::normal_distribution<float> noise(100.0f, 15.0f);

    for (size_t i = 0; i < total_pixels; i++) {
        Iframes[i] = noise(rng);
    }

    // Add some 2D synthetic features (disc and Gaussian blobs)
    for (int iframe = 0; iframe < n_frames; iframe++) {
        float *frame_ptr = Iframes.data() + (size_t)iframe * nx * ny;
        for (int b = 0; b < 20; b++) {
            float cx = 50.0f + (b % 5) * 90.0f + 10.0f * std::sin((float)iframe + b);
            float cy = 50.0f + (b / 5) * 110.0f + 8.0f * std::cos((float)iframe + b);
            float sigma = 6.0f + (b % 4) * 2.0f;
            float amp = 150.0f + (b % 3) * 50.0f;

            int xmin = std::max(0, (int)(cx - 3 * sigma));
            int xmax = std::min(nx - 1, (int)(cx + 3 * sigma));
            int ymin = std::max(0, (int)(cy - 3 * sigma));
            int ymax = std::min(ny - 1, (int)(cy + 3 * sigma));

            for (int y = ymin; y <= ymax; y++) {
                for (int x = xmin; x <= xmax; x++) {
                    float dx = (float)x - cx;
                    float dy = (float)y - cy;
                    frame_ptr[y * nx + x] += amp * std::exp(-(dx * dx + dy * dy) / (2.0f * sigma * sigma));
                }
            }
        }
    }

    // Define 18-parameter polynomial motion model:
    // Models global drift + spatial skew + quadratic distortion across time
    std::vector<float> coeffX(18, 0.0f);
    std::vector<float> coeffY(18, 0.0f);

    // X drift: global linear + acceleration + spatial distortion
    coeffX[0]  = 0.45f;    // z
    coeffX[1]  = -0.015f;  // z^2
    coeffX[2]  = 0.0003f;  // z^3
    coeffX[3]  = 0.08f;    // x * z
    coeffX[4]  = -0.002f;  // x * z^2
    coeffX[6]  = 0.02f;    // x^2 * z
    coeffX[9]  = -0.05f;   // y * z
    coeffX[12] = 0.01f;    // y^2 * z
    coeffX[15] = 0.015f;   // x * y * z

    // Y drift: global drift + spatial expansion
    coeffY[0]  = -0.35f;   // z
    coeffY[1]  = 0.02f;    // z^2
    coeffY[2]  = -0.0004f; // z^3
    coeffY[3]  = -0.04f;   // x * z
    coeffY[9]  = 0.06f;    // y * z
    coeffY[10] = -0.001f;  // y * z^2
    coeffY[12] = -0.015f;  // y^2 * z
    coeffY[15] = -0.01f;   // x * y * z

    // -------------------------------------------------------------
    // Test Case 1: Uniform Accumulation (No Dose Weights)
    // -------------------------------------------------------------
    std::cout << "\n-------------------------------------------------------------" << std::endl;
    std::cout << "Test Case 1: Standard Bilinear Resampling (Uniform Weights)" << std::endl;
    std::cout << "-------------------------------------------------------------" << std::endl;

    std::vector<float> cpu_out((size_t)nx * ny, 0.0f);
    auto t_cpu_start = std::chrono::high_resolution_clock::now();
    cpuRealSpaceInterpolation(cpu_out, Iframes, coeffX.data(), coeffY.data(), nx, ny, n_frames, nullptr);
    auto t_cpu_end = std::chrono::high_resolution_clock::now();
    double cpu_time = std::chrono::duration<double>(t_cpu_end - t_cpu_start).count();
    std::cout << "  CPU Wall Time: " << std::fixed << std::setprecision(4) << cpu_time * 1000.0 << " ms" << std::endl;

    std::vector<float> gpu_out((size_t)nx * ny, 0.0f);
    auto t_gpu_start = std::chrono::high_resolution_clock::now();
    bool status = metalRealSpaceInterpolationRaw(
        Iframes.data(),
        gpu_out.data(),
        coeffX.data(),
        coeffY.data(),
        nx, ny, n_frames,
        0, // device_id
        std::cout,
        nullptr // no weights
    );
    auto t_gpu_end = std::chrono::high_resolution_clock::now();
    double gpu_time = std::chrono::duration<double>(t_gpu_end - t_gpu_start).count();
    std::cout << "  GPU Dispatch Time: " << std::fixed << std::setprecision(4) << gpu_time * 1000.0 << " ms" << std::endl;
    assert(status && "metalRealSpaceInterpolationRaw failed");

    ParityStats stats1 = evaluateParity(gpu_out, cpu_out);
    std::cout << "\n  [Parity Metrics - Test 1]:" << std::endl;
    std::cout << "    Max Pixel Difference:  " << std::scientific << std::setprecision(6) << stats1.max_diff << " (component threshold: <= 5.0)" << std::endl;
    std::cout << "    Mean Pixel Difference: " << std::scientific << std::setprecision(6) << stats1.mean_diff << std::endl;
    std::cout << "    RMSE:                  " << std::scientific << std::setprecision(6) << stats1.rmse << std::endl;
    std::cout << "    Relative Image RMSE:   " << std::scientific << std::setprecision(6) << stats1.rel_rmse << " (" << std::fixed << std::setprecision(4) << stats1.rel_rmse * 100.0 << "%, component threshold: <= 0.1%)" << std::endl;
    std::cout << "    Component Parity Status:         " << (stats1.passed_component_parity ? "PASSED" : "FAILED") << std::endl;

    // -------------------------------------------------------------
    // Test Case 2: Dose-Weighted Accumulation
    // -------------------------------------------------------------
    std::cout << "\n-------------------------------------------------------------" << std::endl;
    std::cout << "Test Case 2: Dose-Weighted Bilinear Resampling" << std::endl;
    std::cout << "-------------------------------------------------------------" << std::endl;

    // Dose weights simulating decay across frames
    std::vector<float> frame_weights(n_frames);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        frame_weights[iframe] = std::exp(-0.06f * (float)iframe);
    }

    std::vector<float> cpu_out_dw((size_t)nx * ny, 0.0f);
    cpuRealSpaceInterpolation(cpu_out_dw, Iframes, coeffX.data(), coeffY.data(), nx, ny, n_frames, frame_weights.data());

    std::vector<float> gpu_out_dw((size_t)nx * ny, 0.0f);
    status = metalRealSpaceInterpolationRaw(
        Iframes.data(),
        gpu_out_dw.data(),
        coeffX.data(),
        coeffY.data(),
        nx, ny, n_frames,
        0,
        std::cout,
        frame_weights.data()
    );
    assert(status && "metalRealSpaceInterpolationRaw (dose-weighted) failed");

    ParityStats stats2 = evaluateParity(gpu_out_dw, cpu_out_dw);
    std::cout << "\n  [Parity Metrics - Test 2 (Dose-Weighted)]:" << std::endl;
    std::cout << "    Max Pixel Difference:  " << std::scientific << std::setprecision(6) << stats2.max_diff << " (component threshold: <= 5.0)" << std::endl;
    std::cout << "    Mean Pixel Difference: " << std::scientific << std::setprecision(6) << stats2.mean_diff << std::endl;
    std::cout << "    RMSE:                  " << std::scientific << std::setprecision(6) << stats2.rmse << std::endl;
    std::cout << "    Relative Image RMSE:   " << std::scientific << std::setprecision(6) << stats2.rel_rmse << " (" << std::fixed << std::setprecision(4) << stats2.rel_rmse * 100.0 << "%, component threshold: <= 0.1%)" << std::endl;
    std::cout << "    Component Parity Status:         " << (stats2.passed_component_parity ? "PASSED" : "FAILED") << std::endl;

    // -------------------------------------------------------------
    // Test Case 3: Edge Clamping Validation Under Extreme Shift
    // -------------------------------------------------------------
    std::cout << "\n-------------------------------------------------------------" << std::endl;
    std::cout << "Test Case 3: Edge Clamping Validation (Extreme Boundary Shifts)" << std::endl;
    std::cout << "-------------------------------------------------------------" << std::endl;

    // Extreme polynomial forcing edge-overflow on all border pixels
    std::vector<float> extreme_coeffX(18, 0.0f);
    std::vector<float> extreme_coeffY(18, 0.0f);
    extreme_coeffX[0] = 12.0f; // 12 px per frame shift -> 180 px total drift
    extreme_coeffY[0] = -15.0f; // -15 px per frame shift

    std::vector<float> cpu_out_clamp((size_t)nx * ny, 0.0f);
    cpuRealSpaceInterpolation(cpu_out_clamp, Iframes, extreme_coeffX.data(), extreme_coeffY.data(), nx, ny, n_frames, nullptr);

    std::vector<float> gpu_out_clamp((size_t)nx * ny, 0.0f);
    status = metalRealSpaceInterpolationRaw(
        Iframes.data(),
        gpu_out_clamp.data(),
        extreme_coeffX.data(),
        extreme_coeffY.data(),
        nx, ny, n_frames,
        0,
        std::cout,
        nullptr
    );
    assert(status && "metalRealSpaceInterpolationRaw (clamping) failed");

    ParityStats stats3 = evaluateParity(gpu_out_clamp, cpu_out_clamp);
    std::cout << "\n  [Parity Metrics - Test 3 (Edge Clamping)]:" << std::endl;
    std::cout << "    Max Pixel Difference:  " << std::scientific << std::setprecision(6) << stats3.max_diff << " (component threshold: <= 5.0)" << std::endl;
    std::cout << "    Mean Pixel Difference: " << std::scientific << std::setprecision(6) << stats3.mean_diff << std::endl;
    std::cout << "    RMSE:                  " << std::scientific << std::setprecision(6) << stats3.rmse << std::endl;
    std::cout << "    Relative Image RMSE:   " << std::scientific << std::setprecision(6) << stats3.rel_rmse << " (" << std::fixed << std::setprecision(4) << stats3.rel_rmse * 100.0 << "%, component threshold: <= 0.1%)" << std::endl;
    std::cout << "    Component Parity Status:         " << (stats3.passed_component_parity ? "PASSED" : "FAILED") << std::endl;

    // -------------------------------------------------------------
    // Test Case 4: High-Resolution Scale Benchmark (2048 x 2048, 16 frames)
    // -------------------------------------------------------------
    std::cout << "\n-------------------------------------------------------------" << std::endl;
    std::cout << "Test Case 4: High-Resolution Scale Test (2048 x 2048, 16 frames)" << std::endl;
    std::cout << "-------------------------------------------------------------" << std::endl;

    const int lnx = 2048, lny = 2048, ln_frames = 16;
    const size_t ltotal_pixels = (size_t)lnx * lny * ln_frames;
    std::vector<float> large_frames(ltotal_pixels, 100.0f);
    // Add grid modulation
    for (size_t i = 0; i < ltotal_pixels; i++) {
        large_frames[i] += 20.0f * std::sin((float)(i % lnx) * 0.05f) * std::cos((float)((i / lnx) % lny) * 0.05f);
    }

    std::vector<float> cpu_large((size_t)lnx * lny, 0.0f);
    auto t_lcpu_start = std::chrono::high_resolution_clock::now();
    cpuRealSpaceInterpolation(cpu_large, large_frames, coeffX.data(), coeffY.data(), lnx, lny, ln_frames, frame_weights.data());
    auto t_lcpu_end = std::chrono::high_resolution_clock::now();
    double lcpu_time = std::chrono::duration<double>(t_lcpu_end - t_lcpu_start).count();
    std::cout << "  CPU Wall Time: " << std::fixed << std::setprecision(2) << lcpu_time * 1000.0 << " ms" << std::endl;

    std::vector<float> gpu_large((size_t)lnx * lny, 0.0f);
    auto t_lgpu_start = std::chrono::high_resolution_clock::now();
    status = metalRealSpaceInterpolationRaw(
        large_frames.data(),
        gpu_large.data(),
        coeffX.data(),
        coeffY.data(),
        lnx, lny, ln_frames,
        0,
        std::cout,
        frame_weights.data()
    );
    auto t_lgpu_end = std::chrono::high_resolution_clock::now();
    double lgpu_time = std::chrono::duration<double>(t_lgpu_end - t_lgpu_start).count();
    std::cout << "  GPU Dispatch Time: " << std::fixed << std::setprecision(2) << lgpu_time * 1000.0 << " ms" << std::endl;
    assert(status && "Large-scale test failed");

    ParityStats stats4 = evaluateParity(gpu_large, cpu_large);
    std::cout << "\n  [Parity Metrics - Test 4 (High-Resolution)]:" << std::endl;
    std::cout << "    Max Pixel Difference:  " << std::scientific << std::setprecision(6) << stats4.max_diff << " (component threshold: <= 5.0)" << std::endl;
    std::cout << "    Mean Pixel Difference: " << std::scientific << std::setprecision(6) << stats4.mean_diff << std::endl;
    std::cout << "    RMSE:                  " << std::scientific << std::setprecision(6) << stats4.rmse << std::endl;
    std::cout << "    Relative Image RMSE:   " << std::scientific << std::setprecision(6) << stats4.rel_rmse << " (" << std::fixed << std::setprecision(4) << stats4.rel_rmse * 100.0 << "%, component threshold: <= 0.1%)" << std::endl;
    std::cout << "    Component Parity Status:         " << (stats4.passed_component_parity ? "PASSED" : "FAILED") << std::endl;
    std::cout << "    Resampling Speedup:    " << std::fixed << std::setprecision(2) << (lcpu_time / lgpu_time) << "x" << std::endl;

    // -------------------------------------------------------------
    // Overall Summary Verdict
    // -------------------------------------------------------------
    bool all_passed = stats1.passed_component_parity && stats2.passed_component_parity && stats3.passed_component_parity && stats4.passed_component_parity;
    std::cout << "\n=============================================================" << std::endl;
    std::cout << "  Overall Test Suite Result: " << (all_passed ? "ALL COMPONENT CHECKS PASSED (FULL MOTIONCORR GATE 2 NOT EVALUATED)" : "FAILED") << std::endl;
    std::cout << "=============================================================" << std::endl;

    return all_passed ? 0 : 1;
}
