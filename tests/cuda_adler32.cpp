#include "src/acc/cuda/cuda_adler32_kernel.cuh"
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void check(cudaError_t e) {
    if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));
}
static uint32_t serial(const uint8_t *p, size_t n) {
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < n; ++i) { a = (a + p[i]) % 65521; b = (b + a) % 65521; }
    return (b << 16) | a;
}
int main(int argc, char **argv) {
    const std::string mode = argc == 3 && std::string(argv[1]) == "--case" ? argv[2] : "all";
    unsigned char *data = nullptr;
    unsigned char *large = nullptr;
    nvcompStatus_t *statuses = nullptr;
    size_t *sizes = nullptr;
    uint32_t *output = nullptr;
    try {
        check(cudaSetDevice(0));
        check(cudaMalloc((void **)&statuses, 4 * sizeof(nvcompStatus_t)));
        check(cudaMalloc((void **)&sizes, 4 * sizeof(size_t)));
        check(cudaMalloc((void **)&output, 4 * sizeof(uint32_t)));
        if (mode == "all" || mode == "healthy") {
            // Two frames, two strips each: full 1001-byte strip, short 503-byte
            // final strip, 1024-byte pitch. Padding must never enter the checksum.
            std::vector<uint8_t> host(4096, 0xa7);
            for (size_t c = 0; c < 4; ++c)
                for (size_t i = 0; i < (c % 2 ? 503u : 1001u); ++i)
                    host[c * 1024 + i] = uint8_t(i * 29 + c * 71);
            check(cudaMalloc((void **)&data, host.size()));
            check(cudaMemcpy(data, host.data(), host.size(), cudaMemcpyHostToDevice));
            nvcompStatus_t status[4] = {nvcompSuccess,nvcompSuccess,nvcompSuccess,nvcompSuccess};
            size_t size[4] = {1001,503,1001,503};
            check(cudaMemcpy(statuses, status, sizeof(status), cudaMemcpyHostToDevice));
            check(cudaMemcpy(sizes, size, sizeof(size), cudaMemcpyHostToDevice));
            adler32StripsKernel<<<4,256>>>(data,1024,1001,503,2,statuses,sizes,output,4);
            check(cudaGetLastError()); check(cudaDeviceSynchronize());
            uint32_t actual[4];
            check(cudaMemcpy(actual, output, sizeof(actual), cudaMemcpyDeviceToHost));
            for (size_t c = 0; c < 4; ++c)
                if (actual[c] != serial(host.data() + c * 1024, size[c]))
                    throw std::runtime_error("healthy/short checksum mismatch");
        }
        if (mode == "all" || mode == "large") {
            // Bounded 512 MiB real device allocation, no TIFF fixture. This
            // exercises the ACTUAL 256-lane kernel past the predecessor's
            // uint64 weighted-reduction overflow boundary, not only its helper.
            const size_t size = size_t(512) << 20;
            const nvcompStatus_t status = nvcompSuccess;
            check(cudaMalloc((void **)&large, size));
            check(cudaMemset(large, 255, size));
            check(cudaMemcpy(statuses, &status, sizeof(status), cudaMemcpyHostToDevice));
            check(cudaMemcpy(sizes, &size, sizeof(size), cudaMemcpyHostToDevice));
            adler32StripsKernel<<<1,256>>>(large,size,size,size,1,statuses,sizes,output,1);
            check(cudaGetLastError()); check(cudaDeviceSynchronize());
            uint32_t actual;
            check(cudaMemcpy(&actual, output, sizeof(actual), cudaMemcpyDeviceToHost));
            if (actual != 0x2a2a3c03u) throw std::runtime_error("512MiB native checksum mismatch");
            check(cudaFree(large)); large = nullptr;
        }
        for (const char *which : {"failed-status", "short-size"}) {
            if (mode != "all" && mode != which) continue;
            const nvcompStatus_t status = std::string(which) == "failed-status"
                ? static_cast<nvcompStatus_t>(-1) : nvcompSuccess;
            const size_t size = std::string(which) == "short-size" ? 7 : 8;
            const uint32_t sentinel = 0xdeadbeefu;
            check(cudaMemcpy(statuses, &status, sizeof(status), cudaMemcpyHostToDevice));
            check(cudaMemcpy(sizes, &size, sizeof(size), cudaMemcpyHostToDevice));
            check(cudaMemcpy(output, &sentinel, sizeof(sentinel), cudaMemcpyHostToDevice));
            // Intentionally inaccessible output. A missing status/length gate
            // tries to read null and fails the launch completion, rather than
            // accidentally checksumming an initialized output buffer.
            adler32StripsKernel<<<1,256>>>(nullptr,8,8,8,1,statuses,sizes,output,1);
            check(cudaGetLastError()); check(cudaDeviceSynchronize());
            uint32_t actual;
            check(cudaMemcpy(&actual, output, sizeof(actual), cudaMemcpyDeviceToHost));
            if (actual != sentinel) throw std::runtime_error("rejected checksum slot changed");
        }
        if (mode != "all" && mode != "healthy" && mode != "large" &&
            mode != "failed-status" && mode != "short-size")
            throw std::runtime_error("unknown case");
        check(cudaFree(data)); data = nullptr;
        check(cudaFree(statuses)); statuses = nullptr;
        check(cudaFree(sizes)); sizes = nullptr;
        check(cudaFree(output)); output = nullptr;
        std::cout << "PASS: actual Adler kernel " << mode << '\n';
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        cudaFree(data); cudaFree(large); cudaFree(statuses); cudaFree(sizes); cudaFree(output);
        return 1;
    }
}
