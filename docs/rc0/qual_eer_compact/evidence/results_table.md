| case | g | up | gain | groups (dropped fractions) | route auto / float | peak RSS auto / float MiB (saving) | NVML VRAM auto / float MiB | tree identity auto vs float |
|---|---:|---:|---|---|---|---|---|---|
| b1_trunc60 | 40 | 1 | no | 58 | compact,compact / float,float | 3301 / 5160 (-36 %) | 8078 / 8048 | no compare (run failed) |
| b2_randbytes | 40 | 1 | no | 58 | compact,compact,compact / float,float,float | 3302 / 5161 (-36 %) | 8078 / 8046 | no compare (run failed) |
| b3_stripff | 40 | 1 | no | 58 | compact,compact,compact / float,float,float | 3303 / 5162 (-36 %) | 8078 / 8046 | no compare (run failed) |
| b4_stripzero | 40 | 1 | no | 58 | compact,compact,compact / float,float,float | 3303 / 5161 (-36 %) | 8078 / 8046 | no compare (run failed) |
| b5_trunc60_noexp | 40 | 1 | no | 58 | compact,compact,compact / float,float,float | 3301 / 5158 (-36 %) | 8078 / 8046 | no compare (run failed) |
| b6_wronggain | 49 | 1 | yes | 39 | - / - | 56 / 56 (+0 %) | 0 / 0 | no compare (run failed) |
| c01_f3_g40_up1 | 40 | 1 | no | 58 (11) | compact / float | 3240 / 5260 (-38 %) | 8738 / 8726 | PASS |
| c02_f4_g40_up1 | 40 | 1 | no | 144 (22) | compact / float | 7625 / 12288 (-38 %) | 20446 / 20446 | PASS |
| c03_g_g49_up1_gain | 49 | 1 | yes | 39 (0) | compact / float | 2358 / 3721 (-37 %) | 6116 / 6140 | PASS |
| c04_g_g49_up1_nogain | 49 | 1 | no | 39 (0) | compact / float | 2293 / 3657 (-37 %) | 6052 / 6052 | PASS |
| c05_f3_g45_up1_rem | 45 | 1 | no | 51 (36) | compact / float | 3016 / 4796 (-37 %) | 7774 / 7774 | PASS |
| c06_f4_g37_up1_rem | 37 | 1 | no | 156 (10) | compact / float | 8009 / 13056 (-39 %) | 22106 / 22106 | PASS |
| c07_g_g47_up1_gain_rem | 47 | 1 | yes | 40 (31) | compact / float | 2392 / 3789 (-37 %) | 6278 / 6286 | PASS |
| c08_f3_g1_up1_sub | 1 | 1 | no | 2331 (0) | compact / float | 2632 / 3960 (-34 %) | 5774 / 5744 | PASS |
| c09_g_g1_up1_gain_sub | 1 | 1 | yes | 1911 (0) | compact / float | 2362 / 3689 (-36 %) | 5838 / 5806 | PASS |
| c10_f3_g40_up2 | 40 | 2 | no | 58 (11) | compact / float | 8906 / 16858 (-47 %) | 33694 / 33694 | PASS |
| c11_g_g49_up2_gain | 49 | 2 | yes | 39 (0) | compact / float | 6390 / 11717 (-45 %) | 23222 / 23138 | PASS |
| c12_g_g49_up2_nogain | 49 | 2 | no | 39 (0) | compact / float | 6134 / 11462 (-46 %) | 22966 / 22966 | PASS |
| c13_f3_g40_up-1 | 40 | -1 | no | 58 (11) | compact / float | 2441 / 2441 (+0 %) | 2342 / 2334 | PASS |
| c14_g_g49_up-1_nogain | 49 | -1 | no | 39 (0) | compact / float | 1787 / 1785 (+0 %) | 1892 / 1892 | PASS |
| c15_f3_g200_up3 | 200 | 3 | no | 11 (131) | compact / float | 7492 / 13866 (-46 %) | 26850 / 26888 | PASS |
| c16_g_g150_up3 | 150 | 3 | no | 12 (111) | compact / float | 7649 / 14562 (-47 %) | 29072 / 28994 | PASS |
| c17_g_g49_up-1_gain_expectfail | 49 | -1 | yes | 39 (0) | - / - | 183 / 183 (+0 %) | 0 / 0 | no compare (run failed) |
| d1_g_up1_gain_defect | 49 | 1 | yes | 39 (0) | compact / float | 2357 / 3718 (-37 %) | 6116 / 6124 | PASS |
| d2_g_up1_gain_defectblock | 49 | 1 | yes | 39 (0) | compact / float | 2421 / 3719 (-35 %) | 6124 / 6140 | PASS |
| d3_g_up2_gain_defectblock | 49 | 2 | yes | 39 (0) | compact / float | 6646 / 11718 (-43 %) | 23222 / 23222 | PASS |
| m1_f4_g40_up2_full | 40 | 2 | no | 144 (22) | compact / float | 21547 / 40171 (-46 %) | 79522 / 79522 | PASS |
| m2_f4_g40_up2_100groups | 40 | 2 | no | 144 (22) | compact / float | 15913 / 28905 (-45 %) | 56164 / 56164 | PASS |
| o1_ovf_upm1_g16384 | 16384 | -1 | no | 3 | float / float | 5625 / 5625 (+0 %) | 574 / 574 | PASS |
| o1n_NOGUARD_upm1_g16384 | 16384 | -1 | no | 3 | compact / float | 5585 / 5625 (-1 %) | 574 / 574 | FAIL (products-only FAIL) |
| o2_ovf_upm1_g16383 | 16383 | -1 | no | 3 | compact / float | 5586 / 5626 (-1 %) | 574 / 574 | PASS |
| o3_boundary_up1_g65535 | 65535 | 1 | no | 3 | compact / float | 5633 / 5658 (-0 %) | 574 / 574 | PASS |
| o4_ovf_up1_g65536 | 65536 | 1 | no | 3 | float / float | 5657 / 5657 (-0 %) | 574 / 574 | PASS |
| o5_ovf_up2_g65536_8K | 65536 | 2 | no | 3 | float / float | 22891 / 22891 (-0 %) | 2734 / 2734 | PASS |
| x1_syn65000_4k_up1 | 40 | 1 | no | 6 | compact / float | 394 / 634 (-38 %) | 1392 / 1390 | PASS |
| x2_syn65000_4k_upm1 | 40 | -1 | no | 6 | compact / float | 214 / 274 (-22 %) | 678 / 670 | PASS |
| x3_syn65002_2k_up1 | 40 | 1 | no | 6 | compact / float | 193 / 252 (-23 %) | 670 / 670 | PASS |
| x4_syn65002_2k_up2 | 40 | 2 | no | 6 | compact / float | 369 / 607 (-39 %) | 1392 / 1390 | PASS |
| x5_syn65001_2k_up2 | 40 | 2 | no | 6 | compact / float | 369 / 610 (-39 %) | 1390 / 1390 | PASS |
