// Decompose CUDA process startup, standalone. No MotionCorr code, so whatever
// this shows is a property of the driver/runtime on this host, not of the
// application. Stages are timed separately because they have different causes:
// context creation is driver work, the first cuFFT plan pays library init on
// top of plan construction, and a first kernel launch pays module loading.
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <cuda_runtime.h>
#include <cufft.h>

using clk = std::chrono::steady_clock;
static double ms(clk::time_point a, clk::time_point b) {
  return std::chrono::duration<double, std::milli>(b - a).count();
}
__global__ void touch(float *p) { p[threadIdx.x] = 1.0f; }

int main(int argc, char **argv) {
  const int NX = argc > 1 ? atoi(argv[1]) : 3710;
  const int NY = argc > 2 ? atoi(argv[2]) : 3838;
  const char *tag = argc > 3 ? argv[3] : "probe";
  // NOTHING may touch CUDA before t0. An earlier version called cudaFree(0)
  // here to "discard" a warm-up, but that call IS context creation, so the
  // stage below then measured an already-initialised context and read 0.0 ms.
  auto t0 = clk::now();

  // 1. context creation: the first CUDA call pays for it
  cudaError_t e = cudaSetDevice(0);
  if (e != cudaSuccess) { fprintf(stderr, "setDevice: %s\n", cudaGetErrorString(e)); return 1; }
  cudaFree(0);
  auto t1 = clk::now();

  // 2. first device allocation of a movie-sized frame buffer
  float *d = nullptr;
  size_t bytes = (size_t)NX * NY * sizeof(float);
  if (cudaMalloc(&d, bytes) != cudaSuccess) { fprintf(stderr, "malloc\n"); return 1; }
  auto t2 = clk::now();

  // 3. first kernel launch: module load + JIT
  touch<<<1, 32>>>(d);
  cudaDeviceSynchronize();
  auto t3 = clk::now();

  // 4. first cuFFT plan: library init + plan construction
  cufftHandle p1; size_t wb = 0; int n[2] = {NY, NX};
  cufftCreate(&p1);
  cufftMakePlanMany(p1, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_R2C, 1, &wb);
  auto t4 = clk::now();

  // 5. second identical plan: plan construction alone, library already up
  cufftHandle p2;
  cufftCreate(&p2);
  cufftMakePlanMany(p2, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_R2C, 1, &wb);
  auto t5 = clk::now();

  printf("PROBE tag=%s ctx_ms=%.1f malloc_ms=%.1f kernel_ms=%.1f "
         "fft_first_ms=%.1f fft_second_ms=%.1f total_ms=%.1f\n",
         tag, ms(t0, t1), ms(t1, t2), ms(t2, t3), ms(t3, t4), ms(t4, t5), ms(t0, t5));
  cufftDestroy(p1); cufftDestroy(p2); cudaFree(d);
  return 0;
}
