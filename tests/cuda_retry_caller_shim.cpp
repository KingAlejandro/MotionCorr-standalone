// Test-only linker interposition at the production runner's alignment boundary.
// Inject one completed-but-nonconverged resident estimate; the actual host retry
// must enter with zero shifts, run native alignment and converge. No src/ switch.
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/error.h"
#include <cstdio>
#include <cstdlib>
#include <type_traits>
static_assert(std::is_same<RFLOAT, double>::value, "This test target uses the double-host ABI");
#define DEVICE_SYMBOL "_Z20cudaAlignPatchDeviceP6float2iiidRSt6vectorIdSaIdEES4_idiRSob"
#define WORKSPACE_SYMBOL "_Z33cudaAlignPatchDeviceWithWorkspaceR23PatchAlignmentWorkspaceP6float2iiidRSt6vectorIdSaIdEES6_idiRSob"
#define HOST_SYMBOL "_Z14cudaAlignPatchRSt6vectorI13MultidimArrayI8tComplexIfEESaIS3_EEiidRS_IdSaIdEES9_idiRSob"
bool realDevice(cufftComplex*, int, int, int, RFLOAT, std::vector<RFLOAT>&,
                std::vector<RFLOAT>&, int, RFLOAT, int, std::ostream&, bool)
    asm("__real_" DEVICE_SYMBOL);
bool wrapDevice(cufftComplex*, int, int, int, RFLOAT, std::vector<RFLOAT>&,
                std::vector<RFLOAT>&, int, RFLOAT, int, std::ostream&, bool)
    asm("__wrap_" DEVICE_SYMBOL);
bool realHost(std::vector<MultidimArray<fComplex>>&, int, int, RFLOAT,
              std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
              std::ostream&, bool) asm("__real_" HOST_SYMBOL);
bool wrapHost(std::vector<MultidimArray<fComplex>>&, int, int, RFLOAT,
              std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
              std::ostream&, bool) asm("__wrap_" HOST_SYMBOL);
bool realWorkspace(PatchAlignmentWorkspace&, cufftComplex*, int, int, int, RFLOAT,
                   std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
                   std::ostream&, bool) asm("__real_" WORKSPACE_SYMBOL);
bool wrapWorkspace(PatchAlignmentWorkspace&, cufftComplex*, int, int, int, RFLOAT,
                   std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
                   std::ostream&, bool) asm("__wrap_" WORKSPACE_SYMBOL);
namespace { bool pending = false, injected = false; }
bool wrapDevice(cufftComplex* f, int n, int nx, int ny, RFLOAT b,
                std::vector<RFLOAT>& x, std::vector<RFLOAT>& y, int iter,
                RFLOAT down, int dev, std::ostream& log, bool global) {
    if (!global && !injected && std::getenv("MC_RETRY_CALLER")) {
        injected = pending = true;
        for (size_t i = 0; i < x.size(); ++i) { x[i] = 123.0 + i; y[i] = -456.0 - i; }
        std::fprintf(stderr, "[retry-caller] injected nonconvergence with nonzero shifts\n");
        return false;
    }
    return realDevice(f, n, nx, ny, b, x, y, iter, down, dev, log, global);
}
bool wrapWorkspace(PatchAlignmentWorkspace& workspace, cufftComplex* f, int n,
                   int nx, int ny, RFLOAT b, std::vector<RFLOAT>& x,
                   std::vector<RFLOAT>& y, int iter, RFLOAT down, int dev,
                   std::ostream& log, bool global) {
    if (!global && !injected && std::getenv("MC_RETRY_CALLER")) {
        injected = pending = true;
        for (size_t i = 0; i < x.size(); ++i) { x[i] = 123.0 + i; y[i] = -456.0 - i; }
        std::fprintf(stderr, "[retry-caller] injected nonconvergence with nonzero shifts\n");
        return false;
    }
    return realWorkspace(workspace, f, n, nx, ny, b, x, y, iter, down, dev, log, global);
}
bool wrapHost(std::vector<MultidimArray<fComplex>>& f, int nx, int ny, RFLOAT b,
              std::vector<RFLOAT>& x, std::vector<RFLOAT>& y, int iter,
              RFLOAT down, int dev, std::ostream& log, bool global) {
    const bool check = pending;
    if (check) {
        for (size_t i = 0; i < x.size(); ++i)
            if (x[i] != 0 || y[i] != 0) REPORT_ERROR("retry-caller: stale first-attempt shift");
        pending = false;
        std::fprintf(stderr, "[retry-caller] actual runner reset both vectors\n");
    }
    const bool ok = realHost(f, nx, ny, b, x, y, iter, down, dev, log, global);
    if (check) {
        if (!ok) REPORT_ERROR("retry-caller: second native attempt did not converge");
        std::fprintf(stderr, "[retry-caller] second native alignment succeeded\n");
    }
    return ok;
}
