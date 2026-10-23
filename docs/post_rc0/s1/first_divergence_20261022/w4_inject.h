// SPDX-License-Identifier: GPL-2.0-or-later
// W4 first-divergence diagnostic overlay. Test builds only; never in production.
// MC_W4_GLOBAL_SHIFTS=file   replace global estimation by these total shifts
//                            (frame order, "x y" per line, frame 0 must be 0 0)
// MC_W4_FIXED_REF=1          global CCF reference = unshifted frame 0
// MC_W4_STATE=dir            full-precision global state, written before STAR
#ifndef MC_W4_INJECT_H
#define MC_W4_INJECT_H
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
namespace w4 {
inline void fail(const char *m) { std::fprintf(stderr, "W4 overlay: %s\n", m); std::abort(); }
inline const char *inject_path() { return std::getenv("MC_W4_GLOBAL_SHIFTS"); }
inline bool fixed_reference() {
    const char *v = std::getenv("MC_W4_FIXED_REF");
    if (v && std::string(v) != "1") fail("MC_W4_FIXED_REF must be 1 or unset");
    if (v && inject_path()) fail("MC_W4_FIXED_REF and MC_W4_GLOBAL_SHIFTS are exclusive");
    return v != nullptr;
}
inline const char *state_dir() { return std::getenv("MC_W4_STATE"); }
inline void read_shifts(int n, std::vector<double> &x, std::vector<double> &y) {
    std::ifstream in(inject_path());
    if (!in) fail("cannot open MC_W4_GLOBAL_SHIFTS");
    double a, b;
    while (in >> a >> b) { x.push_back(a); y.push_back(b); }
    if (!in.eof()) fail("malformed MC_W4_GLOBAL_SHIFTS");
    if ((int)x.size() != n) fail("MC_W4_GLOBAL_SHIFTS frame count differs");
    if (x[0] != 0 || y[0] != 0) fail("frame 0 of MC_W4_GLOBAL_SHIFTS must be 0 0");
}
template <class T>
inline void write_state(const char *name, int iteration, const std::vector<T> &x, const std::vector<T> &y) {
    const char *d = state_dir();
    if (!d) return;
    FILE *f = std::fopen((std::string(d) + "/" + name).c_str(), "a");
    if (!f) fail("cannot open MC_W4_STATE file");
    for (size_t i = 0; i < x.size(); i++)
        std::fprintf(f, "%d %zu %.17g %.17g\n", iteration, i, (double)x[i], (double)y[i]);
    if (std::fclose(f) != 0) fail("cannot close MC_W4_STATE file");
}
}
#endif
