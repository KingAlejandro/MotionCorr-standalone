// Unit test for MotioncorrRunner::fillDefectMask, MotionCor2 txt branch (issue #98).
//
// Exercises the production parser directly: every case below calls
// MotioncorrRunner::fillDefectMask on a real temporary defect file and
// inspects the resulting mask or the thrown RelionError.
#include "src/motioncorr_runner.h"
#include "src/defect_neighbours.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

static int failures = 0, passed = 0;

// Per-process scratch directory, so concurrent ctest jobs and repeat runs on a
// shared build host cannot collide or inherit a stale fixture. Uses POSIX
// mkdir rather than <filesystem>, which would need -lstdc++fs on GCC <= 8 and
// is otherwise unused in this project.
static const std::string &scratch_dir()
{
    static const std::string dir = [] {
        const char *base = getenv("TMPDIR");
        std::string d = std::string(base && *base ? base : "/tmp") +
            "/motioncorr_defect_test_" + std::to_string(static_cast<long>(::getpid()));
        ::mkdir(d.c_str(), 0700);
        return d;
    }();
    return dir;
}

static std::string tmpfile_with(const std::string &body, const std::string &tag)
{
    const std::string p = scratch_dir() + "/" + tag + ".txt";
    std::ofstream o(p, std::ios::binary);
    o << body;
    o.close();
    return p;
}

static void check(bool ok, const std::string &what)
{
    if (ok) { passed++; std::cout << "  PASS  " << what << "\n"; }
    else    { failures++; std::cout << "  FAIL  " << what << "\n"; }
}

// Returns 0 if the parser accepted the file, 1 if it threw. Paints into mask.
static int run(MultidimArray<bool> &mask, int ny, int nx,
               const std::string &body, const std::string &tag, std::string *msg = nullptr)
{
    mask.initZeros(ny, nx);
    std::string p = tmpfile_with(body, tag);
    try { MotioncorrRunner::fillDefectMask(mask, p, 1); }
    catch (RelionError &e) { if (msg) *msg = e.msg; return 1; }
    catch (...) { if (msg) *msg = "(non-RelionError)"; return 1; }
    return 0;
}

static long count_set(MultidimArray<bool> &m)
{
    long c = 0;
    FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(m) if (DIRECT_MULTIDIM_ELEM(m, n)) c++;
    return c;
}

int main()
{
    const int ny = 64, nx = 64;
    MultidimArray<bool> m;
    std::string msg;

    std::cout << "== valid input ==\n";
    check(run(m, ny, nx, "0 0 2 3\n", "v1") == 0 && count_set(m) == 6,
          "single rect 0 0 2 3 -> 6 px");
    check(run(m, ny, nx, "0 0 2 3\n10 10 4 4\n", "v2") == 0 && count_set(m) == 6 + 16,
          "two rects -> 22 px");
    check(run(m, ny, nx, "0 0 2 3", "v3") == 0 && count_set(m) == 6,
          "no trailing newline -> 6 px");
    check(run(m, ny, nx, "  \n 0 0 2 3 \n\n  \n", "v4") == 0 && count_set(m) == 6,
          "blank lines and padding tolerated -> 6 px");

    std::cout << "== empty / whitespace ==\n";
    check(run(m, ny, nx, "", "e1") == 0 && count_set(m) == 0,
          "empty file -> no error, 0 px");
    check(run(m, ny, nx, "\n\n   \n", "e2") == 0 && count_set(m) == 0,
          "whitespace-only -> no error, 0 px");

    std::cout << "== malformed (must be rejected) ==\n";
    check(run(m, ny, nx, "0 0 1 1\nBAD TOKEN\n", "m1", &msg) == 1,
          "issue #98 reproducer 'BAD TOKEN' rejected");
    check(run(m, ny, nx, "BAD TOKEN\n0 0 1 1\n", "m2") == 1, "malformed FIRST rejected");
    check(run(m, ny, nx, "0 0 1 1\n1 1 1 1\nBAD\n", "m3") == 1, "malformed LAST rejected");
    check(run(m, ny, nx, "0 0 1\n", "m4") == 1, "partial record (3 fields) rejected");
    check(run(m, ny, nx, "0 0 1 1\n2 2 2\n", "m5") == 1, "trailing partial record rejected");
    check(run(m, ny, nx, "1.5 2 3 4\n", "m6") == 1, "float token rejected");

    // Policy (issue #98): the supported contract is the UCSF MotionCor2 one --
    // whitespace-separated integer quadruples only. Comments, headers and a
    // UTF-8 BOM are not part of that format and are rejected with a specific
    // diagnostic. These are assertions, not observations: the policy is fixed.
    std::cout << "== comment / header / BOM policy ==\n";
    check(run(m, ny, nx, "# comment\n0 0 2 3\n", "c1", &msg) == 1 &&
              msg.find("does not support") != std::string::npos,
          "'#' comment rejected with a format-explaining message");
    check(run(m, ny, nx, "x y w h\n0 0 2 3\n", "c2") == 1,
          "text header row rejected");
    check(run(m, ny, nx, "\xEF\xBB\xBF" "0 0 2 3\n", "c3", &msg) == 1 &&
              msg.find("byte order mark") != std::string::npos,
          "UTF-8 BOM rejected with a BOM-specific message");

    std::cout << "== diagnostic quality (record is 1-based, line is named) ==\n";
    run(m, ny, nx, "BAD\n", "d1", &msg);
    check(msg.find("record 1") != std::string::npos && msg.find("line 1") != std::string::npos,
          "first record reported as 'record 1, line 1'");
    run(m, ny, nx, "0 0 1 1\n1 1 1 1\nBAD\n", "d2", &msg);
    check(msg.find("record 3") != std::string::npos && msg.find("line 3") != std::string::npos,
          "third record reported as 'record 3, line 3'");
    run(m, ny, nx, "\n\n\n0 0 1 1\nBAD\n", "d3", &msg);
    check(msg.find("record 2") != std::string::npos && msg.find("line 5") != std::string::npos,
          "leading blank lines counted: 'record 2, line 5'");
    run(m, ny, nx, "0 0 1 1\nBAD\n", "d4", &msg);
    check(msg.find("\"BAD\"") != std::string::npos, "offending token quoted in message");
    run(m, ny, nx, "0 0 1\n", "d5", &msg);
    check(msg.find("Truncated") != std::string::npos,
          "partial record distinguished as 'Truncated', not 'Malformed'");
    // A record may straddle a line break. The line counter must keep counting
    // newlines consumed *between fields*, or it desynchronizes for the rest of
    // the file and every later diagnostic names the wrong line.
    check(run(m, ny, nx, "0 0\n1 1\n2 2 2 2\nBAD\n", "d6", &msg) == 1 &&
              msg.find("line 4") != std::string::npos,
          "line stays correct after a record split across lines");
    // A record truncated by EOF names where the record STARTED: by the time the
    // shortfall is detected the whitespace skip has stepped past the last
    // content line, so reporting the current line would name a line that does
    // not exist in the file.
    run(m, ny, nx, "0 0 1 1\n2 2 2\n", "d7", &msg);
    check(msg.find("Truncated") != std::string::npos && msg.find("line 2") != std::string::npos,
          "truncated record names its start line, not one past EOF");

    // A path that opens but cannot be read must not be mistaken for an empty
    // file, which would mask nothing and let the movie publish as if defect
    // correction had succeeded. A directory named *.txt is the reachable case.
    //
    // How much the platform exposes differs: libstdc++ sets badbit, libc++
    // reports an ordinary EOF. Probe this platform first and assert only what
    // it can actually distinguish -- and say so out loud when it cannot, rather
    // than passing silently and looking like coverage.
    std::cout << "== read error is not a valid empty file ==\n";
    {
        const std::string dir = scratch_dir() + "/directory.txt";
        ::mkdir(dir.c_str(), 0700);

        std::ifstream probe(dir);
        bool observable = false;
        if (probe.is_open()) {
            probe.peek();
            observable = probe.bad() || !probe.eof();
        }
        probe.close();

        MultidimArray<bool> dm;
        dm.initZeros(ny, nx);
        int rc_dir = 0;
        std::string dmsg;
        try { MotioncorrRunner::fillDefectMask(dm, dir, 1); }
        catch (RelionError &e) { dmsg = e.msg; rc_dir = 1; }
        catch (...) { rc_dir = 1; }

        if (observable) {
            check(rc_dir == 1 && dmsg.find("could not be read") != std::string::npos,
                  "directory named *.txt rejected as a read error, not empty input");
            check(count_set(dm) == 0, "rejected read error publishes no mask");
        } else {
            std::cout << "  INFO  this platform reports a directory as an ordinary EOF "
                      << "(rc=" << rc_dir << "); the read-error distinction is NOT "
                      << "observable here, so nothing is asserted. libstdc++ does set "
                      << "badbit and the assertion is live there.\n";
        }
        ::rmdir(dir.c_str());
    }

    // Issue #98 Plan bullet 5: the SerialEM detector must keep rejecting
    // SerialEM-style input. Both call sites consult it before fillDefectMask,
    // so the strict parser must not have displaced it.
    std::cout << "== SerialEM detector still discriminates ==\n";
    check(MotioncorrRunner::detectSerialEMDefectText(
              tmpfile_with("CameraSize 4096 4096 1\nBadColumns 1 2\n", "s1")),
          "SerialEM-style file still detected");
    check(!MotioncorrRunner::detectSerialEMDefectText(
              tmpfile_with("0 0 2 3\n10 10 4 4\n", "v5")),
          "valid MotionCor2 file not misdetected as SerialEM");

    std::cout << "== zero / negative size ==\n";
    check(run(m, ny, nx, "5 5 0 4\n", "z1") == 0 && count_set(m) == 0, "w=0 -> skipped, 0 px");
    check(run(m, ny, nx, "5 5 4 0\n", "z2") == 0 && count_set(m) == 0, "h=0 -> skipped, 0 px");
    check(run(m, ny, nx, "5 5 -4 4\n", "z3") == 0 && count_set(m) == 0, "w<0 -> skipped, 0 px");

    std::cout << "== clipping ==\n";
    check(run(m, ny, nx, "-2 -2 4 4\n", "k1") == 0 && count_set(m) == 4,
          "negative origin clips to 2x2 = 4 px");
    check(run(m, ny, nx, "62 62 10 10\n", "k2") == 0 && count_set(m) == 4,
          "overhang bottom-right clips to 2x2 = 4 px");
    check(run(m, ny, nx, "100 100 5 5\n", "k3") == 0 && count_set(m) == 0,
          "fully outside -> 0 px");
    check(run(m, ny, nx, "-50 -50 10 10\n", "k4") == 0 && count_set(m) == 0,
          "fully outside negative -> 0 px");

    std::cout << "== huge rect must finish boundedly (the #98 hang gate) ==\n";
    auto t0 = std::chrono::steady_clock::now();
    int hrc = run(m, ny, nx, "0 0 1000000000 1000000000\n", "h1");
    long hpx = count_set(m);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                  std::chrono::steady_clock::now() - t0).count();
    std::cout << "  INFO  huge rect: rc=" << hrc << " px=" << hpx
              << " elapsed=" << ms << "ms\n";
    check(ms < 1000, "huge 1e9 x 1e9 rect completes in <1s");
    check(hpx == (long)ny * nx, "huge rect fills whole image (clipped, not skipped)");

    auto t1 = std::chrono::steady_clock::now();
    run(m, ny, nx, "-2000000000 -2000000000 4000000000 4000000000\n", "h2");
    auto ms2 = std::chrono::duration_cast<std::chrono::milliseconds>(
                   std::chrono::steady_clock::now() - t1).count();
    std::cout << "  INFO  beyond-INT32 rect elapsed=" << ms2 << "ms px="
              << count_set(m) << "\n";
    check(ms2 < 1000, "rect exceeding INT32 range completes in <1s");

    std::cout << "== integer overflow boundary ==\n";
    // Regression: an out-of-range value sets failbit only AFTER consuming its
    // digits, so a recovery read names the FOLLOWING token. This asserted the
    // wrong token ("5") until the parser switched to token-wise conversion.
    int rc = run(m, ny, nx, "0 0 99999999999999999999999 5\n", "o1", &msg);
    check(rc == 1 && msg.find("99999999999999999999999") != std::string::npos,
          ">LLONG_MAX width names the offending value, not the next field");
    check(msg.find("Out-of-range") != std::string::npos && msg.find("'w'") != std::string::npos,
          ">LLONG_MAX width reported as out-of-range on field 'w'");
    run(m, ny, nx, "0 -99999999999999999999999 5 5\n", "o3", &msg);
    check(msg.find("'y'") != std::string::npos, "out-of-range negative names field 'y'");
    run(m, ny, nx, "0 0 5abc 5\n", "o4", &msg);
    check(msg.find("\"5abc\"") != std::string::npos && msg.find("'w'") != std::string::npos,
          "trailing garbage after digits rejected, whole token quoted");
    run(m, ny, nx, "0 0\n", "o5", &msg);
    check(msg.find("after 2 of 4 fields") != std::string::npos,
          "truncated record reports how many fields were read");
    rc = run(m, ny, nx, "9223372036854775807 0 9223372036854775807 5\n", "o2", &msg);
    check(rc == 0 && count_set(m) == 0,
          "LLONG_MAX x+w does not overflow or crash, paints 0 px");

    std::cout << "== defect premask cache controls ==\n";
    {
        // The premask caches only the static part of the hot-pixel mask: the
        // external defect file and the gain-zero pixels. Every key component
        // below has its own miss case, and the detected-hot-pixel case proves
        // that the per-movie part never reaches the cache.
        MotioncorrRunner runner;
        MultidimArray<float> no_gain;
        const std::string fn_a = tmpfile_with("0 0 2 2\n", "pma");
        const std::string fn_bad = tmpfile_with("0 0 1 1\nBAD\n", "pmb");

        // 1. No external defect file and no gain: an all-false mask, still cached.
        const MultidimArray<bool> &none = runner.getDefectPremask(nx, ny, "", "", no_gain, 1);
        check(runner.isDefectPremaskValid(), "premask with no defect file and no gain is cached");
        check(count_set(const_cast<MultidimArray<bool>&>(none)) == 0,
              "premask with no defect file and no gain is empty");

        // 2. A valid defect file.
        const MultidimArray<bool> &mask_a = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
        check(runner.isDefectPremaskValid(), "premask A cached validly");
        check(count_set(const_cast<MultidimArray<bool>&>(mask_a)) == 4, "premask A has 4 defect pixels");

        // 3. A malformed file must throw and leave the cache invalid, not stale.
        bool threw = false;
        try { runner.getDefectPremask(nx, ny, fn_bad, "", no_gain, 1); }
        catch (RelionError &) { threw = true; }
        check(threw, "premask B threw RelionError on a malformed file");
        check(!runner.isDefectPremaskValid(), "premask cache invalidated after failure on B");
        check(runner.defect_premask_nx == 0 && runner.defect_premask_fn == "",
              "premask cache keys cleared after failure on B");

        // 4. Recovery: A must be reparsed, not read back from corrupt state.
        const MultidimArray<bool> &mask_a2 = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
        check(runner.isDefectPremaskValid(), "premask A re-cached validly after recovery");
        check(count_set(const_cast<MultidimArray<bool>&>(mask_a2)) == 4,
              "premask A has 4 defect pixels after recovery");

        // 5. Changed geometry must miss.
        const MultidimArray<bool> &mask_small = runner.getDefectPremask(32, 32, fn_a, "", no_gain, 1);
        check(XSIZE(mask_small) == 32 && YSIZE(mask_small) == 32,
              "premask follows a changed geometry instead of reusing the old mask");
        check(runner.defect_premask_nx == 32 && runner.defect_premask_ny == 32,
              "premask geometry key follows the new geometry");
        (void)runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);

        // 6. A rewritten defect file under the SAME name must miss. main re-read
        //    and re-validated the file for every movie, so a filename-only key
        //    would silently keep the old parse.
        {
            // mtime has one-second resolution on some filesystems, so the
            // rewrite also changes the size, which the key includes.
            const std::string rewritten = tmpfile_with("0 0 3 3\n0 0 1 1\n", "pma");
            (void)rewritten;
            const MultidimArray<bool> &rewrote = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
            check(count_set(const_cast<MultidimArray<bool>&>(rewrote)) == 9,
                  "a rewritten defect file under the same name is reparsed");
            // Restore the original fixture for the cases below.
            (void)tmpfile_with("0 0 2 2\n", "pma");
            const MultidimArray<bool> &restored = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
            check(count_set(const_cast<MultidimArray<bool>&>(restored)) == 4,
                  "restoring the original defect file is reparsed again");
        }

        // 7. The gain-zero mask, and a changed gain under a new generation.
        MultidimArray<float> gain_one(ny, nx), gain_two(ny, nx);
        gain_one.initConstant(1.0f);
        gain_two.initConstant(1.0f);
        DIRECT_A2D_ELEM(gain_one, 10, 10) = 0.0f;
        DIRECT_A2D_ELEM(gain_two, 20, 20) = 0.0f;
        DIRECT_A2D_ELEM(gain_two, 21, 21) = 0.0f;
        runner.gain_cache_generation = 5;
        const MultidimArray<bool> &with_gain = runner.getDefectPremask(nx, ny, fn_a, "gain.mrc", gain_one, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(with_gain)) == 5,
              "premask unions the defect file with the gain-zero pixels");
        runner.gain_cache_generation = 6;
        const MultidimArray<bool> &with_gain2 = runner.getDefectPremask(nx, ny, fn_a, "gain.mrc", gain_two, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(with_gain2)) == 6,
              "a new gain generation rebuilds the gain-zero part of the premask");
        check(!DIRECT_A2D_ELEM(with_gain2, 10, 10),
              "the previous gain's zero pixel did not survive into the new premask");
        const MultidimArray<bool> &no_gain_again = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(no_gain_again)) == 4,
              "dropping the gain rebuilds the premask without the gain-zero pixels");

        // 8. Detected hot pixels belong to one movie and must never be cached.
        MultidimArray<bool> movie_mask;
        movie_mask = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
        DIRECT_A2D_ELEM(movie_mask, 40, 40) = true;
        DIRECT_A2D_ELEM(movie_mask, 41, 41) = true;
        check(count_set(movie_mask) == 6, "the movie's own copy carries its detected hot pixels");
        const MultidimArray<bool> &next_movie = runner.getDefectPremask(nx, ny, fn_a, "", no_gain, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(next_movie)) == 4,
              "detected hot pixels did not leak into the cached static premask");

        // 9. Dense defects: the cached premask must still reach the Gaussian
        //    replacement branch. A solid 5x5 block leaves exactly the five
        //    plus-shaped centre cells with n_ok <= NUM_MIN_OK for D_MAX = 2.
        const std::string fn_dense = tmpfile_with("8 8 5 5\n", "pmd");
        const MultidimArray<bool> &dense = runner.getDefectPremask(nx, ny, fn_dense, "", no_gain, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(dense)) == 25, "dense premask paints 25 px");
        {
            auto bad = [&dense](int y, int x) { return DIRECT_A2D_ELEM(dense, y, x); };
            int gaussian = 0;
            for (int i = 0; i < ny; i++)
                for (int j = 0; j < nx; j++) {
                    if (!DIRECT_A2D_ELEM(dense, i, j)) continue;
                    if (mc_defect::countValidNeighbours(bad, nx, ny, i, j, 2) <= 6) gaussian++;
                }
            check(gaussian == 5, "dense cached premask reaches Gaussian replacement for 5 pixels");
        }

        // 10. A second runner on this thread must not see the first one's cache.
        MotioncorrRunner other;
        check(!other.isDefectPremaskValid(), "a second runner starts with no cached premask");
        const MultidimArray<bool> &other_mask = other.getDefectPremask(nx, ny, "", "", no_gain, 1);
        check(count_set(const_cast<MultidimArray<bool>&>(other_mask)) == 0,
              "a second runner builds its own premask rather than inheriting one");
        check(count_set(const_cast<MultidimArray<bool>&>(
                  runner.getDefectPremask(nx, ny, fn_dense, "", no_gain, 1))) == 25,
              "the first runner's premask is unaffected by the second runner");
    }

    // Remove the fixtures we created, then the directory.
    for (const char *tag : {"v1","v2","v3","v4","v5","e1","e2","m1","m2","m3","m4","m5","m6",
                            "c1","c2","c3","d1","d2","d3","d4","d5","d6","z1","z2","z3",
                            "k1","k2","k3","k4","h1","h2","o1","o2","o3","o4","o5","s1","d7",
                            "pma","pmb","pmd"}) {
        std::remove((scratch_dir() + "/" + tag + ".txt").c_str());
    }
    ::rmdir(scratch_dir().c_str());

    std::cout << "\n" << passed << " passed, " << failures << " failed\n";
    return failures ? 1 : 0;
}
