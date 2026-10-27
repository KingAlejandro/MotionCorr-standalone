# Mac native pilot r1: STOP at zero comparator

Eight producers (noisy, affine, pedestal, zero; OFF and ON) exited 0 and passed unchanged v3 single-run admission and field scoring. The driver stopped at zero global-only product comparison; integer, fractional, flat and repeated are UNRUN. No producer was retried. Full scratch, including published MRC/EPS/PDF bytes, remains at `/tmp/mc-mac-pilot-20261027/mac-native-r1/`; this compact package retains receipts, runtime, STAR, logs and scores, not the full publication trees.

## Runtime and STAR field scores

RMS / p95 / max in Å; fixed limits 0.20 / 0.40 / 0.80 Å. Flat and repeated are unidentifiable by design and were not run here.

| Case | Arm | Runtime | Runtime gate | STAR | STAR gate |
|---|---|---|---|---|---|
| noisy | OFF | 1.645367/3.337282/7.284050 | FAIL | 1.645381/3.337274/7.283887 | FAIL |
| noisy | ON | 1.095427/2.240219/4.469227 | FAIL | 1.095414/2.240253/4.469297 | FAIL |
| affine | OFF | 0.117034/0.260331/0.537350 | PASS | 0.117044/0.260384/0.537400 | PASS |
| affine | ON | 0.065968/0.142185/0.329485 | PASS | 0.065960/0.142178/0.329476 | PASS |
| pedestal | OFF | 0.116819/0.259915/0.538854 | PASS | 0.116817/0.259908/0.538856 | PASS |
| pedestal | ON | 0.065948/0.142009/0.330322 | PASS | 0.065946/0.141999/0.330321 | PASS |
| zero | OFF | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |
| zero | ON | 0.000000/0.000000/0.000000 | PASS | 0.000000/0.000000/0.000000 | PASS |

P2 (noisy ON strictly improves all three metrics against OFF on both fields): **SUPPORTED**. P1 (all five passing cases remain passing): **INCOMPLETE**; affine, pedestal and zero passed on both fields, integer and fractional UNRUN. Overall prediction verdict: **INCOMPLETE**. No aggregate field metric increased in the four completed pairs; all six noisy metrics decreased, but noisy still fails all three raw limits.

Noisy patch convergence was 8/9 in both arms; final logged RMSD for patch (2,3), center (104,47), increased 1.589500 to 8.364200 px. The STAR local-shift block has 40 rows in each arm (8 patches), with this patch absent. Affine and pedestal each have 9/9 converged and 45 local-shift rows in both arms. The logged CPU RMSD criterion supplies the convergence label; rejection reasons are not established. Zero has no local stage. Global runtime bits, serialized global block and global DC/coupled counters matched in all four pairs.

Witness: each 3x3 ON log has exactly nine `x_norm = 42, pnx = 42, nfx = 22` lines, OFF has none; zero has none in either arm. The six 3x3 runs have nonzero local manipulation counters.

## STOP and diagnosis

Zero global-only pair: runtime JSON and case STAR are raw-byte equal, and the pinned comparator reports `DIFFERENT` with two of seven gated products differing (corrected_micrographs.star and zero_shifts.eps). MRC header bytes 0–223 and pixels 1024 onward compare equal; label block and logs/PDFs are outside the comparator gate. The unchanged comparator resolves roots to `/private/tmp/...`, whereas the output files embed `/tmp/...`; direct diffs show the two unmatched root spellings. A separate read-only diagnostic replacing each literal producer root yields equal bytes in both files. This diagnostic is not the frozen comparator verdict; STOP remains FAIL. No corrected comparator, retry, or further launch occurred.

## Descriptive Mac OFF vs retained Linux OFF

Runtime and STAR values are the same fixed ROI/limits but different venue/build; shown descriptively, no byte identity claimed.

| Case | Mac runtime | Linux runtime | Mac STAR | Linux STAR |
|---|---|---|---|---|
| noisy | 1.645367/3.337282/7.284050 | 1.645371/3.337290/7.284026 | 1.645381/3.337274/7.283887 | 1.645397/3.337279/7.283784 |
| affine | 0.117034/0.260331/0.537350 | 0.117035/0.260334/0.537360 | 0.117044/0.260384/0.537400 | 0.117040/0.260337/0.537391 |
| pedestal | 0.116819/0.259915/0.538854 | 0.116943/0.260269/0.537476 | 0.116817/0.259908/0.538856 | 0.116950/0.260288/0.537494 |
| zero | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 | 0.000000/0.000000/0.000000 |

Source archive commit `5bcfa987` tree `d1a67904bdd515bebc548f881e8889ac4a682bb2`; binary SHA-256 `d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546`. All 33 fixture hashes matched. Ghostscript `/opt/homebrew/bin/gs` version 10.08.0 SHA-256 `d57bb373324bf7e72c5b3fb1a6cc8a9f876eb6f8d2eec23a5a3809a8a108bf9e`. Each run used --j 2 and OMP 2 with recorded occupancy; no benchmark or per-thread affinity claim. The separate disabled-effect mutant fails its test as intended. Mac driver is not independently reviewed; no GPU, real-data, full100, image accuracy or adoption claim.
