// A failed MRC write must fail the movie, never produce a "completed" one.
//
// At 4c952b3f every fwrite/fseek in writeMRC discarded its result and _write
// discarded writeMRC's, so a short write returned success all the way out; and
// the one check that existed -- fclose inside ~fImageHandler -- reported via
// REPORT_ERROR, i.e. a throw from an implicitly noexcept destructor, which is
// std::terminate rather than an error report.
//
// Faults are injected with setrlimit(RLIMIT_FSIZE) so the real stdio buffering
// and the real kernel write path are exercised, at a byte offset we choose, on
// a private temporary file. No shared disk is filled and no privilege is
// needed. SIGXFSZ is ignored so the write returns EFBIG instead of killing us.
//
// The two limits below are not interchangeable:
//   * a payload larger than the stdio buffer is written by a direct write(2),
//     so the short count is visible to the fwrite check;
//   * a product smaller than the stdio buffer is still entirely in the buffer
//     when the last fwrite returns success, so ONLY the checked close can see
//     the failure. That case fails if write counts alone are checked.

#include "src/image.h"

#include <sys/resource.h>
#include <sys/stat.h>
#include <csignal>
#include <cstdio>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const std::string &message)
{
    if (condition) return;
    std::cerr << "FAIL: " << message << std::endl;
    failures++;
}

// Byte limit for regular files created by this process, or RLIM_INFINITY.
void setFileSizeLimit(rlim_t bytes)
{
    struct rlimit rl;
    if (getrlimit(RLIMIT_FSIZE, &rl) != 0)
        throw std::runtime_error("getrlimit(RLIMIT_FSIZE) failed");
    rl.rlim_cur = bytes;
    if (setrlimit(RLIMIT_FSIZE, &rl) != 0)
        throw std::runtime_error("setrlimit(RLIMIT_FSIZE) failed");
}

long fileSize(const std::string &path)
{
    struct stat st;
    if (stat(path.c_str(), &st) != 0) return -1;
    return (long)st.st_size;
}

Image<float> makeImage(int n)
{
    Image<float> img(n, n);
    for (long i = 0; i < (long)n * n; i++)
        DIRECT_MULTIDIM_ELEM(img(), i) = (float)(i % 251) * 0.5f - 3.0f;
    return img;
}

// Write under a file-size limit and report what came back out.
struct Attempt
{
    bool threw = false;
    std::string message;
    long size = -1;
};

Attempt writeUnderLimit(Image<float> &img, const std::string &path, rlim_t limit)
{
    Attempt a;
    remove(path.c_str());
    setFileSizeLimit(limit);
    try {
        img.write(path, -1, false, WRITE_OVERWRITE, Float);
    } catch (RelionError &e) {
        a.threw = true;
        a.message = e.msg;
    }
    setFileSizeLimit(RLIM_INFINITY);
    a.size = fileSize(path);
    return a;
}

const char *TMPDIR_ENV()
{
    const char *t = getenv("TMPDIR");
    return (t != NULL && t[0] != '\0') ? t : "/tmp";
}

} // namespace

int main()
{
    // Without this the first over-limit write kills the process with SIGXFSZ
    // and the test would be reporting the signal, not the writer's behaviour.
    signal(SIGXFSZ, SIG_IGN);

    const std::string dir = std::string(TMPDIR_ENV()) + "/mc_write_faults_" + std::to_string((long)getpid());
    if (mkdir(dir.c_str(), 0700) != 0) {
        std::cerr << "FAIL: cannot create " << dir << std::endl;
        return 1;
    }
    const std::string big_path = dir + "/big.mrc";
    const std::string small_path = dir + "/small.mrc";

    const int BIG = 512;              // 1 MiB payload, larger than any stdio buffer
    const int SMALL = 16;             // 1 KiB payload, fits in the stdio buffer
    const long BIG_BYTES = 1024L + (long)BIG * BIG * 4;
    const long SMALL_BYTES = 1024L + (long)SMALL * SMALL * 4;

    Image<float> big = makeImage(BIG);
    Image<float> small = makeImage(SMALL);

    try {
        // ---- 1. Healthy control: unchanged behaviour, exact bytes ----------
        Attempt healthy = writeUnderLimit(big, big_path, RLIM_INFINITY);
        check(!healthy.threw, "healthy write must not throw: " + healthy.message);
        check(healthy.size == BIG_BYTES,
              "healthy file is " + std::to_string(healthy.size) + " bytes, expected " +
              std::to_string(BIG_BYTES));
        // Read it back so the control proves payload content, not just length.
        {
            Image<float> back;
            back.read(big_path);
            bool same = (XSIZE(back()) == BIG && YSIZE(back()) == BIG);
            for (long i = 0; same && i < (long)BIG * BIG; i++)
                same = (DIRECT_MULTIDIM_ELEM(back(), i) == DIRECT_MULTIDIM_ELEM(big(), i));
            check(same, "healthy round-trip payload differs");
        }

        // ---- 2. Short payload write, caught by the fwrite check ------------
        // 600000 < 1024 + 1 MiB, and the payload is written by a direct
        // write(2), so fwrite itself returns a short item count.
        Attempt shortPayload = writeUnderLimit(big, big_path, 600000);
        check(shortPayload.threw, "a short payload write must throw, not report success");
        check(shortPayload.message.find(big_path) != std::string::npos,
              "the failure must name the output path, got: " + shortPayload.message);
        check(shortPayload.message.find("image data") != std::string::npos,
              "the failure must name the stage, got: " + shortPayload.message);
        check(shortPayload.size >= 0 && shortPayload.size < BIG_BYTES,
              "the injected fault did not actually truncate the file (" +
              std::to_string(shortPayload.size) + " bytes) -- the assertion above would "
              "then be observing something other than the fault");

        // ---- 3. Delayed flush/close failure, caught by the close check -----
        // Header + payload = 2 KiB, below the stdio buffer, so both fwrites
        // report full success and nothing has reached the fd yet. Only the
        // checked close can see this.
        Attempt deferred = writeUnderLimit(small, small_path, 1536);
        check(deferred.threw,
              "a write whose failure only appears at flush must throw; checking fwrite "
              "counts alone is not sufficient for the contract");
        check(deferred.message.find(small_path) != std::string::npos,
              "the deferred failure must name the output path, got: " + deferred.message);
        check(deferred.size >= 0 && deferred.size < SMALL_BYTES,
              "the injected fault did not truncate the small file (" +
              std::to_string(deferred.size) + " bytes)");

        // ---- 4. Negative control: same writes, limit lifted ---------------
        // If these throw, cases 2 and 3 were not observing the injected fault.
        Attempt negBig = writeUnderLimit(big, big_path, RLIM_INFINITY);
        check(!negBig.threw, "negative control (big, no limit) threw: " + negBig.message);
        check(negBig.size == BIG_BYTES, "negative control (big) wrote the wrong size");
        Attempt negSmall = writeUnderLimit(small, small_path, RLIM_INFINITY);
        check(!negSmall.threw, "negative control (small, no limit) threw: " + negSmall.message);
        check(negSmall.size == SMALL_BYTES, "negative control (small) wrote the wrong size");

        // ---- 5. Destructor safety --------------------------------------
        // A handler whose stream cannot be flushed must be destroyed quietly.
        // Reaching the line after this block is the whole assertion: the old
        // destructor called REPORT_ERROR here, and a throw from a noexcept
        // destructor is std::terminate, so this test binary would abort.
        {
            const std::string d_path = dir + "/dtor.mrc";
            remove(d_path.c_str());
            setFileSizeLimit(1536);
            {
                fImageHandler h;
                h.openFile(d_path, WRITE_OVERWRITE);
                const std::vector<char> junk(1400, 'x');
                fwrite(junk.data(), junk.size(), 1, h.fimg);
                // h goes out of scope here with unflushable buffered bytes.
            }
            setFileSizeLimit(RLIM_INFINITY);
            remove(d_path.c_str());
            std::cout << "  destructor with an unflushable stream did not terminate" << std::endl;
        }
    } catch (RelionError &e) {
        setFileSizeLimit(RLIM_INFINITY);
        std::cerr << "FAIL: unexpected RelionError: " << e.msg << std::endl;
        failures++;
    } catch (std::exception &e) {
        setFileSizeLimit(RLIM_INFINITY);
        std::cerr << "FAIL: unexpected exception: " << e.what() << std::endl;
        failures++;
    }

    remove(big_path.c_str());
    remove(small_path.c_str());
    rmdir(dir.c_str());

    if (failures != 0) {
        std::cerr << failures << " check(s) failed" << std::endl;
        return 1;
    }
    std::cout << "image write faults: ok" << std::endl;
    return 0;
}
