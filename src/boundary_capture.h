#ifndef MOTIONCORR_BOUNDARY_CAPTURE_H
#define MOTIONCORR_BOUNDARY_CAPTURE_H
// Default-off, bounded diagnostic. Callers never replace a production input.
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <stdexcept>
namespace mc_boundary {
inline const char *directory() { return std::getenv("MC_BOUNDARY_DIR"); }
inline bool enabled() { const char *p = directory(); return p && *p; }
inline std::atomic<bool>& failed() { static std::atomic<bool> f{false}; return f; }
inline void write(const std::string &name, const void *data, size_t bytes) {
    const std::string path = std::string(directory()) + "/" + name;
    FILE *f = std::fopen(path.c_str(), "wbx"); // never overwrite evidence
    if (!f) { failed() = true; return; }
    const bool ok = std::fwrite(data, 1, bytes, f) == bytes;
    if (std::fclose(f) != 0 || !ok) failed() = true;
}
inline void check() {
    if (failed()) throw std::runtime_error("MC_BOUNDARY_DIR capture incomplete; refusing successful publication");
}
inline void geometry(int nx, int ny, int nf, int cx, int cy, int range, double b) {
    char v[256];
    const int n = std::snprintf(v, sizeof(v),
        "nx %d\nny %d\nnframes %d\nccf_nx %d\nccf_ny %d\nsearch_range %d\nbfactor %.17g\n", nx,ny,nf,cx,cy,range,b);
    write("geometry.txt", v, n);
}
}
#endif
