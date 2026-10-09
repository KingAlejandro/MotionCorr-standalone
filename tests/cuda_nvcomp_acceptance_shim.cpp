// Test-only interposition at the actual ingest caller's descriptor readback.
// The decoder runs on HEALTHY input. A host callback changes only the returned
// acceptance descriptors, not compressed data or the decoder's device output.
// Separate direct-kernel tests prove that device rejection avoids output reads.
// No poisoned context or malformed-Deflate decoder safety is claimed here.
//
// The ingest is pipelined in chunks (docs/nvcomp_ingest_pipeline.md). Each
// chunk reads back three descriptor arrays, in order: status, actual length,
// Adler-32. MC_NVCOMP_ACCEPTANCE_CHUNK (default 0) selects the chunk whose
// readback is edited; every other chunk passes through untouched.
//
//   MC_NVCOMP_ACCEPTANCE_FAULT  status | size | adler
//     status: strip 1 reports a decoder failure, and strip 0's Adler-32 is
//             flipped, so the run also proves status is checked before Adler.
//     size:   strip 1 reports one byte short, same Adler flip.
//     adler:  only strip 0's Adler-32 is flipped.
//
// Gain witness: every fusedU16FlipGainAndSumKernel launch from the ingest is
// counted (the only 16x16-block kernel the ingest launches; nvCOMP's own kernels
// are launched inside libnvcomp and never reach this wrapper). The count is
// printed at exit. A chunk's gain launch must follow its verification, so with
// chunk c refused exactly c launches may have happened; one more would mean the
// refused chunk's bytes reached d_Iframes/d_Isum before it was checked.
#include <cuda_runtime.h>
#include <nvcomp.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>

extern "C" cudaError_t __real_cudaMemcpyAsync(void *, const void *, size_t,
                                             cudaMemcpyKind, cudaStream_t);
extern "C" cudaError_t __real_cudaLaunchKernel(const void *, dim3, dim3, void **, size_t,
                                              cudaStream_t);
namespace {
unsigned readback = 0;
unsigned gain_launches = 0;
bool reported = false;
struct Edit { void *dst; unsigned phase; unsigned chunk; const char *mode; } edits[3];
bool from_ingest() {
    void *frames[24]; const int n = backtrace(frames,24);
    for (int i = 1; i < n; ++i) {
        Dl_info info{};
        if (dladdr(frames[i],&info) && info.dli_sname &&
            std::strstr(info.dli_sname,"ingestCompressedTiffStrips")) return true;
    }
    return false;
}
void report() { std::fprintf(stderr,"[nvcompaccept] gain-launches=%u readbacks=%u\n",
                             gain_launches, readback); }
void CUDART_CB change(void *p) {
    const Edit &e = *static_cast<Edit *>(p);
    const bool adler_only = std::strcmp(e.mode,"adler") == 0;
    if (e.phase == 1 && std::strcmp(e.mode,"status") == 0)
        static_cast<nvcompStatus_t *>(e.dst)[1] = static_cast<nvcompStatus_t>(-1);
    if (e.phase == 2 && std::strcmp(e.mode,"size") == 0)
        --static_cast<size_t *>(e.dst)[1];
    // A bad checksum in EARLIER chunk zero powers status-before-Adler ordering.
    if (e.phase == 3) static_cast<unsigned *>(e.dst)[0] ^= 1;
    if (e.phase == 3 || !adler_only)
        std::fprintf(stderr,"[nvcompaccept] descriptor-readback chunk=%u phase=%u mode=%s\n",
                     e.chunk,e.phase,e.mode);
}
const char *fault_mode() {
    const char *mode = std::getenv("MC_NVCOMP_ACCEPTANCE_FAULT");
    if (!mode) return nullptr;
    if (std::strcmp(mode,"status") && std::strcmp(mode,"size") && std::strcmp(mode,"adler"))
        return "invalid";
    return mode;
}
}
extern "C" cudaError_t __wrap_cudaLaunchKernel(const void *func, dim3 grid, dim3 block,
                                              void **args, size_t shmem, cudaStream_t stream) {
    if (!reported) { reported = true; std::atexit(report); }
    if (block.x == 16 && block.y == 16 && block.z == 1 && from_ingest()) ++gain_launches;
    return __real_cudaLaunchKernel(func,grid,block,args,shmem,stream);
}
extern "C" cudaError_t __wrap_cudaMemcpyAsync(void *dst, const void *src, size_t n,
                                             cudaMemcpyKind kind, cudaStream_t stream) {
    if (!reported) { reported = true; std::atexit(report); }
    const cudaError_t result = __real_cudaMemcpyAsync(dst,src,n,kind,stream);
    if (result != cudaSuccess || kind != cudaMemcpyDeviceToHost || !from_ingest())
        return result;
    const unsigned index = readback++;
    const char *mode = fault_mode();
    if (!mode) return result;
    if (std::strcmp(mode,"invalid") == 0) return cudaErrorInvalidValue;
    const unsigned phase = index % 3 + 1;
    const unsigned chunk = index / 3;
    const char *target_env = std::getenv("MC_NVCOMP_ACCEPTANCE_CHUNK");
    const unsigned target = target_env ? (unsigned)std::strtoul(target_env,nullptr,10) : 0u;
    if (chunk != target) return result;
    const size_t unit = phase == 1 ? sizeof(nvcompStatus_t) :
                        phase == 2 ? sizeof(size_t) : sizeof(unsigned);
    if (n < 2 * unit || n % unit) return cudaErrorInvalidValue;
    edits[phase-1] = {dst,phase,chunk,mode};
    return cudaLaunchHostFunc(stream,change,&edits[phase-1]);
}
