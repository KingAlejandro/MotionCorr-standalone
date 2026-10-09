// Native controls for the dead-buffer aliases of docs/vram_live_ranges.md.
//
// Global arena: cudaAlignPatchDeviceInArena must reproduce cudaAlignPatchDevice
// byte for byte -- shifts, verdict, "Iteration"/"completed" and VRAM log lines and
// the shifted Fourier payload -- whether everything is placed in the arena, the
// arena is too small, or only the cuFFT work area is allocated. The arena is
// filled with NaN first, so a read of an unwritten carved buffer shows.
//
// Real-space refusal: after the movie is borrowed, every reader of d_Iframes
// refuses with a message until computeGlobalInverseFFT rewrites it, and the
// rewritten movie equals that of a session that was never borrowed.
//
// Dose-weighting consume: a reconstruction carving its scratch from the real-space
// movie produces the same sum, byte for byte, as one that allocates it.
//
// --expect-mismatch is for the compiled mutants: the run passes only if some
// check detects a difference.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
bool active = false;
int malloc_calls = 0;
void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}
}

extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active) ++malloc_calls;
    return __real_cudaMalloc(ptr, bytes);
}
}

namespace {
bool expect_mismatch = false;
int mismatches = 0;
// A product difference: fatal normally, counted under --expect-mismatch.
void exactOrCount(bool same, const std::string &what) {
    if (same) return;
    if (!expect_mismatch) throw std::runtime_error("mismatch: " + what);
    ++mismatches;
}
void arm() { malloc_calls = 0; active = true; }
void gpu(cudaError_t e, const char *what) {
    require(e == cudaSuccess, std::string(what) + ": " + cudaGetErrorString(e));
}
bool contains(const std::string &s, const std::string &needle) { return s.find(needle) != std::string::npos; }

// Lines that carry results or claimed totals; timings vary between runs.
std::string contractLines(const std::string &log) {
    std::istringstream in(log);
    std::string line, out;
    while (std::getline(in, line))
        if (line.rfind(" Iteration ", 0) == 0 || contains(line, "] completed;") ||
            contains(line, "Buffer VRAM:") || contains(line, "cuFFT workspace VRAM:") ||
            contains(line, "Peak GPU memory allocated:"))
            out += line + "\n";
    return out;
}

template <class T> std::vector<T> download(const T *d, size_t elems) {
    std::vector<T> h(elems);
    gpu(cudaMemcpy(h.data(), d, elems * sizeof(T), cudaMemcpyDeviceToHost), "download");
    return h;
}
template <class T> bool sameBytes(const std::vector<T> &a, const std::vector<T> &b) {
    return a.size() == b.size() && std::memcmp(a.data(), b.data(), a.size() * sizeof(T)) == 0;
}

// Periodic drift of one random image: the global aligner has real work to do.
// With noise > 0 each frame also gets its own noise, so once the frames are
// aligned the CCF is not symmetric and the weights still move the peak (an
// exactly aligned noiseless pair gives a symmetric CCF under any weighting).
std::vector<Image<float>> movieFrames(int nx, int ny, int frames, unsigned seed, float noise = 0) {
    std::vector<float> base((size_t)nx * ny);
    unsigned s = seed;
    for (auto &v : base) { s = 1664525u * s + 1013904223u; v = (float)((s >> 8) & 1023) / 64.0f; }
    std::vector<Image<float>> out(frames);
    for (int k = 0; k < frames; k++) {
        out[k]().initZeros(ny, nx);
        for (int y = 0; y < ny; y++)
            for (int x = 0; x < nx; x++) {
                const int sx = ((x - k) % nx + nx) % nx, sy = ((y + k / 2) % ny + ny) % ny;
                float v = base[(size_t)sy * nx + sx];
                if (noise > 0) { s = 1664525u * s + 1013904223u; v += noise * (float)((s >> 8) & 1023) / 1024.0f; }
                DIRECT_A2D_ELEM(out[k](), y, x) = v;
            }
    }
    return out;
}

struct Movie {
    std::ostringstream log;
    CudaMovieSession session;
    Movie(const std::vector<Image<float>> &frames)
        : session((int)XSIZE(frames[0]()), (int)YSIZE(frames[0]()), (int)frames.size(), 0, log) {
        MultidimArray<float> sum;
        require(session.initialize(), "session initialize");
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), "session upload");
        require(session.releasePreprocessingBuffers(), "release preprocessing");
        require(session.computeGlobalForwardFFT(), "forward FFT");
    }
};

// ---- global alignment in an arena -----------------------------------------
// A full-size 1280x1152 CCF: cuFFT 12.8 leaves the reported C2R work area
// untouched for power-of-two and small sizes (192..1024 measured), which would
// make a misplaced work area invisible. globalArena checks it is written.
const int GNX = 1280, GNY = 1152, GFRAMES = 6, GITER = 5;
const RFLOAT GB = 150, GDOWN = 1;

struct GlobalResult {
    bool converged = false;
    std::vector<RFLOAT> x, y;
    std::string log;
    std::vector<cufftComplex> fourier;
};

GlobalResult runGlobal(const std::vector<cufftComplex> &input, void *arena, size_t arena_bytes,
                       int expected_mallocs, const std::string &placement, const std::string &label) {
    cufftComplex *d = nullptr;
    gpu(cudaMalloc(&d, input.size() * sizeof(cufftComplex)), "global input");
    gpu(cudaMemcpy(d, input.data(), input.size() * sizeof(cufftComplex), cudaMemcpyHostToDevice), "global upload");
    if (arena) gpu(cudaMemset(arena, 0xFF, arena_bytes), "arena poison");
    GlobalResult r;
    r.x.assign(GFRAMES, 0); r.y.assign(GFRAMES, 0);
    std::ostringstream log;
    arm();
    r.converged = arena
        ? cudaAlignPatchDeviceInArena(d, GFRAMES, GNX, GNY, GB, r.x, r.y, GITER, GDOWN, 0, log, arena, arena_bytes, true)
        : cudaAlignPatchDevice(d, GFRAMES, GNX, GNY, GB, r.x, r.y, GITER, GDOWN, 0, log, true);
    active = false;
    require(malloc_calls == expected_mallocs,
            label + ": " + std::to_string(malloc_calls) + " allocations, expected " + std::to_string(expected_mallocs));
    const std::string all = log.str();
    if (placement.empty())
        require(!contains(all, "Buffer placement:"), label + ": unexpected placement line\n" + all);
    else
        require(contains(all, "Buffer placement:             borrowed dead device memory" + placement),
                label + ": placement line missing\n" + all);
    r.log = contractLines(all);
    r.fourier = download(d, input.size());
    gpu(cudaFree(d), "global input free");
    return r;
}

void compareGlobal(const GlobalResult &ref, const GlobalResult &got, const std::string &label) {
    exactOrCount(ref.converged == got.converged, label + " verdict");
    exactOrCount(sameBytes(ref.x, got.x) && sameBytes(ref.y, got.y), label + " shifts");
    exactOrCount(ref.log == got.log, label + " log\n--- ref\n" + ref.log + "--- got\n" + got.log);
    exactOrCount(sameBytes(ref.fourier, got.fourier), label + " shifted payload");
}

void globalArena() {
    std::vector<cufftComplex> input;
    {
        Movie m(movieFrames(GNX, GNY, GFRAMES, 7u, 12.0f));
        input = download(m.session.getDeviceFourierFrames(), (size_t)GFRAMES * GNY * (GNX / 2 + 1));
    }
    int cnx = 0, cny = 0;
    patchSpectrumWindow(GNX, GNY, GB, GDOWN, cnx, cny);
    const size_t cnfx = cnx / 2 + 1;
    auto up = [](size_t v) { return (v + 511) / 512 * 512; };
    const size_t need = up(cny * cnfx * sizeof(float2)) + up(cny * cnfx * sizeof(float)) +
        up(GFRAMES * cny * cnfx * sizeof(float2)) + up((size_t)GFRAMES * cny * cnx * sizeof(float)) +
        4 * up(GFRAMES * sizeof(float));
    // The work area the aligner's C2R plan asks for, from the same configuration.
    size_t work = 0;
    {
        cufftHandle plan;
        int n[2] = {cny, cnx};
        require(cufftCreate(&plan) == CUFFT_SUCCESS, "probe plan create");
        require(cufftSetAutoAllocation(plan, 0) == CUFFT_SUCCESS, "probe plan auto allocation");
        size_t ignored = 0;
        require(cufftMakePlanMany(plan, 2, n, NULL, 1, cny * (int)cnfx, NULL, 1, cny * cnx, CUFFT_C2R,
                                  GFRAMES, &ignored) == CUFFT_SUCCESS, "probe plan make");
        require(cufftGetSize(plan, &work) == CUFFT_SUCCESS, "probe plan size");
        // The work area must actually be written, or overlapping it with the
        // aligner's buffers changes nothing and the placement is untested.
        void *d_work = nullptr, *d_in = nullptr, *d_out = nullptr;
        const size_t in_bytes = (size_t)GFRAMES * cny * cnfx * sizeof(float2);
        gpu(cudaMalloc(&d_work, work), "probe work");
        gpu(cudaMalloc(&d_in, in_bytes), "probe input");
        gpu(cudaMalloc(&d_out, (size_t)GFRAMES * cny * cnx * sizeof(float)), "probe output");
        gpu(cudaMemcpy(d_in, input.data(), in_bytes, cudaMemcpyHostToDevice), "probe upload");
        gpu(cudaMemset(d_work, 0xAB, work), "probe work poison");
        require(cufftSetWorkArea(plan, d_work) == CUFFT_SUCCESS, "probe work area");
        require(cufftExecC2R(plan, (cufftComplex*)d_in, (cufftReal*)d_out) == CUFFT_SUCCESS, "probe exec");
        std::vector<unsigned char> h_work(work);
        gpu(cudaMemcpy(h_work.data(), d_work, work, cudaMemcpyDeviceToHost), "probe work download");
        size_t written = 0;
        for (unsigned char c : h_work) written += (c != 0xAB);
        require(written > 0, "cuFFT did not write its C2R work area for this geometry");
        cudaFree(d_work); cudaFree(d_in); cudaFree(d_out);
        cufftDestroy(plan);
    }
    require(work > 512, "geometry needs a cuFFT work area larger than the arena slack, got " + std::to_string(work));

    const GlobalResult ref = runGlobal(input, nullptr, 0, 8, "", "global reference");
    // Iteration 2 reads the weight after a C2R has used the work area.
    require(contains(ref.log, " Iteration 2:"), "global reference converged before a second iteration\n" + ref.log);
    // Raw cudaMalloc gives at least 256-byte alignment; align the arena start
    // so its usable size is exactly what is passed.
    const size_t big = need + work + 4096;
    char *raw = nullptr;
    gpu(cudaMalloc((void**)&raw, big + 512), "arena");
    char *arena = (char*)up((size_t)raw);
    int compared = 0;
    compareGlobal(ref, runGlobal(input, arena, big, 0, ", nothing allocated", "arena all placed"),
                  "arena all placed"); ++compared;
    compareGlobal(ref, runGlobal(input, arena, need - 512, 8, "", "arena too small"),
                  "arena too small"); ++compared;
    compareGlobal(ref, runGlobal(input, arena, need + 512, 1, "; cuFFT workspace allocated", "arena work allocated"),
                  "arena work allocated"); ++compared;
    gpu(cudaFree(raw), "arena free");
    std::cout << (expect_mismatch ? "RAN: " : "PASS: ") << compared << " global arena comparisons (need "
              << need << " B, work " << work << " B)\n";
}

// ---- the borrowed real-space movie ----------------------------------------
const int RNX = 320, RNY = 288, RFRAMES = 6;

void realFrameRefusal() {
    const auto frames = movieFrames(RNX, RNY, RFRAMES, 11u);
    std::vector<Image<float>> expected;
    {
        Movie m(frames);
        require(m.session.computeGlobalInverseFFT(), "unborrowed inverse FFT");
        require(m.session.downloadRealFrames(expected), "unborrowed download");
    }
    Movie m(frames);
    size_t bytes = 0;
    void *arena = m.session.borrowRealFramesForGlobalAlignment(bytes);
    require(arena == m.session.getDeviceRealFrames() && bytes == (size_t)RFRAMES * RNX * RNY * sizeof(float),
            "borrow did not return the whole real-space movie");
    gpu(cudaMemset(arena, 0xFF, bytes), "scribble on the borrowed movie");

    const int g_start[2] = {0, 3}, g_size[2] = {3, 3};
    cufftComplex *d_patch = nullptr;
    gpu(cudaMalloc(&d_patch, (size_t)2 * 144 * (160 / 2 + 1) * sizeof(cufftComplex)), "patch buffer");
    std::vector<Image<float>> got;
    Image<float> sum;
    sum().initZeros(RNY, RNX);
    const std::string refusal = "the device real-space movie is no longer valid (global alignment used it as scratch";
    struct Reader { const char *what; std::function<bool()> call; };
    const std::vector<Reader> readers = {
        {"the real-space frame download", [&] { return m.session.downloadRealFrames(got); }},
        {"the unweighted reconstruction", [&] { return m.session.reconstructUnweighted(sum, nullptr, nullptr, nullptr); }},
        {"patch preparation", [&] { return m.session.preparePatchInVram(0, 0, 160, 144, 2, g_start, g_size, d_patch); }},
        {"the forward FFT", [&] { return m.session.computeGlobalForwardFFT(); }},
    };
    int refused = 0;
    for (const auto &r : readers) {
        m.log.str("");
        const bool ok = r.call();
        exactOrCount(!ok && contains(m.log.str(), std::string("ERROR: refusing ") + r.what + ": " + refusal),
                     std::string("borrowed movie not refused by ") + r.what + "\n" + m.log.str());
        refused += !ok;
        require(!m.session.getFailureState().hasFailed(), std::string("refusal recorded a CUDA failure: ") + r.what);
    }
    gpu(cudaFree(d_patch), "patch buffer free");
    require(m.session.computeGlobalInverseFFT(), "inverse FFT after borrow");
    require(m.session.downloadRealFrames(got), "download after the inverse FFT");
    bool same = got.size() == expected.size();
    for (size_t k = 0; same && k < got.size(); k++)
        same = std::memcmp(got[k]().data, expected[k]().data, (size_t)RNX * RNY * sizeof(float)) == 0;
    exactOrCount(same, "inverse FFT did not rewrite the whole borrowed movie");
    std::cout << (expect_mismatch ? "RAN: " : "PASS: ") << refused << " real-space readers refused while borrowed\n";
}

// ---- dose weighting in the consumed movie ---------------------------------
void doseConsume(int nx, int ny, int frames, bool fits) {
    const auto movie = movieFrames(nx, ny, frames, 23u);
    std::vector<RFLOAT> doses(frames);
    for (int k = 0; k < frames; k++) doses[k] = 1.277 * (k + 1);
    const std::string geometry = std::to_string(nx) + "x" + std::to_string(ny) + "x" + std::to_string(frames);
    const std::string borrowed = "Dose-weighting scratch borrowed from the consumed real-space movie";
    require(fits == (mc_cuda::doseScratchLayout(nx, ny, frames).total_bytes <= (size_t)frames * nx * ny * sizeof(float)),
            geometry + ": fixture does not exercise the intended branch");
    Image<float> sums[2];
    for (int consume = 0; consume < 2; consume++) {
        Movie m(movie);
        require(m.session.computeGlobalInverseFFT(), "inverse FFT");
        sums[consume]().resize(ny, nx);
        sums[consume]().initConstant(-12345.0f);
        m.log.str("");
        arm();
        require(m.session.reconstructDoseWeighted(sums[consume], doses, 1.0, nullptr, consume != 0),
                geometry + ": reconstruction failed\n" + m.log.str());
        active = false;
        const bool carved = consume && fits;
        require(contains(m.log.str(), borrowed) == carved, geometry + ": borrow line wrong\n" + m.log.str());
        require(malloc_calls == (carved ? 0 : 1),
                geometry + ": " + std::to_string(malloc_calls) + " reconstruction allocations");
        std::vector<Image<float>> after;
        m.log.str("");
        exactOrCount(m.session.downloadRealFrames(after) == !carved &&
                     (!carved || contains(m.log.str(), "dose weighting consumed it as scratch")),
                     geometry + ": real-space validity after dose weighting\n" + m.log.str());
    }
    exactOrCount(std::memcmp(sums[0]().data, sums[1]().data, (size_t)nx * ny * sizeof(float)) == 0,
                 geometry + ": consumed-movie scratch changed the dose-weighted sum");
}

void doseConsumeAll() {
    doseConsume(320, 288, 6, true);
    doseConsume(332, 250, 3, true);   // odd frame count
    doseConsume(320, 288, 2, false);  // scratch exceeds two frames: allocates
    std::cout << (expect_mismatch ? "RAN: " : "PASS: ") << "dose-weighting scratch in the consumed movie\n";
}
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (std::string(argv[i]) == "--expect-mismatch") expect_mismatch = true;
        else { std::cerr << "unknown argument " << argv[i] << "\n"; return 2; }
    }
    try {
        globalArena();
        realFrameRefusal();
        doseConsumeAll();
    } catch (RelionError &e) {
        std::cerr << "FAIL: " << e.msg << "\n";
        return 1;
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << "\n";
        return 1;
    }
    if (expect_mismatch) {
        if (mismatches == 0) { std::cerr << "FAIL: mutant produced no detectable difference\n"; return 1; }
        std::cout << "PASS: mutant detected (" << mismatches << " mismatches)\n";
        return 0;
    }
    return 0;
}
