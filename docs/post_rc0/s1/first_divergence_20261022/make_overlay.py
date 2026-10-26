#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Apply the W4 diagnostic overlay to an extracted source archive (never a checkout).

usage: make_overlay.py SOURCE_TREE
Every anchor must occur exactly once. With no MC_W4_* variable set, the original
statements execute unchanged; the overlay only adds branches and state writes.
"""
import pathlib, shutil, sys

root = pathlib.Path(sys.argv[1])
assert not (root/'.git').exists(), 'refusing to modify a git checkout'
here = pathlib.Path(__file__).resolve().parent

def edit(rel, pairs):
    p = root/rel; s = p.read_text()
    for old, new in pairs:
        assert s.count(old) == 1, (rel, old[:80], s.count(old))
        s = s.replace(old, new)
    p.write_text(s)

CPU_INJECT = '''\tconst bool w4_fixed = is_global && w4::fixed_reference();
\tif (w4_fixed) logfile << " W4 fixed frame-0 reference" << std::endl;
\tif (is_global && w4::inject_path()) {
\t\tstd::vector<double> w4x, w4y;
\t\tw4::read_shifts(n_frames, w4x, w4y);
\t\tfor (int iframe = 0; iframe < n_frames; iframe++) {
\t\t\tcur_xshifts[iframe] = w4x[iframe] - xshifts[iframe];
\t\t\tcur_yshifts[iframe] = w4y[iframe] - yshifts[iframe];
\t\t\txshifts[iframe] += cur_xshifts[iframe];
\t\t\tyshifts[iframe] += cur_yshifts[iframe];
\t\t}
\t\tfor (int iframe = 1; iframe < n_frames; iframe++)
\t\t\tshiftNonSquareImageInFourierTransform(Fframes[iframe], -cur_xshifts[iframe] / pnx, -cur_yshifts[iframe] / pny);
\t\tw4::write_state("global-iterations.txt", 0, xshifts, yshifts);
\t\tlogfile << " W4 injected global shifts: " << w4::inject_path() << std::endl;
\t\treturn true;
\t}
'''
CPU_FIXED = '''\t\t\tif (w4_fixed) {
\t\t\t\tfor (int y = 0; y < ccf_nfy; y++) {
\t\t\t\t\tconst int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
\t\t\t\t\tfor (int x = 0; x < ccf_nfx; x++) {
\t\t\t\t\t\tDIRECT_A2D_ELEM(Fccs[tid], y, x) = DIRECT_A2D_ELEM(Fframes[0], ly, x) *
\t\t\t\t\t\t                                    DIRECT_A2D_ELEM(Fframes[iframe], ly, x).conj() * DIRECT_A2D_ELEM(weight, y, x);
\t\t\t\t\t}
\t\t\t\t}
\t\t\t} else
'''
edit('src/motioncorr_runner.cpp', [
    ('#include <omp.h>\n', '#include "src/w4_inject.h"\n#include <omp.h>\n'),
    ('\tfor (int iter = 1; iter\t<= max_iter; iter++) {\n\t\tRCTIC(TIMING_MAKE_REF);',
     CPU_INJECT + '\tfor (int iter = 1; iter\t<= max_iter; iter++) {\n\t\tRCTIC(TIMING_MAKE_REF);'),
    ('\t\t\tRCTIC(TIMING_CCF_CALC);\n\t\t\tfor (int y = 0; y < ccf_nfy; y++) {',
     '\t\t\tRCTIC(TIMING_CCF_CALC);\n' + CPU_FIXED + '\t\t\tfor (int y = 0; y < ccf_nfy; y++) {'),
    ('\t\t// Test convergence\n\t\tRFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);',
     '\t\tif (is_global) w4::write_state("global-iterations.txt", iter, xshifts, yshifts);\n\t\t// Test convergence\n\t\tRFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);'),
    ('\tRCTOC(TIMING_GLOBAL_ALIGNMENT);\n\tMC_STAGE("allocate reconstruction");',
     '\tRCTOC(TIMING_GLOBAL_ALIGNMENT);\n\tw4::write_state("global-final.txt", 0, xshifts, yshifts);\n\tMC_STAGE("allocate reconstruction");'),
])

CUDA_KERNEL = '''__global__ void w4FixedRefCCFKernel(
    const float2 *d_Fframes,
    const float *d_weight,
    float2 *d_Fccs,
    int ccf_nfx, int ccf_nfy, int ccf_nfy_half,
    int nfx, int nfy,
    int n_frames)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    int iframe = blockIdx.z;
    if (x < ccf_nfx && y < ccf_nfy && iframe < n_frames) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        float2 fref = d_Fframes[ly * nfx + x];  // unshifted frame 0
        float2 fframe = d_Fframes[iframe * ((size_t)nfy * nfx) + ly * nfx + x];
        float w = d_weight[y * ccf_nfx + x];
        float dr = fref.x;
        float di = fref.y;
        float ccf_r = (dr * fframe.x + di * fframe.y) * w;
        float ccf_i = (di * fframe.x - dr * fframe.y) * w;
        d_Fccs[iframe * ((size_t)ccf_nfy * ccf_nfx) + y * ccf_nfx + x] = make_float2(ccf_r, ccf_i);
    }
}

'''
CUDA_INJECT = '''    const bool w4_fixed = is_global && w4::fixed_reference();
    if (w4_fixed) logfile << " W4 fixed frame-0 reference" << std::endl;
    if (is_global && w4::inject_path()) {
        std::vector<double> w4x, w4y;
        w4::read_shifts(n_frames, w4x, w4y);
        for (int f = 0; f < n_frames; f++) {
            h_cur_xshifts[f] = (float)(w4x[f] - xshifts[f]);
            h_cur_yshifts[f] = (float)(w4y[f] - yshifts[f]);
        }
        updatePatchShifts(h_cur_xshifts.data(), h_cur_yshifts.data(),
            h_shiftx.data(), h_shifty.data(), xshifts, yshifts, n_frames, pnx, pny);
        if (n_frames > 1) {
            ALIGN_CUDA(cudaMemcpy(d_shiftx, h_shiftx.data(), sz_shifts, cudaMemcpyHostToDevice));
            ALIGN_CUDA(cudaMemcpy(d_shifty, h_shifty.data(), sz_shifts, cudaMemcpyHostToDevice));
            fourierShiftKernel<<<gridShift, blockShift>>>(d_Fframes, d_shiftx, d_shifty, data_nfx, data_nfy, data_nfy_half, n_frames);
            ALIGN_LAUNCH(cudaGetLastError());
        }
        w4::write_state("global-iterations.txt", 0, xshifts, yshifts);
        logfile << " W4 injected global shifts: " << w4::inject_path() << std::endl;
        converged = true;
        goto w4_after_loop;
    }
'''
LAUNCH = '        computeCCFKernel<<<gridCCF, blockCCF>>>(d_Fframes, d_Fref, d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, data_nfx, data_nfy, n_frames);\n'
UPDATE = '''        const RFLOAT rmsd = updatePatchShifts(h_cur_xshifts.data(), h_cur_yshifts.data(),
            h_shiftx.data(), h_shifty.data(), xshifts, yshifts, n_frames, pnx, pny);
'''
edit('src/acc/cuda/cuda_alignpatch.cu', [
    ('#include "src/stage_profile.h"\n', '#include "src/stage_profile.h"\n#include "src/w4_inject.h"\n'),
    ('__global__ void findPeakAndInterpolateKernel(', CUDA_KERNEL + '__global__ void findPeakAndInterpolateKernel('),
    ('    for (int iter = 1; iter <= max_iter; iter++) {\n        // 1. Reference computation',
     CUDA_INJECT + '    for (int iter = 1; iter <= max_iter; iter++) {\n        // 1. Reference computation'),
    (LAUNCH, '        if (w4_fixed)\n            w4FixedRefCCFKernel<<<gridCCF, blockCCF>>>(d_Fframes, d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, data_nfx, data_nfy, n_frames);\n        else\n' + LAUNCH),
    (UPDATE, UPDATE + '        if (is_global) w4::write_state("global-iterations.txt", iter, xshifts, yshifts);\n'),
    ('    ALIGN_CUDA(cudaEventRecord(ev_stop_total));', 'w4_after_loop:\n    ALIGN_CUDA(cudaEventRecord(ev_stop_total));'),
])
shutil.copyfile(here/'w4_inject.h', root/'src/w4_inject.h')
print('overlay applied')
