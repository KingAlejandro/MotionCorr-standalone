/* Actual post-image-close input mutation for receipt failure controls only.
 * SPDX-License-Identifier: GPL-2.0-or-later. No fault hook enters production.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>

static int closeAndMutate(FILE *file)
{
    using Close = int (*)(FILE *);
#ifdef __APPLE__
    static auto real = &fclose; // dyld does not interpose references from the replacement image.
#else
    static auto real = reinterpret_cast<Close>(dlsym(RTLD_NEXT, "fclose"));
#endif
    if (!real) _exit(86);
    char path[4096]{};
#ifdef __APPLE__
    const bool path_read = fcntl(fileno(file), F_GETPATH, path) == 0;
#else
    char link[64]; std::snprintf(link, sizeof(link), "/proc/self/fd/%d", fileno(file));
    const ssize_t count = readlink(link, path, sizeof(path) - 1);
    const bool path_read = count >= 0;
    if (path_read) path[count] = 0;
#endif
    const int result = real(file);
    const char *output = std::getenv("MC_RECEIPT_MUTATE_AFTER_CLOSE");
    if (result != 0 || !path_read || !output || std::strcmp(path, output) != 0) return result;
    const char *input = std::getenv("MC_RECEIPT_MUTATE_INPUT");
    const char *witness = std::getenv("MC_RECEIPT_MUTATION_WITNESS");
    if (!input || !witness) _exit(87);
    const char *kind = std::getenv("MC_RECEIPT_MUTATION_KIND");
    if (kind && std::strcmp(kind, "executable") == 0)
    {
        const char *replacement = std::getenv("MC_RECEIPT_REPLACEMENT");
        if (!replacement || rename(replacement, input) != 0) _exit(88);
    }
    else
    {
        const int source = open(input, O_RDWR);
        if (source < 0) _exit(88);
        if (kind && std::strcmp(kind, "defect") == 0)
        {
            char value;
            if (pread(source, &value, 1, 0) != 1) _exit(88);
            value = value == '8' ? '9' : '8';
            if (pwrite(source, &value, 1, 0) != 1) _exit(89);
        }
        else
        {
            float value;
            if (pread(source, &value, sizeof(value), 1024) != sizeof(value)) _exit(88);
            value += 1.0f;
            if (pwrite(source, &value, sizeof(value), 1024) != sizeof(value)) _exit(89);
        }
        if (close(source) != 0) _exit(89);
    }
    const int log = open(witness, O_WRONLY | O_CREAT | O_APPEND, 0600);
    const char record[] = "ACTUAL_SOURCE_CHANGED_AFTER_IMAGE_CLOSE\n";
    if (log < 0 || write(log, record, sizeof(record) - 1) != sizeof(record) - 1 || close(log) != 0) _exit(90);
    return result;
}
#ifdef __APPLE__
__attribute__((used)) static struct { const void *replacement; const void *original; } interpose
    __attribute__((section("__DATA,__interpose"))) = {
        reinterpret_cast<const void *>(&closeAndMutate), reinterpret_cast<const void *>(&fclose)};
#else
extern "C" int fclose(FILE *file) { return closeAndMutate(file); }
#endif
