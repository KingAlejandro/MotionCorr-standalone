// #259 incidence: host/device replay of the local-warp branch decision over the
// real fitted coefficients of a movie's STAR local model. No product source is
// linked; the float arm copies the expressions of
// interpolateAndAccumulatePolynomialKernel (same nvcc, -O3, default FMA contraction).
//
//   old   float coefficients, float x_fitted, float x_target, floorf   (main before the fix)
//   fixed float coefficients, float x_fitted, double floor              (the fix)
//   cpu   double coefficients and evaluation, double target             (the oracle)
//
// Discrete differences change the pixel value by a nearest-pixel jump:
//   flip      one arm interpolates, the other takes the border fallback
//   fallback  both fall back, to different source pixels
// A cell difference (both interpolate, floor differs by one) is continuous: the
// weight moves from ~1 to ~0 across the cell boundary and the value changes by
// at most the local gradient times a float step. It is counted separately.
// usage: replay_branch <movie.star> <nx> <ny> <n_frames>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <cuda_runtime.h>

struct Branch { bool valid; int x0, y0; };

__device__ Branch decide(double xt, double yt, float xtf, float ytf, int nx, int ny, int mode) {
    int x0, y0;
    if (mode == 0) { x0 = (int)floorf(xtf); y0 = (int)floorf(ytf); }     // old
    else { x0 = (int)floor(xt); y0 = (int)floor(yt); }                   // fixed, cpu
    int x1 = x0 + 1, y1 = y0 + 1;
    bool valid = true;
    if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
    if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
    if (x1 >= nx || x0 >= nx - 1) { x0 = nx - 1; valid = false; }
    if (y1 >= ny || y0 >= ny - 1) { y0 = ny - 1; valid = false; }
    return {valid, x0, y0};
}

// counts[0..]: see layout below; per (arm, class)
enum { N_ARM = 2 };
enum { K_FLIP, K_FALLBACK, K_CELL, N_KIND };
enum { C_LASTCOL, C_LASTROW, C_CORNER, C_OTHER, N_CLASS };

__global__ void kernel(unsigned long long *counts,
                       const float *fc, const double *dc, int nx, int ny) {
    int ix = blockIdx.x * blockDim.x + threadIdx.x;
    int iy = blockIdx.y * blockDim.y + threadIdx.y;
    if (ix >= nx || iy >= ny) return;
    // float arm (verbatim)
    float x = (float)ix / (float)nx - 0.5f, y = (float)iy / (float)ny - 0.5f;
    float x_fitted = fc[0] + (fc[1] + fc[2] * x) * x + (fc[3] + fc[4] * y + fc[5] * x) * y;
    float y_fitted = fc[6] + (fc[7] + fc[8] * x) * x + (fc[9] + fc[10] * y + fc[11] * x) * y;
    float xtf = (float)ix - x_fitted, ytf = (float)iy - y_fitted;
    // cpu arm: no contraction, as gcc on a baseline x86-64 target
    double dx = (double)ix / nx - 0.5, dy = (double)iy / ny - 0.5;
    #define MUL __dmul_rn
    #define ADD __dadd_rn
    double xf = ADD(ADD(dc[0], MUL(ADD(dc[1], MUL(dc[2], dx)), dx)), MUL(ADD(ADD(dc[3], MUL(dc[4], dy)), MUL(dc[5], dx)), dy));
    double yf = ADD(ADD(dc[6], MUL(ADD(dc[7], MUL(dc[8], dx)), dx)), MUL(ADD(ADD(dc[9], MUL(dc[10], dy)), MUL(dc[11], dx)), dy));
    double xt = (double)ix - xf, yt = (double)iy - yf;
    Branch cpu = decide(xt, yt, 0.f, 0.f, nx, ny, 2);
    // fixed: float x_fitted widened, double subtraction
    Branch fixedb = decide((double)ix - (double)x_fitted, (double)iy - (double)y_fitted, 0.f, 0.f, nx, ny, 1);
    Branch oldb = decide(0., 0., xtf, ytf, nx, ny, 0);
    int cls = (ix == nx - 1 && iy == ny - 1) ? C_CORNER : ix == nx - 1 ? C_LASTCOL : iy == ny - 1 ? C_LASTROW : C_OTHER;
    // denominator: source coordinate within 1e-3 px of a branch boundary (cpu double)
    bool near = fabs(xt - (nx - 1)) < 1e-3 || fabs(yt - (ny - 1)) < 1e-3 || fabs(xt) < 1e-3 || fabs(yt) < 1e-3;
    Branch arms[2] = {oldb, fixedb};
    for (int a = 0; a < 2; a++) {
        if (arms[a].valid != cpu.valid) {
            atomicAdd(&counts[a * N_KIND * N_CLASS + K_FLIP * N_CLASS + cls], 1ull);
        } else if (!cpu.valid && (arms[a].x0 != cpu.x0 || arms[a].y0 != cpu.y0)) {
            atomicAdd(&counts[a * N_KIND * N_CLASS + K_FALLBACK * N_CLASS + cls], 1ull);
        } else if (cpu.valid && (arms[a].x0 != cpu.x0 || arms[a].y0 != cpu.y0)) {
            atomicAdd(&counts[a * N_KIND * N_CLASS + K_CELL * N_CLASS + cls], 1ull);
        }
    }
    // number of pixels near a boundary in each frame (denominator)
    if (near) atomicAdd(&counts[N_ARM * N_KIND * N_CLASS], 1ull);
}

int main(int argc, char **argv) {
    if (argc != 5) { fprintf(stderr, "usage: replay_branch movie.star nx ny n_frames\n"); return 2; }
    const int nx = atoi(argv[2]), ny = atoi(argv[3]), nf = atoi(argv[4]);
    std::ifstream in(argv[1]);
    std::string line; bool inblock = false; std::vector<double> coef;
    while (std::getline(in, line)) {
        if (line.rfind("data_local_motion_model", 0) == 0) { inblock = true; continue; }
        if (!inblock) continue;
        if (line.rfind("data_", 0) == 0) break;
        std::istringstream ss(line); int idx; double v;
        if (ss >> idx >> v) coef.push_back(v);
    }
    if (coef.size() != 36) { fprintf(stderr, "expected 36 coefficients, got %zu\n", coef.size()); return 3; }
    const double *cx = coef.data(), *cy = coef.data() + 18;

    unsigned long long *d_counts;
    float *d_fc; double *d_dc;
    const int NC = N_ARM * N_KIND * N_CLASS + 1;
    cudaMalloc(&d_counts, NC * 8);
    cudaMalloc(&d_fc, 12 * 4); cudaMalloc(&d_dc, 12 * 8);
    cudaMemset(d_counts, 0, NC * 8);
    dim3 blk(16, 16), grd((nx + 15) / 16, (ny + 15) / 16);
    for (int f = 0; f < nf; f++) {
        float fc[12]; double dc[12];
        const float zf = (float)f, z2f = zf * zf, z3f = zf * z2f;
        const double z = f, z2 = z * z, z3 = z * z2;
        for (int i = 0; i < 6; i++) {
            const int c = 3 * i;
            fc[i] = (float)(cx[c] * zf + cx[c + 1] * z2f + cx[c + 2] * z3f);
            fc[6 + i] = (float)(cy[c] * zf + cy[c + 1] * z2f + cy[c + 2] * z3f);
            dc[i] = cx[c] * z + cx[c + 1] * z2 + cx[c + 2] * z3;
            dc[6 + i] = cy[c] * z + cy[c + 1] * z2 + cy[c + 2] * z3;
        }
        cudaMemcpy(d_fc, fc, sizeof fc, cudaMemcpyHostToDevice);
        cudaMemcpy(d_dc, dc, sizeof dc, cudaMemcpyHostToDevice);
        kernel<<<grd, blk>>>(d_counts, d_fc, d_dc, nx, ny);
    }
    if (cudaDeviceSynchronize() != cudaSuccess) { fprintf(stderr, "cuda error\n"); return 4; }
    unsigned long long counts[N_ARM * N_KIND * N_CLASS + 1];
    cudaMemcpy(counts, d_counts, sizeof counts, cudaMemcpyDeviceToHost);
    const char *arm[2] = {"old", "fixed"}, *kind[3] = {"flip", "fallback", "cell"};
    printf("movie %s nx=%d ny=%d frames=%d pixel-frames=%llu\n", argv[1], nx, ny, nf, (unsigned long long)nx * ny * nf);
    printf("pixel-frames with a source coordinate within 1e-3 px of a bound (cpu double): %llu\n", counts[N_ARM * N_KIND * N_CLASS]);
    for (int a = 0; a < 2; a++)
        for (int k = 0; k < N_KIND; k++) {
            unsigned long long *c = &counts[a * N_KIND * N_CLASS + k * N_CLASS];
            printf("%-5s vs cpu %-8s: %llu (last col %llu, last row %llu, corner %llu, other %llu)\n", arm[a], kind[k],
                   c[0] + c[1] + c[2] + c[3], c[C_LASTCOL], c[C_LASTROW], c[C_CORNER], c[C_OTHER]);
        }
    return 0;
}
