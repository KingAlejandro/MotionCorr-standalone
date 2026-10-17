// Reproducer for CUDA "last error" semantics: a failed cudaMalloc (returned and handled) leaves
// cudaErrorMemoryAllocation pending; the next cudaGetLastError() after an unrelated, successful
// kernel launch returns it. Uses almost no device memory.
#include <cuda_runtime.h>
#include <cstdio>
__global__ void nop() {}
int main() {
  cudaSetDevice(0);
  size_t f, t; cudaMemGetInfo(&f, &t);
  void *p = nullptr;
  cudaError_t e = cudaMalloc(&p, f + (4ull << 30));   // must fail: more than free
  printf("1. cudaMalloc(free+4GiB)            -> %s (handled by caller; error return consumed)\n", cudaGetErrorString(e));
  void *q = nullptr;
  e = cudaMalloc(&q, 1 << 20);
  printf("2. cudaMalloc(1 MiB), unrelated      -> %s\n", cudaGetErrorString(e));
  nop<<<1, 1>>>();
  e = cudaGetLastError();
  printf("3. cudaGetLastError() after good launch -> %s   <-- stale error from step 1\n", cudaGetErrorString(e));
  e = cudaGetLastError();
  printf("4. cudaGetLastError() again          -> %s\n", cudaGetErrorString(e));
  // Control: clear first, then launch.
  cudaMalloc(&p, f + (4ull << 30));
  (void)cudaGetLastError();
  nop<<<1, 1>>>();
  printf("5. control (clear before launch)     -> %s\n", cudaGetErrorString(cudaGetLastError()));
  return 0;
}
