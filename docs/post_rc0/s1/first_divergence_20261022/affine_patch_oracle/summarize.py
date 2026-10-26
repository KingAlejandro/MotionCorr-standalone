#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Print the README tables from attempt02.json and supplement01.json (norms in px).
usage: summarize.py ATTEMPT_JSON SUPPLEMENT_JSON"""
import json, sys
import numpy as np
A = json.load(open(sys.argv[1])); S = json.load(open(sys.argv[2]))
n = lambda v: np.linalg.norm(np.array(v), axis=-1)
for b in ('cpu', 'cuda'):
    d = A['decomposition'][b]; T = d['terms']
    print(f'== {b}: iteration-1 anchored update, norm of each term per frame 1..4 (px)')
    rows = [('native - truth(centre)', n(d['total_native_minus_truth_centre'])),
            ('quantization: native - parabola(double map)', n(T['quantization_native_minus_b'])),
            ('  of which frame-0 anchor term', np.full(5, np.linalg.norm(S[b]['S1_anchor_split']['frame0_term_cand0_minus_b0']))),
            ('  of which frame-f term', n(S[b]['S1_anchor_split']['frame_term_cand_minus_b'])),
            ('parabola vs continuous max (soo objective)', n(T['parabola_b_minus_c'])),
            ('sum-of-others vs fixed template', n(T['blending_c_minus_cT'])),
            ('native input vs analytic render', n(T['input_cT_minus_d'])),
            ('window + deformation: R_fm - truth(centre)', n(T['window_deformation_d_minus_t'])),
            ('  of which window only (pure-translation equivalent)', np.array([0] + [np.linalg.norm(r['window_only_w_minus_t']) for r in S[b]['S2_deformation_vs_window']])),
            ('  of which deformation only', np.array([0] + [np.linalg.norm(r['deformation_only_Rfm_minus_w']) for r in S[b]['S2_deformation_vs_window']]))]
    for name, v in rows: print(f'{name:55s}', ' '.join(f'{x:6.3f}' for x in v[1:]))
    print(f'identity max abs {d["identity_max_abs"]:.2e}')
    print('truth interval range (x,y) per frame 1..4:', [[round(x, 3) for x in t['range_xy']] for t in A['truth_interval'][b][1:]])
    print('native states vs R_fm / truth(centre), last captured iteration, norms:', S[b]['S4_replays']['native_captured_final']['minus_Rfm_norm'], S[b]['S4_replays']['native_captured_final']['minus_truth_centre_norm'])
    for k, v in S[b]['S4_replays'].items():
        if k != 'native_captured_final': print(f'  replay {k:46s} it={v["iterations"]:2d} conv={v["converged"]} to R_fm {np.round(v["minus_Rfm_norm"], 3).tolist()} to truth {np.round(v["minus_truth_centre_norm"], 3).tolist()}')
