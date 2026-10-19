| case | patch | S1-relevant | acceptance CPU/CUDA | iters | final traj diff px | first separation | frame: CPU pick / CUDA pick, margin CPU map / CUDA map (ulps), cand. diff px |
|---|---|---|---|---|---:|---|---|
| e10216-p5-injcpu | (1,4) |  | yes/yes | 4/5 | 0.799 | different integer peak (it 1); last RMSD 0.4827 / 0.4250 | 46: (0, -1) / (2, 3), 0 / 5, 14.07 |
| e10216-p5-injcpu | (1,5) |  | yes/yes | 5/5 | 0.115 | different integer peak (it 1) | 30: (1, 0) / (0, -1) (adj.), 3 / 2, 2.89; 36: (0, 1) / (1, 1) (adj.), 0 / 1, 1.44 |
| e10216-p5-injcpu | (2,4) |  | yes/yes | 4/4 | 0.391 | different integer peak (it 1) | 56: (1, -1) / (1, 0) (adj.), 2 / 3, 0.99 |
| e10216-p5-injcpu | (3,4) |  | yes/yes | 3/3 | 0.128 | different integer peak (it 1) | 39: (-1, 0) / (0, 0) (adj.), 2 / 0, 0.65 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-injcpu | (4,1) |  | yes/yes | 4/4 | 0.103 | different integer peak (it 1) | 50: (0, -1) / (0, 0) (adj.), 2 / 1, 1.04 |
| e10216-p5-injcpu | (4,3) |  | no/no | 5/5 | 0.591 | same integer peak, subpixel (it 2) | 1: same peak (0, -1), 0.57 |
| e10216-p5-injcpu | (5,3) |  | yes/yes | 3/3 | 0.148 | different integer peak (it 1) | 52: (0, 0) / (0, -1) (adj.), 1 / 4, 0.84 |
| e12963-p5-injcpu | (2,1) |  | yes/yes | 3/3 | 0.738 | same integer peak, subpixel (it 1) | 12: same peak (0, 0), 0.60 |
| e12963-p5-injcpu | (2,2) |  | no/no | 5/5 | 4.952 | different integer peak (it 3) | 24: (1, 0) / (2, 0) (adj.), 0 / 3, 0.71; 31: (1, 0) / (0, 0) (adj.), 2 / 0, 0.69 [CUDA-map tie]; 35: (0, 0) / (-1, 1) (adj.), 16 / 1, 5.70 |
| e12963-p5-injcpu | (2,4) |  | yes/yes | 3/3 | 0.314 | different integer peak (it 1) | 37: (-1, 0) / (-1, -1) (adj.), 8 / 10, 0.71 |
| e12963-p5-injcpu | (2,5) | **yes** | yes/yes | 4/3 | 98.385 | different integer peak (it 1); last RMSD 0.2611 / 0.3691 | 2: (0, 0) / (0, 1) (adj.), 10 / 12, 0.54; 32: (-8, 8) / (0, -1), 3 / 35, 45.62; 37: (0, -1) / (0, 0) (adj.), 9 / 9, 0.83 |
| e12963-p5-injcpu | (3,1) |  | yes/yes | 3/3 | 0.363 | different integer peak (it 2) | 28: (0, 0) / (0, -1) (adj.), 3 / 3, 1.38 |
| e12963-p5-injcpu | (3,2) | **yes** | yes/yes | 3/4 | 1.242 | mixed (it 1); last RMSD 0.4893 / 0.3594 | 12: same peak (0, 0), 0.62; 37: (0, 1) / (0, 2) (adj.), 6 / 4, 1.69 |
| e12963-p5-injcpu | (3,3) |  | yes/yes | 3/3 | 0.302 | different integer peak (it 1) | 27: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.78 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-injcpu | (3,4) |  | yes/yes | 3/3 | 0.384 | mixed (it 1) | 1: (0, 0) / (0, -1) (adj.), 1 / 8, 0.60; 5: same peak (0, 0), 0.55 |
| e12963-p5-injcpu | (3,5) |  | yes/yes | 5/5 | 0.457 | mixed (it 1) | 6: (0, 0) / (1, 0) (adj.), 0 / 1, 0.56; 9: (1, 1) / (0, 0) (adj.), 14 / 1, 1.21; 13: same peak (0, 1), 0.65; 21: (0, 0) / (-1, -12), 5 / 33, 47.07 |
| e12963-p5-injcpu | (4,1) | **yes** | no/yes | 5/4 | 1.802 | mixed (it 1); last RMSD 0.8283 / 0.4932 | 10: same peak (-1, 1), 0.73; 31: (1, 1) / (0, 2) (adj.), 1 / 3, 3.86 |
| e12963-p5-injcpu | (4,2) |  | yes/yes | 4/4 | 0.550 | same integer peak, subpixel (it 1) | 24: same peak (0, -1), 0.54 |
| e12963-p5-injcpu | (4,3) |  | yes/yes | 3/3 | 0.463 | different integer peak (it 1) | 4: (-1, 0) / (0, 0) (adj.), 0 / 1, 0.58 |
| e12963-p5-injcpu | (5,1) |  | no/no | 5/5 | 30.989 | mixed (it 1) | 22: same peak (0, 1), 0.97; 27: (0, 0) / (0, -1) (adj.), 3 / 6, 1.82; 39: same peak (0, 0), 0.56 |
| e12963-p5-injcpu | (5,2) | **yes** | yes/yes | 3/4 | 35.501 | different integer peak (it 1); last RMSD 0.3800 / 0.2277 | 8: (0, 0) / (0, -1) (adj.), 1 / 12, 0.96; 18: (0, -1) / (0, 0) (adj.), 0 / 0, 1.53 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-injcpu | (5,3) |  | yes/yes | 3/3 | 0.674 | same integer peak, subpixel (it 1) | 28: same peak (0, 0), 0.60; 37: same peak (0, -1), 0.51 |
| e12963-p5-injcpu | (5,4) | **yes** | yes/yes | 3/3 | 1.315 | mixed (it 1) | 13: (0, 0) / (-1, 1) (adj.), 0 / 9, 1.40; 20: same peak (-1, 0), 0.79; 26: same peak (-1, -1), 0.53 |
| e10216-p5-injcuda | (1,3) | **yes** | yes/yes | 4/3 | 1.332 | different integer peak (it 1); last RMSD 0.3481 / 0.4790 | 42: (-1, 0) / (0, 0) (adj.), 1 / 0, 0.65 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-injcuda | (1,4) | **yes** | yes/no | 4/5 | 13.605 | different integer peak (it 1); last RMSD 0.4829 / 2.4001 | 46: (0, -1) / (2, 3), 2 / 5, 14.08 |
| e10216-p5-injcuda | (1,5) |  | yes/yes | 5/5 | 0.383 | different integer peak (it 1) | 24: (1, 1) / (0, 0) (adj.), 1 / 2, 2.51; 30: (1, 0) / (0, -1) (adj.), 3 / 1, 2.87 |
| e10216-p5-injcuda | (2,4) |  | yes/yes | 4/4 | 0.553 | different integer peak (it 1) | 56: (1, -1) / (1, 0) (adj.), 3 / 2, 0.97 |
| e10216-p5-injcuda | (3,4) |  | yes/yes | 3/3 | 0.133 | different integer peak (it 1) | 39: (-1, 0) / (0, 0) (adj.), 2 / 0, 0.65 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-injcuda | (3,5) |  | no/no | 5/5 | 0.173 | different integer peak (it 1) | 56: (0, 2) / (0, 1) (adj.), 1 / 6, 1.41 |
| e10216-p5-injcuda | (4,1) |  | yes/yes | 4/4 | 0.116 | different integer peak (it 1) | 50: (0, -1) / (0, 0) (adj.), 6 / 0, 1.05 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-injcuda | (4,3) |  | no/no | 5/5 | 0.567 | different integer peak (it 5) | 48: (0, 1) / (0, 0) (adj.), 14 / 0, 0.59 [CUDA-map tie] |
| e10216-p5-injcuda | (5,1) |  | yes/yes | 3/3 | 0.119 | different integer peak (it 1) | 29: (1, -1) / (0, 0) (adj.), 0 / 1, 0.86 |
| e10216-p5-injcuda | (5,3) |  | yes/yes | 3/3 | 0.120 | different integer peak (it 1) | 52: (0, 0) / (0, -1) (adj.), 1 / 1, 0.87 |
| e10216-p5-injcuda | (5,4) |  | yes/yes | 3/4 | 0.545 | no frame event; RMSD either side of 0.5 px; last RMSD 0.4947 / 0.2043 |  |
| e12963-p5-injcuda | (2,1) |  | yes/yes | 3/3 | 0.700 | same integer peak, subpixel (it 1) | 12: same peak (0, 0), 0.59 |
| e12963-p5-injcuda | (2,2) |  | no/no | 5/5 | 2.771 | same integer peak, subpixel (it 1) | 2: same peak (0, -1), 0.51 |
| e12963-p5-injcuda | (2,4) |  | yes/yes | 3/3 | 0.300 | different integer peak (it 1) | 37: (-1, 0) / (-1, -1) (adj.), 9 / 10, 0.71 |
| e12963-p5-injcuda | (2,5) | **yes** | yes/yes | 4/3 | 98.435 | different integer peak (it 1); last RMSD 0.2653 / 0.3558 | 2: (0, 0) / (0, 1) (adj.), 10 / 13, 0.52; 32: (-8, 8) / (0, -1), 1 / 36, 45.63; 37: (0, -1) / (0, 0) (adj.), 9 / 9, 0.83 |
| e12963-p5-injcuda | (3,1) |  | yes/yes | 3/3 | 0.380 | different integer peak (it 2) | 28: (0, 0) / (0, -1) (adj.), 2 / 6, 1.34 |
| e12963-p5-injcuda | (3,2) |  | yes/yes | 3/4 | 0.994 | mixed (it 1); last RMSD 0.4773 / 0.3720 | 12: same peak (0, 0), 0.64; 37: (0, 1) / (0, 2) (adj.), 8 / 1, 1.57 |
| e12963-p5-injcuda | (3,3) |  | yes/yes | 3/3 | 0.306 | different integer peak (it 1) | 27: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.79 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-injcuda | (3,4) |  | yes/yes | 3/3 | 0.372 | mixed (it 1) | 3: (-1, 0) / (0, 0) (adj.), 1 / 0, 1.25 [CUDA-map tie; CPU rule would match CPU]; 5: same peak (0, 0), 0.56 |
| e12963-p5-injcuda | (3,5) |  | yes/yes | 5/5 | 0.482 | mixed (it 1) | 13: same peak (0, 1), 0.62; 21: (0, 0) / (-1, -12), 4 / 36, 47.10 |
| e12963-p5-injcuda | (4,1) | **yes** | no/yes | 5/4 | 1.130 | mixed (it 1); last RMSD 0.7515 / 0.4680 | 10: same peak (-1, 1), 0.78; 24: same peak (0, 0), 0.52; 31: (1, 1) / (0, 2) (adj.), 2 / 2, 3.75 |
| e12963-p5-injcuda | (4,2) |  | yes/yes | 4/4 | 0.554 | same integer peak, subpixel (it 1) | 18: same peak (-1, -1), 0.57; 24: same peak (0, -1), 0.59 |
| e12963-p5-injcuda | (4,3) |  | yes/yes | 3/3 | 0.494 | different integer peak (it 1) | 4: (-1, 0) / (0, 0) (adj.), 1 / 1, 0.70 |
| e12963-p5-injcuda | (5,1) |  | no/no | 5/5 | 30.958 | mixed (it 1) | 22: same peak (0, 1), 0.95; 27: (0, 0) / (0, -1) (adj.), 3 / 7, 1.85; 39: same peak (0, 0), 0.57 |
| e12963-p5-injcuda | (5,2) | **yes** | yes/yes | 3/4 | 35.325 | different integer peak (it 1); last RMSD 0.3681 / 0.2486 | 8: (0, 0) / (0, -1) (adj.), 1 / 12, 0.92 |
| e12963-p5-injcuda | (5,3) |  | yes/yes | 3/3 | 0.772 | same integer peak, subpixel (it 1) | 28: same peak (0, 0), 0.65 |
| e12963-p5-injcuda | (5,4) | **yes** | yes/yes | 4/3 | 1.499 | mixed (it 1); last RMSD 0.3065 / 0.4918 | 13: (0, 0) / (-1, 1) (adj.), 0 / 10, 1.44; 20: same peak (-1, 0), 0.79; 26: (0, 0) / (-1, -1) (adj.), 1 / 11, 2.04 |
