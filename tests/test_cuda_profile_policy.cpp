// Issue #74: the optional detailed CUDA profiling policy must stay explicit
// and must default to the behaviour shipped in #82 (detailed events ON).
//
// The policy header is plain C++ and pulls in no CUDA headers, so this runs in
// ordinary CPU CI with no GPU. It exercises the uncached environment parser;
// cudaDetailedProfileEnabled() caches its answer for the life of the process
// by design, so it is checked once for the unset-environment default.

#include "src/acc/cuda/cuda_profile_policy.h"

#include <cstdio>
#include <cstdlib>

static int failures = 0;

static void check(const char *what, bool got, bool want)
{
    if (got != want) {
        std::printf("FAIL: %s -> %s, expected %s\n", what,
                    got ? "enabled" : "disabled", want ? "enabled" : "disabled");
        failures++;
    } else {
        std::printf("ok:   %s -> %s\n", what, got ? "enabled" : "disabled");
    }
}

static void checkValue(const char *value, bool want)
{
    setenv("RELION_CUDA_DETAILED_PROFILE", value, 1);
    check(value, cudaDetailedProfileFromEnvironment(), want);
}

int main()
{
    unsetenv("RELION_CUDA_DETAILED_PROFILE");
    check("<unset> (build default)", cudaDetailedProfileFromEnvironment(),
          RELION_CUDA_DETAILED_PROFILE_DEFAULT != 0);
    check("<unset> is the #82 behaviour", cudaDetailedProfileEnabled(), true);

    checkValue("", true);            // empty falls back to the build default
    checkValue("0", false);
    checkValue("off", false);
    checkValue("OFF", false);
    checkValue("false", false);
    checkValue("FALSE", false);
    checkValue("no", false);
    checkValue("1", true);
    checkValue("on", true);
    checkValue("yes", true);
    checkValue("anything else", true);

    unsetenv("RELION_CUDA_DETAILED_PROFILE");
    if (failures == 0) {
        std::printf("PASS\n");
        return 0;
    }
    std::printf("FAILED (%d)\n", failures);
    return 1;
}
