// Test-only file mutation at the actual two-pass nvCOMP caller. Healthy Deflate
// files only: this control makes no corrupt-decoder safety claim.
#include <tiffio.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>
#include <string>

namespace {
bool changed = false;
unsigned opens = 0;
int reader_fd = -1;
std::string movie;
bool from_ingest() {
    void *frames[24];
    const int n = backtrace(frames, 24);
    for (int i = 1; i < n; ++i) {
        Dl_info info{};
        if (dladdr(frames[i], &info) && info.dli_sname &&
            std::strstr(info.dli_sname, "ingestCompressedTiffStrips")) return true;
    }
    return false;
}
void mutate(const char *when) {
    const char *point = std::getenv("MC_TIFF_CHANGE_POINT");
    const char *mode = std::getenv("MC_TIFF_CHANGE_MODE");
    if (changed || !point || !mode || std::strcmp(point, when)) return;
    bool ok = false;
    if (!std::strcmp(mode, "grow")) {
        FILE *f = std::fopen(movie.c_str(), "ab");
        if (f) {
            ok = std::fwrite("identity-control", 1, 16, f) == 16;
            if (std::fclose(f)) ok = false;
        }
    } else if (!std::strcmp(mode, "replace")) {
        const char *replacement = std::getenv("MC_TIFF_REPLACEMENT");
        ok = replacement && std::rename(replacement, movie.c_str()) == 0;
    }
    if (!ok) { std::fprintf(stderr, "[tiffidentity] mutation failed\n"); std::abort(); }
    changed = true;
    std::fprintf(stderr, "[tiffidentity] changed mode=%s point=%s\n", mode, when);
}
}
extern "C" TIFF *__real_TIFFOpen(const char *, const char *);
extern "C" void __real_TIFFClose(TIFF *);
extern "C" ssize_t __real_pread(int, void *, size_t, off_t);
extern "C" TIFF *__wrap_TIFFOpen(const char *name, const char *mode) {
    const bool ingest = from_ingest();
    if (ingest && opens++ == 0) movie = name;
    TIFF *t = __real_TIFFOpen(name, mode);
    // Mutate after a reader has opened: a rename leaves that handle on the old
    // inode, so checking the handle alone would miss the change of pathname.
    if (ingest && opens == 2 && t) {
        reader_fd = TIFFFileno(t);
        mutate("reader-open");
    }
    return t;
}
extern "C" void __wrap_TIFFClose(TIFF *t) {
    const bool tags = from_ingest() && opens == 1;
    __real_TIFFClose(t);
    if (tags) mutate("tag-close");
}
extern "C" ssize_t __wrap_pread(int fd, void *dst, size_t n, off_t offset) {
    if (fd == reader_fd) mutate("strip-read");
    return __real_pread(fd, dst, n, offset);
}
