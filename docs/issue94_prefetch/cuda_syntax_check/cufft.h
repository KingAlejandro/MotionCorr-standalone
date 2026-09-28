#pragma once
#include <cuda_runtime.h>
struct cufftComplex { float x, y; };
struct cufftDoubleComplex { double x, y; };
typedef float cufftReal;
typedef int cufftHandle;
typedef int cufftResult;
enum { CUFFT_SUCCESS = 0, CUFFT_R2C = 0x2a, CUFFT_C2R = 0x2c, CUFFT_C2C = 0x29 };
typedef int cufftType;
inline cufftResult cufftPlan2d(cufftHandle *p, int nx, int ny, cufftType t) { (void)p;(void)nx;(void)ny;(void)t; return 0; }
inline cufftResult cufftPlanMany(cufftHandle *p, int r, int *n, int *ie, int is, int id, int *oe, int os, int od, cufftType t, int b) { (void)p;(void)r;(void)n;(void)ie;(void)is;(void)id;(void)oe;(void)os;(void)od;(void)t;(void)b; return 0; }
inline cufftResult cufftDestroy(cufftHandle p) { (void)p; return 0; }
inline cufftResult cufftExecR2C(cufftHandle p, cufftReal *i, cufftComplex *o) { (void)p;(void)i;(void)o; return 0; }
inline cufftResult cufftExecC2R(cufftHandle p, cufftComplex *i, cufftReal *o) { (void)p;(void)i;(void)o; return 0; }
inline cufftResult cufftSetStream(cufftHandle p, cudaStream_t s) { (void)p;(void)s; return 0; }
inline cufftResult cufftGetSize(cufftHandle p, size_t *s) { (void)p;(void)s; return 0; }
