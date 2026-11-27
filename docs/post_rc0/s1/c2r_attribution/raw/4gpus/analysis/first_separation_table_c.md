| case | patch | S1-relevant | acceptance CPU/CUDA | iters | final traj diff px | first separation | frame: CPU pick / CUDA pick, margin CPU map / CUDA map (ulps), cand. diff px |
|---|---|---|---|---|---:|---|---|
| e10216-p5-injcpu-herm | (1,5) |  | yes/yes | 5/5 | 0.229 | different integer peak (it 1) | 36: (0, 1) / (1, 1) (adj.), 0 / 1, 1.48 |
| e10216-p5-injcpu-herm | (3,4) |  | yes/yes | 3/3 | 0.090 | different integer peak (it 1) | 39: (-1, 0) / (0, 0) (adj.), 2 / 0, 0.65 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-injcpu-herm | (5,3) |  | yes/yes | 3/3 | 0.044 | different integer peak (it 1) | 52: (0, 0) / (0, -1) (adj.), 1 / 2, 0.84 |
| e10216-p5-injcpu-herm | (5,4) |  | yes/yes | 4/3 | 0.471 | no frame event; RMSD either side of 0.5 px; last RMSD 0.1880 / 0.4984 |  |
| e10216-p5-own-herm | (1,5) |  | yes/yes | 5/5 | 0.990 | different integer peak (it 1) | 24: (1, 1) / (0, 0) (adj.), 1 / 2, 2.50; 36: (0, 1) / (1, 1) (adj.), 0 / 0, 1.52 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-own-herm | (3,4) |  | yes/yes | 3/3 | 0.090 | different integer peak (it 1) | 39: (-1, 0) / (0, 0) (adj.), 2 / 0, 0.66 [CUDA-map tie; CPU rule would match CPU] |
| e10216-p5-own-herm | (4,3) |  | no/no | 5/5 | 0.109 | same integer peak, subpixel (it 2) | 1: same peak (0, -1), 0.57 |
| e10216-p5-own-herm | (5,5) |  | no/no | 5/5 | 0.094 | different integer peak (it 1) | 51: (0, 0) / (-1, 0) (adj.), 1 / 1, 0.51 |
| e12963-p5-injcpu-herm | (2,5) |  | yes/yes | 4/5 | 0.281 | different integer peak (it 1); last RMSD 0.2611 / 0.1676 | 32: (-8, 8) / (0, -1), 3 / 1, 45.51 |
| e12963-p5-injcpu-herm | (3,1) |  | yes/yes | 3/3 | 0.139 | different integer peak (it 1) | 35: (0, 0) / (0, 1) (adj.), 1 / 1, 1.07 |
| e12963-p5-injcpu-herm | (3,2) |  | yes/yes | 3/3 | 0.170 | different integer peak (it 1) | 2: (0, 0) / (0, 1) (adj.), 2 / 1, 0.56 |
| e12963-p5-injcpu-herm | (3,3) |  | yes/yes | 3/3 | 0.191 | different integer peak (it 1) | 27: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.84 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-injcpu-herm | (3,5) |  | yes/yes | 5/5 | 0.109 | different integer peak (it 1) | 5: (1, 0) / (1, -1) (adj.), 2 / 0, 1.86 [CUDA-map tie] |
| e12963-p5-injcpu-herm | (4,1) |  | no/no | 5/5 | 0.600 | different integer peak (it 3) | 31: (0, 0) / (0, 1) (adj.), 0 / 6, 1.60 |
| e12963-p5-injcpu-herm | (4,3) |  | yes/yes | 3/3 | 0.136 | mixed (it 1) | 4: (-1, 0) / (0, 0) (adj.), 0 / 1, 0.51; 22: same peak (-7, -13), 0.51 |
| e12963-p5-injcpu-herm | (5,1) |  | no/no | 5/5 | 0.286 | different integer peak (it 1) | 27: (0, 0) / (0, -1) (adj.), 3 / 1, 1.56 |
| e12963-p5-injcpu-herm | (5,3) |  | yes/yes | 3/3 | 0.159 | same integer peak, subpixel (it 2) | 28: same peak (0, 0), 0.56 |
| e12963-p5-injcpu-herm | (5,4) |  | yes/yes | 3/4 | 0.730 | different integer peak (it 1); last RMSD 0.4555 / 0.2511 | 13: (0, 0) / (-1, 1) (adj.), 0 / 2, 1.29; 26: (-1, -1) / (0, 0) (adj.), 0 / 1, 1.77 |
| e12963-p5-own-herm | (1,1) | **yes** | yes/yes | 3/3 | 1.916 | different integer peak (it 1) | 31: (0, 0) / (-1, 1) (adj.), 2 / 1, 5.26 |
| e12963-p5-own-herm | (3,3) |  | yes/yes | 3/3 | 0.226 | different integer peak (it 1) | 27: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.84 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-own-herm | (3,4) |  | yes/yes | 3/3 | 0.175 | different integer peak (it 1) | 3: (-1, 0) / (0, 0) (adj.), 0 / 0, 0.99 [CUDA-map tie; CPU rule would match CPU] |
| e12963-p5-own-herm | (3,5) |  | yes/yes | 5/5 | 0.100 | different integer peak (it 1) | 5: (1, 0) / (1, -1) (adj.), 2 / 0, 1.79 [CUDA-map tie] |
| e12963-p5-own-herm | (4,1) |  | no/no | 5/5 | 0.422 | different integer peak (it 3) | 31: (0, 0) / (0, 1) (adj.), 0 / 3, 1.60 |
| e12963-p5-own-herm | (4,3) |  | yes/yes | 3/3 | 0.144 | different integer peak (it 1) | 4: (-1, 0) / (0, 0) (adj.), 0 / 1, 0.52 |
| e12963-p5-own-herm | (5,1) | **yes** | no/yes | 5/4 | 30.558 | different integer peak (it 1); last RMSD 4.9400 / 0.4477 | 27: (0, 0) / (0, -1) (adj.), 3 / 1, 1.55 |
| e12963-p5-own-herm | (5,4) |  | yes/yes | 3/3 | 0.307 | different integer peak (it 1) | 13: (0, 0) / (-1, 1) (adj.), 0 / 3, 1.33 |
