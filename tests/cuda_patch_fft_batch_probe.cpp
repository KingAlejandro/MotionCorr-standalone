// Is the patch R2C bit-identical when the n grouped patch tiles are not
// transformed by one batch-n plan? Measurement for low-VRAM Tier 2
// (docs/perf_vram_tier1/report.md): without a resident real-space movie, the
// patch tiles would be produced and transformed fewer at a time.
//
// The reference is the session's patch plan (CudaMovieSession::preparePatchInVram):
// 2-D {ph, pw}, idist ph*pw, odist ph*(pw/2+1), batch n, auto-allocation on.
// Compared bitwise against it, per patch geometry and n:
//   slots  - a batch-1 plan executed n times at the same slot offsets;
//   tile   - a batch-1 plan on one separately allocated tile per transform.
// Every arm is repeated with auto-allocation off and an explicit work area, and
// with explicit inembed/onembed strides, so a difference can be attributed.
//
// Measurement only: always exits 0 when a device is present (77 when not).

#include <cuda_runtime.h>
#include <cufft.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <utility>
#include <vector>

namespace {

#define CK(x) do { cudaError_t e = (x); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s at line %d\n", cudaGetErrorString(e), __LINE__); std::exit(2); } } while (0)
#define FK(x) do { cufftResult e = (x); if (e != CUFFT_SUCCESS) { \
    std::fprintf(stderr, "cuFFT %d at line %d\n", (int)e, __LINE__); std::exit(2); } } while (0)

enum Variant { DEFAULT, NO_AUTO, EMBED, N_VARIANTS };

struct Plan {
    cufftHandle h = 0;
    void *work = nullptr;
    ~Plan() { if (h) cufftDestroy(h); if (work) cudaFree(work); }
};

void makePlan(Plan &p, int pw, int ph, int batch, int variant) {
    const int pnfx = pw / 2 + 1;
    int n[2] = {ph, pw};
    int inembed[2] = {ph, pw}, onembed[2] = {ph, pnfx};
    const bool embed = variant == EMBED;
    size_t work = 0;
    FK(cufftCreate(&p.h));
    if (variant == NO_AUTO) FK(cufftSetAutoAllocation(p.h, 0));
    FK(cufftMakePlanMany(p.h, 2, n, embed ? inembed : NULL, 1, ph * pw,
                         embed ? onembed : NULL, 1, ph * pnfx, CUFFT_R2C, batch, &work));
    if (variant == NO_AUTO) {
        CK(cudaMalloc(&p.work, work ? work : 1));
        FK(cufftSetWorkArea(p.h, p.work));
    }
}

size_t countDiff(const std::vector<cufftComplex> &a, const std::vector<cufftComplex> &b) {
    const uint32_t *x = (const uint32_t *)a.data(), *y = (const uint32_t *)b.data();
    size_t d = 0;
    for (size_t i = 0; i < 2 * a.size(); i++) d += (x[i] != y[i]);
    return d;
}

// The runner's patch_bounds, for every patch of a px x py grid.
std::set<std::pair<int, int>> patchSizes(int nx, int ny, int px, int py) {
    std::set<std::pair<int, int>> sizes;
    const int pnx = nx / px, pny = ny / py;
    for (int iy = 0; iy < py; iy++)
        for (int ix = 0; ix < px; ix++) {
            int x0 = ix * pnx, y0 = iy * pny, x1 = x0 + pnx, y1 = y0 + pny;
            if (x1 > nx) x1 = nx;
            if (y1 > ny) y1 = ny;
            if ((x1 - x0) % 2 == 1) { if (x1 == nx) x0++; else x1--; }
            if ((y1 - y0) % 2 == 1) { if (y1 == ny) y0++; else y1--; }
            sizes.insert({x1 - x0, y1 - y0});
        }
    return sizes;
}

struct Row { size_t slots[N_VARIANTS], tile[N_VARIANTS], ref_variant[N_VARIANTS]; size_t words; };

Row probe(int pw, int ph, int n) {
    const int pnfx = pw / 2 + 1;
    const size_t R = (size_t)pw * ph, F = (size_t)ph * pnfx;
    std::vector<float> h_in(R * n);
    uint32_t state = 2463534242u ^ (uint32_t)(pw * 7919 + ph * 104729 + n);
    for (float &v : h_in) {   // detector-like counts, scaled like a grouped patch
        state = state * 1664525u + 1013904223u;
        v = (float)((state >> 9) & 0x3FFF) * 0.731f;
    }
    float *d_in = nullptr, *d_tile = nullptr;
    cufftComplex *d_out = nullptr, *d_tile_out = nullptr;
    CK(cudaMalloc((void **)&d_in, R * n * sizeof(float)));
    CK(cudaMalloc((void **)&d_out, F * n * sizeof(cufftComplex)));
    CK(cudaMalloc((void **)&d_tile, R * sizeof(float)));
    CK(cudaMalloc((void **)&d_tile_out, F * sizeof(cufftComplex)));
    CK(cudaMemcpy(d_in, h_in.data(), R * n * sizeof(float), cudaMemcpyHostToDevice));

    Row row{};
    row.words = 2 * F * n;
    std::vector<cufftComplex> ref, got(F * n);
    for (int v = 0; v < N_VARIANTS; v++) {
        std::vector<cufftComplex> batch_out(F * n);
        {
            Plan p; makePlan(p, pw, ph, n, v);
            CK(cudaMemset(d_out, 0xFF, F * n * sizeof(cufftComplex)));
            FK(cufftExecR2C(p.h, d_in, d_out));
            CK(cudaMemcpy(batch_out.data(), d_out, F * n * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
        }
        if (v == DEFAULT) ref = batch_out;
        row.ref_variant[v] = countDiff(ref, batch_out);

        Plan p1; makePlan(p1, pw, ph, 1, v);
        CK(cudaMemset(d_out, 0xFF, F * n * sizeof(cufftComplex)));
        for (int i = 0; i < n; i++) FK(cufftExecR2C(p1.h, d_in + i * R, d_out + i * F));
        CK(cudaMemcpy(got.data(), d_out, F * n * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
        row.slots[v] = countDiff(ref, got);

        for (int i = 0; i < n; i++) {
            CK(cudaMemcpy(d_tile, d_in + i * R, R * sizeof(float), cudaMemcpyDeviceToDevice));
            FK(cufftExecR2C(p1.h, d_tile, d_tile_out));
            CK(cudaMemcpy(got.data() + i * F, d_tile_out, F * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
        }
        row.tile[v] = countDiff(ref, got);
    }
    cudaFree(d_in); cudaFree(d_out); cudaFree(d_tile); cudaFree(d_tile_out);
    return row;
}

} // namespace

int main() {
    int devices = 0;
    if (cudaGetDeviceCount(&devices) != cudaSuccess || devices == 0) {
        std::printf("no CUDA device\n");
        return 77;
    }
    struct Movie { const char *name; int nx, ny, px, py; };
    const Movie movies[] = {
        {"tutorial 5x5", 3838, 3710, 5, 5}, {"tutorial 3x3", 3838, 3710, 3, 3},
        {"tutorial 7x7", 3838, 3710, 7, 7}, {"K3 5x5", 5760, 4092, 5, 5},
        {"Falcon4 5x5", 4096, 4096, 5, 5},
    };
    const int ns[] = {24, 25, 40, 50};
    int version = 0;
    cufftGetVersion(&version);
    cudaDeviceProp prop{};
    CK(cudaGetDeviceProperties(&prop, 0));
    std::printf("cuFFT %d on %s\n", version, prop.name);
    std::printf("words_differing vs batch-n default plan; columns per variant default/noauto/embed\n");
    std::printf("%-14s %9s %3s %12s | %-26s | %-26s | %-20s\n", "movie", "patch", "n", "words",
                "slots (batch-1 at offsets)", "tile (batch-1, own buf)", "batch-n variant");
    size_t rows = 0, rows_differing = 0;
    for (const Movie &m : movies)
        for (const auto &s : patchSizes(m.nx, m.ny, m.px, m.py))
            for (int n : ns) {
                const Row r = probe(s.first, s.second, n);
                bool differs = false;
                for (int v = 0; v < N_VARIANTS; v++)
                    differs |= r.slots[v] || r.tile[v] || r.ref_variant[v];
                rows++;
                rows_differing += differs;
                std::printf("%-14s %4dx%-4d %3d %12zu | %8zu/%8zu/%8zu | %8zu/%8zu/%8zu | %6zu/%6zu/%6zu%s\n",
                            m.name, s.first, s.second, n, r.words,
                            r.slots[0], r.slots[1], r.slots[2], r.tile[0], r.tile[1], r.tile[2],
                            r.ref_variant[0], r.ref_variant[1], r.ref_variant[2],
                            differs ? "  DIFFERS" : "");
                std::fflush(stdout);
            }
    std::printf("summary: %zu of %zu rows differ in at least one arm or variant\n",
                rows_differing, rows);
    return 0;
}
