// SPDX-License-Identifier: GPL-2.0-or-later
// Healthy controlled input; injected API statuses are not damaged-stream tests.
#include <nvtiff.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
static int calls=0;
static bool mode(const char* s){const char* m=std::getenv("MC_NVTIFF_FAULT");return m&&std::strcmp(m,s)==0;}
template<class T> T real(const char* name){auto p=dlsym(RTLD_NEXT,name);if(!p){std::fprintf(stderr,"INTERPOSER missing %s\n",name);std::abort();}return reinterpret_cast<T>(p);}
extern "C" nvtiffStatus_t nvtiffDecode(nvtiffStream_t t,nvtiffDecoder_t d,nvtiffDecodeParams_t p,nvtiffImage_t* i,cudaStream_t s){
    ++calls;std::fprintf(stderr,"INTERPOSER decode %d\n",calls);
    if(mode("decode-refusal"))return NVTIFF_STATUS_TIFF_NOT_SUPPORTED;
    if(mode("decode-execution"))return NVTIFF_STATUS_EXECUTION_FAILED;
    return real<decltype(&nvtiffDecode)>("nvtiffDecode")(t,d,p,i,s);
}
extern "C" cudaError_t cudaStreamSynchronize(cudaStream_t s){
    auto rc=real<decltype(&cudaStreamSynchronize)>("cudaStreamSynchronize")(s);
    if(calls&&mode("completion")){std::fprintf(stderr,"INTERPOSER completion\n");return cudaErrorIllegalAddress;}
    return rc;
}
extern "C" nvtiffStatus_t nvtiffDecoderDestroy(nvtiffDecoder_t d,cudaStream_t s){
    auto rc=real<decltype(&nvtiffDecoderDestroy)>("nvtiffDecoderDestroy")(d,s);
    std::fprintf(stderr,"INTERPOSER destroy %d\n",calls);
    if(mode("destroy"))return NVTIFF_STATUS_INTERNAL_ERROR;
    return rc;
}
