// --fft_size_policy fast: frequency consistency of the padded transforms
// (docs/fft_size_policy.md). Each session product is compared against an
// independent pipeline that pads on the host and transforms with its own plans:
//   forward  — spectra of the mean-padded frame, scaled by 1/(fnx*fny), bytes;
//   inverse  — the cropped C2R returns the original frame;
//   patch    — spectra of the mean-padded group sums, scaled by 1/(fft_w*fft_h), bytes;
//   dose     — weights evaluated on the padded frequency grid, polynomial and direct.
// --expect-mismatch inverts the verdict for the compiled mutants in CMakeLists.txt.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/motioncorr_runner.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Mismatch : std::runtime_error { using std::runtime_error::runtime_error; };

void gpu(cudaError_t e, const char *what) {
    if (e != cudaSuccess) throw std::runtime_error(std::string(what) + ": " + cudaGetErrorString(e));
}
void fft(cufftResult r, const char *what) {
    if (r != CUFFT_SUCCESS) throw std::runtime_error(std::string(what) + ": cuFFT " + std::to_string((int)r));
}
// Infrastructure failures throw runtime_error; product disagreements throw
// Mismatch, the only outcome a mutant may produce.
void expect(bool ok, const std::string &what) { if (!ok) throw Mismatch(what); }

// Multiples of 1/64 below 512 in magnitude: every double sum of a frame is
// exact, so the host mean equals the device reduction bit for bit.
std::vector<float> frames(int nx, int ny, int n, unsigned seed) {
    std::vector<float> v((size_t)nx * ny * n);
    unsigned s = seed;
    for (auto &x : v) { s = 1664525u * s + 1013904223u; x = (float)((int)(s >> 16) - 32768) / 64.0f; }
    // A per-frame offset makes the pad value matter.
    for (int f = 0; f < n; ++f)
        for (size_t i = 0; i < (size_t)nx * ny; ++i) v[(size_t)f * nx * ny + i] += 3.0f * f + 1.5f;
    return v;
}
float frameMean(const float *f, size_t n) {
    double s = 0.0;
    for (size_t i = 0; i < n; ++i) s += f[i];
    return (float)(s / (double)n);
}

__global__ void scaleKernel(cufftComplex *d, size_t n, float s) {
    const size_t i = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) { d[i].x *= s; d[i].y *= s; }
}

// Oracle R2C of `batch` dense w x h real images, scaled by 1/(w*h).
std::vector<cufftComplex> paddedSpectra(const std::vector<float> &real, int w, int h, int batch) {
    const size_t rpix = (size_t)w * h, ctile = (size_t)h * (w / 2 + 1);
    float *dr = nullptr; cufftComplex *df = nullptr;
    gpu(cudaMalloc(&dr, rpix * batch * sizeof(float)), "oracle real alloc");
    gpu(cudaMalloc(&df, ctile * batch * sizeof(cufftComplex)), "oracle spectrum alloc");
    gpu(cudaMemcpy(dr, real.data(), rpix * batch * sizeof(float), cudaMemcpyHostToDevice), "oracle upload");
    cufftHandle plan; int n[2] = {h, w};
    fft(cufftPlanMany(&plan, 2, n, nullptr, 1, (int)rpix, nullptr, 1, (int)ctile, CUFFT_R2C, batch), "oracle plan");
    fft(cufftExecR2C(plan, dr, df), "oracle R2C");
    scaleKernel<<<(unsigned)((ctile * batch + 255) / 256), 256>>>(df, ctile * batch, 1.0f / ((float)w * h));
    gpu(cudaGetLastError(), "oracle scale"); gpu(cudaDeviceSynchronize(), "oracle wait");
    std::vector<cufftComplex> out(ctile * batch);
    gpu(cudaMemcpy(out.data(), df, out.size() * sizeof(cufftComplex), cudaMemcpyDeviceToHost), "oracle download");
    fft(cufftDestroy(plan), "oracle plan destroy");
    gpu(cudaFree(dr), "oracle real free"); gpu(cudaFree(df), "oracle spectrum free");
    return out;
}

void sizes() {
    const int table[][2] = {{3710, 3750}, {3838, 3840}, {742, 750}, {766, 768}, {1236, 1250},
                            {1278, 1280}, {530, 540}, {548, 560}, {4096, 4096}, {5760, 5760}, {1, 2}};
    for (const auto &t : table)
        expect(mc_cuda::fastFftSize(t[0]) == t[1],
               "fastFftSize(" + std::to_string(t[0]) + ") != " + std::to_string(t[1]));
    auto smooth = [](int m) { for (int p : {2, 3, 5, 7}) while (m % p == 0) m /= p; return m == 1; };
    for (int n = 1; n <= 6000; ++n) {
        const int m = mc_cuda::fastFftSize(n);
        expect(m >= n && m % 2 == 0 && smooth(m), "fastFftSize(" + std::to_string(n) + ") not an even 7-smooth bound");
        for (int k = n + (n & 1); k < m; k += 2) expect(!smooth(k), "fastFftSize(" + std::to_string(n) + ") not minimal");
    }
    std::cout << "PASS sizes: fastFftSize is the least even 7-smooth bound for 1..6000\n";
}

// nx=262 (2*131) -> 270, ny=254 (2*127) -> 256: both axes padded, unequally.
constexpr int NX = 262, NY = 254, NF = 6;

void forwardAndInverse() {
    const int fnx = mc_cuda::fastFftSize(NX), fny = mc_cuda::fastFftSize(NY);
    const size_t pix = (size_t)NX * NY, fpix = (size_t)fnx * fny;
    const std::vector<float> real = frames(NX, NY, NF, 11u);
    std::vector<float> padded(fpix * NF);
    for (int f = 0; f < NF; ++f) {
        const float m = frameMean(&real[f * pix], pix);
        for (int y = 0; y < fny; ++y) for (int x = 0; x < fnx; ++x)
            padded[f * fpix + (size_t)y * fnx + x] = (x < NX && y < NY) ? real[f * pix + (size_t)y * NX + x] : m;
    }
    const std::vector<cufftComplex> want = paddedSpectra(padded, fnx, fny, NF);

    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    session.setFftSizePolicyFast(true);
    if (!session.initialize()) throw std::runtime_error("session init failed: " + log.str());
    if (!session.frameFftPadded() || session.getFftNx() != fnx || session.getFftNy() != fny)
        throw std::runtime_error("session did not adopt the padded extents");
    gpu(cudaMemcpy(session.getDeviceRealFrames(), real.data(), pix * NF * sizeof(float), cudaMemcpyHostToDevice), "upload");
    if (!session.computeGlobalForwardFFT()) throw std::runtime_error("forward FFT failed: " + log.str());
    std::vector<cufftComplex> got(want.size());
    gpu(cudaMemcpy(got.data(), session.getDeviceFourierFrames(), got.size() * sizeof(cufftComplex), cudaMemcpyDeviceToHost), "spectra download");
    expect(std::memcmp(got.data(), want.data(), got.size() * sizeof(cufftComplex)) == 0,
           "forward spectra differ from the mean-padded oracle");

    if (!session.computeGlobalInverseFFT()) throw std::runtime_error("inverse FFT failed: " + log.str());
    std::vector<float> back(pix * NF);
    gpu(cudaMemcpy(back.data(), session.getDeviceRealFrames(), back.size() * sizeof(float), cudaMemcpyDeviceToHost), "real download");
    double worst = 0.0;
    for (size_t i = 0; i < back.size(); ++i) worst = std::max(worst, (double)std::fabs(back[i] - real[i]));
    // Single-precision round trip of values below ~530: measured ~1e-4. A crop
    // offset or stride error moves whole rows and is orders of magnitude larger.
    expect(worst <= 2e-3, "inverse round trip error " + std::to_string(worst));
    // The resident spectra survive the inverse for dose weighting.
    gpu(cudaMemcpy(got.data(), session.getDeviceFourierFrames(), got.size() * sizeof(cufftComplex), cudaMemcpyDeviceToHost), "spectra re-download");
    expect(std::memcmp(got.data(), want.data(), got.size() * sizeof(cufftComplex)) == 0,
           "inverse FFT did not preserve the padded spectra");
    session.release();
    std::cout << "PASS forward/inverse " << NX << 'x' << NY << " -> " << fnx << 'x' << fny
              << ": spectra byte-identical to the mean-padded oracle; round trip max error " << worst << "\n";
}

void patch() {
    const int pw = 131, ph = 127, x0 = 37, y0 = 29;       // 131 -> 140, 127 -> 128
    const int fw = mc_cuda::fastFftSize(pw), fh = mc_cuda::fastFftSize(ph);
    const int group_start[] = {0, 2, 3}, group_size[] = {2, 1, 3}, ng = 3;
    const size_t pix = (size_t)NX * NY;
    const std::vector<float> real = frames(NX, NY, NF, 23u);
    std::vector<float> means(NF);
    for (int f = 0; f < NF; ++f) means[f] = frameMean(&real[f * pix], pix);
    std::vector<float> padded((size_t)ng * fw * fh);
    for (int g = 0; g < ng; ++g) for (int y = 0; y < fh; ++y) for (int x = 0; x < fw; ++x) {
        float s = 0.0f;
        for (int i = 0; i < group_size[g]; ++i) {
            const int f = group_start[g] + i;
            s += (x < pw && y < ph) ? real[f * pix + (size_t)(y0 + y) * NX + x0 + x] : means[f];
        }
        padded[(size_t)g * fw * fh + (size_t)y * fw + x] = s;
    }
    const std::vector<cufftComplex> want = paddedSpectra(padded, fw, fh, ng);

    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    session.setFftSizePolicyFast(true);
    if (!session.initialize()) throw std::runtime_error("session init failed: " + log.str());
    expect(session.patchFftExtent(pw) == fw && session.patchFftExtent(ph) == fh, "patchFftExtent disagrees with fastFftSize");
    gpu(cudaMemcpy(session.getDeviceRealFrames(), real.data(), pix * NF * sizeof(float), cudaMemcpyHostToDevice), "upload");
    cufftComplex *out = nullptr;
    gpu(cudaMalloc(&out, want.size() * sizeof(cufftComplex)), "patch output alloc");
    if (!session.preparePatchInVram(x0, y0, pw, ph, ng, group_start, group_size, out, 0, 0, fw, fh))
        throw std::runtime_error("patch preparation failed: " + log.str());
    gpu(cudaDeviceSynchronize(), "patch wait");
    std::vector<cufftComplex> got(want.size());
    gpu(cudaMemcpy(got.data(), out, got.size() * sizeof(cufftComplex), cudaMemcpyDeviceToHost), "patch download");
    gpu(cudaFree(out), "patch output free");
    expect(std::memcmp(got.data(), want.data(), got.size() * sizeof(cufftComplex)) == 0,
           "patch spectra differ from the mean-padded group-sum oracle");
    session.release();
    std::cout << "PASS patch " << pw << 'x' << ph << " -> " << fw << 'x' << fh
              << ": spectra byte-identical to the padded group-sum oracle\n";
}

// Grant & Grigorieff weight, written independently of cuda_realspace_dw.cu,
// on the padded fnx x fny grid; host double precision.
double doseWeight(int x, int ly, int fnx, int fny, double apix, const std::vector<RFLOAT> &doses, int j) {
    const int n = (int)doses.size();
    if (x == 0 && ly == 0) return 1.0 / std::sqrt((double)n);
    const double dinv = std::sqrt((double)ly * ly / ((double)fny * fny) + (double)x * x / ((double)fnx * fnx)) / apix;
    const double Ne = (0.245 * std::pow(dinv, -1.665) + 2.81) * 2.0;
    double sq = 0.0;
    for (int k = 0; k < n; ++k) { const double w = std::exp(-doses[k] / Ne); sq += w * w; }
    return std::exp(-doses[j] / Ne) / std::sqrt(sq);
}

void dose(bool polynomial) {
    const int fnx = mc_cuda::fastFftSize(NX), fny = mc_cuda::fastFftSize(NY), fnfx = fnx / 2 + 1;
    const size_t pix = (size_t)NX * NY, fpix = (size_t)fnx * fny, ctile = (size_t)fny * fnfx;
    const RFLOAT apix = 1.12;
    std::vector<RFLOAT> doses(NF);
    for (int j = 0; j < NF; ++j) doses[j] = 4.0 * (j + 1);   // up to 24 e/A^2: weights differ strongly
    const std::vector<float> real = frames(NX, NY, NF, 37u);

    // Oracle: weight each padded spectrum on the host, C2R with its own plan, crop.
    std::vector<float> padded(fpix * NF);
    for (int f = 0; f < NF; ++f) {
        const float m = frameMean(&real[f * pix], pix);
        for (int y = 0; y < fny; ++y) for (int x = 0; x < fnx; ++x)
            padded[f * fpix + (size_t)y * fnx + x] = (x < NX && y < NY) ? real[f * pix + (size_t)y * NX + x] : m;
    }
    std::vector<cufftComplex> spectra = paddedSpectra(padded, fnx, fny, NF);
    for (int f = 0; f < NF; ++f) for (int y = 0; y < fny; ++y) for (int x = 0; x < fnfx; ++x) {
        const int ly = y > fny / 2 ? y - fny : y;
        const float w = (float)doseWeight(x, ly, fnx, fny, apix, doses, f);
        cufftComplex &c = spectra[f * ctile + (size_t)y * fnfx + x];
        c.x *= w; c.y *= w;
    }
    std::vector<float> weighted(fpix * NF);
    {
        cufftComplex *dc = nullptr; float *dr = nullptr;
        gpu(cudaMalloc(&dc, spectra.size() * sizeof(cufftComplex)), "oracle c alloc");
        gpu(cudaMalloc(&dr, weighted.size() * sizeof(float)), "oracle r alloc");
        gpu(cudaMemcpy(dc, spectra.data(), spectra.size() * sizeof(cufftComplex), cudaMemcpyHostToDevice), "oracle c upload");
        cufftHandle plan; int n[2] = {fny, fnx};
        fft(cufftPlanMany(&plan, 2, n, nullptr, 1, (int)ctile, nullptr, 1, (int)fpix, CUFFT_C2R, NF), "oracle c2r plan");
        fft(cufftExecC2R(plan, dc, dr), "oracle C2R");
        gpu(cudaDeviceSynchronize(), "oracle c2r wait");
        gpu(cudaMemcpy(weighted.data(), dr, weighted.size() * sizeof(float), cudaMemcpyDeviceToHost), "oracle r download");
        fft(cufftDestroy(plan), "oracle c2r destroy");
        gpu(cudaFree(dc), "oracle c free"); gpu(cudaFree(dr), "oracle r free");
    }
    ThirdOrderPolynomialModel model;
    model.coeffX.resize(18); model.coeffY.resize(18);
    for (int k = 0; k < 18; ++k) {
        // Shifts of a few pixels at the last frame.
        const RFLOAT c = k % 3 == 0 ? 0.3 : k % 3 == 1 ? 0.02 : 0.001;
        model.coeffX(k) = (k % 2 ? -1 : 1) * c;
        model.coeffY(k) = (k % 2 ? 1 : -1) * c * .7;
    }
    // Host reference of the session's accumulation rules on the cropped frames:
    // the bilinear polynomial resampler, or a direct sum.
    std::vector<double> want(pix, 0.0);
    for (int f = 0; f < NF; ++f) {
        const float *fr = &weighted[f * fpix];
        if (!polynomial) {
            for (int y = 0; y < NY; ++y) for (int x = 0; x < NX; ++x) want[(size_t)y * NX + x] += fr[(size_t)y * fnx + x];
            continue;
        }
        const double z = f, z2 = z * z, z3 = z2 * z;
        double cx[6], cy[6];
        for (int i = 0; i < 6; ++i) {
            cx[i] = model.coeffX(3 * i) * z + model.coeffX(3 * i + 1) * z2 + model.coeffX(3 * i + 2) * z3;
            cy[i] = model.coeffY(3 * i) * z + model.coeffY(3 * i + 1) * z2 + model.coeffY(3 * i + 2) * z3;
        }
        for (int iy = 0; iy < NY; ++iy) for (int ix = 0; ix < NX; ++ix) {
            const double x = (double)ix / NX - 0.5, y = (double)iy / NY - 0.5;
            const double sx = cx[0] + cx[1] * x + cx[2] * x * x + cx[3] * y + cx[4] * y * y + cx[5] * x * y;
            const double sy = cy[0] + cy[1] * x + cy[2] * x * x + cy[3] * y + cy[4] * y * y + cy[5] * x * y;
            const double xs = ix - sx, ys = iy - sy;
            const int x0 = (int)std::floor(xs), y0 = (int)std::floor(ys);
            const double fx = xs - x0, fy = ys - y0;
            if (x0 < 0 || y0 < 0 || x0 + 1 >= NX || y0 + 1 >= NY) continue;
            auto at = [&](int xx, int yy) { return (double)fr[(size_t)yy * fnx + xx]; };
            want[(size_t)iy * NX + ix] += (1 - fy) * ((1 - fx) * at(x0, y0) + fx * at(x0 + 1, y0)) +
                                          fy * ((1 - fx) * at(x0, y0 + 1) + fx * at(x0 + 1, y0 + 1));
        }
    }

    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    session.setFftSizePolicyFast(true);
    if (!session.initialize()) throw std::runtime_error("session init failed: " + log.str());
    gpu(cudaMemcpy(session.getDeviceRealFrames(), real.data(), pix * NF * sizeof(float), cudaMemcpyHostToDevice), "upload");
    if (!session.computeGlobalForwardFFT()) throw std::runtime_error("forward FFT failed: " + log.str());
    Image<float> out; out().resize(NY, NX); out().initConstant(-12345.0f);
    if (!session.reconstructDoseWeighted(out, doses, apix, polynomial ? &model : nullptr))
        throw std::runtime_error("dose reconstruction failed: " + log.str());
    session.release();

    // The pixels the resampler treats differently at the border (clamping)
    // are excluded from the polynomial comparison; the direct sum covers all.
    double worst = 0.0, scale = 0.0;
    const int m = polynomial ? 12 : 0;
    for (int y = m; y < NY - m; ++y) for (int x = m; x < NX - m; ++x) {
        const size_t i = (size_t)y * NX + x;
        worst = std::max(worst, std::fabs((double)out().data[i] - want[i]));
        scale = std::max(scale, std::fabs(want[i]));
    }
    const double rel = worst / scale;
    // Float weights and transforms against a double-weighted reference:
    // measured ~1e-6. Weights evaluated on the unpadded grid differ by ~1e-3.
    expect(rel <= 2e-5, std::string("dose-weighted sum (") + (polynomial ? "polynomial" : "direct") +
                        ") relative max error " + std::to_string(rel));
    std::cout << "PASS dose " << (polynomial ? "polynomial" : "direct")
              << ": weights on the padded grid, relative max error " << rel << "\n";
}

} // namespace

int main(int argc, char **argv) {
    const bool expect_mismatch = argc == 2 && std::string(argv[1]) == "--expect-mismatch";
    if (argc > 1 && !expect_mismatch) { std::cerr << "usage: cuda_fft_size_policy [--expect-mismatch]\n"; return 2; }
    try {
        sizes();
        forwardAndInverse();
        patch();
        dose(false);
        dose(true);
    } catch (const Mismatch &e) {
        std::cout << (expect_mismatch ? "PASS (expected mismatch): " : "FAIL: ") << e.what() << "\n";
        return expect_mismatch ? 0 : 1;
    } catch (const std::exception &e) {
        std::cout << "ERROR: " << e.what() << "\n";
        return 1;
    }
    if (expect_mismatch) { std::cout << "FAIL: mutant produced no mismatch\n"; return 1; }
    return 0;
}
