#include "src/acc/cuda/cuda_adler32_kernel.cuh"
#include <iostream>
#include <stdexcept>
#include <vector>

int main() {
    try {
        std::vector<unsigned char> v(8192, 0xff);
        nvcompStatus_t status = nvcompSuccess;
        size_t size = v.size();
        uint32_t out = 0;
        adler32StripsKernel(v.data(), size, size, size, 1, &status, &size, &out, 1);
        uint32_t a = 1, b = 0;
        for (auto d : v) { a = (a + d) % 65521; b = (b + a) % 65521; }
        if (out != ((b << 16) | a)) throw std::runtime_error("actual kernel normal checksum");
        size = 503;
        adler32StripsKernel(v.data(), 1024, 1001, 503, 1, &status, &size, &out, 1);
        a = 1; b = 0;
        for (size_t i = 0; i < size; ++i) { a = (a + v[i]) % 65521; b = (b + a) % 65521; }
        if (out != ((b << 16) | a)) throw std::runtime_error("actual kernel final strip checksum");
        out = 0xdeadbeef; size = 8; status = nvcompErrorInvalidValue;
        adler32StripsKernel(nullptr, 8, 8, 8, 1, &status, &size, &out, 1);
        if (out != 0xdeadbeef) throw std::runtime_error("failed status checksum slot changed");
        size = 7; status = nvcompSuccess;
        adler32StripsKernel(nullptr, 8, 8, 8, 1, &status, &size, &out, 1);
        if (out != 0xdeadbeef) throw std::runtime_error("short size checksum slot changed");
        std::cout << "PASS: actual kernel body, one CPU lane: healthy/full/short, "
                     "failed-status and short-size null-output guards\n";
    } catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
