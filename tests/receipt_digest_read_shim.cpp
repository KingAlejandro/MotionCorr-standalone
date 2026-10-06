/* Test-only actual descriptor read failure; no production fault hook.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static ssize_t readWithDigestFault(int fd, void *buffer, size_t length)
{
#ifdef __APPLE__
    static auto real = &read;
#else
    using Read = ssize_t (*)(int, void *, size_t);
    static auto real = reinterpret_cast<Read>(dlsym(RTLD_NEXT, "read"));
#endif
    if (!real) _exit(86);
    const char *target = std::getenv("MC_RECEIPT_READ_FAULT_PATH");
    const int flags = fcntl(fd, F_GETFL);
    struct stat status{};
    if (target && flags >= 0 && (flags & O_NONBLOCK) && fstat(fd, &status) == 0 && S_ISREG(status.st_mode))
    {
        char path[4096]{};
#ifdef __APPLE__
        const bool known = fcntl(fd, F_GETPATH, path) == 0;
#else
        char link[64]; std::snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
        const auto count = readlink(link, path, sizeof(path) - 1);
        const bool known = count >= 0;
        if (known) path[count] = 0;
#endif
        if (known && std::strcmp(target, path) == 0)
        {
            const char *witness = std::getenv("MC_RECEIPT_READ_FAULT_WITNESS");
            const int log = witness ? open(witness, O_WRONLY | O_CREAT | O_APPEND, 0600) : -1;
            const char record[] = "ACTUAL_DIGEST_READ_EIO\n";
            if (log < 0 || write(log, record, sizeof(record) - 1) != sizeof(record) - 1 || close(log) != 0) _exit(87);
            errno = EIO;
            return -1;
        }
    }
    return real(fd, buffer, length);
}
#ifdef __APPLE__
__attribute__((used)) static struct { const void *replacement; const void *original; } interpose
    __attribute__((section("__DATA,__interpose"))) = {
        reinterpret_cast<const void *>(&readWithDigestFault), reinterpret_cast<const void *>(&read)};
#else
extern "C" ssize_t read(int fd, void *buffer, size_t length) { return readWithDigestFault(fd, buffer, length); }
#endif
