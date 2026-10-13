// Startup-cost probe: times cuInit, context creation and pinned allocation.
// probe hold <sec>          : cuInit only, then sleep (keeps GPUs attached, no context, no VRAM)
// probe time <dev> <MiB> [hugepage]
#include <cuda.h>
#include <cuda_runtime.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include <unistd.h>
static double now() { return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
#define CK(x) do { auto e = (x); if (e) { fprintf(stderr, "%s failed %d\n", #x, (int)e); return 1; } } while (0)
int main(int argc, char **argv) {
  if (argc >= 3 && !strcmp(argv[1], "hold")) { CK(cuInit(0)); fprintf(stderr, "holding\n"); sleep(atoi(argv[2])); return 0; }
  int dev = atoi(argv[2]); size_t mib = atoi(argv[3]); bool huge = argc > 4;
  double t0 = now(); CK(cuInit(0));
  double t1 = now(); CK(cudaSetDevice(dev)); CK(cudaFree(0));
  double t2 = now(); void *p; CK(cudaHostAlloc(&p, mib << 20, cudaHostAllocDefault));
  double t3 = now(); CK(cudaFreeHost(p));
  double t4 = now();
  void *q = mmap(nullptr, mib << 20, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (huge) madvise(q, mib << 20, MADV_HUGEPAGE);
  memset(q, 0, mib << 20);
  double t5 = now(); CK(cudaHostRegister(q, mib << 20, cudaHostRegisterDefault));
  double t6 = now(); CK(cudaHostUnregister(q));
  double t7 = now(); CK(cudaDeviceReset());
  double t8 = now();
  printf("dev=%d cuInit=%.1f ctx=%.1f hostAlloc=%.1f freeHost=%.1f touch=%.1f hostRegister=%.1f unregister=%.1f reset=%.1f ms\n",
         dev, t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4, t6 - t5, t7 - t6, t8 - t7);
  return 0;
}
