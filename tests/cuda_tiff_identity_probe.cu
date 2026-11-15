// SPDX-License-Identifier: GPL-2.0-or-later
// Test-only translation unit: export the exact host stub address for launch
// interposition, including when the kernel symbol itself is not exported.
// The normal motioncorr_core object and installed binary have no probe.
#ifndef MC_TIFF_IDENTITY_SESSION_SOURCE
#define MC_TIFF_IDENTITY_SESSION_SOURCE "src/acc/cuda/cuda_movie_session.cu"
#endif
#include MC_TIFF_IDENTITY_SESSION_SOURCE

extern "C" const void *mc_tiff_identity_conversion_kernel() {
    return reinterpret_cast<const void *>(fusedU16FlipGainAndSumKernel);
}
