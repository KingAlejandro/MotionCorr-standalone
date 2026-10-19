| case | patch | S1-relevant | acceptance CPU/CUDA | iters | final traj diff px | first separation | frame: CPU pick / CUDA pick, margin CPU map / CUDA map (ulps), cand. diff px |
|---|---|---|---|---|---:|---|---|
| e10216-p3 | (1,1) |  | yes/yes | 4/4 | 0.314 | different integer peak (it 1) | 1: (1, 0) / (0, 1) (adj.), 1 / 3, 1.60 |
| e10216-p3 | (2,1) | **yes** | yes/yes | 3/4 | 1.132 | different integer peak (it 2); last RMSD 0.2513 / 0.2253 | 1: (0, 1) / (0, 2) (adj.), 3 / 4, 1.79 |
| e10216-p3 | (2,3) |  | yes/yes | 3/2 | 0.381 | no frame event; RMSD either side of 0.5 px; last RMSD 0.1665 / 0.4996 |  |
| e10216-p5 | (1,4) | **yes** | yes/no | 4/5 | 13.590 | different integer peak (it 1); last RMSD 0.4827 / 2.4001 | 46: (0, -1) / (2, 3), 0 / 5, 14.06 |
| e10216-p5 | (1,5) |  | yes/yes | 5/5 | 0.538 | different integer peak (it 1) | 24: (1, 1) / (0, 0) (adj.), 1 / 2, 2.50; 30: (1, 0) / (0, -1) (adj.), 3 / 1, 2.89; 36: (0, 1) / (1, 1) (adj.), 0 / 0, 1.49 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5 | (2,4) |  | yes/yes | 4/4 | 0.523 | different integer peak (it 1) | 56: (1, -1) / (1, 0) (adj.), 2 / 2, 0.99 |
| e10216-p5 | (3,4) |  | yes/yes | 3/3 | 0.145 | different integer peak (it 1) | 39: (-1, 0) / (0, 0) (adj.), 2 / 0, 0.66 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5 | (4,1) |  | yes/yes | 4/4 | 0.100 | different integer peak (it 1) | 50: (0, -1) / (0, 0) (adj.), 2 / 0, 1.06 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5 | (4,3) |  | no/no | 5/5 | 0.574 | same integer peak, subpixel (it 2) | 1: same peak (0, -1), 0.57 |
| e10216-p5 | (5,1) |  | yes/yes | 3/3 | 0.144 | different integer peak (it 1) | 29: (1, -1) / (0, 0) (adj.), 2 / 1, 0.87 |
| e10216-p5 | (5,3) |  | yes/yes | 3/3 | 0.121 | different integer peak (it 1) | 52: (0, 0) / (0, -1) (adj.), 1 / 1, 0.85 |
| e12963-p5 | (2,1) |  | yes/yes | 3/3 | 0.720 | same integer peak, subpixel (it 1) | 12: same peak (0, 0), 0.59 |
| e12963-p5 | (2,2) |  | no/no | 5/5 | 2.816 | different integer peak (it 3) | 24: (1, 0) / (2, 0) (adj.), 0 / 4, 0.83 |
| e12963-p5 | (2,4) |  | yes/yes | 3/3 | 0.292 | different integer peak (it 1) | 37: (-1, 0) / (-1, -1) (adj.), 8 / 10, 0.70 |
| e12963-p5 | (2,5) | **yes** | yes/yes | 4/3 | 98.400 | different integer peak (it 1); last RMSD 0.2611 / 0.3558 | 2: (0, 0) / (0, 1) (adj.), 10 / 13, 0.52; 32: (-8, 8) / (0, -1), 3 / 36, 45.61; 37: (0, -1) / (0, 0) (adj.), 9 / 9, 0.83 |
| e12963-p5 | (3,1) |  | yes/yes | 3/3 | 0.409 | different integer peak (it 2) | 28: (0, 0) / (0, -1) (adj.), 3 / 6, 1.40 |
| e12963-p5 | (3,2) | **yes** | yes/yes | 3/4 | 1.102 | mixed (it 1); last RMSD 0.4893 / 0.3720 | 12: same peak (0, 0), 0.66; 37: (0, 1) / (0, 2) (adj.), 6 / 1, 1.50 |
| e12963-p5 | (3,3) |  | yes/yes | 3/3 | 0.325 | different integer peak (it 1) | 27: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.79 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5 | (3,4) |  | yes/yes | 3/3 | 0.404 | mixed (it 1) | 1: (0, 0) / (0, -1) (adj.), 1 / 8, 0.60; 3: (-1, 0) / (0, 0) (adj.), 0 / 0, 1.25 [CUDA-map tie; CPU rule would match CPU]; 5: same peak (0, 0), 0.58 |
| e12963-p5 | (3,5) |  | yes/yes | 5/5 | 0.419 | mixed (it 1) | 6: (0, 0) / (1, 0) (adj.), 0 / 2, 0.59; 13: same peak (0, 1), 0.58; 21: (0, 0) / (-1, -12), 5 / 36, 47.10 |
| e12963-p5 | (4,1) | **yes** | no/yes | 5/4 | 1.670 | mixed (it 1); last RMSD 0.8283 / 0.4680 | 10: same peak (-1, 1), 0.82; 24: same peak (0, 0), 0.51; 31: (1, 1) / (0, 2) (adj.), 1 / 2, 3.78 |
| e12963-p5 | (4,2) |  | yes/yes | 4/4 | 0.564 | same integer peak, subpixel (it 1) | 18: same peak (-1, -1), 0.57; 24: same peak (0, -1), 0.62 |
| e12963-p5 | (4,3) |  | yes/yes | 3/3 | 0.482 | different integer peak (it 1) | 4: (-1, 0) / (0, 0) (adj.), 0 / 1, 0.65 |
| e12963-p5 | (5,1) |  | no/no | 5/5 | 31.015 | mixed (it 1) | 22: same peak (0, 1), 1.03; 27: (0, 0) / (0, -1) (adj.), 3 / 7, 1.86; 39: same peak (0, 0), 0.54 |
| e12963-p5 | (5,2) | **yes** | yes/yes | 3/4 | 35.326 | different integer peak (it 1); last RMSD 0.3800 / 0.2486 | 8: (0, 0) / (0, -1) (adj.), 1 / 12, 0.91 |
| e12963-p5 | (5,3) |  | yes/yes | 3/3 | 0.713 | same integer peak, subpixel (it 1) | 28: same peak (0, 0), 0.54 |
| e12963-p5 | (5,4) | **yes** | yes/yes | 3/3 | 1.267 | mixed (it 1) | 13: (0, 0) / (-1, 1) (adj.), 0 / 10, 1.43; 20: same peak (-1, 0), 0.79; 26: same peak (-1, -1), 0.55 |
| e10474f3-p5 | (1,1) |  | no/no | 5/5 | 0.277 | same integer peak, subpixel (it 3) | 6: same peak (0, 1), 0.68 |
| e10474f3-p5 | (1,2) | **yes** | no/yes | 5/5 | 0.483 | different integer peak (it 3) | 6: (0, 0) / (0, 2), 0 / 68, 5.91 |
| e10474f3-p5 | (1,3) |  | no/no | 5/5 | 0.611 | same integer peak, subpixel (it 3) | 6: same peak (2, 3), 0.76 |
| e10474f3-p5 | (1,4) |  | no/no | 5/5 | 0.972 | different integer peak (it 1) | 55: (0, -1) / (0, 0) (adj.), 14 / 0, 1.13 [CUDA-map tie; CPU rule would match CPU] |
| e10474f3-p5 | (1,5) |  | no/no | 5/5 | 0.792 | mixed (it 4) | 4: (0, 4) / (0, 3) (adj.), 4 / 24, 1.74; 6: same peak (2, 0), 0.62; 12: (0, 1) / (0, 0) (adj.), 15 / 28, 0.82 |
| e10641b-p5 | (1,5) |  | no/no | 5/5 | 0.112 | different integer peak (it 3) | 62: (-1, 0) / (0, 0) (adj.), 0 / 1, 0.55 |
| e10641b-p5 | (3,2) |  | yes/yes | 4/4 | 0.157 | different integer peak (it 2) | 32: (-1, 0) / (0, 0) (adj.), 1 / 0, 0.70 [CUDA-map tie; CPU rule would match CPU] |
| e10641b-p5 | (3,4) |  | no/no | 5/5 | 0.442 | different integer peak (it 2) | 61: (0, 1) / (0, 0) (adj.), 3 / 1, 0.55 |
| e10641b-p5 | (4,1) |  | no/no | 5/5 | 1.986 | different integer peak (it 1) | 38: (0, 0) / (-1, 1) (adj.), 1 / 1, 2.45 |
| e10641b-p5 | (4,3) |  | no/no | 5/5 | 0.517 | different integer peak (it 2) | 38: (0, 0) / (1, 0) (adj.), 2 / 2, 1.12; 68: (0, -1) / (0, 0) (adj.), 1 / 5, 1.59 |
| e10641b-p5 | (4,5) |  | no/no | 5/5 | 0.379 | different integer peak (it 3) | 57: (0, 0) / (0, 1) (adj.), 2 / 2, 1.84 |
| e10641b-p5 | (5,2) | **yes** | no/yes | 5/5 | 0.500 | different integer peak (it 1) | 41: (0, 0) / (-1, 1) (adj.), 0 / 1, 4.33 |
| e10641b-p5 | (5,3) |  | no/no | 5/5 | 5.645 | different integer peak (it 1) | 62: (-1, -1) / (0, 0) (adj.), 2 / 0, 4.06 [CUDA-map tie; CPU rule would match CPU] |
