// Process with a context and a 128 MiB pinned buffer; PROBE_RESET=1 tears down explicitly.
#include <cuda_runtime.h>
#include <cstdlib>
int main() { cudaSetDevice(0); void *p; cudaHostAlloc(&p, 128u << 20, 0); void *d; cudaMalloc(&d, 1u << 30);
  if (getenv("PROBE_RESET")) { cudaFree(d); cudaFreeHost(p); cudaDeviceReset(); } return 0; }
