// Feed identical CCF arrays directly to the production GPU peak kernel and a
// serial CPU raster scan. This control contains no FFT-engine differences.
#include <cuda_runtime.h>
#include <cmath>
#include <iostream>
#include <vector>

__global__ void findPeakAndInterpolateKernel(
    const float *, float *, float *, int, int, int, float, float, int);

#define CUDA_REQUIRE(call) do { \
    const cudaError_t error = (call); \
    if (error != cudaSuccess) { \
        std::cerr << #call << ": " << cudaGetErrorString(error) << '\n'; \
        return 1; \
    } \
} while (0)

int main() {
    constexpr int nx = 64, ny = 48, radius = 12, width = 2 * radius + 1;
    constexpr int cases = 5;
    constexpr float scale_x = 1.5f, scale_y = 2.0f;
    std::vector<float> ccfs(cases * nx * ny, 0.0f);
    auto at = [&](int frame, int index) -> float & {
        const int x = index % width - radius;
        const int y = index / width - radius;
        return ccfs[frame * nx * ny + (y < 0 ? y + ny : y) * nx + (x < 0 ? x + nx : x)];
    };
    // Equal maxima in different thread lanes: old reduction chose 256 over 1.
    at(0, 1) = at(0, 256) = 5.0f;
    // Unique maximum and same-lane ties retain their original result.
    at(1, 400) = 5.0f;
    at(2, 1) = at(2, 257) = 5.0f;
    // Case 3 is flat; case 4 distinguishes strict ties from near ties.
    at(4, 1) = 5.0f;
    at(4, 256) = std::nextafter(5.0f, 6.0f);

    std::vector<float> expected_x(cases), expected_y(cases);
    for (int frame = 0; frame < cases; ++frame) {
        float maximum = -1e30f;
        int best = 0;
        for (int index = 0; index < width * width; ++index) {
            if (at(frame, index) > maximum) {
                maximum = at(frame, index);
                best = index;
            }
        }
        // All selected peaks have symmetric neighbours, so interpolation is zero.
        expected_x[frame] = (best % width - radius) * scale_x;
        expected_y[frame] = (best / width - radius) * scale_y;
    }

    float *device_ccfs = nullptr, *device_x = nullptr, *device_y = nullptr;
    CUDA_REQUIRE(cudaMalloc(&device_ccfs, ccfs.size() * sizeof(float)));
    CUDA_REQUIRE(cudaMalloc(&device_x, cases * sizeof(float)));
    CUDA_REQUIRE(cudaMalloc(&device_y, cases * sizeof(float)));
    CUDA_REQUIRE(cudaMemcpy(device_ccfs, ccfs.data(), ccfs.size() * sizeof(float), cudaMemcpyHostToDevice));
    std::vector<float> x(cases), y(cases);
    int failures = 0;
    for (int repeat = 0; repeat < 20; ++repeat) {
        findPeakAndInterpolateKernel<<<cases, 256>>>(
            device_ccfs, device_x, device_y, nx, ny, radius, scale_x, scale_y, cases);
        CUDA_REQUIRE(cudaGetLastError());
        CUDA_REQUIRE(cudaMemcpy(x.data(), device_x, cases * sizeof(float), cudaMemcpyDeviceToHost));
        CUDA_REQUIRE(cudaMemcpy(y.data(), device_y, cases * sizeof(float), cudaMemcpyDeviceToHost));
        for (int frame = 0; frame < cases; ++frame) {
            if (x[frame] != expected_x[frame] || y[frame] != expected_y[frame]) {
                std::cerr << "Repeat " << repeat << ", case " << frame << ": got "
                          << x[frame] << ',' << y[frame] << ", expected "
                          << expected_x[frame] << ',' << expected_y[frame] << '\n';
                ++failures;
            }
        }
    }
    CUDA_REQUIRE(cudaFree(device_ccfs));
    CUDA_REQUIRE(cudaFree(device_x));
    CUDA_REQUIRE(cudaFree(device_y));
    if (failures) return 1;
    std::cout << "Five common-CCF peak controls match CPU raster order on 20 repeats\n";
    return 0;
}
