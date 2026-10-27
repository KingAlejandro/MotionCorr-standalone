// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef MOTIONCORR_TEST_HERMITIAN_PROJECTION_ORACLE_H
#define MOTIONCORR_TEST_HERMITIAN_PROJECTION_ORACLE_H

// Host-usable portion of the native C2R oracle; no CUDA headers or runtime.
#include <cmath>
#include <complex>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace hermitian_oracle {
using cd = std::complex<double>;

// Independent valid-input reference: double host projection of the boundary
// columns; self-conjugate bins take their real part. Other bins are untouched.
inline bool boundary_column(int x, int nx) { return x == 0 || (nx % 2 == 0 && nx > 1 && x == nx / 2); }
inline std::vector<cd> project_reference(const float *f, int nx, int ny) {
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
// Compare the float components separately: the buffer type may have padding.
// Numeric equality accepts -0 -> +0 and cannot establish byte preservation.
template<class Complex>
bool same_input_bytes(const Complex &value, const float *input) {
    return std::memcmp(&value.x, input, sizeof(float)) == 0 &&
           std::memcmp(&value.y, input + 1, sizeof(float)) == 0;
}

// Checks one production consumption buffer against the specified operator:
// interior bins bit-identical to the input spectrum; boundary-column bins equal
// to the host projection (within float rounding of the 0.5*(u+v) arithmetic);
// self-conjugate bins exactly real; an already-Hermitian input bit-identical.
// A zero buffer is Hermitian, so the projection values are compared, not just
// the symmetry.
template<class Complex>
bool verify_projection(const char *label, const std::vector<Complex> &buf, const float *f,
                       const std::vector<cd> &z, int nx, int ny, bool already_hermitian, bool quiet = false) {
    const int w = nx / 2 + 1;
    size_t interior_bad = 0, boundary_bad = 0, real_bad = 0;
    for (int y = 0; y < ny; ++y) for (int x = 0; x < w; ++x) {
        const size_t i = (size_t)y * w + x, j = (size_t)((ny - y) % ny) * w + x;
        if (!boundary_column(x, nx)) {
            interior_bad += !same_input_bytes(buf[i], f + 2 * i);
            continue;
        }
        const double tol = 3e-7 * (std::abs(cd(f[2 * i], f[2 * i + 1])) + std::abs(cd(f[2 * j], f[2 * j + 1])));
        boundary_bad += std::abs(cd(buf[i].x, buf[i].y) - z[i]) > tol;
        if (i == j) real_bad += buf[i].y != 0.0f;
    }
    size_t differing = 0;
    if (already_hermitian)
        for (size_t i = 0; i < (size_t)w * ny; ++i) differing += !same_input_bytes(buf[i], f + 2 * i);
    const bool ok = !interior_bad && !boundary_bad && !real_bad && !differing;
    if (!quiet)
        std::cout << label << " projection interior_changed=" << interior_bad << " boundary_wrong=" << boundary_bad
                  << " self_conjugate_not_real=" << real_bad << " hermitian_passthrough_diff=" << differing
                  << (ok ? " PASS" : " FAIL") << '\n';
    return ok;
}
// Apply only after constructing an already-Hermitian fixture. Include actual
// negative zeros in interiors, self-conjugate bins and a conjugate boundary pair.
// The production kernel skips pairs that are numerically Hermitian; a self-bin
// imaginary -0 also compares equal to zero and is left untouched. In contrast,
// projecting a nonzero imaginary self-bin deliberately writes canonical +0.
inline void add_signed_zero_fixture(float *f, int nx, int ny) {
    if (nx < 3 || ny < 3) throw std::runtime_error("signed-zero fixture needs nx,ny >= 3");
    const int w = nx / 2 + 1;
    f[2] = -0.0f; f[3] = -0.0f; // Interior x=1, y=0.
    for (int x = 0; x < w; ++x) {
        if (!boundary_column(x, nx)) continue;
        f[2 * x + 1] = -0.0f; // Self-conjugate y=0.
        if (ny % 2 == 0) f[2 * ((ny / 2) * w + x) + 1] = -0.0f;
        const size_t a = size_t(w) + x, b = size_t(ny - 1) * w + x;
        f[2 * a] = f[2 * b] = -0.0f;
        f[2 * a + 1] = -0.0f; f[2 * b + 1] = +0.0f;
    }
}

// Shared by the host regression and the native oracle. Each corruption changes
// exactly one zero sign and exercises verify_projection itself, not a copy.
template<class Complex>
void signed_zero_self_test() {
    auto require = [](bool ok, const char *what) { if (!ok) throw std::runtime_error(what); };
    for (auto dims : {std::pair<int,int>{8, 6}, {7, 5}, {8, 5}, {7, 6}}) {
        const int nx = dims.first, ny = dims.second, w = nx / 2 + 1;
        const size_t nf = size_t(w) * ny;
        std::vector<float> f(2 * nf, 0.0f);
        f[0] = 1.0f; // Retain nonzero signal, rather than an all-zero fixture.
        add_signed_zero_fixture(f.data(), nx, ny);
        const auto z = project_reference(f.data(), nx, ny);
        std::vector<Complex> good(nf);
        for (size_t i = 0; i < nf; ++i) { good[i].x = f[2 * i]; good[i].y = f[2 * i + 1]; }
        for (bool passthrough : {false, true})
            require(verify_projection("", good, f.data(), z, nx, ny, passthrough, true),
                    "signed-zero self-test: unchanged fixture rejected");
        for (int component : {0, 1}) {
            auto bad = good;
            float &v = component == 0 ? bad[1].x : bad[1].y;
            require(v == 0.0f && std::signbit(v), "signed-zero self-test: interior fixture lacks -0");
            v = +0.0f;
            for (bool passthrough : {false, true})
                require(!verify_projection("", bad, f.data(), z, nx, ny, passthrough, true),
                        "signed-zero self-test: changed interior zero sign accepted");
        }
        // Boundary-only mutations isolate the already-Hermitian byte check.
        // The numerical projection check deliberately accepts either zero sign.
        for (int x = 0; x < w; ++x) {
            if (!boundary_column(x, nx)) continue;
            for (size_t i : {size_t(x), size_t(w + x)}) {
                for (int component : {0, 1}) {
                    if (i == size_t(x) && component == 0) continue;
                    auto bad = good;
                    float &v = component == 0 ? bad[i].x : bad[i].y;
                    require(v == 0.0f && std::signbit(v), "signed-zero self-test: boundary fixture lacks -0");
                    v = +0.0f;
                    require(verify_projection("", bad, f.data(), z, nx, ny, false, true),
                            "signed-zero self-test: numerical boundary check became byte-exact");
                    require(!verify_projection("", bad, f.data(), z, nx, ny, true, true),
                            "signed-zero self-test: changed Hermitian boundary zero sign accepted");
                }
            }
        }
    }
    std::cout << "signed-zero self-test PASS (interior and Hermitian boundary byte changes rejected)\n";
}

} // namespace hermitian_oracle
#endif
