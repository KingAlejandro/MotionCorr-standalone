/* MotionCorr file content identity. Copyright (C) 2026 MotionCorr contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef MOTIONCORR_PROCESSING_FILE_DIGEST_H
#define MOTIONCORR_PROCESSING_FILE_DIGEST_H

#include <cstddef>
#include <cstdint>
#include <string>

namespace motioncorr_identity
{
struct FileSnapshot
{
    uint64_t device, inode, size;
    int64_t mtime_seconds, mtime_nanoseconds, ctime_seconds, ctime_nanoseconds;
    bool operator==(const FileSnapshot &other) const;
    bool operator!=(const FileSnapshot &other) const { return !(*this == other); }
};
struct FileDigest
{
    std::string sha256;
    FileSnapshot snapshot;
};

// Follow file symlinks but accept regular files only. Errors include the path.
FileSnapshot snapshotFile(const std::string &path);
// One descriptor, bounded64KiB read buffer, checked EOF/size and descriptor/path
// identity before return. A snapshot detects observed mutation, not atomic
// immutability against an unrelated writer after this call.
FileDigest digestFile(const std::string &path);
void requireUnchanged(const std::string &path, const FileSnapshot &snapshot);
std::string sha256Bytes(const void *data, size_t count);
// Linux's proc magiclink opens the running executable inode rather than a
// replacement at its former pathname. macOS uses its loader path; it has no
// equivalent proc magiclink to pin a subsequently replaced executable.
std::string executablePath();
}
#endif
