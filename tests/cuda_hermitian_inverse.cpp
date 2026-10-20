// SPDX-License-Identifier: GPL-2.0-or-later
// Issue #253: identical FFTW-shifted bytes through the production inverse paths.
#include "src/acc/cuda/cuda_fft_prep.h"
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <fftw3.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool ok, const char *what) {
    if (!ok) throw std::runtime_error(what);
}
static void check(cudaError_t e) { require(e == cudaSuccess, cudaGetErrorString(e)); }
static bool compare(const char *path, const float *got, const std::vector<float> &ref,
                    int nx, int ny, float scale = 1.0f) {
    double max_error = 0, max_ref = 0, error_sq = 0, ref_sq = 0, row_sq = 0;
    for (int y = 0; y < ny; ++y) {
        double row = 0;
        for (int x = 0; x < nx; ++x) {
            const size_t i = (size_t)y * nx + x;
            const double r = (double)ref[i] * scale, e = got[i] - r;
            max_error = std::max(max_error, std::abs(e));
            max_ref = std::max(max_ref, std::abs(r));
            error_sq += e * e; ref_sq += r * r; row += e;
        }
        row_sq += (row / nx) * (row / nx);
    }
    const double rel_max = max_error / max_ref, rel_rmse = std::sqrt(error_sq / ref_sq);
    const bool ok = rel_max <= 2e-6 && rel_rmse <= 2e-6;
    std::cout << path << " nx=" << nx << " ny=" << ny << " max_relative=" << rel_max
              << " relative_rmse=" << rel_rmse << " row_mean_rms_over_max="
              << std::sqrt(row_sq / ny) / max_ref << " " << (ok ? "PASS" : "FAIL") << '\n';
    return ok;
}

static bool run(int nx, int ny, double sx, double sy, bool plans, bool session_only) {
    const size_t nr = (size_t)nx * ny, nf = (size_t)(nx / 2 + 1) * ny;
    std::vector<float> image(nr), reference(nr);
    uint32_t state = 7;
    for (float &v : image) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5;
        v = float(state & 65535) / 65536.0f - 0.5f;
    }
    // Odd-width frame strides need not preserve cuFFT complex alignment.
    const int frames = nx % 2 ? 1 : 2;
    std::vector<MultidimArray<fComplex>> spectra(frames);
    for (auto &f : spectra) f.resizeNoCp(2, 1, ny, nx / 2 + 1);
    auto *f = MULTIDIM_ARRAY(spectra[0]);
    auto forward = fftwf_plan_dft_r2c_2d(ny, nx, image.data(), (fftwf_complex*)f, FFTW_ESTIMATE);
    require(forward != nullptr, "FFTW forward plan");
    fftwf_execute(forward); fftwf_destroy_plan(forward);
    for (int y = 0; y < ny; ++y) for (int x = 0; x <= nx / 2; ++x) {
        const int ky = y <= ny / 2 ? y : y - ny;
        const double phase = -2.0 * std::acos(-1.0) * (x * sx / nx + ky * sy / ny);
        const fComplex shift(float(std::cos(phase) / nr), float(std::sin(phase) / nr));
        f[(size_t)y * (nx / 2 + 1) + x] *= shift;
    }
    if (frames > 1) std::memcpy(MULTIDIM_ARRAY(spectra[1]), f, nf * sizeof(fComplex));
    // FFTW C2R destroys its input; both backends get fresh copies of the same bytes.
    std::vector<fComplex> fftw_input(f, f + nf);
    auto inverse = fftwf_plan_dft_c2r_2d(ny, nx, (fftwf_complex*)fftw_input.data(),
                                        reference.data(), FFTW_ESTIMATE);
    require(inverse != nullptr, "FFTW inverse plan");
    fftwf_execute(inverse); fftwf_destroy_plan(inverse);
    std::cout << "shift=" << sx << "," << sy << '\n';
    bool ok = true;
    {
        CudaMovieSession session(nx, ny, frames, 0, std::cerr);
        require(session.initialize(), "session initialize");
        check(cudaMemcpy(session.getDeviceFourierFrames(), f, nf * sizeof(fComplex), cudaMemcpyHostToDevice));
        if (frames > 1) check(cudaMemcpy(session.getDeviceFourierFrames() + nf, f, nf * sizeof(fComplex), cudaMemcpyHostToDevice));
        require(session.computeGlobalInverseFFT(), "session inverse");
        std::vector<Image<float>> got;
        require(session.downloadRealFrames(got), "session download");
        for (auto &im : got) ok = compare("session", MULTIDIM_ARRAY(im()), reference, nx, ny) && ok;
        std::vector<fComplex> retained(nf);
        check(cudaMemcpy(retained.data(), session.getDeviceFourierFrames(), nf * sizeof(fComplex), cudaMemcpyDeviceToHost));
        require(std::memcmp(retained.data(), f, nf * sizeof(fComplex)) == 0, "inverse modified resident spectra");
    }
    if (session_only) return ok;
    std::vector<Image<float>> got;
    require(cudaInverseFFT2D(spectra, got, nx, ny, 0, std::cerr, true), "wrapper inverse");
    for (auto &im : got) ok = compare("wrapper", MULTIDIM_ARRAY(im()), reference, nx, ny) && ok;
    cudaReleaseCachedFrames();
    // The host dose wrapper infers an even nx from the half-spectrum width.
    if (nx % 2 == 0) {
        Image<float> sum;
        sum().reshape(ny, nx);
        std::vector<RFLOAT> doses(2, 0);
        require(cudaDoseWeightAndInterpolate(spectra, sum, doses, 1.0, nullptr, 0, std::cerr), "dose inverse");
        ok = compare("dose", MULTIDIM_ARRAY(sum()), reference, nx, ny, std::sqrt(2.0f)) && ok;
    }
    if (plans) {
        // Characterisation only: full-size PlanMany batch 1 and batch 2. Production
        // full-frame inverses use batch 1; CCF inverses use batched reduced grids.
        for (int batch : {1, 2}) {
            cufftComplex *din = nullptr; float *dout = nullptr;
            check(cudaMalloc((void**)&din, batch * nf * sizeof(cufftComplex)));
            check(cudaMalloc((void**)&dout, batch * nr * sizeof(float)));
            cufftHandle plan; require(cufftCreate(&plan) == CUFFT_SUCCESS, "cuFFT create");
            int dims[2] = {ny, nx}; size_t work = 0;
            require(cufftMakePlanMany(plan, 2, dims, nullptr, 1, nf, nullptr, 1, nr,
                                     CUFFT_C2R, batch, &work) == CUFFT_SUCCESS, "cuFFT plan many");
            for (int b = 0; b < batch; ++b)
                check(cudaMemcpy(din + b * nf, f, nf * sizeof(cufftComplex), cudaMemcpyHostToDevice));
            require(cufftExecC2R(plan, din, dout) == CUFFT_SUCCESS, "cuFFT exec");
            check(cudaDeviceSynchronize());
            check(cudaMemcpy(image.data(), dout, nr * sizeof(float), cudaMemcpyDeviceToHost));
            compare(batch == 1 ? "raw_planmany_batch1" : "raw_planmany_batch2", image.data(), reference, nx, ny);
            require(cufftDestroy(plan) == CUFFT_SUCCESS, "cuFFT destroy");
            check(cudaFree(din)); check(cudaFree(dout));
        }
    }
    return ok;
}
int main(int argc, char **argv) {
    try {
        bool expect_mismatch = false, matrix = false, session_only = false;
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            if (a == "--expect-mismatch") { expect_mismatch = true; session_only = true; }
            else if (a == "--matrix") matrix = true;
            else throw std::runtime_error("unknown argument");
        }
        int count = 0; check(cudaGetDeviceCount(&count)); require(count > 0, "native GPU required");
        cudaDeviceProp prop; check(cudaGetDeviceProperties(&prop, 0));
        int version = 0; require(cufftGetVersion(&version) == CUFFT_SUCCESS, "cuFFT version");
        std::cout << std::setprecision(12) << "device=" << prop.name << " cufft=" << version << '\n';
        bool ok = run(4096, 4096, 0.3, 0.2, matrix, session_only);
        if (!expect_mismatch) {
            // Isolated x/y shifts and odd/even boundaries exercise both columns,
            // self-paired rows, and absence of an x-Nyquist column at odd nx.
            for (auto shift : {std::pair<double,double>{0.3,0}, {0,0.2}, {1,2}, {0,0}})
                ok = run(64, 48, shift.first, shift.second, false, false) && ok;
            for (auto dims : {std::pair<int,int>{63,47}, {64,47}, {63,48}})
                ok = run(dims.first, dims.second, 0.3, 0.2, false, false) && ok;
            if (matrix) for (auto dims : {std::pair<int,int>{5760,4092}, {3710,3838}, {7676,7420}, {11520,8184}})
                ok = run(dims.first, dims.second, 0.3, 0.2, true, false) && ok;
        }
        if (expect_mismatch) { require(!ok, "mutant did not cause mismatch"); return 0; }
        return ok ? 0 : 1;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
}
