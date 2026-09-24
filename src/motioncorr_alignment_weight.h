#ifndef MOTIONCORR_ALIGNMENT_WEIGHT_H_
#define MOTIONCORR_ALIGNMENT_WEIGHT_H_

#include <cmath>
#include "src/macros.h"

// Use the CPU alignment expression and its RFLOAT intermediates for each row.
// The final store is float on both paths, including when CUDA uploads the row.
inline void fillMotioncorrAlignmentWeightRow(float *row, int y, int ccf_nfx,
                                             int ccf_nfy, int nfx, int nfy,
                                             RFLOAT scaled_B)
{
    const int ccf_nfy_half = ccf_nfy / 2;
    const int ly = (y > ccf_nfy_half) ? (y - ccf_nfy) : y;
    RFLOAT ly2 = ly * (RFLOAT)ly / (nfy * (RFLOAT)nfy);
    for (int x = 0; x < ccf_nfx; x++) {
        RFLOAT dist2 = ly2 + x * (RFLOAT)x / (nfx * (RFLOAT)nfx);
        row[x] = exp(- 2 * dist2 * scaled_B);
    }
}

#endif
