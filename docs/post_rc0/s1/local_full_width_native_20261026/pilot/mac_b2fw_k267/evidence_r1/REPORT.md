# B2FW K267 Mac experiment: results

32/32 producers exited 0; no retries. The frozen prediction and plain OFF base (DC arm none, no coupled peak) apply, distinct from the earlier UP base. Unchanged v3 `field_metrics_bound` scores runtime and STAR using pinned truth, geometry and ROI. The custom driver validates receipts, staged inputs, publication inventory, DC-none environment and witnesses; the v3 producer admission layer for the earlier coupled/DC-both pilot does not describe these arms and was not used. The Mac driver has not been independently reviewed.

## Frozen K predictions

- **K1 SUPPORTED:** zero passes in every arm; integer/fractional are identical across arms, and flat/repeated are UNIDENTIFIABLE. Integer/fractional fail the raw accuracy limits on this plain base; K1 predicts equality, not accuracy.
- **K2 SUPPORTED:** noisy B2FW improves all three metrics against OFF on runtime and STAR, but still fails all three raw limits.
- **K3 NOT SUPPORTED:** affine B2FW passes and improves all three metrics versus FW; pedestal B2FW equals FW but both fail all three limits, so the required pedestal pass is false.

The unchanged comparator returned IDENTICAL for all 15 global-only OFF versus B2/FW/B2FW comparisons. Runtime and case STAR are raw-byte equal within each such pair. The earlier pilot zero FAIL is untouched. Each 3×3 FW/B2FW log has nine exact `x_norm = 42, pnx = 42, nfx = 22` witnesses; all other arms/cases have none. Global runtime trajectories and serialized global blocks match OFF within every case.

## Runtime and STAR fields

RMS/p95/max Å; unchanged limits .20/.40/.80. Flat/repeated are UNIDENTIFIABLE; FAIL denotes raw distances only.

| Case | Arm | Runtime | Gate | STAR | Gate |
|---|---|---|---|---|---|
| noisy | OFF | 3.003762/6.359308/19.833258 | FAIL | 3.003768/6.359313/19.833325 | FAIL |
| noisy | B2 | 5.035883/9.911937/40.577373 | FAIL | 5.035882/9.912065/40.577380 | FAIL |
| noisy | FW | 0.912636/1.791501/3.652432 | FAIL | 0.912609/1.791479/3.652345 | FAIL |
| noisy | B2FW | 0.683857/1.245751/2.828689 | FAIL | 0.683846/1.245756/2.828637 | FAIL |
| affine | OFF | 0.288847/0.487553/0.877361 | FAIL | 0.288855/0.487550/0.877437 | FAIL |
| affine | B2 | 0.225973/0.454631/0.866072 | FAIL | 0.225962/0.454625/0.866022 | FAIL |
| affine | FW | 0.184131/0.358798/0.603752 | PASS | 0.184132/0.358813/0.603826 | PASS |
| affine | B2FW | 0.143303/0.247821/0.596656 | PASS | 0.143301/0.247807/0.596594 | PASS |
| pedestal | OFF | 2.119133/3.603757/3.893113 | FAIL | 2.119133/3.603757/3.893113 | FAIL |
| pedestal | B2 | 2.119133/3.603757/3.893113 | FAIL | 2.119133/3.603757/3.893113 | FAIL |
| pedestal | FW | 2.119133/3.603757/3.893113 | FAIL | 2.119133/3.603757/3.893113 | FAIL |
| pedestal | B2FW | 2.119133/3.603757/3.893113 | FAIL | 2.119133/3.603757/3.893113 | FAIL |
| zero | OFF | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| zero | B2 | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| zero | FW | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| zero | B2FW | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| integer | OFF | 0.366051/0.541240/0.541240 | FAIL | 0.366050/0.541237/0.541237 | FAIL |
| integer | B2 | 0.366051/0.541240/0.541240 | FAIL | 0.366050/0.541237/0.541237 | FAIL |
| integer | FW | 0.366051/0.541240/0.541240 | FAIL | 0.366050/0.541237/0.541237 | FAIL |
| integer | B2FW | 0.366051/0.541240/0.541240 | FAIL | 0.366050/0.541237/0.541237 | FAIL |
| fractional | OFF | 0.507011/0.824971/0.824971 | FAIL | 0.507011/0.824971/0.824971 | FAIL |
| fractional | B2 | 0.507011/0.824971/0.824971 | FAIL | 0.507011/0.824971/0.824971 | FAIL |
| fractional | FW | 0.507011/0.824971/0.824971 | FAIL | 0.507011/0.824971/0.824971 | FAIL |
| fractional | B2FW | 0.507011/0.824971/0.824971 | FAIL | 0.507011/0.824971/0.824971 | FAIL |
| flat | OFF | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| flat | B2 | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| flat | FW | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| flat | B2FW | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| repeated | OFF | 16.533858/28.003916/28.003916 | FAIL | 16.533858/28.003916/28.003916 | FAIL |
| repeated | B2 | 16.533858/28.003916/28.003916 | FAIL | 16.533858/28.003916/28.003916 | FAIL |
| repeated | FW | 16.533858/28.003916/28.003916 | FAIL | 16.533858/28.003916/28.003916 | FAIL |
| repeated | B2FW | 16.533858/28.003916/28.003916 | FAIL | 16.533858/28.003916/28.003916 | FAIL |

## Noisy patch acceptance and B2 regression

| Arm | Included patches | Logged converged | Excluded centers |
|---|---:|---:|---|
| OFF | 7/9 | 7/9 | (104, 15), (104, 47) |
| B2 | 7/9 | 7/9 | (104, 15), (104, 47) |
| FW | 9/9 | 9/9 | none |
| B2FW | 9/9 | 9/9 | none |

B2 noisy regression reproduces: runtime 3.003762/6.359308/19.833258 → 5.035883/9.911937/40.577373 Å against OFF; STAR also increases on all three metrics. B2FW is 0.683857/1.245751/2.828689 Å runtime and 0.683846/1.245756/2.828637 Å STAR: better than OFF and FW on all three, but above all limits.

Pedestal logs a zero global trajectory and zero final RMSD at every patch in every arm, yet field scoring fails. This observation does not establish cause; convergence does not prove accuracy.

## Provenance

Source archive 5bcfa987 tree d1a67904bdd515bebc548f881e8889ac4a682bb2; binary SHA-256 d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546. Frozen spec SHA-256 5304253b5bcea349eb306f8972acb069b624ce050095a2b7977f11d6a3756597 was committed at 1d39f8e2 before producers. Driver verified all 33 fixture bytes and hashes and v3 tool pins. B2 flag is exactly --experimental_local_b2 as in #287 census. Arms use --j 2, OMP 2, BLAS 1, DC none, no coupled-peak flag. Canonical producer root: /private/tmp/mc-mac-pilot-20261027/b2fw-k267-r1. Occupancy, argv and environment are retained per run; no throughput or per-thread affinity claim.

Compact evidence retains receipts, scores, runtime, STAR, logs and comparator records. MRC/EPS/PDF publication bytes remain under the scratch root, hash-bound by receipts but not included here. Census R0–R4, CUDA, real data, full100, scientific acceptance and adoption are not claimed.
