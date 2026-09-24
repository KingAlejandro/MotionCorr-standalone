#ifndef GLOBAL_PEAK_PROBE_H_
#define GLOBAL_PEAK_PROBE_H_

// Issue #36 Phase-1 diagnostic only. Enable explicitly with all three env vars:
//   MOTIONCORR_PEAK_TRACE_DIR=/existing/output/directory
//   MOTIONCORR_PEAK_TRACE_FRAME=<zero-based post-grouping alignPatch ordinal>
//   MOTIONCORR_PEAK_TRACE_ITER=<1-based global-alignment iteration>
// The trace intentionally does not claim source-frame mapping or input hashing;
// it is a compact peak-stage probe, not the full raw-array ADR trace.
// The directory may already contain the other backend's trace; this backend's
// output file must not exist and is created with O_CREAT|O_EXCL.
// Run one movie per process: this Phase-1 probe does not select a movie from
// a multi-movie input and will refuse a second same-backend output.

#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <fcntl.h>
#include <iomanip>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include "src/error.h"

struct GlobalPeakProbeConfig {
    bool enabled;
    std::string directory;
    int frame_index;
    int iteration;

    GlobalPeakProbeConfig() : enabled(false), frame_index(0), iteration(0) {}
};

struct GlobalPeakProbeRecord {
    int frame_index;
    int iteration;
    int peak_x;
    int peak_y;
    double peak_value;
    double center;
    double x_minus;
    double x_plus;
    double y_minus;
    double y_plus;
    double denominator_x;
    double denominator_y;
    double shift_x_unscaled;
    double shift_y_unscaled;
    double shift_x_scaled;
    double shift_y_scaled;
    double frame0_shift_x_scaled;
    double frame0_shift_y_scaled;
    double frame0_recentered_shift_x;
    double frame0_recentered_shift_y;
    double recentered_shift_x;
    double recentered_shift_y;
    bool x_interpolated;
    bool y_interpolated;
};

inline bool readGlobalPeakProbeConfig(GlobalPeakProbeConfig &config)
{
    const char *directory = std::getenv("MOTIONCORR_PEAK_TRACE_DIR");
    const char *frame = std::getenv("MOTIONCORR_PEAK_TRACE_FRAME");
    const char *iteration = std::getenv("MOTIONCORR_PEAK_TRACE_ITER");
    if (!directory && !frame && !iteration) {
        config.enabled = false;
        return false;
    }
    if (!directory || !*directory || !frame || !*frame || !iteration || !*iteration)
        REPORT_ERROR("Global peak trace requires MOTIONCORR_PEAK_TRACE_DIR, _FRAME, and _ITER together");

    char *end = nullptr;
    errno = 0;
    long frame_value = std::strtol(frame, &end, 10);
    if (errno || end == frame || *end || frame_value < 0 || frame_value > 2147483647L)
        REPORT_ERROR("MOTIONCORR_PEAK_TRACE_FRAME must be a non-negative integer");
    errno = 0;
    long iteration_value = std::strtol(iteration, &end, 10);
    if (errno || end == iteration || *end || iteration_value < 1 || iteration_value > 2147483647L)
        REPORT_ERROR("MOTIONCORR_PEAK_TRACE_ITER must be a positive integer");

    config.enabled = true;
    config.directory = directory;
    config.frame_index = (int)frame_value;
    config.iteration = (int)iteration_value;
    return true;
}

inline std::string globalPeakProbeFilename(const GlobalPeakProbeConfig &config, const char *backend)
{
    std::string path = config.directory;
    if (!path.empty() && path[path.size() - 1] != '/') path += '/';
    path += "motioncorr-global-peak-";
    path += backend;
    path += ".json";
    return path;
}

inline std::string globalPeakProbeJsonString(const std::string &value)
{
    std::ostringstream escaped;
    for (std::string::const_iterator it = value.begin(); it != value.end(); ++it) {
        const unsigned char ch = (unsigned char)*it;
        if (ch == '"' || ch == '\\') escaped << '\\' << (char)ch;
        else if (ch == '\n') escaped << "\\n";
        else if (ch == '\r') escaped << "\\r";
        else if (ch == '\t') escaped << "\\t";
        else if (ch < 0x20) escaped << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << (int)ch << std::dec;
        else escaped << (char)ch;
    }
    return escaped.str();
}

inline void requireFreshGlobalPeakProbeOutput(const GlobalPeakProbeConfig &config, const char *backend)
{
    struct stat info;
    if (stat(config.directory.c_str(), &info) != 0 || !S_ISDIR(info.st_mode))
        REPORT_ERROR("Global peak trace directory must already exist: " + config.directory);
    const std::string path = globalPeakProbeFilename(config, backend);
    if (lstat(path.c_str(), &info) == 0)
        REPORT_ERROR("Refusing stale global peak trace output: " + path);
    if (errno != ENOENT)
        REPORT_ERROR("Cannot inspect global peak trace output: " + path);
}

inline void writeGlobalPeakProbeRecord(const GlobalPeakProbeConfig &config, const char *backend,
                                       const std::string &device, const std::string &movie_identity,
                                       const GlobalPeakProbeRecord &record)
{
    const double values[] = {
        record.peak_value, record.center, record.x_minus, record.x_plus, record.y_minus, record.y_plus,
        record.denominator_x, record.denominator_y, record.shift_x_unscaled, record.shift_y_unscaled,
        record.shift_x_scaled, record.shift_y_scaled, record.frame0_shift_x_scaled,
        record.frame0_shift_y_scaled, record.frame0_recentered_shift_x,
        record.frame0_recentered_shift_y, record.recentered_shift_x, record.recentered_shift_y
    };
    for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); ++i)
        if (!std::isfinite(values[i]))
            REPORT_ERROR("Global peak trace contains a non-finite value; refusing invalid JSON");
    const std::string path = globalPeakProbeFilename(config, backend);
    std::ostringstream output;
    output << std::setprecision(17)
        << "{\n  \"format\": \"motioncorr-global-peak-probe-v1\",\n"
        << "  \"scope\": \"phase-1 global peak probe; not the full raw-array ADR trace\",\n"
        << "  \"backend\": \"" << backend << "\",\n"
        << "  \"device\": \"" << globalPeakProbeJsonString(device) << "\",\n"
        << "  \"movie_path\": \"" << globalPeakProbeJsonString(movie_identity) << "\",\n"
        << "  \"input_content_hash\": null,\n"
        << "  \"frame_index\": " << record.frame_index << ",\n"
        << "  \"frame_index_mapping\": \"zero-based post-grouping alignPatch ordinal; source-frame mapping not captured\",\n"
        << "  \"iteration\": " << record.iteration << ",\n"
        << "  \"peak\": {\"x\": " << record.peak_x << ", \"y\": " << record.peak_y
        << ", \"value\": " << record.peak_value << "},\n"
        << "  \"stencil\": {\"center\": " << record.center << ", \"x_minus\": " << record.x_minus
        << ", \"x_plus\": " << record.x_plus << ", \"y_minus\": " << record.y_minus
        << ", \"y_plus\": " << record.y_plus << "},\n"
        << "  \"denominator_x\": " << record.denominator_x << ",\n"
        << "  \"denominator_y\": " << record.denominator_y << ",\n"
        << "  \"x_interpolation_used\": " << (record.x_interpolated ? "true" : "false") << ",\n"
        << "  \"y_interpolation_used\": " << (record.y_interpolated ? "true" : "false") << ",\n"
        << "  \"shift_unscaled\": {\"x\": " << record.shift_x_unscaled << ", \"y\": " << record.shift_y_unscaled << "},\n"
        << "  \"shift_scaled\": {\"x\": " << record.shift_x_scaled << ", \"y\": " << record.shift_y_scaled << "},\n"
        << "  \"frame0_shift_scaled\": {\"x\": " << record.frame0_shift_x_scaled << ", \"y\": " << record.frame0_shift_y_scaled << "},\n"
        << "  \"frame0_shift_recentered\": {\"x\": " << record.frame0_recentered_shift_x << ", \"y\": " << record.frame0_recentered_shift_y << "},\n"
        << "  \"selected_shift_recentered\": {\"x\": " << record.recentered_shift_x << ", \"y\": " << record.recentered_shift_y << "}\n}\n";
    const std::string payload = output.str();
    // O_EXCL rejects stale files and symlinks atomically, even if another run races
    // the earlier freshness check. The directory may contain the other backend's trace.
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0)
        REPORT_ERROR("Cannot exclusively create global peak trace output: " + path);
    size_t written = 0;
    while (written < payload.size()) {
        ssize_t result = write(fd, payload.data() + written, payload.size() - written);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) {
            close(fd);
            unlink(path.c_str());
            REPORT_ERROR("Failed while writing global peak trace output: " + path);
        }
        written += (size_t)result;
    }
    if (close(fd) != 0) {
        unlink(path.c_str());
        REPORT_ERROR("Failed while closing global peak trace output: " + path);
    }
}

#endif
