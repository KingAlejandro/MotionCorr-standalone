// Cost of pinning the 128 MiB nvCOMP staging pool once, in a fresh process, and
// whether it meets direct compaction. One JSON line per process.
//
//   hostalloc   cudaHostAlloc (main)
//   reg_huge    2 MiB-aligned mmap + MADV_DONTFORK + MADV_HUGEPAGE + cudaHostRegister (this branch)
//   reg_4k      the same with MADV_NOHUGEPAGE (no THP, so no compaction on fault)
//
// vmstat deltas are system-wide, so other tenants can add to them; acquire_ms
// and the region's AnonHugePages are this process's own.
//
// nvcc -O2 -o pin_probe pin_probe.cu && ./pin_probe reg_huge
#include <cuda_runtime.h>
#include <sys/mman.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>

#define CK(x) do { cudaError_t e_ = (x); if (e_ != cudaSuccess) { std::printf("{\"error\":\"%s\"}\n", cudaGetErrorString(e_)); std::exit(2); } } while (0)

static const size_t kBytes = (size_t)128 << 20, kHuge = (size_t)2 << 20;
static const char *kKeys[] = {"compact_stall", "compact_fail", "compact_success", "thp_fault_alloc",
                              "thp_fault_fallback", "compact_migrate_scanned", "compact_free_scanned",
                              "allocstall_normal", "allocstall_movable"};

static std::map<std::string, long long> vmstat() {
    std::map<std::string, long long> m;
    std::ifstream f("/proc/vmstat");
    std::string k; long long v;
    while (f >> k >> v) m[k] = v;
    return m;
}

// Free blocks of order >= 9 (2 MiB with 4 KiB pages) over all Normal zones.
static long long freeHugeBlocks() {
    std::ifstream f("/proc/buddyinfo");
    std::string line; long long n = 0;
    while (std::getline(f, line)) {
        if (line.find("Normal") == std::string::npos) continue;
        std::istringstream is(line.substr(line.find("Normal") + 6));
        long long c; int order = 0;
        while (is >> c) { if (order >= 9) n += c << (order - 9); ++order; }
    }
    return n;
}

static long long anonHugeKb(void *p) {
    std::ifstream f("/proc/self/smaps");
    std::string line; const uintptr_t a = (uintptr_t)p; bool in = false;
    while (std::getline(f, line)) {
        unsigned long lo, hi;
        if (std::sscanf(line.c_str(), "%lx-%lx ", &lo, &hi) == 2 && line.find(':') > line.find(' ')) { in = a >= lo && a < hi; continue; }
        long long kb;
        if (in && std::sscanf(line.c_str(), "AnonHugePages: %lld kB", &kb) == 1) return kb;
    }
    return -1;
}

static void *mapAligned(int advice) {
    const size_t span = kBytes + kHuge;
    void *raw = mmap(nullptr, span, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) return nullptr;
    uintptr_t base = (uintptr_t)raw, al = (base + kHuge - 1) & ~(uintptr_t)(kHuge - 1);
    if (al > base) munmap(raw, al - base);
    if (base + span > al + kBytes) munmap((void *)(al + kBytes), base + span - (al + kBytes));
    madvise((void *)al, kBytes, MADV_DONTFORK);
    madvise((void *)al, kBytes, advice);
    return (void *)al;
}

int main(int argc, char **argv) {
    const std::string method = argc > 1 ? argv[1] : "reg_huge";
    CK(cudaFree(0));
    const long long blocks = freeHugeBlocks();
    const auto v0 = vmstat();
    const auto t0 = std::chrono::steady_clock::now();
    void *h = nullptr;
    if (method == "hostalloc") CK(cudaHostAlloc(&h, kBytes, cudaHostAllocDefault));
    else {
        h = mapAligned(method == "reg_huge" ? MADV_HUGEPAGE : MADV_NOHUGEPAGE);
        if (!h) { std::printf("{\"error\":\"mmap\"}\n"); return 2; }
        CK(cudaHostRegister(h, kBytes, cudaHostRegisterDefault));
    }
    const auto t1 = std::chrono::steady_clock::now();
    const auto v1 = vmstat();
    const long long huge_kb = method == "hostalloc" ? -1 : anonHugeKb(h);
    const auto t2 = std::chrono::steady_clock::now();
    if (method == "hostalloc") CK(cudaFreeHost(h));
    else { CK(cudaHostUnregister(h)); munmap(h, kBytes); }
    const auto t3 = std::chrono::steady_clock::now();
    auto ms = [](auto a, auto b) { return std::chrono::duration<double, std::milli>(b - a).count(); };
    std::printf("{\"method\":\"%s\",\"acquire_ms\":%.2f,\"release_ms\":%.2f,\"anon_huge_kb\":%lld,\"free_2m_blocks\":%lld",
                method.c_str(), ms(t0, t1), ms(t2, t3), huge_kb, blocks);
    for (const char *k : kKeys) {
        auto a = v0.find(k), b = v1.find(k);
        if (a != v0.end() && b != v1.end()) std::printf(",\"d_%s\":%lld", k, b->second - a->second);
    }
    std::printf("}\n");
    return 0;
}
