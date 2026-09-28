// Minimal stub: enough of the CUDA runtime surface for a HOST-ONLY syntax check.
#pragma once
#include <cstddef>
typedef int cudaError_t;
enum { cudaSuccess = 0, cudaErrorMemoryAllocation = 2 };
typedef struct CUstream_st *cudaStream_t;
typedef struct CUevent_st *cudaEvent_t;
enum cudaMemcpyKind { cudaMemcpyHostToDevice, cudaMemcpyDeviceToHost,
                      cudaMemcpyDeviceToDevice, cudaMemcpyHostToHost, cudaMemcpyDefault };
struct cudaDeviceProp { char name[256]; size_t totalGlobalMem; int major, minor; };
inline cudaError_t cudaMalloc(void **p, size_t n) { (void)p; (void)n; return 0; }
inline cudaError_t cudaFree(void *p) { (void)p; return 0; }
inline cudaError_t cudaMemcpy(void *d, const void *s, size_t n, cudaMemcpyKind k) { (void)d;(void)s;(void)n;(void)k; return 0; }
inline cudaError_t cudaMemcpyAsync(void *d, const void *s, size_t n, cudaMemcpyKind k, cudaStream_t t) { (void)d;(void)s;(void)n;(void)k;(void)t; return 0; }
inline cudaError_t cudaMemset(void *d, int v, size_t n) { (void)d;(void)v;(void)n; return 0; }
inline cudaError_t cudaDeviceSynchronize() { return 0; }
inline cudaError_t cudaStreamSynchronize(cudaStream_t s) { (void)s; return 0; }
inline cudaError_t cudaStreamCreate(cudaStream_t *s) { (void)s; return 0; }
inline cudaError_t cudaStreamDestroy(cudaStream_t s) { (void)s; return 0; }
inline cudaError_t cudaEventCreate(cudaEvent_t *e) { (void)e; return 0; }
inline cudaError_t cudaEventDestroy(cudaEvent_t e) { (void)e; return 0; }
inline cudaError_t cudaEventRecord(cudaEvent_t e, cudaStream_t s) { (void)e;(void)s; return 0; }
inline cudaError_t cudaEventSynchronize(cudaEvent_t e) { (void)e; return 0; }
inline cudaError_t cudaEventElapsedTime(float *ms, cudaEvent_t a, cudaEvent_t b) { (void)ms;(void)a;(void)b; return 0; }
inline cudaError_t cudaGetLastError() { return 0; }
inline cudaError_t cudaPeekAtLastError() { return 0; }
inline const char *cudaGetErrorString(cudaError_t e) { (void)e; return "stub"; }
inline cudaError_t cudaSetDevice(int d) { (void)d; return 0; }
inline cudaError_t cudaGetDevice(int *d) { (void)d; return 0; }
inline cudaError_t cudaGetDeviceCount(int *n) { (void)n; return 0; }
inline cudaError_t cudaGetDeviceProperties(cudaDeviceProp *p, int d) { (void)p;(void)d; return 0; }
inline cudaError_t cudaMemGetInfo(size_t *f, size_t *t) { (void)f;(void)t; return 0; }
inline cudaError_t cudaDeviceReset() { return 0; }
inline cudaError_t cudaHostAlloc(void **p, size_t n, unsigned f) { (void)p;(void)n;(void)f; return 0; }
inline cudaError_t cudaFreeHost(void *p) { (void)p; return 0; }
enum { cudaErrorNotReady = 600 };
#define cudaStreamPerThread ((cudaStream_t)2)
inline cudaError_t cudaEventQuery(cudaEvent_t e) { (void)e; return 0; }
inline cudaError_t cudaEventCreateWithFlags(cudaEvent_t *e, unsigned f) { (void)e;(void)f; return 0; }
