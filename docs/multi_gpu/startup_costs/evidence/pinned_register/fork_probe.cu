// Fork exposure of a 128 MiB pinned host buffer, per pinning method.
//
//   hostalloc        cudaHostAlloc (main's staging pool)
//   register         2 MiB-aligned mmap + MADV_HUGEPAGE + cudaHostRegister (351db93d)
//   register_dfork   the same plus MADV_DONTFORK (this branch)
//
// For each: the VMA's smaps VmFlags ("dc" = not copied on fork), whether a fork
// child still has the address mapped (mincore), how long fork() takes in the
// parent, and whether the device reads what the parent wrote AFTER the fork
// while the child is still alive (stale = the H2D copy read an old page).
//
// nvcc -O2 -o fork_probe fork_probe.cu && ./fork_probe
#include <cuda_runtime.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { std::printf("CUDA error %s at %s\n", cudaGetErrorString(e_), #x); std::exit(2); } } while (0)

static const size_t kBytes = (size_t)128 << 20;
static const size_t kHuge = (size_t)2 << 20;

static std::string vmflags(void *p) {
    std::ifstream f("/proc/self/smaps");
    std::string line, flags = "?";
    const uintptr_t a = (uintptr_t)p;
    bool in = false;
    while (std::getline(f, line)) {
        unsigned long lo, hi;
        if (std::sscanf(line.c_str(), "%lx-%lx ", &lo, &hi) == 2 && line.find(':') > line.find(' ')) {
            in = (a >= lo && a < hi);
            continue;
        }
        if (in && line.rfind("VmFlags:", 0) == 0) { flags = line.substr(9); break; }
    }
    return flags;
}

static void *mapAligned(bool dontfork) {
    const size_t span = kBytes + kHuge;
    void *raw = mmap(nullptr, span, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) { std::perror("mmap"); std::exit(2); }
    uintptr_t base = (uintptr_t)raw, al = (base + kHuge - 1) & ~(uintptr_t)(kHuge - 1);
    if (al > base) munmap(raw, al - base);
    if (base + span > al + kBytes) munmap((void *)(al + kBytes), base + span - (al + kBytes));
    if (dontfork && madvise((void *)al, kBytes, MADV_DONTFORK) != 0) { std::perror("madvise DONTFORK"); std::exit(2); }
    madvise((void *)al, kBytes, MADV_HUGEPAGE);
    return (void *)al;
}

static void run(const char *name) {
    const bool hostalloc = std::strcmp(name, "hostalloc") == 0;
    const bool dontfork = std::strcmp(name, "register_dfork") == 0;
    void *h = nullptr;
    if (hostalloc) CK(cudaHostAlloc(&h, kBytes, cudaHostAllocDefault));
    else { h = mapAligned(dontfork); CK(cudaHostRegister(h, kBytes, cudaHostRegisterDefault)); }
    std::memset(h, 0x11, kBytes);
    void *d = nullptr;
    CK(cudaMalloc(&d, kBytes));
    std::vector<unsigned char> back(kBytes);

    // to_parent: the child's mincore verdict; to_child: the parent's "copied, exit".
    int to_parent[2], to_child[2];
    if (pipe(to_parent) != 0 || pipe(to_child) != 0) { std::perror("pipe"); std::exit(2); }
    std::fflush(nullptr);
    const auto t0 = std::chrono::steady_clock::now();
    const pid_t pid = fork();
    if (pid == 0) {
        unsigned char vec[1];
        const int mapped = mincore(h, 4096, vec) == 0 ? 1 : (errno == ENOMEM ? 0 : 2);
        char c = (char)('0' + mapped);
        (void)!write(to_parent[1], &c, 1);
        // Stay alive (sharing any COW pages) until the parent has copied.
        char x;
        (void)!read(to_child[0], &x, 1);
        _exit(0);
    }
    const double fork_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    char c = '?';
    (void)!read(to_parent[0], &c, 1);
    // Parent writes a new pattern after the fork, then the device copies it.
    std::memset(h, 0x22, kBytes);
    CK(cudaMemcpy(d, h, kBytes, cudaMemcpyHostToDevice));
    CK(cudaMemcpy(back.data(), d, kBytes, cudaMemcpyDeviceToHost));
    size_t stale = 0;
    for (size_t i = 0; i < kBytes; i += 4096) stale += back[i] != 0x22;
    (void)!write(to_child[1], "x", 1);
    int st = 0;
    waitpid(pid, &st, 0);
    close(to_parent[0]); close(to_parent[1]); close(to_child[0]); close(to_child[1]);

    std::printf("%-15s vmflags=[%s] child_mapped=%c fork_ms=%.1f stale_pages=%zu/%zu\n", name,
                vmflags(h).c_str(), c, fork_ms, stale, kBytes / 4096);
    std::fflush(stdout);
    CK(cudaFree(d));
    if (hostalloc) CK(cudaFreeHost(h));
    else { CK(cudaHostUnregister(h)); munmap(h, kBytes); }
}

int main(int argc, char **argv) {
    CK(cudaFree(0));
    const char *cases[] = {"hostalloc", "register", "register_dfork"};
    const int reps = argc > 1 ? std::atoi(argv[1]) : 3;
    for (int r = 0; r < reps; ++r)
        for (const char *c : cases) run(c);
    return 0;
}
