// VRAM balloon: cudaMalloc N MiB on the visible device, touch it, report, sleep until killed.
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
#include <signal.h>
int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: balloon MiB\n"); return 2; }
  size_t mib = strtoull(argv[1], 0, 10);
  size_t chunk = 1024ull << 20;  // 1 GiB allocations so a tail remainder is exact
  size_t left = mib << 20;
  if (cudaSetDevice(0) != cudaSuccess) { fprintf(stderr, "setdevice failed\n"); return 3; }
  while (left) {
    size_t n = left < chunk ? left : chunk; void *p = nullptr;
    cudaError_t e = cudaMalloc(&p, n);
    if (e != cudaSuccess) { fprintf(stderr, "cudaMalloc %zu failed: %s\n", n, cudaGetErrorString(e)); return 4; }
    if (cudaMemset(p, 0xA5, n) != cudaSuccess) { fprintf(stderr, "memset failed\n"); return 5; }
    left -= n;
  }
  cudaDeviceSynchronize();
  size_t f, t; cudaMemGetInfo(&f, &t);
  printf("BALLOON_READY held_mib=%zu free_mib=%zu total_mib=%zu\n", mib, f >> 20, t >> 20); fflush(stdout);
  signal(SIGTERM, SIG_DFL);
  for (;;) sleep(1);
}
