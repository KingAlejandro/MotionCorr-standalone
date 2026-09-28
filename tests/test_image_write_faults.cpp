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
#include <unistd.h>
#include <sys/wait.h>
#include <cstdlib>
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

// The (soft, hard) RLIMIT_FSIZE this process inherited, captured once. Restoring
// means putting exactly this back -- not RLIM_INFINITY, which an unprivileged
// process cannot set when the inherited hard limit is finite, as it is on many
// CI and HPC systems. Getting that wrong makes the test fail at setrlimit,
// before the writer fault it exists to inject ever runs.
struct rlimit inherited_fsize;

void captureFileSizeLimit()
{
    if (getrlimit(RLIMIT_FSIZE, &inherited_fsize) != 0)
        throw std::runtime_error("getrlimit(RLIMIT_FSIZE) failed");
}

// Lower only the soft limit; the hard limit is left exactly as inherited.
void setFileSizeLimit(rlim_t bytes)
{
    struct rlimit rl = inherited_fsize;
    if (rl.rlim_max != RLIM_INFINITY && bytes > rl.rlim_max)
        bytes = rl.rlim_max;   // cannot raise the soft limit above the hard one
    rl.rlim_cur = bytes;
    if (setrlimit(RLIMIT_FSIZE, &rl) != 0)
        throw std::runtime_error("setrlimit(RLIMIT_FSIZE, soft=" +
                                 std::to_string((unsigned long long)bytes) + ") failed");
}

// Put back exactly what we inherited, whatever that was.
void restoreFileSizeLimit()
{
    if (setrlimit(RLIMIT_FSIZE, &inherited_fsize) != 0)
        throw std::runtime_error("setrlimit(RLIMIT_FSIZE) restore failed");
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

// limit == RLIM_INFINITY means "inject nothing"; setFileSizeLimit clamps it to the
// inherited hard limit, so that is the widest this process is allowed to ask for.
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
    restoreFileSizeLimit();
    a.size = fileSize(path);
    return a;
}

const char *TMPDIR_ENV()
{
    const char *t = getenv("TMPDIR");
    return (t != NULL && t[0] != '\0') ? t : "/tmp";
}

} // namespace

// Re-run this same binary in a child whose *hard* RLIMIT_FSIZE is finite.
//
// This is the environment the CI/HPC case actually presents, and it is the one
// that used to break the harness rather than the writer: restoring the soft
// limit to RLIM_INFINITY exceeds a finite hard limit, setrlimit returns EINVAL,
// and the suite dies before injecting anything. Lowering a hard limit needs no
// privilege, so the control is cheap and self-contained.
//
// FINITE_HARD is well above the largest product written here, so everything the
// suite does is still reachable; only the *restore* path changes meaning.
int runFiniteHardLimitChild(const char *self)
{
    const rlim_t FINITE_HARD = 8u * 1024u * 1024u;

    struct rlimit rl;
    if (getrlimit(RLIMIT_FSIZE, &rl) != 0) {
        std::cerr << "FAIL: getrlimit before re-exec failed" << std::endl;
        return 1;
    }
    if (rl.rlim_max != RLIM_INFINITY && rl.rlim_max < FINITE_HARD) {
        // Already tighter than the control wants. Nothing to prove by loosening
        // (we could not anyway), and the outer run already exercised it.
        std::cout << "  finite-hard-limit control: inherited hard limit is already "
                  << (unsigned long long)rl.rlim_max << " bytes; outer run covered it"
                  << std::endl;
        return 0;
    }

    pid_t pid = fork();
    if (pid < 0) {
        std::cerr << "FAIL: fork for the finite-hard-limit control failed" << std::endl;
        return 1;
    }
    if (pid == 0) {
        struct rlimit child = {FINITE_HARD, FINITE_HARD};
        if (setrlimit(RLIMIT_FSIZE, &child) != 0) _exit(97);
        setenv("MC_WRITE_FAULTS_IN_CHILD", "1", 1);
        execl(self, self, (char*)NULL);
        _exit(98);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) != pid) {
        std::cerr << "FAIL: waitpid for the finite-hard-limit control failed" << std::endl;
        return 1;
    }
    if (!WIFEXITED(status)) {
        std::cerr << "FAIL: the finite-hard-limit control was killed by signal "
                  << WTERMSIG(status) << std::endl;
        return 1;
    }
    const int rc = WEXITSTATUS(status);
    if (rc == 97 || rc == 98) {
        std::cerr << "FAIL: could not set up the finite-hard-limit control (rc " << rc << ")"
                  << std::endl;
        return 1;
    }
    if (rc != 0) {
        std::cerr << "FAIL: the suite does not survive a finite hard RLIMIT_FSIZE of "
                  << (unsigned long long)FINITE_HARD << " bytes (child exit " << rc
                  << "). An unprivileged process cannot raise a hard limit, so a restore "
                     "to RLIM_INFINITY fails here before any writer fault is injected."
                  << std::endl;
        return 1;
    }
    std::cout << "  finite-hard-limit control: suite passed with hard RLIMIT_FSIZE = "
              << (unsigned long long)FINITE_HARD << " bytes" << std::endl;
    return 0;
}

int main(int argc, char **argv)
{
    // Without this the first over-limit write kills the process with SIGXFSZ
    // and the test would be reporting the signal, not the writer's behaviour.
    signal(SIGXFSZ, SIG_IGN);

    const bool in_child = (getenv("MC_WRITE_FAULTS_IN_CHILD") != NULL);

    captureFileSizeLimit();
    {
        struct rlimit rl = inherited_fsize;
        std::cout << "  inherited RLIMIT_FSIZE: soft="
                  << (rl.rlim_cur == RLIM_INFINITY ? "infinity" : std::to_string((unsigned long long)rl.rlim_cur))
                  << " hard="
                  << (rl.rlim_max == RLIM_INFINITY ? "infinity" : std::to_string((unsigned long long)rl.rlim_max))
                  << (in_child ? "  (finite-hard-limit control child)" : "") << std::endl;
        // The healthy control writes a 1 049 600-byte MRC. Under a hard limit
        // below that, nothing here is meaningful -- say so instead of reporting
        // a writer defect that is really the environment.
        if (rl.rlim_max != RLIM_INFINITY && rl.rlim_max < 1049600u) {
            std::cerr << "FAIL: inherited hard RLIMIT_FSIZE (" << (unsigned long long)rl.rlim_max
                      << " bytes) is below the 1049600-byte healthy control; this environment "
                         "cannot run the suite" << std::endl;
            return 1;
        }
    }

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

        // ---- 5. Destructor safety, non-vacuously --------------------------
        // The point of the case is that a handler holding bytes which CANNOT be
        // flushed is destroyed quietly. So it has to establish that they really
        // could not be flushed, or it passes no matter what happens: 3000 bytes
        // under a 1536-byte limit, below the stdio buffer so nothing reaches the
        // fd until the close, and afterwards the file on disk must be shorter
        // than what was handed to the stream.
        //
        // Reaching the line after the inner scope is the other half. The old
        // destructor called REPORT_ERROR here, and a throw from an implicitly
        // noexcept destructor is std::terminate, so this binary would abort
        // rather than report anything. Case 3 above separately shows the same
        // conditions being reported when the close is explicit.
        //
        // Deliberately uses only the pre-existing fImageHandler interface, so
        // this file still compiles against unfixed source and can serve as the
        // negative control there.
        {
            const std::string d_path = dir + "/dtor.mrc";
            const std::vector<char> junk(3000, 'x');
            remove(d_path.c_str());
            setFileSizeLimit(1536);
            {
                fImageHandler h;
                h.openFile(d_path, WRITE_OVERWRITE);
                check(fwrite(junk.data(), junk.size(), 1, h.fimg) == 1,
                      "the buffered write itself must succeed, or this case is "
                      "testing the wrong thing");
                // h goes out of scope here holding unflushable buffered bytes.
            }
            restoreFileSizeLimit();
            const long left = fileSize(d_path);
            check(left >= 0 && left < 3000,
                  "the destructor's stream flushed after all (" + std::to_string(left) +
                  " bytes on disk): this case would pass without observing anything");
            remove(d_path.c_str());
            std::cout << "  destructor dropped " << (3000 - left)
                      << " unflushable bytes without terminating" << std::endl;
        }
    } catch (RelionError &e) {
        restoreFileSizeLimit();
        std::cerr << "FAIL: unexpected RelionError: " << e.msg << std::endl;
        failures++;
    } catch (std::exception &e) {
        restoreFileSizeLimit();
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

    // Run everything above again under a finite hard limit, unless we already are
    // that child. Outermost only, so the recursion is exactly one level deep.
    if (!in_child && argc > 0 && argv[0] != NULL) {
        if (runFiniteHardLimitChild(argv[0]) != 0) return 1;
    }

    std::cout << "image write faults: ok" << (in_child ? " (finite hard limit)" : "") << std::endl;
    return 0;
}
