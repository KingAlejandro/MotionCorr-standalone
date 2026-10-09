// Does a movie FFT give the same bits when the real frames share the Fourier
// allocation? docs/low_vram_movie_layout.md.
//
// The low-VRAM session layout stores real frame i at float offset i*nx*ny inside
// the Fourier buffer. The forward transform then copies real frame i into the
// one-frame tile and transforms tile -> Fourier slot i (descending i), and the
// inverse copies Fourier slot i into the tile and transforms tile -> real slot i
// (ascending i). Both change the address one side of the transform reads or
// writes. This checks, per geometry, that the whole forward and inverse movie
// transforms are byte-identical to the split layout the default session uses.
//
// In-place padded R2C is reported for information only: it needs a different
// plan layout and is not used by the session.
//
// Plans are built exactly as CudaMovieSession::initialize builds them: 2-D,
// batch 1, auto-allocation off, one shared work area.

#include <cuda_runtime.h>
#include <cufft.h>

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <vector>

namespace {

#define CK(x) do { cudaError_t e = (x); if (e != cudaSuccess) { \
    std::fprintf(stderr, "CUDA %s at line %d\n", cudaGetErrorString(e), __LINE__); std::exit(2); } } while (0)
#define FK(x) do { cufftResult e = (x); if (e != CUFFT_SUCCESS) { \
    std::fprintf(stderr, "cuFFT %d at line %d\n", (int)e, __LINE__); std::exit(2); } } while (0)

struct Plans {
    cufftHandle r2c = 0, c2r = 0;
    void *work = nullptr;
};

Plans makePlans(int nx, int ny) {
    const int nfx = nx / 2 + 1;
    Plans p;
    int n[2] = {ny, nx};
    size_t w_r2c = 0, w_c2r = 0;
    FK(cufftCreate(&p.r2c));
    FK(cufftSetAutoAllocation(p.r2c, 0));
    FK(cufftMakePlanMany(p.r2c, 2, n, NULL, 1, nx * ny, NULL, 1, ny * nfx, CUFFT_R2C, 1, &w_r2c));
    FK(cufftCreate(&p.c2r));
    FK(cufftSetAutoAllocation(p.c2r, 0));
    FK(cufftMakePlanMany(p.c2r, 2, n, NULL, 1, ny * nfx, NULL, 1, nx * ny, CUFFT_C2R, 1, &w_c2r));
    const size_t w = w_r2c > w_c2r ? w_r2c : w_c2r;
    CK(cudaMalloc(&p.work, w ? w : 1));
    FK(cufftSetWorkArea(p.r2c, p.work));
    FK(cufftSetWorkArea(p.c2r, p.work));
    return p;
}

void freePlans(Plans &p) {
    cufftDestroy(p.r2c);
    cufftDestroy(p.c2r);
    cudaFree(p.work);
}

size_t countDiff(const void *a, const void *b, size_t words) {
    const uint32_t *x = (const uint32_t *)a, *y = (const uint32_t *)b;
    size_t d = 0;
    for (size_t i = 0; i < words; i++) d += (x[i] != y[i]);
    return d;
}

// Returns the number of failed comparisons for this geometry.
int probe(int nx, int ny, int n_frames) {
    const int nfx = nx / 2 + 1;
    const size_t R = (size_t)nx * ny;          // floats per real frame
    const size_t F = (size_t)ny * nfx;         // complex per Fourier frame
    Plans plans = makePlans(nx, ny);

    std::vector<float> h_real(R * n_frames);
    uint32_t state = 12345u + (uint32_t)nx * 31u + (uint32_t)ny;
    for (float &v : h_real) {
        state = state * 1664525u + 1013904223u;
        v = (float)((state >> 8) & 0xFFFF) * 0.37f;   // detector-like non-negative counts
    }

    float *d_real = nullptr;           // split layout: real movie
    cufftComplex *d_four = nullptr;    // split layout: Fourier movie
    cufftComplex *d_unified = nullptr; // low-VRAM layout: one buffer
    cufftComplex *d_tile = nullptr;    // one complex frame
    CK(cudaMalloc((void **)&d_real, R * n_frames * sizeof(float)));
    CK(cudaMalloc((void **)&d_four, F * n_frames * sizeof(cufftComplex)));
    CK(cudaMalloc((void **)&d_unified, F * n_frames * sizeof(cufftComplex)));
    CK(cudaMalloc((void **)&d_tile, F * sizeof(cufftComplex)));
    float *const u_real = (float *)d_unified;

    CK(cudaMemcpy(d_real, h_real.data(), R * n_frames * sizeof(float), cudaMemcpyHostToDevice));
    CK(cudaMemcpy(u_real, h_real.data(), R * n_frames * sizeof(float), cudaMemcpyHostToDevice));

    // Forward. Split: real slot -> Fourier slot. Unified: descending, through the tile.
    for (int i = 0; i < n_frames; i++)
        FK(cufftExecR2C(plans.r2c, d_real + i * R, d_four + i * F));
    for (int i = n_frames - 1; i >= 0; i--) {
        CK(cudaMemcpy(d_tile, u_real + i * R, R * sizeof(float), cudaMemcpyDeviceToDevice));
        FK(cufftExecR2C(plans.r2c, (cufftReal *)d_tile, d_unified + i * F));
    }
    CK(cudaDeviceSynchronize());
    std::vector<cufftComplex> h_four(F * n_frames), h_uni(F * n_frames);
    CK(cudaMemcpy(h_four.data(), d_four, F * n_frames * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
    CK(cudaMemcpy(h_uni.data(), d_unified, F * n_frames * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
    const size_t fwd_diff = countDiff(h_four.data(), h_uni.data(), 2 * F * n_frames);

    // Inverse. Both copy the Fourier slot to the tile first (C2R destroys its
    // input). Split: tile -> real slot. Unified: ascending, tile -> real slot in place.
    for (int i = 0; i < n_frames; i++) {
        CK(cudaMemcpy(d_tile, d_four + i * F, F * sizeof(cufftComplex), cudaMemcpyDeviceToDevice));
        FK(cufftExecC2R(plans.c2r, d_tile, d_real + i * R));
    }
    for (int i = 0; i < n_frames; i++) {
        CK(cudaMemcpy(d_tile, d_unified + i * F, F * sizeof(cufftComplex), cudaMemcpyDeviceToDevice));
        FK(cufftExecC2R(plans.c2r, d_tile, u_real + i * R));
    }
    CK(cudaDeviceSynchronize());
    std::vector<float> h_inv(R * n_frames), h_uinv(R * n_frames);
    CK(cudaMemcpy(h_inv.data(), d_real, R * n_frames * sizeof(float), cudaMemcpyDeviceToHost));
    CK(cudaMemcpy(h_uinv.data(), u_real, R * n_frames * sizeof(float), cudaMemcpyDeviceToHost));
    const size_t inv_diff = countDiff(h_inv.data(), h_uinv.data(), R * n_frames);

    // Information only: in-place padded R2C of frame 0.
    size_t inplace_diff = (size_t)-1;
    {
        cufftHandle ip = 0;
        int n[2] = {ny, nx};
        int inembed[2] = {ny, 2 * nfx}, onembed[2] = {ny, nfx};
        size_t wb = 0;
        if (cufftCreate(&ip) == CUFFT_SUCCESS &&
            cufftMakePlanMany(ip, 2, n, inembed, 1, (int)(2 * F), onembed, 1, (int)F,
                              CUFFT_R2C, 1, &wb) == CUFFT_SUCCESS) {
            CK(cudaMemset(d_tile, 0, F * sizeof(cufftComplex)));
            CK(cudaMemcpy2D(d_tile, 2 * nfx * sizeof(float), h_real.data(), nx * sizeof(float),
                            nx * sizeof(float), ny, cudaMemcpyHostToDevice));
            if (cufftExecR2C(ip, (cufftReal *)d_tile, d_tile) == CUFFT_SUCCESS) {
                std::vector<cufftComplex> h_ip(F);
                CK(cudaMemcpy(h_ip.data(), d_tile, F * sizeof(cufftComplex), cudaMemcpyDeviceToHost));
                inplace_diff = countDiff(h_four.data(), h_ip.data(), 2 * F);
            }
        }
        if (ip) cufftDestroy(ip);
    }

    std::printf("%5dx%-5d frames=%d forward_words_differing=%zu inverse_words_differing=%zu"
                " | info: in-place padded R2C frame0 words_differing=%lld of %zu\n",
                nx, ny, n_frames, fwd_diff, inv_diff, (long long)inplace_diff, 2 * F);

    cudaFree(d_real);
    cudaFree(d_four);
    cudaFree(d_unified);
    cudaFree(d_tile);
    freePlans(plans);
    return (fwd_diff != 0) + (inv_diff != 0);
}

} // namespace

int main() {
    int devices = 0;
    if (cudaGetDeviceCount(&devices) != cudaSuccess || devices == 0) {
        std::printf("no CUDA device\n");
        return 77;
    }
    // Tutorial geometry both ways round, powers of two, a 2x super-resolution
    // frame, and odd/even sizes whose real stride is not 256-byte aligned. An odd
    // nx*ny is excluded: the split layout's own R2C then reads a 4-byte-aligned
    // frame and cuFFT rejects it (CUFFT_INVALID_VALUE), so there is no reference.
    const int geom[][3] = {
        {3838, 3710, 5}, {3710, 3838, 5}, {4096, 4096, 3}, {7676, 7420, 3},
        {512, 512, 7}, {1000, 998, 5}, {35, 30, 9}, {32, 24, 9}, {750, 1022, 5},
    };
    int failures = 0;
    for (const auto &g : geom) failures += probe(g[0], g[1], g[2]);
    int version = 0;
    cufftGetVersion(&version);
    std::printf("cuFFT %d: %d failed comparison(s)\n", version, failures);
    return failures == 0 ? 0 : 1;
}
