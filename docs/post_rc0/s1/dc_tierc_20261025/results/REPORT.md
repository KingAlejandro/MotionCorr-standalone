# Four-arm DC comparison (generated)

Control: imported unchanged rule reproduces v2.2 summary exactly (80 rows / 240 pairs / 965 regression entries; 804 Tier B records).

## Tier B: field RMS vs none, per backend (cells = 10 conditions; paired seeds)

| backend | arm | cells improves (raw p<.05) | cells harms (raw) | improves after Holm(60) | harms after Holm(60) | seeds meeting all 3 limits /100 | seeds meeting RMS / p95 / max limit |
|---|---|---:|---:|---:|---:|---:|---|
| cpu | none | - | - | - | - | 22/100 | 23 / 26 / 30 |
| cpu | global | 3 | 0 | 0 | 0 | 22/100 | 23 / 26 / 30 |
| cpu | local | 1 | 0 | 0 | 0 | 22/100 | 23 / 26 / 30 |
| cpu | both | 2 | 0 | 0 | 0 | 23/100 | 24 / 28 / 32 |
| cuda | none | - | - | - | - | 22/100 | 23 / 27 / 30 |
| cuda | global | 1 | 1 | 0 | 0 | 22/100 | 23 / 28 / 30 |
| cuda | local | 0 | 0 | 0 | 0 | 22/100 | 23 / 26 / 30 |
| cuda | both | 1 | 0 | 0 | 0 | 23/100 | 24 / 28 / 32 |

### Every primary cell (arm - none, field RMS Angstrom; W/L = seeds improved/worsened)

| cond | backend | arm | n | W/L/T | raw p | Holm p | median delta | boot95 median delta | median delta p95 / max | transfer gain/loss | limit pass fixed/new |
|---|---|---|---:|---|---:|---:|---:|---|---|---|---|
| pedestal32 | cpu | global | 10 | 10/0/0 | 0.001953 | 0.1172 | -0.7902 | [-1.395, -0.5864] | -1.298 / -1.781 | 10/0 | 0/0 |
| pedestal32 | cpu | local | 10 | 10/0/0 | 0.001953 | 0.1172 | -0.5701 | [-0.9659, -0.1686] | -0.7886 / -1.298 | 7/3 | 0/0 |
| pedestal32 | cpu | both | 10 | 10/0/0 | 0.001953 | 0.1172 | -1.347 | [-1.924, -1.119] | -2.381 / -3.37 | 10/0 | 1/0 |
| pedestal0 | cpu | global | 10 | 5/5/0 | 1 | 1 | 3.029e-09 | [-1.512e-07, 1.187e-07] | -4.427e-08 / 2.068e-07 | 7/3 | 0/0 |
| pedestal0 | cpu | local | 10 | 7/3/0 | 0.3438 | 1 | -3.553e-08 | [-8.17e-08, 1.016e-07] | -5.013e-07 / -2.324e-07 | 5/5 | 0/0 |
| pedestal0 | cpu | both | 10 | 7/3/0 | 0.3438 | 1 | -7.328e-08 | [-2.285e-07, 7.001e-08] | -1.796e-08 / -3.125e-07 | 6/4 | 0/0 |
| contrast025 | cpu | global | 10 | 7/3/0 | 0.3438 | 1 | -0.003427 | [-0.008341, 0.0002309] | -0.00893 / -0.02629 | 8/2 | 0/0 |
| contrast025 | cpu | local | 10 | 8/2/0 | 0.1094 | 1 | -0.004638 | [-0.01249, -0.0009752] | -0.01224 / -0.0329 | 8/2 | 0/0 |
| contrast025 | cpu | both | 10 | 9/1/0 | 0.02148 | 1 | -0.008975 | [-0.01326, -0.003887] | -0.02058 / -0.05639 | 7/3 | 0/0 |
| contrast4 | cpu | global | 10 | 4/6/0 | 0.7539 | 1 | 3.661e-06 | [-9.799e-06, 1.785e-05] | -5.569e-06 / 3.199e-05 | 4/6 | 0/0 |
| contrast4 | cpu | local | 10 | 7/3/0 | 0.3438 | 1 | -2.167e-05 | [-3.707e-05, 2.054e-05] | -3.22e-05 / -5.94e-05 | 7/3 | 0/0 |
| contrast4 | cpu | both | 10 | 6/4/0 | 0.7539 | 1 | -1.86e-05 | [-3.849e-05, 3.729e-05] | -3.344e-05 / -7.994e-05 | 4/6 | 0/0 |
| dose1 | cpu | global | 10 | 6/4/0 | 0.7539 | 1 | -0.0002108 | [-0.0003951, 0.0001789] | -0.0004744 / -0.000317 | 9/1 | 0/0 |
| dose1 | cpu | local | 10 | 5/5/0 | 1 | 1 | -1.71e-05 | [-0.0003446, 0.0003079] | -3.108e-05 / 0.001031 | 5/5 | 0/0 |
| dose1 | cpu | both | 10 | 6/4/0 | 0.7539 | 1 | -3.685e-05 | [-0.0001829, 0.0002586] | -0.0001076 / -0.0003163 | 6/4 | 0/0 |
| dose05 | cpu | global | 10 | 5/5/0 | 1 | 1 | 1.793e-05 | [-0.0002192, 0.0002471] | 0.00038 / 0.0001298 | 6/4 | 0/0 |
| dose05 | cpu | local | 10 | 6/4/0 | 0.7539 | 1 | -0.0001398 | [-0.000297, 0.0001232] | -5.359e-05 / -0.0008935 | 6/4 | 0/0 |
| dose05 | cpu | both | 10 | 5/5/0 | 1 | 1 | 5.061e-05 | [-0.0001594, 0.000294] | 0.0001713 / -0.0004934 | 4/6 | 0/0 |
| dose2 | cpu | global | 10 | 6/4/0 | 0.7539 | 1 | -0.0001759 | [-0.0005834, 0.0004012] | -0.0006295 / -0.0002554 | 5/5 | 0/0 |
| dose2 | cpu | local | 10 | 4/6/0 | 0.7539 | 1 | 6.056e-05 | [-0.000166, 0.000523] | 0.0004845 / 0.00184 | 6/4 | 0/0 |
| dose2 | cpu | both | 10 | 4/6/0 | 0.7539 | 1 | 0.0002168 | [-0.0002961, 0.0005802] | 0.0004485 / 0.002027 | 5/5 | 0/0 |
| dose4 | cpu | global | 10 | 10/0/0 | 0.001953 | 0.1172 | -0.0001732 | [-0.0005959, -5.939e-05] | -0.0002971 / 8.177e-05 | 6/4 | 0/0 |
| dose4 | cpu | local | 10 | 6/4/0 | 0.7539 | 1 | -8.451e-05 | [-0.0006553, 0.0002348] | 8.789e-05 / -0.001363 | 8/2 | 0/0 |
| dose4 | cpu | both | 10 | 7/3/0 | 0.3438 | 1 | -0.0003021 | [-0.0006043, 0.0001276] | -0.0003761 / 8.73e-05 | 8/2 | 0/0 |
| outmodel | cpu | global | 10 | 4/6/0 | 0.7539 | 1 | 2.434e-05 | [-6.217e-05, 7.409e-05] | 6.883e-05 / 0.001109 | 4/6 | 0/0 |
| outmodel | cpu | local | 10 | 7/3/0 | 0.3438 | 1 | -4.171e-05 | [-0.0001468, 1.617e-05] | -1.734e-05 / -0.001247 | 6/4 | 0/0 |
| outmodel | cpu | both | 10 | 5/5/0 | 1 | 1 | -1.854e-05 | [-0.0001602, 3.899e-05] | -0.0001074 / -0.0004884 | 6/4 | 0/0 |
| nonsquare | cpu | global | 10 | 9/1/0 | 0.02148 | 1 | -0.0003181 | [-0.000669, -8.107e-05] | -0.0005767 / -0.002693 | 4/6 | 0/0 |
| nonsquare | cpu | local | 10 | 6/4/0 | 0.7539 | 1 | -0.0001766 | [-0.0004379, 0.0002315] | 3.643e-05 / -0.001457 | 6/4 | 0/0 |
| nonsquare | cpu | both | 10 | 6/4/0 | 0.7539 | 1 | -0.0003327 | [-0.0007371, 0.0001112] | -0.0002681 / -0.001005 | 3/7 | 0/0 |
| pedestal32 | cuda | global | 10 | 10/0/0 | 0.001953 | 0.1172 | -0.7455 | [-0.8157, -0.5692] | -0.9856 / -1.502 | 10/0 | 0/0 |
| pedestal32 | cuda | local | 10 | 8/2/0 | 0.1094 | 1 | -0.5332 | [-0.6963, -0.1065] | -0.9108 / -1.627 | 7/3 | 0/0 |
| pedestal32 | cuda | both | 10 | 10/0/0 | 0.001953 | 0.1172 | -1.272 | [-1.382, -1.087] | -2.041 / -3.189 | 10/0 | 1/0 |
| pedestal0 | cuda | global | 10 | 3/7/0 | 0.3438 | 1 | 4.48e-08 | [-8.918e-08, 1.898e-07] | -2.837e-07 / -4.583e-07 | 6/4 | 0/0 |
| pedestal0 | cuda | local | 10 | 4/6/0 | 0.7539 | 1 | 7.747e-08 | [-5.087e-08, 1.527e-07] | 2.427e-07 / 3.353e-07 | 5/5 | 0/0 |
| pedestal0 | cuda | both | 10 | 5/5/0 | 1 | 1 | 1.573e-08 | [-8.468e-08, 2.751e-07] | -3.073e-07 / -9.059e-09 | 4/6 | 0/0 |
| contrast025 | cuda | global | 10 | 5/5/0 | 1 | 1 | 0.000179 | [-0.004793, 0.003012] | -0.005796 / -0.01355 | 6/4 | 0/0 |
| contrast025 | cuda | local | 10 | 3/7/0 | 0.3438 | 1 | 0.002747 | [-0.0008453, 0.005196] | 0.008444 / -0.0168 | 9/1 | 0/0 |
| contrast025 | cuda | both | 10 | 4/6/0 | 0.7539 | 1 | 0.001797 | [-0.0019, 0.004458] | 0.0005121 / -0.01616 | 7/3 | 0/0 |
| contrast4 | cuda | global | 10 | 3/7/0 | 0.3438 | 1 | 1.119e-06 | [-5.089e-06, 1.935e-05] | 1.215e-05 / 6.356e-05 | 8/2 | 0/0 |
| contrast4 | cuda | local | 10 | 7/3/0 | 0.3438 | 1 | -4.791e-06 | [-3.124e-05, 1.721e-05] | -1.404e-05 / -8.522e-05 | 7/3 | 0/0 |
| contrast4 | cuda | both | 10 | 5/5/0 | 1 | 1 | 3.259e-06 | [-3.394e-05, 2.958e-05] | 4.29e-06 / -4.075e-05 | 7/3 | 0/0 |
| dose1 | cuda | global | 10 | 5/5/0 | 1 | 1 | 1.019e-05 | [-0.0003563, 0.000167] | 0.0001141 / 0.0001388 | 4/6 | 0/0 |
| dose1 | cuda | local | 10 | 2/8/0 | 0.1094 | 1 | 0.0002477 | [-1.465e-05, 0.0006194] | 0.0006977 / 0.0005349 | 5/5 | 0/0 |
| dose1 | cuda | both | 10 | 4/6/0 | 0.7539 | 1 | 0.0001564 | [-0.0001445, 0.0005684] | 0.0005277 / -0.0004735 | 3/7 | 0/0 |
| dose05 | cuda | global | 10 | 4/6/0 | 0.7539 | 1 | 0.0002912 | [-0.000309, 0.0005001] | -0.0002057 / 0.0001609 | 4/6 | 0/0 |
| dose05 | cuda | local | 10 | 7/3/0 | 0.3438 | 1 | -0.0002578 | [-0.0004778, 0.00023] | -0.0004615 / -0.0005393 | 5/5 | 0/0 |
| dose05 | cuda | both | 10 | 4/6/0 | 0.7539 | 1 | 0.0001179 | [-0.0004145, 0.0004471] | 2.414e-05 / 4.033e-05 | 3/7 | 0/0 |
| dose2 | cuda | global | 10 | 5/5/0 | 1 | 1 | 0.0001111 | [-0.0002686, 0.0004759] | -1.86e-05 / -0.0001849 | 7/3 | 0/0 |
| dose2 | cuda | local | 10 | 2/8/0 | 0.1094 | 1 | 0.0002641 | [2.793e-05, 0.0005311] | 0.000534 / 0.001802 | 5/5 | 0/0 |
| dose2 | cuda | both | 10 | 2/8/0 | 0.1094 | 1 | 0.0003513 | [5.242e-05, 0.0007269] | 0.0006603 / 0.001674 | 6/4 | 0/0 |
| dose4 | cuda | global | 10 | 4/6/0 | 0.7539 | 1 | 7.701e-05 | [-0.0002385, 0.0003317] | 8.81e-05 / 0.0003046 | 7/3 | 0/0 |
| dose4 | cuda | local | 10 | 4/6/0 | 0.7539 | 1 | 0.0001846 | [-0.0001403, 0.000661] | 0.0004679 / 0.001419 | 4/6 | 0/0 |
| dose4 | cuda | both | 10 | 5/5/0 | 1 | 1 | 9.086e-05 | [-0.0001902, 0.000546] | 0.0004451 / 0.001648 | 6/4 | 0/0 |
| outmodel | cuda | global | 10 | 1/9/0 | 0.02148 | 1 | 2.358e-05 | [1.213e-05, 9.615e-05] | 0.0001245 / 0.0001013 | 7/3 | 0/0 |
| outmodel | cuda | local | 10 | 8/2/0 | 0.1094 | 1 | -0.000119 | [-0.0001563, 4.073e-05] | -0.0001824 / -0.0007846 | 8/2 | 0/0 |
| outmodel | cuda | both | 10 | 7/3/0 | 0.3438 | 1 | -9.39e-05 | [-0.0001476, 3.826e-05] | -0.0001162 / -0.0006882 | 10/0 | 0/0 |
| nonsquare | cuda | global | 10 | 7/3/0 | 0.3438 | 1 | -0.00023 | [-0.0003882, 0.0002055] | -0.0008638 / -0.0004307 | 3/7 | 0/0 |
| nonsquare | cuda | local | 10 | 7/3/0 | 0.3438 | 1 | -5.841e-05 | [-0.0002841, 0.0004936] | -0.0002275 / -8.762e-06 | 5/5 | 0/0 |
| nonsquare | cuda | both | 10 | 5/5/0 | 1 | 1 | -8.643e-05 | [-0.0003317, 0.0004299] | -0.0004204 / -0.001088 | 2/8 | 0/0 |

### Material harms in Tier B (1 seed entries; also in tierB_material_harms.csv)

| id | arm | reasons | rms none -> arm | p95 none -> arm | max none -> arm |
|---|---|---|---|---|---|
| B-nonsquare-s09-cuda-local | local | limit_cross:p95 | 0.2043 -> 0.2053 | 0.3992 -> 0.401 | 0.7523 -> 0.7573 |

Existing regression rule: 965 entries (all in tierB_regressions_all.csv). Material harm is a subset by construction only for limit crossings; see protocol.

## Tier C (no truth): change vs none, convergence, CPU/CUDA agreement

Graded: CPU 408, CUDA 111 records; 102 configs from 51 movies / 10 families; CUDA present for 28 configs (27 with all four arms).

| backend | arm | metric | movies | configs | median | boot95 | max | configs / movies >= 0.1 |
|---|---|---|---:|---:|---:|---|---:|---|
| cpu | global | relative_rmse | 51 | 102 | 0.04286 | [0.02399, 0.08089] | 1.25 | 21 / 17 |
| cpu | global | global_rms_px | 51 | 102 | 0.02003 | [0.01622, 0.03055] | 74.69 |  |
| cpu | local | relative_rmse | 51 | 102 | 0.01125 | [0.006443, 0.02402] | 0.6874 | 16 / 14 |
| cpu | local | global_rms_px | 51 | 102 | 0 | [0, 0] | 0 |  |
| cpu | both | relative_rmse | 51 | 102 | 0.0377 | [0.02156, 0.06189] | 1.25 | 19 / 16 |
| cpu | both | global_rms_px | 51 | 102 | 0.02003 | [0.01622, 0.03055] | 74.69 |  |
| cuda | global | relative_rmse | 14 | 28 | 0.14 | [0.06855, 0.4218] | 1.25 | 13 / 9 |
| cuda | global | global_rms_px | 14 | 28 | 0.04631 | [0.02606, 0.05593] | 81.16 |  |
| cuda | local | relative_rmse | 14 | 28 | 0.1301 | [0.0365, 0.3113] | 0.5096 | 11 / 9 |
| cuda | local | global_rms_px | 14 | 28 | 0 | [0, 0] | 0 |  |
| cuda | both | relative_rmse | 14 | 27 | 0.1514 | [0.0939, 0.3262] | 1.25 | 14 / 11 |
| cuda | both | global_rms_px | 14 | 27 | 0.04631 | [0.02366, 0.05593] | 81.16 |  |

### Convergence change vs none (config-paired; sign test shown, not in any family)

| backend | arm | matched | fixed | new | both nonconv | ambiguous/error | unmatched | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cpu | global | 102 | 0 | 0 | 4 | 0 | 0 | 1 |
| cpu | local | 102 | 0 | 0 | 4 | 0 | 0 | 1 |
| cpu | both | 102 | 0 | 0 | 4 | 0 | 0 | 1 |
| cuda | global | 28 | 0 | 0 | 2 | 0 | 74 | 1 |
| cuda | local | 28 | 0 | 0 | 2 | 0 | 74 | 1 |
| cuda | both | 27 | 0 | 0 | 2 | 0 | 75 | 1 |

### CPU/CUDA agreement (relative image RMSE, separate axis)

| arm | movies | configs | median | boot95 | max | configs >= 0.1 | strict backend gate exit 0 (of present) |
|---|---:|---:|---:|---|---:|---:|---|
| none | 14 | 28 | 0.1052 | [0.03826, 0.264] | 1.251 | 12 | 0 / 28 |
| global | 14 | 28 | 0.06746 | [0.02643, 0.3459] | 0.5613 | 7 | 0 / 28 |
| local | 14 | 28 | 0.04995 | [0.0176, 0.2759] | 1.251 | 8 | 0 / 28 |
| both | 14 | 27 | 0.0001498 | [0.0001355, 0.000229] | 0.0004588 | 0 | 0 / 27 |

#### Primary Tier C family: agreement of arm minus none (per movie; negative = closer CPU/CUDA agreement)

| arm | movies | closer/further/tie | raw p | Holm p (3) | median delta | boot95 |
|---|---:|---|---:|---:|---:|---|
| global | 14 | 9/5/0 | 0.424 | 0.424 | -0.02349 | [-0.1306, 0.1572] |
| local | 14 | 9/3/2 | 0.146 | 0.292 | -0.009932 | [-0.02222, 0] |
| both | 14 | 14/0/0 | 0.0001221 | 0.0003662 | -0.1115 | [-0.2637, -0.03812] |

Post-hoc caveat (not in the declared family): matched movies come from few datasets, and movies of one dataset are not independent. Per-family closer/further/tie: global {'e10216': [8, 2, 0], 'e12963': [1, 3, 0]}; local {'e10216': [5, 3, 2], 'e12963': [4, 0, 0]}; both {'e10216': [10, 0, 0], 'e12963': [4, 0, 0]}.

## Incomplete or unmatched

| tier | backend | arm | expected | present/graded | never run | orphan | other |
|---|---|---|---:|---:|---:|---:|---:|
| C | cpu | both | 102 | 102 | 0 | 0 | 0 |
| C | cpu | global | 102 | 102 | 0 | 0 | 0 |
| C | cpu | local | 102 | 102 | 0 | 0 | 0 |
| C | cpu | none | 102 | 102 | 0 | 0 | 0 |
| C | cuda | both | 102 | 27 | 74 | 1 | 0 |
| C | cuda | global | 102 | 28 | 74 | 0 | 0 |
| C | cuda | local | 102 | 28 | 74 | 0 | 0 |
| C | cuda | none | 102 | 28 | 74 | 0 | 0 |
| B | cpu | both | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cpu | global | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cpu | local | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cpu | none | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cuda | both | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cuda | global | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cuda | local | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |
| B | cuda | none | 100 | 100 present / 100 evaluated | 0 | 0 | 0 |

Tier C configs without a CPU/CUDA comparison per arm: {'none': 74, 'global': 74, 'local': 74, 'both': 75} of 102 (names in RESULTS.json).
