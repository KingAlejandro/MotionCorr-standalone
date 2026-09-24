// Compare every scalar in one pair of exact Issue #36 trace chunks.
// Build: g++ -O3 -std=gnu++17 tools/compare_full_trace_chunk.cpp -lcrypto -o /tmp/compare_full_trace_chunk
// Usage: compare_full_trace_chunk <cpu.bin> <cuda.bin> <cpu dtype> <cuda dtype>
#include <cmath>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <openssl/evp.h>
#include <string>
#include <vector>

template<typename T>
static double decode(const unsigned char *bytes)
{
    T value;
    std::memcpy(&value, bytes, sizeof(T));
    return (double)value;
}

static std::string hexDigest(EVP_MD_CTX *context)
{
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int length = 0;
    if (EVP_DigestFinal_ex(context, digest, &length) != 1) return "";
    static const char digits[] = "0123456789abcdef";
    std::string hex;
    for (unsigned int i = 0; i < length; ++i) {
        hex += digits[digest[i] >> 4];
        hex += digits[digest[i] & 15];
    }
    return hex;
}

static bool validDtype(const std::string &value)
{
    return value == "f4" || value == "f8" || value == "c8" || value == "i4";
}

static size_t widthOf(const std::string &value) { return value == "f8" ? 8 : 4; }

static double decodeDtype(const unsigned char *value, const std::string &dtype)
{
    if (dtype == "f8") return decode<double>(value);
    if (dtype == "i4") return decode<int32_t>(value);
    return decode<float>(value);
}

int main(int argc, char **argv)
{
    if (argc != 5) return 2;
    const std::string cpu_dtype = argv[3], cuda_dtype = argv[4];
    if (!validDtype(cpu_dtype) || !validDtype(cuda_dtype)) return 2;
    const size_t cpu_width = widthOf(cpu_dtype), cuda_width = widthOf(cuda_dtype);
    const uintmax_t cpu_bytes = std::filesystem::file_size(argv[1]);
    const uintmax_t cuda_bytes = std::filesystem::file_size(argv[2]);
    if (cpu_bytes % cpu_width || cuda_bytes % cuda_width ||
        cpu_bytes / cpu_width != cuda_bytes / cuda_width) return 3;
    const uintmax_t scalar_count = cpu_bytes / cpu_width;
    std::ifstream cpu(argv[1], std::ios::binary), cuda(argv[2], std::ios::binary);
    if (!cpu || !cuda) return 3;
    EVP_MD_CTX *cpu_hash = EVP_MD_CTX_new(), *cuda_hash = EVP_MD_CTX_new();
    if (!cpu_hash || !cuda_hash || EVP_DigestInit_ex(cpu_hash, EVP_sha256(), nullptr) != 1 ||
        EVP_DigestInit_ex(cuda_hash, EVP_sha256(), nullptr) != 1) return 4;
    const size_t chunk = 1 << 20;
    std::vector<unsigned char> a(chunk * 2), b(chunk * 2);
    uintmax_t processed = 0, different = 0, finite = 0, nonfinite = 0;
    uintmax_t first = std::numeric_limits<uintmax_t>::max();
    double first_cpu = 0, first_cuda = 0, max_abs = 0;
    long double sum_cpu = 0, sum_cpu_sq = 0, sum_diff_sq = 0;
    while (processed < scalar_count) {
        const size_t n = (size_t)std::min<uintmax_t>(chunk / std::max(cpu_width, cuda_width), scalar_count - processed);
        const size_t na = n * cpu_width, nb = n * cuda_width;
        cpu.read((char *)a.data(), na); cuda.read((char *)b.data(), nb);
        if ((size_t)cpu.gcount() != na || (size_t)cuda.gcount() != nb) return 5;
        if (EVP_DigestUpdate(cpu_hash, a.data(), na) != 1 || EVP_DigestUpdate(cuda_hash, b.data(), nb) != 1) return 4;
        for (size_t offset = 0; offset < n; ++offset) {
            const uintmax_t index = processed + offset;
            const double x = decodeDtype(a.data() + offset * cpu_width, cpu_dtype);
            const double y = decodeDtype(b.data() + offset * cuda_width, cuda_dtype);
            if (x != y) {
                ++different;
                if (first == std::numeric_limits<uintmax_t>::max()) { first = index; first_cpu = x; first_cuda = y; }
            }
            if (!std::isfinite(x) || !std::isfinite(y)) { ++nonfinite; continue; }
            const long double delta = (long double)x - (long double)y;
            sum_cpu += x; sum_cpu_sq += (long double)x * x;
            sum_diff_sq += delta * delta;
            max_abs = std::max(max_abs, (double)std::abs(delta));
            ++finite;
        }
        processed += n;
    }
    const std::string cpu_sha = hexDigest(cpu_hash), cuda_sha = hexDigest(cuda_hash);
    EVP_MD_CTX_free(cpu_hash); EVP_MD_CTX_free(cuda_hash);
    if (cpu_sha.empty() || cuda_sha.empty()) return 4;
    const long double mean = finite ? sum_cpu / finite : 0;
    const long double variance = finite ? std::max((long double)0, sum_cpu_sq / finite - mean * mean) : 0;
    const double rmse = finite ? std::sqrt((double)(sum_diff_sq / finite)) : 0;
    const double relative_l2 = sum_cpu_sq ? std::sqrt((double)(sum_diff_sq / sum_cpu_sq)) : 0;
    const double stddev = std::sqrt((double)variance);
    std::cout << std::setprecision(17)
              << "{\"cpu_dtype\":\"" << cpu_dtype << "\",\"cuda_dtype\":\"" << cuda_dtype
              << "\",\"cpu_bytes\":" << cpu_bytes << ",\"cuda_bytes\":" << cuda_bytes
              << ",\"scalar_count\":" << scalar_count
              << ",\"scalar_different\":" << different
              << ",\"first_different_scalar\":";
    if (first == std::numeric_limits<uintmax_t>::max()) std::cout << "null";
    else std::cout << first;
    std::cout << ",\"first_cpu\":" << first_cpu << ",\"first_cuda\":" << first_cuda
              << ",\"nonfinite\":" << nonfinite << ",\"rmse\":" << rmse
              << ",\"relative_l2\":";
    if (!sum_cpu_sq && sum_diff_sq) std::cout << "null";
    else std::cout << relative_l2;
    std::cout << ",\"cpu_std\":" << stddev << ",\"relative_rmse_std\":";
    if (!stddev && rmse) std::cout << "null";
    else std::cout << (stddev ? rmse / stddev : 0);
    std::cout
              << ",\"max_abs\":" << max_abs
              << ",\"cpu_sha256\":\"" << cpu_sha << "\",\"cuda_sha256\":\"" << cuda_sha << "\"}\n";
    return nonfinite ? 6 : 0;
}
