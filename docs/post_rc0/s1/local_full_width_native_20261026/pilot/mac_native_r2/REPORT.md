# Mac pilot: canonical continuation results

Eight continuation producers exited 0 and passed v3 admission and scoring; integer, fractional, flat and repeated OFF/ON product comparisons each returned IDENTICAL under the unchanged comparator. Together with the eight retained r1 producers, all 16 frozen runs are scored; none was retried. The r1 zero comparator result stays **FAIL**, and the full pilot therefore retains a product compatibility failure. Both r1 and r2 full output trees remain under `/private/tmp/mc-mac-pilot-20261027/`; committed receipts bind their inventories, but compact evidence excludes MRC/EPS/PDF bytes.

## Field metrics

RMS/p95/max Å; gates 0.20/0.40/0.80. Flat and repeated are UNIDENTIFIABLE: FAIL denotes raw numerical distances, not an identifiable motion gate.

| Case | Arm | Runtime | Gate | STAR | Gate |
|---|---|---|---|---|---|
| noisy | OFF | 1.645367/3.337282/7.284050 | FAIL | 1.645381/3.337274/7.283887 | FAIL |
| noisy | ON | 1.095427/2.240219/4.469227 | FAIL | 1.095414/2.240253/4.469297 | FAIL |
| affine | OFF | 0.117034/0.260331/0.537350 | PASS | 0.117044/0.260384/0.537400 | PASS |
| affine | ON | 0.065968/0.142185/0.329485 | PASS | 0.065960/0.142178/0.329476 | PASS |
| pedestal | OFF | 0.116819/0.259915/0.538854 | PASS | 0.116817/0.259908/0.538856 | PASS |
| pedestal | ON | 0.065948/0.142009/0.330322 | PASS | 0.065946/0.141999/0.330321 | PASS |
| zero | OFF | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| zero | ON | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| integer | OFF | 0.075078/0.117348/0.117348 | PASS | 0.075078/0.117346/0.117346 | PASS |
| integer | ON | 0.075078/0.117348/0.117348 | PASS | 0.075078/0.117346/0.117346 | PASS |
| fractional | OFF | 0.029718/0.048277/0.048277 | PASS | 0.029716/0.048273/0.048273 | PASS |
| fractional | ON | 0.029718/0.048277/0.048277 | PASS | 0.029716/0.048273/0.048273 | PASS |
| flat | OFF | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| flat | ON | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| repeated | OFF | 9.012581/14.197954/14.197954 | FAIL | 9.012581/14.197954/14.197954 | FAIL |
| repeated | ON | 9.012581/14.197954/14.197954 | FAIL | 9.012581/14.197954/14.197954 | FAIL |

P1 five retained pass cases preserved on both fields: **SUPPORTED**. P2 noisy strictly improves every metric on both fields: **SUPPORTED**. Combined frozen prediction: **SUPPORTED**. This is a prediction result, not scientific acceptance; noisy remains FAIL against all raw limits and the r1 zero comparator FAIL remains. Flat/repeated remain UNIDENTIFIABLE with raw FAIL distances unchanged.

Field metric increases ON versus OFF: **0** across 8 cases × 2 fields × 3 metrics. Global-only runtime and case STAR are byte-equal within each pair; r2 global-only comparator gates are IDENTICAL. The r1 zero comparator is DIFFERENT and is not relabelled.

Patch-level regression: noisy excluded patch (2,3), center (104,47), final logged RMSD increased **1.589500 → 8.364200 px**. It is excluded from the local-shift block in both arms (40 rows / 8 patches), despite overall noisy field improvement. Noisy patch convergence is 8/9 in both arms; affine and pedestal 9/9 in both. Other increases in final logged patch RMSD are listed below; these are convergence increments, not truth error measures.

| Case | Patch center | OFF RMSD px | ON RMSD px |
|---|---|---:|---:|
| noisy | (62,15) | 0.365565 | 0.446857 |
| noisy | (104,47) | 1.589500 | 8.364200 |
| affine | (20,15) | 0.199388 | 0.211151 |
| affine | (62,47) | 0.023885 | 0.028900 |
| pedestal | (20,15) | 0.198998 | 0.211261 |
| pedestal | (62,47) | 0.023527 | 0.029472 |

Witness: nine exact `x_norm = 42, pnx = 42, nfx = 22` lines in each 3×3 ON run, zero in 3×3 OFF and in all global-only runs. Global full-precision trajectories, serialized global STAR blocks, global DC and coupled counters match within each pair.

## Descriptive Mac OFF and retained Linux OFF

| Case | Mac runtime | Linux runtime | Mac STAR | Linux STAR |
|---|---|---|---|---|
| noisy | 1.645367/3.337282/7.284050 | 1.645371/3.337290/7.284026 | 1.645381/3.337274/7.283887 | 1.645397/3.337279/7.283784 |
| affine | 0.117034/0.260331/0.537350 | 0.117035/0.260334/0.537360 | 0.117044/0.260384/0.537400 | 0.117040/0.260337/0.537391 |
| pedestal | 0.116819/0.259915/0.538854 | 0.116943/0.260269/0.537476 | 0.116817/0.259908/0.538856 | 0.116950/0.260288/0.537494 |
| zero | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 |
| integer | 0.075078/0.117348/0.117348 | 0.074187/0.115719/0.115719 | 0.075078/0.117346/0.117346 | 0.074187/0.115719/0.115719 |
| fractional | 0.029718/0.048277/0.048277 | 0.029714/0.048264/0.048264 | 0.029716/0.048273/0.048273 | 0.029712/0.048260/0.048260 |
| flat | 2.104421/3.436505/3.436505 | 2.104421/3.436505/3.436505 | 2.104421/3.436505/3.436505 | 2.104421/3.436505/3.436505 |
| repeated | 9.012581/14.197954/14.197954 | 9.012581/14.197954/14.197954 | 9.012581/14.197954/14.197954 | 9.012581/14.197954/14.197954 |

Mac arm64 source archive `5bcfa987`, binary SHA-256 `d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546`; fixtures all 33 pinned hashes match. Ghostscript `/opt/homebrew/bin/gs` 10.08.0 SHA-256 `d57bb373324bf7e72c5b3fb1a6cc8a9f876eb6f8d2eec23a5a3809a8a108bf9e`; producer PATH includes `/opt/homebrew/bin`. All producers used --j 2 and OMP 2. No per-thread affinity or performance claim. Disabled-effect mutant failed the local test as required. The Mac driver has not been independently reviewed. No GPU, real-data, full100, image accuracy or adoption claim.
