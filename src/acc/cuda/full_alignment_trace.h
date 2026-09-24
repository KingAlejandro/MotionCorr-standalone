#ifndef MOTIONCORR_FULL_ALIGNMENT_TRACE_H_
#define MOTIONCORR_FULL_ALIGNMENT_TRACE_H_

// Opt-in Issue #36 diagnostic. Run one movie per process, with --j 1 and a
// fresh existing directory. The explicit GiB budget overrides the 256 MiB
// selected-frame probe because this mode records every frame and patch.
//   MOTIONCORR_FULL_TRACE_DIR=<fresh existing directory>
//   MOTIONCORR_FULL_TRACE_MAX_GIB=<positive integer, e.g. 128>
// Raw chunks contain derived movie data and must remain on the analysis host.

#include <cerrno>
#include <cstddef>
#include <cstdlib>
#include <dirent.h>
#include <fcntl.h>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#include "src/error.h"

// Columns: peak_x, peak_y, center, x_minus, x_plus, y_minus, y_plus,
// denominator_x, denominator_y, unscaled_x, unscaled_y, scaled_x, scaled_y,
// x_interpolated, y_interpolated, reserved. All are stored as float64.
struct FullPeakRecord { double value[16]; };

inline bool fullTraceEnabled()
{
    return std::getenv("MOTIONCORR_FULL_TRACE_DIR") != nullptr;
}

inline std::string fullTraceDirectory()
{
    const char *dir = std::getenv("MOTIONCORR_FULL_TRACE_DIR");
    if (!dir || !*dir) REPORT_ERROR("MOTIONCORR_FULL_TRACE_DIR is empty");
    struct stat info;
    if (lstat(dir, &info) != 0 || !S_ISDIR(info.st_mode))
        REPORT_ERROR("Full trace directory must be an existing, real directory");
    return std::string(dir);
}

inline size_t fullTraceBudget()
{
    const char *value = std::getenv("MOTIONCORR_FULL_TRACE_MAX_GIB");
    if (!value || !*value) REPORT_ERROR("Full trace requires MOTIONCORR_FULL_TRACE_MAX_GIB");
    char *end = nullptr;
    errno = 0;
    unsigned long long gib = std::strtoull(value, &end, 10);
    if (errno || end == value || *end || gib == 0 || gib > 1024)
        REPORT_ERROR("MOTIONCORR_FULL_TRACE_MAX_GIB must be an integer from 1 to 1024");
    return (size_t)gib * 1024 * 1024 * 1024;
}

inline std::string fullTracePath(const std::string &name)
{
    for (size_t i = 0; i < name.size(); ++i) {
        const char c = name[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_'))
            REPORT_ERROR("Invalid full trace key");
    }
    if (name.empty()) REPORT_ERROR("Empty full trace key");
    return fullTraceDirectory() + "/" + name;
}

inline std::string fullTraceKey(const std::string &scope, int iteration,
                                const std::string &stage, int frame = -1)
{
    std::ostringstream key;
    key << scope << "_i" << std::setw(2) << std::setfill('0') << iteration << "_" << stage;
    if (frame >= 0) key << "_f" << std::setw(3) << std::setfill('0') << frame;
    return key.str();
}

inline void fullTraceWriteFile(const std::string &path, const void *data, size_t bytes)
{
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) REPORT_ERROR("Refusing stale or unwritable full trace file: " + path);
    const char *src = static_cast<const char *>(data);
    size_t offset = 0;
    while (offset < bytes) {
        ssize_t n = write(fd, src + offset, bytes - offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) {
            close(fd);
            unlink(path.c_str());
            REPORT_ERROR("Full trace write failed: " + path);
        }
        offset += (size_t)n;
    }
    if (close(fd) != 0) {
        unlink(path.c_str());
        REPORT_ERROR("Full trace close failed: " + path);
    }
}

inline void fullTraceStart(const std::string &backend, const std::string &movie)
{
    if (!fullTraceEnabled()) return;
    (void)fullTraceBudget();
    const std::string directory = fullTraceDirectory();
    DIR *listing = opendir(directory.c_str());
    if (!listing) REPORT_ERROR("Cannot inspect full trace directory");
    bool occupied = false;
    while (struct dirent *entry = readdir(listing)) {
        const std::string name(entry->d_name);
        if (name != "." && name != "..") { occupied = true; break; }
    }
    closedir(listing);
    if (occupied) REPORT_ERROR("Full trace directory must be empty before a run");
    const std::string text = "backend=" + backend + "\nmovie=" + movie + "\nformat=motioncorr-full-trace-v1\n";
    fullTraceWriteFile(fullTracePath("trace_start"), text.data(), text.size());
}

inline void fullTraceArray(const std::string &key, const void *data, size_t bytes,
                           const std::string &dtype, const std::string &shape)
{
    if (!fullTraceEnabled()) return;
    const std::string stem = fullTracePath(key);
    const std::string budget_path = fullTraceDirectory() + "/trace_budget";
    int budget_fd = open(budget_path.c_str(), O_RDWR | O_CREAT | O_NOFOLLOW, 0600);
    struct stat budget_info;
    if (budget_fd < 0 || fstat(budget_fd, &budget_info) != 0 || !S_ISREG(budget_info.st_mode) ||
        flock(budget_fd, LOCK_EX) != 0)
        REPORT_ERROR("Cannot lock full trace budget");
    size_t consumed = 0;
    const ssize_t count = read(budget_fd, &consumed, sizeof(consumed));
    if (count != 0 && count != sizeof(consumed)) {
        close(budget_fd);
        REPORT_ERROR("Cannot read full trace budget");
    }
    const size_t limit = fullTraceBudget();
    if (bytes > limit || consumed > limit - bytes) {
        close(budget_fd);
        REPORT_ERROR("Full trace exceeds explicit GiB budget");
    }
    consumed += bytes;
    if (lseek(budget_fd, 0, SEEK_SET) < 0 || write(budget_fd, &consumed, sizeof(consumed)) != sizeof(consumed)) {
        close(budget_fd);
        REPORT_ERROR("Cannot update full trace budget");
    }
    close(budget_fd);
    fullTraceWriteFile(stem + ".bin", data, bytes);
    std::ostringstream metadata;
    metadata << "{\"key\":\"" << key << "\",\"dtype\":\"" << dtype
             << "\",\"shape\":[" << shape << "],\"bytes\":" << bytes
             << ",\"endian\":\"native\"}\n";
    const std::string payload = metadata.str();
    fullTraceWriteFile(stem + ".json", payload.data(), payload.size());
}

inline void fullTraceEnd()
{
    if (!fullTraceEnabled()) return;
    const char done[] = "complete\n";
    fullTraceWriteFile(fullTracePath("trace_complete"), done, sizeof(done) - 1);
}

#endif
