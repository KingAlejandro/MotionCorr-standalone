/***************************************************************************
 *
 * Author: "Sjors H.W. Scheres"
 * MRC Laboratory of Molecular Biology
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 ***************************************************************************/
// Frozen sumUnweightedFrames control from #178 e8f3eb8. Interpolation is the
// unchanged production entry point; accumulation retains separate scans.
#pragma once
#include "src/motioncorr_runner.h"
struct MotioncorrRunnerTestAccess {
    static void stream(MotioncorrRunner &r, Image<float> &sum, Image<float> *even,
                       Image<float> *odd, std::vector<Image<float>> &frames,
                       MotionModel *model, std::ostream &log) {
        r.sumUnweightedFrames(sum, even, odd, frames, model, log);
    }
    static void materialize(MotioncorrRunner &r, std::vector<Image<float>> &out,
                            std::vector<Image<float>> &frames, MotionModel *model,
                            std::ostream &log, int offset = 0) {
        r.realSpaceInterpolation_withoutsum(out, frames, model, log, offset);
    }
    static void direct(MotioncorrRunner &r, Image<float> &sum,
                       std::vector<Image<float>> &frames, MotionModel *model,
                       std::ostream &log) {
        r.realSpaceInterpolation(sum, frames, model, log);
    }
    static void separate(MotioncorrRunner &r, Image<float> &sum, Image<float> *even,
                         Image<float> *odd, std::vector<Image<float>> &frames,
                         MotionModel *model, std::ostream &log) {
        std::vector<Image<float>> view(1), aligned(1);
        for (int iframe = 0; iframe < static_cast<int>(frames.size()); ++iframe) {
            view[0]().alias(frames[iframe]());
            aligned[0]().initZeros(frames[iframe]());
            r.realSpaceInterpolation_withoutsum(aligned, view, model, log, iframe);
            #pragma omp parallel for num_threads(r.n_threads)
            FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(sum()) {
                DIRECT_MULTIDIM_ELEM(sum(), n) += DIRECT_MULTIDIM_ELEM(aligned[0](), n);
            }
            Image<float> *split = (iframe % 2 == 0) ? even : odd;
            if (split) {
                FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY((*split)()) {
                    DIRECT_MULTIDIM_ELEM((*split)(), n) += DIRECT_MULTIDIM_ELEM(aligned[0](), n);
                }
            }
        }
    }
};
