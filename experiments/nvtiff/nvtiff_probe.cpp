// SPDX-License-Identifier: GPL-2.0-or-later
// Standalone Issue #141 experiment; no MotionCorr processing path is changed.
#include <nvtiff.h>
#if NVTIFF_VER_MAJOR != 0 || NVTIFF_VER_MINOR != 8
#error "This experiment targets the nvTIFF 0.8 IFD-offset/region API."
#endif

#include <algorithm>
#include <chrono>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
using Clock = std::chrono::steady_clock;
double elapsed(Clock::time_point t) {
    return std::chrono::duration<double>(Clock::now() - t).count();
}
void nv(nvtiffStatus_t s, const char* stage) {
    if (s != NVTIFF_STATUS_SUCCESS)
        throw std::runtime_error(std::string(stage) + ": nvTIFF status " + std::to_string(s));
}
void cu(cudaError_t s, const char* stage) {
    if (s != cudaSuccess)
        throw std::runtime_error(std::string(stage) + ": " + cudaGetErrorString(s));
}
size_t product(size_t a, size_t b) {
    if (b && a > std::numeric_limits<size_t>::max() / b)
        throw std::runtime_error("size overflow");
    return a * b;
}
size_t number(const std::string& value) {
    if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("expected a nonnegative decimal integer: " + value);
    const auto n = std::stoull(value);
    if (n > std::numeric_limits<size_t>::max()) throw std::runtime_error("integer too large");
    return static_cast<size_t>(n);
}
std::string quoted(const std::string& s) {
    std::ostringstream out;
    out << '"';
    const char hex[] = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32 || c >= 127) out << "\\u00" << hex[c >> 4] << hex[c & 15];
        else out << c;
    }
    out << '"';
    return out.str();
}
struct Options {
    std::string movie, dump;
    size_t first = 0, count = 0, batch = 1;
    size_t max_input = size_t(1) << 30, max_output = size_t(256) << 20;
    size_t device = 0;
    bool trusted = false, probe = false;
};
Options options(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (key == "--trusted-input") o.trusted = true;
        else if (key == "--probe-only") o.probe = true;
        else if (key == "--help") {
            std::cout << "motioncorr_nvtiff_probe --movie FILE --trusted-input [--probe-only]\n"
                         "  [--dump NEW_FILE] [--first INDEX_0_BASED] [--count N]\n"
                         "  [--batch-frames N] [--device LOCAL_ORDINAL]\n"
                         "  [--max-input-bytes N] [--max-output-bytes N]\n"
                         "Default count: all remaining images; default batch: one frame.\n";
            std::exit(0);
        } else {
            if (i + 1 == argc) throw std::runtime_error("missing value for " + key);
            const std::string value = argv[++i];
            if (key == "--movie") o.movie = value;
            else if (key == "--dump") o.dump = value;
            else if (key == "--first") o.first = number(value);
            else if (key == "--count") o.count = number(value);
            else if (key == "--batch-frames") o.batch = number(value);
            else if (key == "--device") o.device = number(value);
            else if (key == "--max-input-bytes") o.max_input = number(value);
            else if (key == "--max-output-bytes") o.max_output = number(value);
            else throw std::runtime_error("unknown option " + key);
        }
    }
    if (o.movie.empty() || !o.trusted)
        throw std::runtime_error("--movie and --trusted-input are required, including for probing");
    if (!o.batch || !o.max_input || !o.max_output || o.batch > UINT32_MAX || o.device > INT_MAX)
        throw std::runtime_error("invalid resource limit/device/batch size");
    if (o.probe && !o.dump.empty()) throw std::runtime_error("--probe-only cannot write a dump");
    return o;
}

// The library lazily parses this same immutable byte snapshot throughout decode.
// No reopen between admission and decoding. This is not a compressed-data validator.
std::vector<uint8_t> snapshot(const Options& o) {
    int fd = open(o.movie.c_str(), O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) throw std::runtime_error("open input: " + std::string(std::strerror(errno)));
    struct Close { int fd; ~Close() { close(fd); } } close_fd{fd};
    struct stat before{}, after{};
    if (fstat(fd, &before) || !S_ISREG(before.st_mode) || before.st_size <= 0 ||
        static_cast<uintmax_t>(before.st_size) > o.max_input)
        throw std::runtime_error("input must be a nonempty regular file within --max-input-bytes");
    std::vector<uint8_t> data(static_cast<size_t>(before.st_size));
    size_t pos = 0;
    while (pos < data.size()) {
        const auto n = read(fd, data.data() + pos, std::min(data.size() - pos, size_t(1) << 20));
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) throw std::runtime_error("input read failed or truncated");
        pos += static_cast<size_t>(n);
    }
    if (fstat(fd, &after) || before.st_size != after.st_size || before.st_mtime != after.st_mtime ||
        before.st_ctime != after.st_ctime)
        throw std::runtime_error("input changed while taking snapshot");
    return data;
}

struct Resources {
    cudaStream_t stream = nullptr;
    nvtiffStream_t tiff = nullptr;
    nvtiffDecoder_t decoder = nullptr;
    nvtiffDecodeParams_t params = nullptr;
    cudaEvent_t start = nullptr, stop = nullptr;
    void* output = nullptr;
    bool usable = true;
    void cuda(cudaError_t s, const char* stage) {
        if (s != cudaSuccess) usable = false; // No redispatch after an observed CUDA failure.
        cu(s, stage);
    }
    void closeChecked() {
        if (stream && usable) cuda(cudaStreamSynchronize(stream), "cleanup stream completion");
        if (!usable) throw std::runtime_error("CUDA cleanup incomplete; process owns abandoned device state");
        if (decoder) {
            const auto old = decoder; decoder = nullptr;
            const auto s = nvtiffDecoderDestroy(old, stream);
            // Destroy may enqueue frees; complete even if its immediate status failed.
            const auto sync = cudaStreamSynchronize(stream);
            cuda(sync, "decoder destroy completion");
            if (s != NVTIFF_STATUS_SUCCESS) usable = false;
            nv(s, "decoder destroy");
        }
        if (params) { const auto old = params; params = nullptr; nv(nvtiffDecodeParamsDestroy(old), "params destroy"); }
        if (tiff) { const auto old = tiff; tiff = nullptr; nv(nvtiffStreamClose(old), "TIFF close"); }
        if (output) { cuda(cudaFree(output), "output free"); output = nullptr; }
        if (start) { cuda(cudaEventDestroy(start), "start event destroy"); start = nullptr; }
        if (stop) { cuda(cudaEventDestroy(stop), "stop event destroy"); stop = nullptr; }
        if (stream) { cuda(cudaStreamDestroy(stream), "stream destroy"); stream = nullptr; }
    }
    ~Resources() {
        try { closeChecked(); }
        catch (const std::exception& e) { std::cerr << "nvTIFF cleanup: " << e.what() << '\n'; }
    }
};

// Unique sibling temporary; link publishes without replacing an existing path.
// Success publication waits until decoder completion and checked resource cleanup.
struct Dump {
    std::string target, temporary;
    int fd = -1;
    explicit Dump(const std::string& path) : target(path) {
        std::string pattern = path + ".tmp.XXXXXX";
        std::vector<char> p(pattern.begin(), pattern.end()); p.push_back(0);
        fd = mkstemp(p.data());
        if (fd < 0) throw std::runtime_error("create dump temporary: " + std::string(std::strerror(errno)));
        temporary = p.data();
    }
    void write(const void* buffer, size_t bytes) {
        const auto* p = static_cast<const uint8_t*>(buffer);
        while (bytes) {
            const auto n = ::write(fd, p, std::min(bytes, size_t(1) << 20));
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) throw std::runtime_error("write dump failed");
            p += n; bytes -= static_cast<size_t>(n);
        }
    }
    void integer(uint64_t n) {
        uint8_t le[8];
        for (int i = 0; i != 8; ++i) le[i] = static_cast<uint8_t>(n >> (8 * i));
        write(le, sizeof(le));
    }
    void publish() {
        const int old = fd; fd = -1;
        if (close(old)) throw std::runtime_error("close dump failed");
        if (link(temporary.c_str(), target.c_str()))
            throw std::runtime_error("publish dump (destination must not exist): " + std::string(std::strerror(errno)));
        // The complete target is already published; removal failure is explicit.
        if (unlink(temporary.c_str())) throw std::runtime_error("remove dump temporary failed");
        temporary.clear();
    }
    ~Dump() { if (fd >= 0) close(fd); if (!temporary.empty()) unlink(temporary.c_str()); }
};

uint16_t shortTag(nvtiffStream_t s, size_t off, uint16_t tag, uint16_t fallback) {
    nvtiffTagDataType_t type{}; uint32_t size = 0, count = 0;
    const auto status = nvtiffStreamGetTagInfo(s, off, tag, &type, &size, &count);
    if (status == NVTIFF_STATUS_TAG_NOT_FOUND) return fallback;
    nv(status, "tag info");
    if (type != NVTIFF_TAG_TYPE_SHORT || size != 2 || count != 1)
        throw std::runtime_error("unexpected scalar SHORT TIFF tag " + std::to_string(tag));
    uint16_t value = 0;
    nv(nvtiffStreamGetTagValue(s, off, tag, &value, 1), "tag value");
    return value;
}

uint32_t imageDepth(nvtiffStream_t s, size_t off) {
    // ImageDepth is a 3D TIFF extension. Ordinary 2D files omit it, while
    // nvTIFF 0.8 reports geometry.image_depth=0 for those same files.
    nvtiffTagDataType_t type{}; uint32_t size = 0, count = 0;
    const auto status = nvtiffStreamGetTagInfo(s, off, 32997, &type, &size, &count);
    if (status == NVTIFF_STATUS_TAG_NOT_FOUND) return 1;
    nv(status, "ImageDepth tag info");
    if (type != NVTIFF_TAG_TYPE_LONG || size != 4 || count != 1)
        throw std::runtime_error("unexpected scalar LONG ImageDepth tag");
    uint32_t depth = 0;
    nv(nvtiffStreamGetTagValue(s, off, 32997, &depth, 1), "ImageDepth tag value");
    return depth;
}

int run(const Options& o) {
    const auto whole = Clock::now();
    const uint16_t endian = 1;
    if (*reinterpret_cast<const uint8_t*>(&endian) != 1)
        throw std::runtime_error("native sample dump currently requires a little-endian host");
    auto bytes = snapshot(o);
    int version_major = 0, version_minor = 0, version_patch = 0;
    nv(nvtiffGetProperty(MAJOR_VERSION, &version_major), "runtime major version");
    nv(nvtiffGetProperty(MINOR_VERSION, &version_minor), "runtime minor version");
    nv(nvtiffGetProperty(PATCH_LEVEL, &version_patch), "runtime patch version");
    if (version_major != NVTIFF_VER_MAJOR || version_minor != NVTIFF_VER_MINOR)
        throw std::runtime_error("nvTIFF runtime/header API version mismatch");
    Resources r; // Destroy before releasing the source snapshot.
    cu(cudaSetDevice(static_cast<int>(o.device)), "select device");
    cudaDeviceProp prop{};
    cu(cudaGetDeviceProperties(&prop, static_cast<int>(o.device)), "device properties");
    std::ostringstream uuid;
    const char hex[] = "0123456789abcdef";
    for (unsigned char c : prop.uuid.bytes) uuid << hex[c >> 4] << hex[c & 15];
    r.cuda(cudaStreamCreateWithFlags(&r.stream, cudaStreamNonBlocking), "create stream");
    nv(nvtiffStreamOpen(bytes.data(), bytes.size(), &r.tiff), "open snapshot");
    nv(nvtiffDecoderCreateSimple(&r.decoder, r.stream), "create decoder");
    nv(nvtiffDecodeParamsCreate(&r.params), "create params");
    nv(nvtiffDecodeParamsSetOutputFormat(r.params, NVTIFF_OUTPUT_UNCHANGED_I), "unchanged samples");
    nvtiffStreamHeader_t header{};
    nv(nvtiffStreamGetHeader(r.tiff, &header), "TIFF header");
    std::vector<size_t> offsets;
    std::unordered_set<size_t> visited;
    for (size_t off = header.first_ifd_offset; off != NVTIFF_NO_IMAGE;) {
        if (off >= bytes.size() || !visited.insert(off).second || offsets.size() >= 100000)
            throw std::runtime_error("invalid/cyclic/excessive IFD chain");
        offsets.push_back(off);
        nv(nvtiffStreamGetNextIFDOffset(r.tiff, off, &off), "next IFD");
    }
    if (offsets.empty() || o.first >= offsets.size()) throw std::runtime_error("empty movie or first frame out of range");
    const size_t count = o.count ? o.count : offsets.size() - o.first;
    if (count > offsets.size() - o.first) throw std::runtime_error("frame range exceeds movie");
    nvtiffImageInfo_t first{};
    bool supported = true;
    std::ostringstream frames;
    // Inspect the full movie, not merely its selected prefix.
    for (size_t i = 0; i < offsets.size(); ++i) {
        nvtiffImageInfo_t info{}; nvtiffImageGeometry_t geometry{};
        nv(nvtiffStreamGetImageInfo(r.tiff, offsets[i], &info), "image info");
        nv(nvtiffStreamGetImageGeometry(r.tiff, offsets[i], &geometry), "image geometry");
        const auto orientation = shortTag(r.tiff, offsets[i], 274, 1);
        const auto predictor = shortTag(r.tiff, offsets[i], 317, 1);
        const auto depth = imageDepth(r.tiff, offsets[i]);
        if (i == 0) first = info;
        const bool admitted = info.image_width && info.image_height &&
            info.image_width == first.image_width && info.image_height == first.image_height &&
            info.samples_per_pixel == 1 && info.bits_per_pixel == info.bits_per_sample[0] &&
            (info.bits_per_sample[0] == 8 || info.bits_per_sample[0] == 16) &&
            info.bits_per_sample[0] == first.bits_per_sample[0] &&
            info.sample_format[0] == NVTIFF_SAMPLEFORMAT_UINT &&
            info.photometric_int == NVTIFF_PHOTOMETRIC_MINISBLACK &&
            info.planar_config == NVTIFF_PLANARCONFIG_CONTIG &&
            depth == 1 && geometry.image_depth <= 1 && orientation == 1 && (predictor == 1 || predictor == 2);
        nvtiffDecodeRegion_t region{}; region.ifd_offset = offsets[i];
        nv(nvtiffDecodeParamsSetRegions(r.params, &region, 1), "probe region");
        const auto status = nvtiffDecodeCheckSupported(r.tiff, r.decoder, r.params, nullptr);
        supported = supported && admitted && status == NVTIFF_STATUS_SUCCESS;
        if (i) frames << ',';
        frames << "{\"index\":" << i << ",\"ifd_offset\":" << offsets[i]
               << ",\"width\":" << info.image_width << ",\"height\":" << info.image_height
               << ",\"bits\":" << info.bits_per_sample[0] << ",\"compression\":" << info.compression
               << ",\"geometry_type\":" << geometry.type << ",\"strile_height\":" << geometry.strile_height
               << ",\"orientation\":" << orientation << ",\"predictor\":" << predictor
               << ",\"samples_per_pixel\":" << info.samples_per_pixel
               << ",\"photometric\":" << info.photometric_int << ",\"planar_config\":" << info.planar_config
               << ",\"depth\":" << geometry.image_depth
               << ",\"tag_depth\":" << depth
               << ",\"sample_format\":" << info.sample_format[0]
               << ",\"experiment_admitted\":" << (admitted ? "true" : "false")
               << ",\"nvtiff_status\":" << status << '}';
    }
    const double admission_s = elapsed(whole);
    if (!supported || o.probe) {
        r.closeChecked();
        std::cout << "{\"mode\":\"probe\",\"movie\":" << quoted(o.movie)
                  << ",\"device\":" << o.device << ",\"uuid_hex\":" << quoted(uuid.str())
                  << ",\"device_name\":" << quoted(prop.name)
                  << ",\"nvtiff_runtime\":\"" << version_major << '.' << version_minor << '.' << version_patch << "\""
                  << ",\"frames\":[" << frames.str() << "],\"supported\":" << (supported ? "true" : "false")
                  << ",\"input_snapshot_bytes\":" << bytes.size() << ",\"wall_s\":" << elapsed(whole)
                  << ",\"decode_executed\":false}\n";
        return supported ? 0 : 3;
    }
    const size_t bps = first.bits_per_sample[0] / 8;
    const size_t pitch = product(first.image_width, bps);
    const size_t frame_bytes = product(pitch, first.image_height);
    const size_t batch = std::min(o.batch, count);
    const size_t output_bytes = product(frame_bytes, batch);
    if (output_bytes > o.max_output) throw std::runtime_error("decoded batch exceeds --max-output-bytes");
    r.cuda(cudaMalloc(&r.output, output_bytes), "allocate decoded batch");
    r.cuda(cudaEventCreate(&r.start), "create timing event");
    r.cuda(cudaEventCreate(&r.stop), "create timing event");
    std::vector<uint8_t> host(o.dump.empty() ? 0 : output_bytes);
    std::unique_ptr<Dump> dump;
    if (!o.dump.empty()) {
        dump = std::make_unique<Dump>(o.dump);
        dump->integer(first.image_width); dump->integer(first.image_height);
        dump->integer(count); dump->integer(bps);
    }
    double decode_wall_s = 0, copy_s = 0, dump_s = 0, stream_ms = 0;
    for (size_t pos = 0; pos < count; pos += batch) {
        const size_t n = std::min(batch, count - pos);
        std::vector<nvtiffDecodeRegion_t> regions(n);
        std::vector<void*> planes(n);
        std::vector<size_t> pitches(n, pitch);
        std::vector<nvtiffImage_t> images(n);
        for (size_t i = 0; i < n; ++i) {
            regions[i].ifd_offset = offsets[o.first + pos + i];
            planes[i] = static_cast<uint8_t*>(r.output) + i * frame_bytes;
            images[i] = nvtiffImage_t{&planes[i], &pitches[i], 1};
        }
        nv(nvtiffDecodeParamsSetRegions(r.params, regions.data(), static_cast<uint32_t>(n)), "decode regions");
        // No invisible serial splitting of an incompatible requested batch.
        nv(nvtiffDecodeCheckSupported(r.tiff, r.decoder, r.params, images.data()), "batch/output support");
        const auto t = Clock::now();
        r.cuda(cudaEventRecord(r.start, r.stream), "start timing");
        const auto status = nvtiffDecode(r.tiff, r.decoder, r.params, images.data(), r.stream);
        // Complete even on immediate decode failure, before reusing/destroying decoder.
        const auto stop_status = cudaEventRecord(r.stop, r.stream);
        const auto sync_status = cudaStreamSynchronize(r.stream);
        if (sync_status != cudaSuccess || stop_status != cudaSuccess ||
            status == NVTIFF_STATUS_EXECUTION_FAILED) r.usable = false;
        // Retain both API and completion errors instead of masking the original status.
        if (status != NVTIFF_STATUS_SUCCESS || stop_status != cudaSuccess || sync_status != cudaSuccess)
            throw std::runtime_error("decode: nvTIFF=" + std::to_string(status) +
                " event=" + cudaGetErrorString(stop_status) + " completion=" + cudaGetErrorString(sync_status));
        decode_wall_s += elapsed(t);
        float ms = 0;
        r.cuda(cudaEventElapsedTime(&ms, r.start, r.stop), "elapsed event time");
        stream_ms += ms;
        if (dump) {
            const auto copy = Clock::now();
            r.cuda(cudaMemcpy(host.data(), r.output, n * frame_bytes, cudaMemcpyDeviceToHost), "copy samples");
            copy_s += elapsed(copy);
            const auto write = Clock::now();
            // nvTIFF unchanged output is top-down. Match rwTIFF's bottom-up movie
            // convention, with no arithmetic, gain application or sample conversion.
            for (size_t i = 0; i < n; ++i)
                for (size_t y = first.image_height; y != 0; --y)
                    dump->write(host.data() + i * frame_bytes + (y - 1) * pitch, pitch);
            dump_s += elapsed(write);
        }
    }
    r.closeChecked();
    if (dump) dump->publish();
    std::cout << "{\"mode\":\"decode\",\"movie\":" << quoted(o.movie)
              << ",\"nvtiff_headers\":\"" << NVTIFF_VER_MAJOR << '.' << NVTIFF_VER_MINOR
              << '.' << NVTIFF_VER_PATCH << '.' << NVTIFF_VER_BUILD << "\""
              << ",\"nvtiff_runtime\":\"" << version_major << '.' << version_minor << '.' << version_patch << "\""
              << ",\"device\":" << o.device
              << ",\"uuid_hex\":" << quoted(uuid.str()) << ",\"device_name\":" << quoted(prop.name)
              << ",\"frames\":[" << frames.str() << "],\"first\":" << o.first << ",\"count\":" << count
              << ",\"batch_frames\":" << batch << ",\"row_order\":\"MRC-bottom-up\""
              << ",\"input_snapshot_bytes\":" << bytes.size() << ",\"output_device_bytes\":" << output_bytes
              << ",\"decoder_internal_device_bytes\":null,\"host_output_bytes\":" << host.size()
              << ",\"admission_wall_s\":" << admission_s << ",\"decode_wall_s\":" << decode_wall_s
              << ",\"decode_stream_ms\":" << stream_ms << ",\"sample_copy_wall_s\":" << copy_s
              << ",\"dump_write_wall_s\":" << dump_s << ",\"total_wall_s\":" << elapsed(whole)
              << ",\"dump\":" << quoted(o.dump) << ",\"decode_executed\":true,\"cleanup_complete\":true}\n";
    if (!std::cout) throw std::runtime_error("report output failed");
    return 0;
}
} // namespace

int main(int argc, char** argv) {
    try { std::cout.precision(9); return run(options(argc, argv)); }
    catch (const std::exception& e) {
        std::cerr << "motioncorr_nvtiff_probe: " << e.what() << '\n';
        return 1;
    }
}
