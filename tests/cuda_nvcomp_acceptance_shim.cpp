// Test-only interposition at the actual ingest caller's descriptor readback.
// The decoder runs on HEALTHY input. A host callback changes only the returned
// acceptance descriptors, not compressed data or the decoder's device output.
// Separate direct-kernel tests prove that device rejection avoids output reads.
// No poisoned context or malformed-Deflate decoder safety is claimed here.
#include <cuda_runtime.h>
#include <nvcomp.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>

extern "C" cudaError_t __real_cudaMemcpyAsync(void *, const void *, size_t,
                                             cudaMemcpyKind, cudaStream_t);
namespace {
unsigned readback = 0;
struct Edit { void *dst; unsigned phase; const char *mode; } edits[3];
bool from_ingest() {
    void *frames[24]; const int n = backtrace(frames,24);
    for (int i = 1; i < n; ++i) {
        Dl_info info{};
        if (dladdr(frames[i],&info) && info.dli_sname &&
            std::strstr(info.dli_sname,"ingestCompressedTiffStrips")) return true;
    }
    return false;
}
void CUDART_CB change(void *p) {
    const Edit &e = *static_cast<Edit *>(p);
    if (e.phase == 1 && std::strcmp(e.mode,"status") == 0)
        static_cast<nvcompStatus_t *>(e.dst)[1] = static_cast<nvcompStatus_t>(-1);
    if (e.phase == 2 && std::strcmp(e.mode,"size") == 0)
        --static_cast<size_t *>(e.dst)[1];
    // A bad checksum in EARLIER chunk zero powers status-before-Adler ordering.
    if (e.phase == 3) static_cast<unsigned *>(e.dst)[0] ^= 1;
    std::fprintf(stderr,"[nvcompaccept] descriptor-readback phase=%u mode=%s\n",e.phase,e.mode);
}
}
extern "C" cudaError_t __wrap_cudaMemcpyAsync(void *dst, const void *src, size_t n,
                                             cudaMemcpyKind kind, cudaStream_t stream) {
    const cudaError_t result = __real_cudaMemcpyAsync(dst,src,n,kind,stream);
    const char *mode = std::getenv("MC_NVCOMP_ACCEPTANCE_FAULT");
    if (result != cudaSuccess || !mode || kind != cudaMemcpyDeviceToHost || !from_ingest())
        return result;
    if (++readback > 3 || (std::strcmp(mode,"status") && std::strcmp(mode,"size")))
        return cudaErrorInvalidValue;
    const size_t unit = readback == 1 ? sizeof(nvcompStatus_t) :
                        readback == 2 ? sizeof(size_t) : sizeof(unsigned);
    if (n < 2 * unit || n % unit) return cudaErrorInvalidValue;
    edits[readback-1] = {dst,readback,mode};
    return cudaLaunchHostFunc(stream,change,&edits[readback-1]);
}
