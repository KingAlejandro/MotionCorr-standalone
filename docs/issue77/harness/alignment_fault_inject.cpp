// Test-only LD_PRELOAD shim. It injects once AFTER the flushed global alignment
// marker, excluding movie-session preprocessing/FFT allocation. Never linked
// into or shipped with the production executable; never used for timings.
#include <cuda_runtime_api.h>
#include <cufft.h>
#include <dlfcn.h>
#include <atomic>
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
static std::atomic<bool> fired(false);
static bool inject(const char *kind) {
    const char *requested=std::getenv("MC_TEST_FAULT_KIND");
    const char *logpath=std::getenv("MC_TEST_FAULT_LOG");
    if(!requested || !logpath || std::string(requested)!=kind || fired.load()) return false;
    std::ifstream stream(logpath);
    std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    if(text.find("\nGlobal alignment:\n")==std::string::npos || text.find("[CUDA Global Alignment] completed")!=std::string::npos) return false;
    bool expected=false;
    if(!fired.compare_exchange_strong(expected,true)) return false;
    std::fprintf(stderr,"[TEST_ONLY_FAULT] %s injected after flushed global alignment marker in %s\n",kind,logpath);
    std::fflush(stderr);
    return true;
}
extern "C" cudaError_t cudaMalloc(void **ptr,size_t bytes) {
    if(inject("cudaMalloc")) { *ptr=nullptr;return cudaErrorMemoryAllocation; }
    using F=cudaError_t (*)(void**,size_t);
    static F original=reinterpret_cast<F>(dlsym(RTLD_NEXT,"cudaMalloc"));
    return original(ptr,bytes);
}
extern "C" cufftResult cufftPlanMany(cufftHandle *plan,int rank,int *n,int *inembed,int istride,int idist,int *onembed,int ostride,int odist,cufftType type,int batch) {
    if(inject("cufftPlanMany")) { *plan=0;return CUFFT_ALLOC_FAILED; }
    using F=cufftResult (*)(cufftHandle*,int,int*,int*,int,int,int*,int,int,cufftType,int);
    static F original=reinterpret_cast<F>(dlsym(RTLD_NEXT,"cufftPlanMany"));
    return original(plan,rank,n,inembed,istride,idist,onembed,ostride,odist,type,batch);
}
