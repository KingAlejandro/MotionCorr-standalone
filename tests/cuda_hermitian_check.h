// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
// Test-only interposition: inspect the actual consumption buffer before cuFFT
// can destroy it. No instrumentation is linked into motioncorr_core.
#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <map>
#include <stdexcept>
#include <vector>
#include <iostream>
namespace hermitian_test {
struct Violation : std::runtime_error { using std::runtime_error::runtime_error; };
struct Geometry { int nx, ny, batch, distance; };
inline std::map<cufftHandle, Geometry> plans;
inline size_t checked = 0;
inline void remember(cufftHandle p, int rank, int *n, int stride, int distance,
                     cufftType type, int batch, cufftResult result) {
    if (result != CUFFT_SUCCESS || type != CUFFT_C2R) return;
    if (rank != 2 || stride != 1) throw std::runtime_error("unsupported invariant-test plan");
    plans[p] = {n[1], n[0], batch, distance ? distance : n[0] * (n[1]/2+1)};
}
inline void check(cufftHandle p, cufftComplex *data) {
    const auto g = plans.at(p);
    const size_t nf = size_t(g.ny) * (g.nx/2+1);
    std::vector<cufftComplex> host(nf);
    for (int b=0; b<g.batch; ++b) {
        const auto err = cudaMemcpy(host.data(), data + size_t(b)*g.distance,
                                    nf*sizeof(cufftComplex), cudaMemcpyDeviceToHost);
        if (err != cudaSuccess) throw std::runtime_error(cudaGetErrorString(err));
        for (int column=0; column<(g.nx%2 == 0 && g.nx>1 ? 2 : 1); ++column) {
            const int x = column ? g.nx/2 : 0;
            for (int y=0; y<=g.ny/2; ++y) {
                const auto u=host[size_t(y)*(g.nx/2+1)+x];
                const auto v=host[size_t((g.ny-y)%g.ny)*(g.nx/2+1)+x];
                // Exact: the projection stores both members from one owner.
                // Self-conjugate rows require u.imag == -u.imag, hence zero.
                if (!std::isfinite(u.x) || !std::isfinite(u.y) ||
                    u.x != v.x || u.y != -v.y) {
                    std::cerr << "INVARIANT FAIL nx="<<g.nx<<" ny="<<g.ny
                              <<" batch="<<b<<" x="<<x<<" y="<<y<<'\n';
                    throw Violation("non-Hermitian input immediately before C2R");
                }
            }
        }
    }
    ++checked;
}
}
