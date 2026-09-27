#ifndef CUDA_PROFILE_POLICY_H_
#define CUDA_PROFILE_POLICY_H_

// Optional detailed CUDA event profiling policy (issue #74).
//
// "Detailed" profiling means the per-substage and per-frame cudaEvent pairs
// inside cuda_alignpatch.cu and cuda_realspace_dw.cu, together with the
// cudaEventSynchronize() call that each of them needs before its elapsed time
// can be read. Those synchronizations exist only so that a duration can be
// printed. They are not what makes the results correct:
//
//   * ordering between stages is provided by the default stream, which is
//     unchanged here;
//   * the host never reads device results early, because every download is a
//     blocking cudaMemcpy to pageable host memory;
//   * every stage still ends with one checked completion boundary -- the
//     always-on total event pair and its cudaEventSynchronize(), which is
//     error-checked exactly as before -- so a kernel fault is still reported
//     before the stage prints its completion marker.
//
// Nothing here changes arithmetic, reduction order, streams, batching or
// allocation. Only whether intermediate durations are measured and printed.
//
// Default: ENABLED, which reproduces the behaviour shipped in #82 byte for
// byte. This header adds the switch and documents the default; it does not
// change it.
//
// Runtime:  RELION_CUDA_DETAILED_PROFILE=0 disables the detailed events.
//           Accepted "off" spellings: "0", "off", "OFF", "false", "FALSE", "no".
//           Anything else, including unset, leaves the build default in place.
// Build:    -DRELION_CUDA_DETAILED_PROFILE_DEFAULT=0 flips the default without
//           touching this file.
//
// The runtime switch is deliberate: it lets the enabled and disabled arms of a
// measurement run from one identical binary, so the comparison cannot be
// confounded by codegen differences.

#include <cstdlib>
#include <cstring>

#ifndef RELION_CUDA_DETAILED_PROFILE_DEFAULT
#define RELION_CUDA_DETAILED_PROFILE_DEFAULT 1
#endif

static bool cudaDetailedProfileFromEnvironment()
{
    const char *value = getenv("RELION_CUDA_DETAILED_PROFILE");
    if (value == nullptr || value[0] == '\0')
        return RELION_CUDA_DETAILED_PROFILE_DEFAULT != 0;
    return !(strcmp(value, "0") == 0 || strcmp(value, "off") == 0 ||
             strcmp(value, "OFF") == 0 || strcmp(value, "false") == 0 ||
             strcmp(value, "FALSE") == 0 || strcmp(value, "no") == 0);
}

// Resolved once per process; safe to call from OpenMP movie threads.
static bool cudaDetailedProfileEnabled()
{
    static const bool enabled = cudaDetailedProfileFromEnvironment();
    return enabled;
}

#endif /* CUDA_PROFILE_POLICY_H_ */
