#include <cuda_runtime_api.h>
#include <cstdio>
#include <cstdlib>

// CLI-only witness: return a single logical device without consulting CUDA.
// Every test uses a nonexistent STAR and must exit before processing a movie.
extern "C" cudaError_t cudaGetDeviceCount(int *count)
{
    const char *path = std::getenv("MC_ENUM_WITNESS");
    if (!path) std::abort();
    FILE *out = std::fopen(path, "a");
    if (!out) std::abort();
    std::fputs("cudaGetDeviceCount\n", out);
    if (std::fclose(out) != 0) std::abort();
    *count = 1;
    return cudaSuccess;
}
