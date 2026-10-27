# ALL K267 Mac experiment: results

All eight new ALL producers exited 0; no producer was retried. The six retained comparator arms were verified against their committed receipts, scored metadata and publication hashes before launch and were not rerun. ALL uses DC both, coupled peak all, --experimental_local_b2 and --experimental_local_full_width_weight; --j 2 and OMP 2.

## Frozen predictions

- **A1 SUPPORTED:** zero, integer, fractional, affine and pedestal pass on both fields.
- **A2 SUPPORTED:** noisy improves RMS, p95 and max against plain OFF on both fields, but ALL fails all three raw accuracy limits.
- **A3 SUPPORTED:** flat/repeated remain UNIDENTIFIABLE; integer and fractional match retained UPFW via the unchanged product comparator and raw runtime/STAR byte comparisons.

The earlier B2FW K3 failure and zero-pair comparator FAIL remain recorded. All three 3×3 ALL runs have nine exact local full-width witnesses; global-only runs have none. Global full-precision trajectories and serialized STAR blocks match UPFW in all cases; DC/coupled manipulation counters are recorded in the per-run facts.

## ALL field scores

RMS/p95/max Å; limits .20/.40/.80. Flat/repeated are UNIDENTIFIABLE; their raw distance checks fail.

| Case | Runtime | Gate | STAR | Gate |
|---|---|---|---|---|
| noisy | 0.824849/1.651998/3.216749 | FAIL | 0.824817/1.651998/3.216770 | FAIL |
| affine | 0.065407/0.140854/0.330747 | PASS | 0.065412/0.140890/0.330761 | PASS |
| pedestal | 0.065361/0.140789/0.330672 | PASS | 0.065358/0.140739/0.330686 | PASS |
| zero | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| integer | 0.075078/0.117348/0.117348 | PASS | 0.075078/0.117346/0.117346 | PASS |
| fractional | 0.029718/0.048277/0.048277 | PASS | 0.029716/0.048273/0.048273 | PASS |
| flat | 2.104421/3.436505/3.436505 | FAIL | 2.104421/3.436505/3.436505 | FAIL |
| repeated | 9.012581/14.197954/14.197954 | FAIL | 9.012581/14.197954/14.197954 | FAIL |

## Noisy comparisons and patch inclusion

| Arm | Runtime | STAR | Included patches | Converged patches | Excluded centers |
|---|---|---|---:|---:|---|
| OFF | 3.003762/6.359308/19.833258 | 3.003768/6.359313/19.833325 | 7/9 | 7/9 | (104, 15), (104, 47) |
| UP | 1.645367/3.337282/7.284050 | 1.645381/3.337274/7.283887 | 8/9 | 8/9 | (104, 47) |
| UPFW | 1.095427/2.240219/4.469227 | 1.095414/2.240253/4.469297 | 8/9 | 8/9 | (104, 47) |
| B2FW | 0.683857/1.245751/2.828689 | 0.683846/1.245756/2.828637 | 9/9 | 9/9 | none |
| ALL | 0.824849/1.651998/3.216749 | 0.824817/1.651998/3.216770 | 8/9 | 8/9 | (104, 47) |

Noisy ALL improves on UP and UPFW but is worse on all three metrics than plain-base B2FW, on both fields. Relative to UPFW, affine and pedestal ALL each have a small max-error increase on both fields while remaining PASS:

| Case | Runtime max UPFW → ALL (Å) | STAR max UPFW → ALL (Å) |
|---|---|---|
| affine | 0.329485 → 0.330747 | 0.329476 → 0.330761 |
| pedestal | 0.330322 → 0.330672 | 0.330321 → 0.330686 |

## Provenance and limitations

Frozen spec SHA-256 e7acf6aee81ffe4865a488391f8b23b95d09267ad1bab69d9202c662c4ac75d2 committed at 731b9701 before producers. Archive 5bcfa987, binary SHA-256 d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546; all 33 fixture sizes and hashes and v3 tool pins verified. Canonical root /private/tmp/mc-mac-pilot-20261027/all-k267-r1; per-run argv, env, occupancy and publication hashes retained. Unchanged v3 `field_metrics_bound` scores runtime and STAR; custom producer receipt checks are used because the previous v3 admission rows do not include the B2 flag. This driver has not been independently reviewed.

Compact evidence retains runtime, STAR, logs, receipts, scores and comparator records; complete MRC/EPS/PDF products remain under scratch and are hash-bound by receipts. No census A4–A6, GPU, real-data, image accuracy, full100, scientific acceptance or adoption claim follows.
