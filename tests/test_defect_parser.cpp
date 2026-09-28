// Unit test for MotioncorrRunner::fillDefectMask, MotionCor2 txt branch (issue #98).
//
// Exercises the production parser directly: every case below calls
// MotioncorrRunner::fillDefectMask on a real temporary defect file and
// inspects the resulting mask or the thrown RelionError.
#include "src/motioncorr_runner.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>

static int failures = 0, passed = 0;

static std::string tmpfile_with(const std::string &body, const std::string &tag)
{
    std::string p = "/tmp/i98_defect_" + tag + ".txt";
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
    int rc = run(m, ny, nx, "0 0 99999999999999999999999 5\n", "o1", &msg);
    std::cout << "  INFO  >LLONG_MAX width -> "
              << (rc ? "REJECTED: " + msg : "accepted") << "\n";
    rc = run(m, ny, nx, "9223372036854775807 0 9223372036854775807 5\n", "o2", &msg);
    check(rc == 0 && count_set(m) == 0,
          "LLONG_MAX x+w does not overflow or crash, paints 0 px");

    std::cout << "\n" << passed << " passed, " << failures << " failed\n";
    return failures ? 1 : 0;
}
