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
#include <complex>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "cuda_hermitian_check.h"

extern "C" {
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int*, int*, int, int, int*, int, int, cufftType, int, size_t*);
cufftResult __real_cufftExecC2R(cufftHandle, cufftComplex*, cufftReal*);
cufftResult __wrap_cufftMakePlanMany(cufftHandle p, int rank, int *n, int *ie, int is, int id, int *oe, int os, int od, cufftType t, int b, size_t *w) {
    auto r = __real_cufftMakePlanMany(p, rank, n, ie, is, id, oe, os, od, t, b, w);
    hermitian_test::remember(p, rank, n, is, id, t, b, r); return r;
}
static bool raw_characterization = false;
static bool capture_on = false, oracle_mode = false;
static std::vector<std::vector<cufftComplex>> captured;
cufftResult __wrap_cufftExecC2R(cufftHandle p, cufftComplex *in, cufftReal *out) {
    if (!raw_characterization && capture_on) {
        // The exact consumption buffer, copied before cuFFT may overwrite it.
        const auto g = hermitian_test::plans.at(p);
        const size_t nf = size_t(g.ny) * (g.nx / 2 + 1);
        for (int b = 0; b < g.batch; ++b) {
            captured.emplace_back(nf);
            if (cudaMemcpy(captured.back().data(), in + size_t(b) * g.distance,
                           nf * sizeof(cufftComplex), cudaMemcpyDeviceToHost) != cudaSuccess)
                return CUFFT_INTERNAL_ERROR;
        }
    }
    // Oracle-mutant mode disables the invariant so the numerical/projection
    // oracle below is the only thing that can fail.
    if (!raw_characterization && !oracle_mode) hermitian_test::check(p, in);
    return __real_cufftExecC2R(p, in, out);
}
}
static bool expect_invariant_failure = false, expect_oracle_failure = false;
using cd = std::complex<double>;

static void require(bool ok, const char *what) {
    if (!ok) throw std::runtime_error(what);
}
static void check(cudaError_t e) { require(e == cudaSuccess, cudaGetErrorString(e)); }
static bool compare(const char *path, const float *got, const std::vector<double> &ref,
                    int nx, int ny, float scale = 1.0f) {
    double max_error = 0, max_ref = 0, error_sq = 0, ref_sq = 0, row_sq = 0;
    for (int y = 0; y < ny; ++y) {
        double row = 0;
        for (int x = 0; x < nx; ++x) {
            const size_t i = (size_t)y * nx + x;
            const double r = ref[i] * scale, e = got[i] - r;
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

// ---- Independent valid-input reference ------------------------------------
// The CUDA path receives a spectrum whose x=0 / x=nx/2 columns are not
// conjugate-symmetric. The reference never feeds that to an inverse: it first
// projects the columns on the host (in double): conjugate pair -> (u+conj(v))/2
// stored as h and conj(h); self-conjugate bins -> real part. Everything else
// is untouched.
static bool boundary_column(int x, int nx) { return x == 0 || (nx % 2 == 0 && nx > 1 && x == nx / 2); }
static std::vector<cd> project_reference(const float *f, int nx, int ny) {
    const int w = nx / 2 + 1;
    std::vector<cd> z((size_t)w * ny);
    for (size_t i = 0; i < z.size(); ++i) z[i] = cd(f[2 * i], f[2 * i + 1]);
    for (int x = 0; x < w; ++x) {
        if (!boundary_column(x, nx)) continue;
        for (int y = 0; y <= ny / 2; ++y) {
            const size_t a = (size_t)y * w + x, b = (size_t)((ny - y) % ny) * w + x;
            if (a == b) { z[a] = cd(z[a].real(), 0.0); continue; }
            const cd h = 0.5 * (z[a] + std::conj(z[b]));
            z[a] = h; z[b] = std::conj(h);
        }
    }
    return z;
}
// Explicit full-complex inverse DFT of a valid half spectrum: the omitted
// columns are the conjugates of the stored ones (weight 2); the self-conjugate
// columns count once. No FFT library involved.
static std::vector<double> direct_inverse(const std::vector<cd> &z, int nx, int ny) {
    const int w = nx / 2 + 1;
    const double two_pi = 2.0 * std::acos(-1.0);
    std::vector<cd> cx((size_t)w * nx), cy((size_t)ny * ny);
    for (int k = 0; k < w; ++k) for (int x = 0; x < nx; ++x)
        cx[(size_t)k * nx + x] = std::polar(1.0, two_pi * double((size_t)k * x % nx) / nx);
    for (int k = 0; k < ny; ++k) for (int y = 0; y < ny; ++y)
        cy[(size_t)k * ny + y] = std::polar(1.0, two_pi * double((size_t)k * y % ny) / ny);
    std::vector<double> out((size_t)nx * ny);
    for (int y = 0; y < ny; ++y) for (int x = 0; x < nx; ++x) {
        double sum = 0;
        for (int ky = 0; ky < ny; ++ky) for (int kx = 0; kx < w; ++kx)
            sum += (boundary_column(kx, nx) ? 1.0 : 2.0) *
                   (z[(size_t)ky * w + kx] * cy[(size_t)ky * ny + y] * cx[(size_t)kx * nx + x]).real();
        out[(size_t)y * nx + x] = sum;
    }
    return out;
}
static std::vector<double> fftw_double_inverse(std::vector<cd> z, int nx, int ny) {
    std::vector<double> out((size_t)nx * ny);
    auto plan = fftw_plan_dft_c2r_2d(ny, nx, reinterpret_cast<fftw_complex*>(z.data()), out.data(), FFTW_ESTIMATE);
    require(plan != nullptr, "FFTW double inverse plan");
    fftw_execute(plan); fftw_destroy_plan(plan);
    return out;
}

// Checks one production consumption buffer against the specified operator:
// interior bins bit-identical to the input spectrum; boundary-column bins equal
// to the host projection (within float rounding of the 0.5*(u+v) arithmetic);
// self-conjugate bins exactly real; an already-Hermitian input bit-identical.
// A zero buffer is Hermitian, so the projection values are compared, not just
// the symmetry.
static bool verify_projection(const char *label, const std::vector<cufftComplex> &buf, const float *f,
                              const std::vector<cd> &z, int nx, int ny, bool already_hermitian, bool quiet = false) {
    const int w = nx / 2 + 1;
    size_t interior_bad = 0, boundary_bad = 0, real_bad = 0;
    for (int y = 0; y < ny; ++y) for (int x = 0; x < w; ++x) {
        const size_t i = (size_t)y * w + x, j = (size_t)((ny - y) % ny) * w + x;
        if (!boundary_column(x, nx)) {
            interior_bad += buf[i].x != f[2 * i] || buf[i].y != f[2 * i + 1];
            continue;
        }
        const double tol = 3e-7 * (std::abs(cd(f[2 * i], f[2 * i + 1])) + std::abs(cd(f[2 * j], f[2 * j + 1])));
        boundary_bad += std::abs(cd(buf[i].x, buf[i].y) - z[i]) > tol;
        if (i == j) real_bad += buf[i].y != 0.0f;
    }
    size_t differing = 0;
    if (already_hermitian)
        for (size_t i = 0; i < (size_t)w * ny; ++i) differing += buf[i].x != f[2 * i] || buf[i].y != f[2 * i + 1];
    const bool ok = !interior_bad && !boundary_bad && !real_bad && !differing;
    if (!quiet)
        std::cout << label << " projection interior_changed=" << interior_bad << " boundary_wrong=" << boundary_bad
                  << " self_conjugate_not_real=" << real_bad << " hermitian_passthrough_diff=" << differing
                  << (ok ? " PASS" : " FAIL") << '\n';
    return ok;
}
// The oracle must be able to fail: each defect below has to be rejected.
static void oracle_self_test() {
    for (auto dims : {std::pair<int,int>{8, 6}, {7, 5}, {8, 5}, {7, 6}}) {
        const int nx = dims.first, ny = dims.second, w = nx / 2 + 1;
        const size_t nf = (size_t)w * ny;
        std::vector<float> f(2 * nf);
        uint32_t s = 99;
        for (float &v : f) { s ^= s << 13; s ^= s >> 17; s ^= s << 5; v = float(s & 1023) / 1024.0f - 0.5f; }
        const auto z = project_reference(f.data(), nx, ny);
        auto make = [&](const std::vector<cd> &src) {
            std::vector<cufftComplex> b(nf);
            for (size_t i = 0; i < nf; ++i) b[i] = make_cuFloatComplex(float(src[i].real()), float(src[i].imag()));
            return b;
        };
        const auto good = make(z);
        std::vector<cd> raw(nf);
        for (size_t i = 0; i < nf; ++i) raw[i] = cd(f[2 * i], f[2 * i + 1]);
        auto zeroed = good, zero = good, nudged = good;
        for (size_t i = 0; i < nf; ++i) {
            if (boundary_column(int(i % w), nx)) zeroed[i] = make_cuFloatComplex(0, 0);
            zero[i] = make_cuFloatComplex(0, 0);
        }
        for (size_t i = 0; i < nf; ++i) if (!boundary_column(int(i % w), nx)) { nudged[i].x = std::nextafter(nudged[i].x, 1e9f); break; }
        require(verify_projection("", good, f.data(), z, nx, ny, false, true), "oracle self-test: valid projection rejected");
        require(!verify_projection("", make(raw), f.data(), z, nx, ny, false, true), "oracle self-test: unprojected buffer accepted");
        require(!verify_projection("", zeroed, f.data(), z, nx, ny, false, true), "oracle self-test: zeroed boundary columns accepted");
        require(!verify_projection("", zero, f.data(), z, nx, ny, false, true), "oracle self-test: zero buffer accepted");
        require(!verify_projection("", nudged, f.data(), z, nx, ny, false, true), "oracle self-test: altered interior bin accepted");
        // Already-Hermitian input passes through bit-identically; the projection is idempotent.
        std::vector<float> h(2 * nf);
        for (size_t i = 0; i < nf; ++i) { h[2 * i] = float(z[i].real()); h[2 * i + 1] = float(z[i].imag()); }
        const auto zh = project_reference(h.data(), nx, ny);
        require(verify_projection("", good, h.data(), zh, nx, ny, true, true), "oracle self-test: Hermitian pass-through rejected");
        require(!verify_projection("", nudged, h.data(), zh, nx, ny, true, true), "oracle self-test: altered Hermitian input accepted");
        for (size_t i = 0; i < nf; ++i) require(zh[i] == cd(h[2 * i], h[2 * i + 1]), "host projection not idempotent");
        // The two independent references agree on valid input.
        const auto d = direct_inverse(z, nx, ny), q = fftw_double_inverse(z, nx, ny);
        double e = 0, m = 0;
        for (size_t i = 0; i < d.size(); ++i) { e = std::max(e, std::abs(d[i] - q[i])); m = std::max(m, std::abs(d[i])); }
        require(e <= 1e-12 * m, "direct DFT and double FFTW references disagree");
    }
    std::cout << "oracle self-test PASS (rejects unprojected, zeroed-boundary, zero and altered-interior buffers)\n";
}

static bool is_integer(double v) { return v == std::floor(v); }

// One session inverse; returns the output frames and the consumption buffers.
static std::vector<Image<float>> session_inverse(int nx, int ny, int frames, const float *input,
                                                 std::vector<std::vector<cufftComplex>> &buffers) {
    const size_t nf = (size_t)(nx / 2 + 1) * ny;
    CudaMovieSession session(nx, ny, frames, 0, std::cerr);
    require(session.initialize(), "session initialize");
    for (int i = 0; i < frames; ++i)
        check(cudaMemcpy(session.getDeviceFourierFrames() + i * nf, input, nf * sizeof(fComplex), cudaMemcpyHostToDevice));
    captured.clear(); capture_on = true;
    const bool inverted = session.computeGlobalInverseFFT();
    capture_on = false; buffers = captured;
    require(inverted, "session inverse");
    std::vector<Image<float>> got;
    require(session.downloadRealFrames(got), "session download");
    std::vector<fComplex> retained(nf);
    for (int i = 0; i < frames; ++i) {
        check(cudaMemcpy(retained.data(), session.getDeviceFourierFrames() + i * nf, nf * sizeof(fComplex), cudaMemcpyDeviceToHost));
        require(std::memcmp(retained.data(), input, nf * sizeof(fComplex)) == 0, "inverse modified resident spectra");
    }
    return got;
}

// hermitian_input: the fixture spectrum is replaced by its exact host projection,
// so the production projection must pass it through bit-identically.
static bool run(int nx, int ny, double sx, double sy, bool plans, bool session_only, bool hermitian_input = false) {
    const size_t nr = (size_t)nx * ny, nf = (size_t)(nx / 2 + 1) * ny;
    std::vector<float> image(nr);
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
    float *fp = reinterpret_cast<float*>(f);
    if (hermitian_input) {
        const auto zh = project_reference(fp, nx, ny);
        for (size_t i = 0; i < nf; ++i) { fp[2 * i] = float(zh[i].real()); fp[2 * i + 1] = float(zh[i].imag()); }
    }
    if (frames > 1) std::memcpy(MULTIDIM_ARRAY(spectra[1]), f, nf * sizeof(fComplex));
    const std::vector<float> input(fp, fp + 2 * nf);
    // Reference: project the host spectrum, then invert a valid spectrum in double.
    const auto projected = project_reference(input.data(), nx, ny);
    const auto reference = fftw_double_inverse(projected, nx, ny);
    std::cout << "shift=" << sx << "," << sy << (hermitian_input ? " hermitian_input" : "") << '\n';
    bool ok = true;
    const bool small = nr <= 8192;
    if (small) {
        double e = 0, m = 0;
        const auto direct = direct_inverse(projected, nx, ny);
        for (size_t i = 0; i < nr; ++i) { e = std::max(e, std::abs(direct[i] - reference[i])); m = std::max(m, std::abs(direct[i])); }
        require(e <= 1e-12 * m, "direct DFT and double FFTW references disagree");
    }
    std::vector<double> analytic;
    if (is_integer(sx) && is_integer(sy)) {
        // An integer shift of a known real image is itself a valid spectrum.
        analytic.resize(nr);
        for (int y = 0; y < ny; ++y) for (int x = 0; x < nx; ++x)
            analytic[(size_t)y * nx + x] = image[(size_t)(((y - (long)sy) % ny + ny) % ny) * nx + ((x - (long)sx) % nx + nx) % nx];
        double e = 0, m = 0;
        for (size_t i = 0; i < nr; ++i) { e = std::max(e, std::abs(analytic[i] - reference[i])); m = std::max(m, std::abs(analytic[i])); }
        require(e <= 1e-6 * m, "host reference does not reproduce the known shifted image");
    }
    {
        std::vector<std::vector<cufftComplex>> buffers;
        const auto got = session_inverse(nx, ny, frames, input.data(), buffers);
        require(buffers.size() == (size_t)frames, "session C2R call count");
        for (auto &im : got) {
            ok = compare("session", MULTIDIM_ARRAY(im()), reference, nx, ny) && ok;
            if (!analytic.empty()) ok = compare("session_vs_known_image", MULTIDIM_ARRAY(im()), analytic, nx, ny) && ok;
        }
        for (auto &b : buffers) ok = verify_projection("session", b, input.data(), projected, nx, ny, hermitian_input) && ok;
        if (small && !hermitian_input) {
            // Idempotence: the projected consumption buffer is a fixed point.
            std::vector<float> again(2 * nf);
            std::memcpy(again.data(), buffers[0].data(), nf * sizeof(cufftComplex));
            std::vector<std::vector<cufftComplex>> second;
            const auto got2 = session_inverse(nx, ny, frames, again.data(), second);
            const auto zp = project_reference(again.data(), nx, ny);
            for (auto &b : second) ok = verify_projection("session_idempotence", b, again.data(), zp, nx, ny, true) && ok;
            for (int i = 0; i < frames; ++i)
                require(std::memcmp(MULTIDIM_ARRAY(got2[i]()), MULTIDIM_ARRAY(got[i]()), nr * sizeof(float)) == 0,
                        "projected spectrum does not invert bit-identically");
        }
    }
    if (session_only) return ok;
    std::vector<Image<float>> got;
    captured.clear(); capture_on = true;
    const bool wrapped = cudaInverseFFT2D(spectra, got, nx, ny, 0, std::cerr, true);
    capture_on = false;
    require(wrapped, "wrapper inverse");
    require(captured.size() == (size_t)frames, "wrapper C2R call count");
    for (int i = 0; i < frames; ++i)
        require(std::memcmp(MULTIDIM_ARRAY(spectra[i]), input.data(), nf * sizeof(fComplex)) == 0, "wrapper modified its input spectra");
    for (auto &im : got) {
        ok = compare("wrapper", MULTIDIM_ARRAY(im()), reference, nx, ny) && ok;
        if (!analytic.empty()) ok = compare("wrapper_vs_known_image", MULTIDIM_ARRAY(im()), analytic, nx, ny) && ok;
    }
    for (auto &b : captured) ok = verify_projection("wrapper", b, input.data(), projected, nx, ny, hermitian_input) && ok;
    cudaReleaseCachedFrames();
    // The host dose wrapper infers an even nx from the half-spectrum width.
    // Dose weighting rescales the spectrum, so only the numerical oracle applies.
    if (nx % 2 == 0) {
        Image<float> sum;
        sum().reshape(ny, nx);
        std::vector<RFLOAT> doses(2, 0);
        require(cudaDoseWeightAndInterpolate(spectra, sum, doses, 1.0, nullptr, 0, std::cerr), "dose inverse");
        ok = compare("dose", MULTIDIM_ARRAY(sum()), reference, nx, ny, std::sqrt(2.0f)) && ok;
        if (!analytic.empty()) ok = compare("dose_vs_known_image", MULTIDIM_ARRAY(sum()), analytic, nx, ny, std::sqrt(2.0f)) && ok;
    }
    if (plans) {
        // Characterisation only: full-size PlanMany batch 1 and batch 2. Production
        // full-frame inverses use batch 1; CCF inverses use batched reduced grids.
        // The unprojected input is invalid; this is not an oracle.
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
            std::cout << "CHARACTERIZATION ONLY: invalid raw C2R input; numerical leakage is platform-specific\n";
            raw_characterization = true;
            require(cufftExecC2R(plan, din, dout) == CUFFT_SUCCESS, "cuFFT exec");
            raw_characterization = false;
            check(cudaDeviceSynchronize());
            std::vector<float> raw(nr);
            check(cudaMemcpy(raw.data(), dout, nr * sizeof(float), cudaMemcpyDeviceToHost));
            const bool discarded = compare(batch == 1 ? "raw_planmany_batch1" : "raw_planmany_batch2", raw.data(), reference, nx, ny);
            std::cout << (discarded ? "No numerical leak observed (invariant remains the negative control)\n"
                                   : "Numerical leak observed (characterization, not a test failure)\n");
            require(cufftDestroy(plan) == CUFFT_SUCCESS, "cuFFT destroy");
            check(cudaFree(din)); check(cudaFree(dout));
        }
    }
    return ok;
}
int main(int argc, char **argv) {
    try {
        bool matrix = false, session_only = false;
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            if (a == "--expect-invariant-failure") expect_invariant_failure = true;
            else if (a == "--expect-oracle-failure") expect_oracle_failure = oracle_mode = true;
            else if (a == "--matrix") matrix = true;
            else throw std::runtime_error("unknown argument");
        }
        int count = 0; check(cudaGetDeviceCount(&count)); require(count > 0, "native GPU required");
        cudaDeviceProp prop; check(cudaGetDeviceProperties(&prop, 0));
        int version = 0; require(cufftGetVersion(&version) == CUFFT_SUCCESS, "cuFFT version");
        std::cout << std::setprecision(12) << "device=" << prop.name << " cufft=" << version << '\n';
        oracle_self_test();
        if (expect_oracle_failure) {
            // Mutant mode: the invariant is off; only the oracle may reject.
            const bool ok = run(64, 48, 0.3, 0.2, false, false);
            if (ok) throw std::runtime_error("mutant passed the output oracle");
            std::cout << "ORACLE REJECTED MUTANT\n";
            return 0;
        }
        bool ok = run(4096, 4096, 0.3, 0.2, matrix, session_only);
        if (!expect_invariant_failure) {
            // Isolated x/y shifts and odd/even boundaries exercise both columns,
            // self-paired rows, and absence of an x-Nyquist column at odd nx.
            for (auto shift : {std::pair<double,double>{0.3,0}, {0,0.2}, {1,2}, {0,0}})
                ok = run(64, 48, shift.first, shift.second, false, false) && ok;
            for (auto dims : {std::pair<int,int>{63,47}, {64,47}, {63,48}}) {
                ok = run(dims.first, dims.second, 0.3, 0.2, false, false) && ok;
                // Integer shift: analytic known-image oracle; Hermitian input: pass-through.
                ok = run(dims.first, dims.second, 1, 2, false, false) && ok;
                ok = run(dims.first, dims.second, 0.3, 0.2, false, false, true) && ok;
            }
            ok = run(64, 48, 0.3, 0.2, false, false, true) && ok;
            if (matrix) for (auto dims : {std::pair<int,int>{5760,4092}, {3710,3838}, {7676,7420}, {11520,8184}})
                ok = run(dims.first, dims.second, 0.3, 0.2, true, false) && ok;
        }
        if (expect_invariant_failure) throw std::runtime_error("mutant did not violate invariant");
        std::cout << "INVARIANT PASS inverses=" << hermitian_test::checked << '\n';
        return ok ? 0 : 1;
    } catch (const hermitian_test::Violation &e) {
        std::cerr << e.what() << '\n'; return expect_invariant_failure ? 0 : 1;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
}
