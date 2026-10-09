// cuFFT time at exact frame/patch sizes versus nearby smooth sizes.
// Standalone: nvcc -O2 -arch=sm_80 fft_size_bench.cu -lcufft -o fft_size_bench
// Usage: fft_size_bench [reps] < cases   where each line is "label nx ny batch".
// For every case it times the exact size and the next even 7-smooth, 5-smooth
// and 3-smooth sizes >= (nx, ny), out of place, R2C and C2R, and prints one TSV
// row per (case, size, direction): median ms per execution over [reps] runs.
#include <cufft.h>
#include <cuda_runtime.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#define CK(x) do { cudaError_t e = (x); if (e != cudaSuccess) { \
    fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); exit(1); } } while (0)
#define FK(x) do { cufftResult rc_ = (x); if (rc_ != CUFFT_SUCCESS) { \
    fprintf(stderr, "%s:%d cufft %d\n", __FILE__, __LINE__, (int)rc_); exit(1); } } while (0)

static bool smooth(int n, int maxp) {
    const int ps[] = {2, 3, 5, 7};
    for (int p : ps) { if (p > maxp) break; while (n % p == 0) n /= p; }
    return n == 1;
}
static int nextSmoothEven(int n, int maxp) {
    for (int m = n + (n & 1);; m += 2) if (smooth(m, maxp)) return m;
}

static float timeOne(int nx, int ny, int batch, cufftType type, int reps) {
    cufftHandle plan;
    int n[2] = {ny, nx};
    size_t work = 0;
    FK(cufftCreate(&plan));
    FK(cufftMakePlanMany(plan, 2, n, NULL, 1, 0, NULL, 1, 0, type, batch, &work));
    const size_t nreal = (size_t)nx * ny * batch;
    const size_t ncomp = (size_t)(nx / 2 + 1) * ny * batch;
    float *r; cufftComplex *c;
    CK(cudaMalloc(&r, nreal * sizeof(float)));
    CK(cudaMalloc(&c, ncomp * sizeof(cufftComplex)));
    CK(cudaMemset(r, 0, nreal * sizeof(float)));
    CK(cudaMemset(c, 0, ncomp * sizeof(cufftComplex)));
    cudaEvent_t a, b; CK(cudaEventCreate(&a)); CK(cudaEventCreate(&b));
    auto exec = [&]() {
        if (type == CUFFT_R2C) FK(cufftExecR2C(plan, r, c));
        else FK(cufftExecC2R(plan, c, r));
    };
    for (int i = 0; i < 3; i++) exec();
    std::vector<float> t;
    for (int i = 0; i < reps; i++) {
        CK(cudaEventRecord(a)); exec(); CK(cudaEventRecord(b));
        CK(cudaEventSynchronize(b));
        float ms; CK(cudaEventElapsedTime(&ms, a, b)); t.push_back(ms);
    }
    std::sort(t.begin(), t.end());
    cufftDestroy(plan); cudaFree(r); cudaFree(c); cudaEventDestroy(a); cudaEventDestroy(b);
    return t[t.size() / 2];
}

int main(int argc, char **argv) {
    const int reps = argc > 1 ? atoi(argv[1]) : 30;
    std::string label; int nx, ny, batch;
    printf("case\tkind\tnx\tny\tbatch\tr2c_ms\tc2r_ms\n");
    while (std::cin >> label >> nx >> ny >> batch) {
        struct S { const char *kind; int nx, ny; };
        std::vector<S> sizes = {{"exact", nx, ny},
                                {"7smooth", nextSmoothEven(nx, 7), nextSmoothEven(ny, 7)},
                                {"5smooth", nextSmoothEven(nx, 5), nextSmoothEven(ny, 5)},
                                {"3smooth", nextSmoothEven(nx, 3), nextSmoothEven(ny, 3)}};
        for (const S &s : sizes) {
            const float f = timeOne(s.nx, s.ny, batch, CUFFT_R2C, reps);
            const float i = timeOne(s.nx, s.ny, batch, CUFFT_C2R, reps);
            printf("%s\t%s\t%d\t%d\t%d\t%.4f\t%.4f\n", label.c_str(), s.kind, s.nx, s.ny, batch, f, i);
            fflush(stdout);
        }
    }
    return 0;
}
